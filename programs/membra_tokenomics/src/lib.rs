use anchor_lang::prelude::*;
use anchor_lang::solana_program::{system_instruction, program::invoke_signed};

// =============================================================================
// MEMBRA Early-Risk Curve / QR Tokenomics Protocol — Solana Program v0.1
// =============================================================================
// Core Guardrail: No guaranteed profit. No infinite passive rewards.
// Cashback is capped, disclosed, pool-limited, and claimable only if funded.
//
// Flow:
// 1. Authority initializes a TokenSale (bonding curve, decay, splits, caps).
// 2. Buyers scan QR → see terms → connect wallet → send SOL/USDC.
// 3. Bonding curve calculates base tokens. Decay formula calculates early bonus.
// 4. Contribution is split: 80% treasury, 10% protocol, 5% validator, 5% early-reward-pool.
// 5. BuyerReceipt is recorded on-chain.
// 6. Earlier eligible buyers may claim a capped rebate from the early-reward-pool.
// 7. Authority finalizes the sale → liquidity migrated → claims enabled.
// =============================================================================

declare_id!("Tok3nom1csMEMBRAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"); // TODO: replace with deployed program ID

#[program]
pub mod membra_tokenomics {
    use super::*;

    // =========================================================================
    // 1. Initialize Token Sale
    // =========================================================================
    pub fn initialize_sale(
        ctx: Context<InitializeSale>,
        sale_id: u64,
        base_price_lamports: u64,
        slope_bps: u64,
        max_bonus_bps: u16,
        sale_duration_sec: u64,
        early_reward_cap_lamports: u64,
        max_rebate_per_buyer_lamports: u64,
        rebate_rate_bps: u16,
    ) -> Result<()> {
        require!(
            base_price_lamports > 0,
            MembraTokenomicsError::InvalidPrice
        );
        require!(
            max_bonus_bps <= 5000,
            MembraTokenomicsError::BonusTooHigh
        ); // max 50% bonus
        require!(
            rebate_rate_bps <= 2000,
            MembraTokenomicsError::RebateTooHigh
        ); // max 20% rebate
        require!(
            sale_duration_sec > 0,
            MembraTokenomicsError::InvalidDuration
        );

        let sale = &mut ctx.accounts.token_sale;
        sale.authority = ctx.accounts.authority.key();
        sale.sale_id = sale_id;
        sale.status = SaleStatus::Draft as u8;
        sale.base_price_lamports = base_price_lamports;
        sale.slope_bps = slope_bps;
        sale.max_bonus_bps = max_bonus_bps;
        sale.sale_duration_sec = sale_duration_sec;
        sale.start_time = 0; // set when activated
        sale.end_time = 0;
        sale.total_raised_lamports = 0;
        sale.total_tokens_allocated = 0;
        sale.contribution_count = 0;

        // Splits (default 80/10/5/5)
        sale.split_treasury_bps = 8000;
        sale.split_protocol_bps = 1000;
        sale.split_validator_bps = 500;
        sale.split_early_reward_bps = 500;
        let total_split = sale.split_treasury_bps as u64
            + sale.split_protocol_bps as u64
            + sale.split_validator_bps as u64
            + sale.split_early_reward_bps as u64;
        require!(total_split == 10000, MembraTokenomicsError::InvalidSplits);

        // Wallets
        sale.treasury = ctx.accounts.treasury.key();
        sale.protocol_wallet = ctx.accounts.protocol_wallet.key();
        sale.validator_pool = ctx.accounts.validator_pool.key();

        // Rebate guardrails
        sale.early_reward_cap_lamports = early_reward_cap_lamports;
        sale.early_reward_distributed_lamports = 0;
        sale.max_rebate_per_buyer_lamports = max_rebate_per_buyer_lamports;
        sale.rebate_rate_bps = rebate_rate_bps;

        sale.bump = ctx.bumps.token_sale;
        sale.early_reward_pool_bump = ctx.bumps.early_reward_pool;

        emit!(SaleInitialized {
            sale: sale.key(),
            authority: sale.authority,
            sale_id,
            base_price_lamports,
            max_bonus_bps,
            early_reward_cap_lamports,
        });

        Ok(())
    }

    // =========================================================================
    // 2. Activate Sale (authority only)
    // =========================================================================
    pub fn activate_sale(ctx: Context<ManageSale>) -> Result<()> {
        let sale = &mut ctx.accounts.token_sale;
        require!(
            sale.status == SaleStatus::Draft as u8,
            MembraTokenomicsError::InvalidSaleStatus
        );

        let clock = Clock::get()?;
        sale.status = SaleStatus::Active as u8;
        sale.start_time = clock.unix_timestamp;
        sale.end_time = clock.unix_timestamp + sale.sale_duration_sec as i64;

        emit!(SaleActivated {
            sale: sale.key(),
            start_time: sale.start_time,
            end_time: sale.end_time,
        });

        Ok(())
    }

    // =========================================================================
    // 3. Contribute (buyer sends SOL, receives token allocation + potential bonus)
    // =========================================================================
    pub fn contribute(
        ctx: Context<Contribute>,
        amount_lamports: u64,
    ) -> Result<()> {
        require!(amount_lamports > 0, MembraTokenomicsError::ZeroContribution);

        let sale = &mut ctx.accounts.token_sale;
        let clock = Clock::get()?;

        // Guardrails
        require!(
            sale.status == SaleStatus::Active as u8,
            MembraTokenomicsError::SaleNotActive
        );
        require!(
            clock.unix_timestamp <= sale.end_time,
            MembraTokenomicsError::SaleExpired
        );

        // ─── Terms & Risk Disclosure Acknowledgment ───
        // Off-chain UI must display terms before calling this instruction.
        // On-chain we record that buyer accepted by signing the tx.

        // ─── Bonding Curve: price = base + slope * total_raised / 10_000 ───
        let current_price = calculate_price(
            sale.base_price_lamports,
            sale.slope_bps,
            sale.total_raised_lamports,
        )?;

        // Base tokens = amount * 1_000_000 / current_price (6 decimal precision)
        let base_tokens = (amount_lamports as u128)
            .checked_mul(1_000_000)
            .unwrap()
            .checked_div(current_price as u128)
            .unwrap() as u64;

        // ─── Decay Bonus: time-based early reward ───
        let elapsed = clock.unix_timestamp.saturating_sub(sale.start_time) as u64;
        let bonus_bps = calculate_time_decay_bonus(
            sale.max_bonus_bps,
            elapsed,
            sale.sale_duration_sec,
        )?;
        let bonus_tokens = (base_tokens as u128)
            .checked_mul(bonus_bps as u128)
            .unwrap()
            .checked_div(10_000)
            .unwrap() as u64;
        let total_tokens = base_tokens.saturating_add(bonus_tokens);

        // ─── Contribution Split ───
        let to_treasury = (amount_lamports as u128)
            .checked_mul(sale.split_treasury_bps as u128)
            .unwrap()
            .checked_div(10_000)
            .unwrap() as u64;
        let to_protocol = (amount_lamports as u128)
            .checked_mul(sale.split_protocol_bps as u128)
            .unwrap()
            .checked_div(10_000)
            .unwrap() as u64;
        let to_validator = (amount_lamports as u128)
            .checked_mul(sale.split_validator_bps as u128)
            .unwrap()
            .checked_div(10_000)
            .unwrap() as u64;
        let to_early_reward = amount_lamports
            .saturating_sub(to_treasury)
            .saturating_sub(to_protocol)
            .saturating_sub(to_validator);

        // Guardrail: early reward pool cannot exceed cap
        let new_early_total = sale
            .early_reward_distributed_lamports
            .checked_add(to_early_reward)
            .unwrap();
        require!(
            new_early_total <= sale.early_reward_cap_lamports,
            MembraTokenomicsError::EarlyRewardCapReached
        );

        // ─── Transfer Splits ───
        let sale_key = sale.key();
        let seeds = &[b"token_sale", &sale.sale_id.to_le_bytes(), &[sale.bump]];
        let signer = &[&seeds[..]];

        transfer_lamports(
            &ctx.accounts.buyer.to_account_info(),
            &ctx.accounts.treasury.to_account_info(),
            to_treasury,
        )?;
        transfer_lamports(
            &ctx.accounts.buyer.to_account_info(),
            &ctx.accounts.protocol_wallet.to_account_info(),
            to_protocol,
        )?;
        transfer_lamports(
            &ctx.accounts.buyer.to_account_info(),
            &ctx.accounts.validator_pool.to_account_info(),
            to_validator,
        )?;
        transfer_lamports(
            &ctx.accounts.buyer.to_account_info(),
            &ctx.accounts.early_reward_pool.to_account_info(),
            to_early_reward,
        )?;

        // ─── Update Sale State ───
        sale.total_raised_lamports = sale
            .total_raised_lamports
            .checked_add(amount_lamports)
            .unwrap();
        sale.total_tokens_allocated = sale
            .total_tokens_allocated
            .checked_add(total_tokens)
            .unwrap();
        sale.contribution_count = sale.contribution_count.checked_add(1).unwrap();
        sale.early_reward_distributed_lamports = new_early_total;

        // ─── Record Contribution ───
        let contribution = &mut ctx.accounts.contribution;
        contribution.sale = sale.key();
        contribution.buyer = ctx.accounts.buyer.key();
        contribution.amount_lamports = amount_lamports;
        contribution.base_tokens = base_tokens;
        contribution.bonus_tokens = bonus_tokens;
        contribution.total_tokens = total_tokens;
        contribution.bonus_bps = bonus_bps;
        contribution.price_at_contribution = current_price;
        contribution.contribution_index = sale.contribution_count;
        contribution.created_at = clock.unix_timestamp;
        contribution.bump = ctx.bumps.contribution;

        // ─── Record / Update Buyer Receipt ───
        let receipt = &mut ctx.accounts.buyer_receipt;
        receipt.sale = sale.key();
        receipt.buyer = ctx.accounts.buyer.key();
        receipt.total_contributed_lamports = receipt
            .total_contributed_lamports
            .checked_add(amount_lamports)
            .unwrap();
        receipt.total_tokens_allocated = receipt
            .total_tokens_allocated
            .checked_add(total_tokens)
            .unwrap();
        receipt.rebate_claimed_lamports = receipt.rebate_claimed_lamports; // unchanged
        receipt.rebate_claim_status = if receipt.rebate_claim_status == RebateClaimStatus::Claimed as u8 {
            RebateClaimStatus::Claimed as u8
        } else {
            RebateClaimStatus::Eligible as u8
        };
        receipt.last_updated_at = clock.unix_timestamp;
        receipt.bump = ctx.bumps.buyer_receipt;

        emit!(ContributionRecorded {
            sale: sale.key(),
            buyer: ctx.accounts.buyer.key(),
            amount_lamports,
            base_tokens,
            bonus_tokens,
            bonus_bps,
            contribution_index: contribution.contribution_index,
        });

        Ok(())
    }

    // =========================================================================
    // 4. Claim Rebate (earlier buyers claim capped rebate from early-reward-pool)
    // =========================================================================
    pub fn claim_rebate(ctx: Context<ClaimRebate>) -> Result<()> {
        let sale = &ctx.accounts.token_sale;
        require!(
            sale.status == SaleStatus::Finalized as u8
                || sale.status == SaleStatus::LiquidityMigrated as u8,
            MembraTokenomicsError::ClaimsNotEnabled
        );

        let receipt = &mut ctx.accounts.buyer_receipt;
        require!(
            receipt.rebate_claim_status != RebateClaimStatus::Claimed as u8,
            MembraTokenomicsError::AlreadyClaimed
        );
        require!(
            receipt.rebate_claim_status != RebateClaimStatus::Expired as u8,
            MembraTokenomicsError::ClaimExpired
        );

        let clock = Clock::get()?;
        // Optional: claim window expires 30 days after finalization
        let claim_deadline = sale.end_time.saturating_add(30 * 24 * 60 * 60);
        require!(
            clock.unix_timestamp <= claim_deadline,
            MembraTokenomicsError::ClaimWindowClosed
        );

        // ─── Calculate Capped Rebate ───
        // Rebate = contribution * rebate_rate_bps / 10_000, capped per buyer and pool
        let raw_rebate = (receipt.total_contributed_lamports as u128)
            .checked_mul(sale.rebate_rate_bps as u128)
            .unwrap()
            .checked_div(10_000)
            .unwrap() as u64;

        let pool_remaining = sale
            .early_reward_cap_lamports
            .saturating_sub(sale.early_reward_distributed_lamports);
        // Note: distributed tracks what went INTO the pool. For claims we need pool balance.
        // The pool balance is tracked by the early_reward_pool account lamports minus rent.
        let pool_balance = ctx
            .accounts
            .early_reward_pool
            .lamports()
            .saturating_sub(Rent::get()?.minimum_balance(0));

        let rebate = raw_rebate
            .min(sale.max_rebate_per_buyer_lamports)
            .min(pool_balance);

        require!(rebate > 0, MembraTokenomicsError::NoRebateAvailable);

        // ─── Transfer Rebate ───
        let sale_key = sale.key();
        let seeds = &[
            b"early_reward_pool",
            sale_key.as_ref(),
            &[sale.early_reward_pool_bump],
        ];
        let signer = &[&seeds[..]];

        invoke_signed(
            &system_instruction::transfer(
                &ctx.accounts.early_reward_pool.key(),
                &ctx.accounts.buyer.key(),
                rebate,
            ),
            &[
                ctx.accounts.early_reward_pool.to_account_info(),
                ctx.accounts.buyer.to_account_info(),
                ctx.accounts.system_program.to_account_info(),
            ],
            signer,
        )?;

        // ─── Update Receipt ───
        receipt.rebate_claimed_lamports = receipt
            .rebate_claimed_lamports
            .checked_add(rebate)
            .unwrap();
        receipt.rebate_claim_status = RebateClaimStatus::Claimed as u8;
        receipt.last_updated_at = clock.unix_timestamp;

        emit!(RebateClaimed {
            sale: sale.key(),
            buyer: receipt.buyer,
            rebate_lamports: rebate,
        });

        Ok(())
    }

    // =========================================================================
    // 5. Finalize Sale (authority only → claims enabled, liquidity migrated)
    // =========================================================================
    pub fn finalize_sale(ctx: Context<ManageSale>) -> Result<()> {
        let sale = &mut ctx.accounts.token_sale;
        require!(
            sale.status == SaleStatus::Active as u8,
            MembraTokenomicsError::InvalidSaleStatus
        );

        sale.status = SaleStatus::Finalized as u8;

        emit!(SaleFinalized {
            sale: sale.key(),
            total_raised_lamports: sale.total_raised_lamports,
            total_tokens_allocated: sale.total_tokens_allocated,
            contribution_count: sale.contribution_count,
        });

        Ok(())
    }

    // =========================================================================
    // 6. Migrate Liquidity (authority only → status LiquidityMigrated)
    // =========================================================================
    pub fn migrate_liquidity(ctx: Context<ManageSale>) -> Result<()> {
        let sale = &mut ctx.accounts.token_sale;
        require!(
            sale.status == SaleStatus::Finalized as u8,
            MembraTokenomicsError::InvalidSaleStatus
        );

        sale.status = SaleStatus::LiquidityMigrated as u8;

        emit!(LiquidityMigrated {
            sale: sale.key(),
            treasury: sale.treasury,
            total_raised_lamports: sale.total_raised_lamports,
        });

        Ok(())
    }

    // =========================================================================
    // 7. Cancel Sale (authority only → refunds must be handled off-chain in v0.1)
    // =========================================================================
    pub fn cancel_sale(ctx: Context<ManageSale>) -> Result<()> {
        let sale = &mut ctx.accounts.token_sale;
        require!(
            sale.status == SaleStatus::Draft as u8
                || sale.status == SaleStatus::Active as u8
                || sale.status == SaleStatus::Paused as u8,
            MembraTokenomicsError::InvalidSaleStatus
        );

        sale.status = SaleStatus::Cancelled as u8;

        emit!(SaleCancelled {
            sale: sale.key(),
            total_raised_lamports: sale.total_raised_lamports,
        });

        Ok(())
    }

    // =========================================================================
    // 8. Pause / Resume (authority only)
    // =========================================================================
    pub fn set_sale_pause(ctx: Context<ManageSale>, paused: bool) -> Result<()> {
        let sale = &mut ctx.accounts.token_sale;
        if paused {
            require!(
                sale.status == SaleStatus::Active as u8,
                MembraTokenomicsError::InvalidSaleStatus
            );
            sale.status = SaleStatus::Paused as u8;
        } else {
            require!(
                sale.status == SaleStatus::Paused as u8,
                MembraTokenomicsError::InvalidSaleStatus
            );
            sale.status = SaleStatus::Active as u8;
        }
        Ok(())
    }
}

// =============================================================================
// MATH HELPERS (checked integer arithmetic, no floats)
// =============================================================================

/// Linear bonding curve: price = base + slope * total_raised / 10_000
fn calculate_price(
    base_price: u64,
    slope_bps: u64,
    total_raised: u64,
) -> Result<u64> {
    let slope_component = (total_raised as u128)
        .checked_mul(slope_bps as u128)
        .unwrap()
        .checked_div(10_000)
        .unwrap() as u64;
    base_price
        .checked_add(slope_component)
        .ok_or(MembraTokenomicsError::MathOverflow.into())
}

/// Time-decay bonus: max_bonus * (1 - elapsed / duration)
/// Returns basis points (0 .. max_bonus_bps)
fn calculate_time_decay_bonus(
    max_bonus_bps: u16,
    elapsed_sec: u64,
    duration_sec: u64,
) -> Result<u16> {
    if elapsed_sec >= duration_sec {
        return Ok(0);
    }
    // remaining_ratio = (duration - elapsed) * 10_000 / duration
    let remaining_ratio = ((duration_sec - elapsed_sec) as u128)
        .checked_mul(10_000)
        .unwrap()
        .checked_div(duration_sec as u128)
        .unwrap() as u64;

    let bonus = (max_bonus_bps as u128)
        .checked_mul(remaining_ratio as u128)
        .unwrap()
        .checked_div(10_000)
        .unwrap() as u16;

    Ok(bonus)
}

fn transfer_lamports(
    from: &AccountInfo,
    to: &AccountInfo,
    amount: u64,
) -> Result<()> {
    require!(
        from.lamports() >= amount,
        MembraTokenomicsError::InsufficientFunds
    );
    **from.try_borrow_mut_lamports()? = from
        .lamports()
        .checked_sub(amount)
        .unwrap();
    **to.try_borrow_mut_lamports()? = to
        .lamports()
        .checked_add(amount)
        .unwrap();
    Ok(())
}

// =============================================================================
// ENUMS
// =============================================================================

#[derive(Clone, Copy, PartialEq, AnchorSerialize, AnchorDeserialize)]
pub enum SaleStatus {
    Draft = 0,
    Active = 1,
    Paused = 2,
    Finalized = 3,
    Cancelled = 4,
    LiquidityMigrated = 5,
}

#[derive(Clone, Copy, PartialEq, AnchorSerialize, AnchorDeserialize)]
pub enum RebateClaimStatus {
    Pending = 0,
    Eligible = 1,
    Claimed = 2,
    Expired = 3,
    Denied = 4,
}

// =============================================================================
// ACCOUNTS
// =============================================================================

#[account]
pub struct TokenSale {
    pub authority: Pubkey,
    pub sale_id: u64,
    pub status: u8,
    pub base_price_lamports: u64,
    pub slope_bps: u64,
    pub max_bonus_bps: u16,
    pub sale_duration_sec: u64,
    pub start_time: i64,
    pub end_time: i64,
    pub total_raised_lamports: u64,
    pub total_tokens_allocated: u64,
    pub contribution_count: u64,
    pub treasury: Pubkey,
    pub protocol_wallet: Pubkey,
    pub validator_pool: Pubkey,
    pub split_treasury_bps: u16,
    pub split_protocol_bps: u16,
    pub split_validator_bps: u16,
    pub split_early_reward_bps: u16,
    pub early_reward_cap_lamports: u64,
    pub early_reward_distributed_lamports: u64,
    pub max_rebate_per_buyer_lamports: u64,
    pub rebate_rate_bps: u16,
    pub bump: u8,
    pub early_reward_pool_bump: u8,
}

#[account]
pub struct Contribution {
    pub sale: Pubkey,
    pub buyer: Pubkey,
    pub amount_lamports: u64,
    pub base_tokens: u64,
    pub bonus_tokens: u64,
    pub total_tokens: u64,
    pub bonus_bps: u16,
    pub price_at_contribution: u64,
    pub contribution_index: u64,
    pub created_at: i64,
    pub bump: u8,
}

#[account]
pub struct BuyerReceipt {
    pub sale: Pubkey,
    pub buyer: Pubkey,
    pub total_contributed_lamports: u64,
    pub total_tokens_allocated: u64,
    pub rebate_claimed_lamports: u64,
    pub rebate_claim_status: u8,
    pub last_updated_at: i64,
    pub bump: u8,
}

// =============================================================================
// CONTEXTS
// =============================================================================

#[derive(Accounts)]
#[instruction(sale_id: u64)]
pub struct InitializeSale<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,
    #[account(
        init,
        payer = authority,
        space = 8 + TokenSale::INIT_SPACE,
        seeds = [b"token_sale", &sale_id.to_le_bytes()],
        bump
    )]
    pub token_sale: Account<'info, TokenSale>,
    /// CHECK: treasury wallet (external system account)
    pub treasury: AccountInfo<'info>,
    /// CHECK: protocol wallet (external system account)
    pub protocol_wallet: AccountInfo<'info>,
    /// CHECK: validator pool wallet (external system account)
    pub validator_pool: AccountInfo<'info>,
    #[account(
        init,
        payer = authority,
        space = 8 + 0, // minimal account, holds lamports
        seeds = [b"early_reward_pool", token_sale.key().as_ref()],
        bump
    )]
    /// CHECK: early reward pool PDA (holds SOL for rebates)
    pub early_reward_pool: AccountInfo<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct ManageSale<'info> {
    #[account(mut)]
    pub authority: Signer<'info>,
    #[account(
        mut,
        has_one = authority @ MembraTokenomicsError::Unauthorized,
    )]
    pub token_sale: Account<'info, TokenSale>,
}

#[derive(Accounts)]
pub struct Contribute<'info> {
    #[account(mut)]
    pub buyer: Signer<'info>,
    #[account(
        mut,
        seeds = [b"token_sale", &token_sale.sale_id.to_le_bytes()],
        bump = token_sale.bump,
    )]
    pub token_sale: Account<'info, TokenSale>,
    /// CHECK: treasury wallet
    #[account(mut, address = token_sale.treasury @ MembraTokenomicsError::InvalidWallet)]
    pub treasury: AccountInfo<'info>,
    /// CHECK: protocol wallet
    #[account(mut, address = token_sale.protocol_wallet @ MembraTokenomicsError::InvalidWallet)]
    pub protocol_wallet: AccountInfo<'info>,
    /// CHECK: validator pool wallet
    #[account(mut, address = token_sale.validator_pool @ MembraTokenomicsError::InvalidWallet)]
    pub validator_pool: AccountInfo<'info>,
    /// CHECK: early reward pool PDA
    #[account(
        mut,
        seeds = [b"early_reward_pool", token_sale.key().as_ref()],
        bump = token_sale.early_reward_pool_bump,
    )]
    pub early_reward_pool: AccountInfo<'info>,
    #[account(
        init,
        payer = buyer,
        space = 8 + Contribution::INIT_SPACE,
        seeds = [
            b"contribution",
            token_sale.key().as_ref(),
            buyer.key().as_ref(),
            &(token_sale.contribution_count + 1).to_le_bytes(),
        ],
        bump
    )]
    pub contribution: Account<'info, Contribution>,
    #[account(
        mut,
        init_if_needed,
        payer = buyer,
        space = 8 + BuyerReceipt::INIT_SPACE,
        seeds = [b"buyer_receipt", token_sale.key().as_ref(), buyer.key().as_ref()],
        bump
    )]
    pub buyer_receipt: Account<'info, BuyerReceipt>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct ClaimRebate<'info> {
    #[account(mut)]
    pub buyer: Signer<'info>,
    #[account(
        mut,
        seeds = [b"token_sale", &token_sale.sale_id.to_le_bytes()],
        bump = token_sale.bump,
    )]
    pub token_sale: Account<'info, TokenSale>,
    #[account(
        mut,
        seeds = [b"early_reward_pool", token_sale.key().as_ref()],
        bump = token_sale.early_reward_pool_bump,
    )]
    /// CHECK: early reward pool PDA
    pub early_reward_pool: AccountInfo<'info>,
    #[account(
        mut,
        seeds = [b"buyer_receipt", token_sale.key().as_ref(), buyer.key().as_ref()],
        bump = buyer_receipt.bump,
        constraint = buyer_receipt.buyer == buyer.key() @ MembraTokenomicsError::Unauthorized,
    )]
    pub buyer_receipt: Account<'info, BuyerReceipt>,
    pub system_program: Program<'info, System>,
}

// =============================================================================
// SPACE CALCULATIONS
// =============================================================================

impl TokenSale {
    pub const INIT_SPACE: usize =
        32 + 8 + 1 + 8 + 8 + 2 + 8 + 8 + 8 + 8 + 8 + 8 + 32 + 32 + 32 + 2 + 2 + 2 + 2 + 8 + 8 + 8 + 2 + 1 + 1;
}

impl Contribution {
    pub const INIT_SPACE: usize =
        32 + 32 + 8 + 8 + 8 + 8 + 2 + 8 + 8 + 8 + 1;
}

impl BuyerReceipt {
    pub const INIT_SPACE: usize =
        32 + 32 + 8 + 8 + 8 + 1 + 8 + 1;
}

// =============================================================================
// EVENTS
// =============================================================================

#[event]
pub struct SaleInitialized {
    pub sale: Pubkey,
    pub authority: Pubkey,
    pub sale_id: u64,
    pub base_price_lamports: u64,
    pub max_bonus_bps: u16,
    pub early_reward_cap_lamports: u64,
}

#[event]
pub struct SaleActivated {
    pub sale: Pubkey,
    pub start_time: i64,
    pub end_time: i64,
}

#[event]
pub struct ContributionRecorded {
    pub sale: Pubkey,
    pub buyer: Pubkey,
    pub amount_lamports: u64,
    pub base_tokens: u64,
    pub bonus_tokens: u64,
    pub bonus_bps: u16,
    pub contribution_index: u64,
}

#[event]
pub struct RebateClaimed {
    pub sale: Pubkey,
    pub buyer: Pubkey,
    pub rebate_lamports: u64,
}

#[event]
pub struct SaleFinalized {
    pub sale: Pubkey,
    pub total_raised_lamports: u64,
    pub total_tokens_allocated: u64,
    pub contribution_count: u64,
}

#[event]
pub struct LiquidityMigrated {
    pub sale: Pubkey,
    pub treasury: Pubkey,
    pub total_raised_lamports: u64,
}

#[event]
pub struct SaleCancelled {
    pub sale: Pubkey,
    pub total_raised_lamports: u64,
}

// =============================================================================
// ERRORS
// =============================================================================

#[error_code]
pub enum MembraTokenomicsError {
    #[msg("Unauthorized")]
    Unauthorized,
    #[msg("Invalid sale status for this operation")]
    InvalidSaleStatus,
    #[msg("Sale is not active")]
    SaleNotActive,
    #[msg("Sale has expired")]
    SaleExpired,
    #[msg("Invalid price parameters")]
    InvalidPrice,
    #[msg("Max bonus too high (max 50%)")]
    BonusTooHigh,
    #[msg("Rebate rate too high (max 20%)")]
    RebateTooHigh,
    #[msg("Invalid sale duration")]
    InvalidDuration,
    #[msg("Split percentages must sum to 10000 bps")]
    InvalidSplits,
    #[msg("Contribution amount must be greater than zero")]
    ZeroContribution,
    #[msg("Math overflow")]
    MathOverflow,
    #[msg("Insufficient funds")]
    InsufficientFunds,
    #[msg("Early reward cap reached")]
    EarlyRewardCapReached,
    #[msg("Invalid wallet address")]
    InvalidWallet,
    #[msg("Claims are not yet enabled")]
    ClaimsNotEnabled,
    #[msg("Rebate already claimed")]
    AlreadyClaimed,
    #[msg("Claim expired")]
    ClaimExpired,
    #[msg("Claim window closed")]
    ClaimWindowClosed,
    #[msg("No rebate available")]
    NoRebateAvailable,
}
