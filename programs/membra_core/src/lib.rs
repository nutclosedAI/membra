use anchor_lang::prelude::*;

// =============================================================================
// MEMBRA Proof-of-Job Protocol — Solana Program v0.1
// =============================================================================
// No-custody version. No token custody, no escrow, no DeFi, no automatic payout.
// v0.1: create job, submit manifest root, submit votes, finalize consensus,
//       record receipt hash.
//
// On-chain: hashes, state transitions, votes, receipts
// Off-chain: raw prompts, full source code, model outputs, private data
// =============================================================================

declare_id!("jApWwbd5HUBdw5vxF9pXZQQhgTLPrK1zYcJdSaw49h9"); // TODO: replace with deployed program ID

#[program]
pub mod membra_core {
    use super::*;

    // =========================================================================
    // 1. Initialize Protocol Config (authority sets global params)
    // =========================================================================
    pub fn initialize(ctx: Context<Initialize>, authority: Pubkey) -> Result<()> {
        let config = &mut ctx.accounts.protocol_config;
        config.authority = authority;
        config.version = 1; // v0.1
        config.bump = ctx.bumps.protocol_config;
        config.validator_min_stake = 0; // v0.1: no staking required
        config.consensus_threshold_bps = 6667; // 66.67% = 2/3
        config.paused = false;
        Ok(())
    }

    // =========================================================================
    // 2. Create Job
    //    Creates JobAccount from chat/job hash.
    // =========================================================================
    pub fn create_job(
        ctx: Context<CreateJob>,
        job_id_hash: [u8; 32],
        chat_hash: [u8; 32],
        job_spec_hash: [u8; 32],
    ) -> Result<()> {
        require!(!ctx.accounts.protocol_config.paused, MembraError::ProtocolPaused);

        let job = &mut ctx.accounts.job_account;
        job.creator = ctx.accounts.creator.key();
        job.job_id_hash = job_id_hash;
        job.chat_hash = chat_hash;
        job.job_spec_hash = job_spec_hash;
        job.status = JobStatus::Created as u8;
        job.created_at = Clock::get()?.unix_timestamp;
        job.bump = ctx.bumps.job_account;

        emit!(JobCreated {
            job: job.key(),
            creator: job.creator,
            job_id_hash,
            chat_hash,
        });

        Ok(())
    }

    // =========================================================================
    // 3. Submit Artifact Manifest
    //    Stores artifact Merkle root, manifest hash, metadata URI hash.
    // =========================================================================
    pub fn submit_artifact_manifest(
        ctx: Context<SubmitArtifactManifest>,
        manifest_hash: [u8; 32],
        artifact_root: [u8; 32],
        metadata_uri_hash: [u8; 32],
        artifact_count: u32,
    ) -> Result<()> {
        let job = &mut ctx.accounts.job_account;
        require!(
            job.status == JobStatus::Created as u8,
            MembraError::InvalidJobStatus
        );
        require!(
            job.creator == ctx.accounts.signer.key(),
            MembraError::Unauthorized
        );

        let manifest = &mut ctx.accounts.artifact_manifest;
        manifest.job = job.key();
        manifest.manifest_hash = manifest_hash;
        manifest.artifact_root = artifact_root;
        manifest.metadata_uri_hash = metadata_uri_hash;
        manifest.artifact_count = artifact_count;
        manifest.created_at = Clock::get()?.unix_timestamp;
        manifest.bump = ctx.bumps.artifact_manifest;

        job.status = JobStatus::ArtifactsSubmitted as u8;

        emit!(ArtifactManifestSubmitted {
            job: job.key(),
            manifest: manifest.key(),
            artifact_root,
            artifact_count,
        });

        Ok(())
    }

    // =========================================================================
    // 4. Submit Validator Vote
    //    Stores validator vote: accept/reject, score, reason hash.
    // =========================================================================
    pub fn submit_validator_vote(
        ctx: Context<SubmitValidatorVote>,
        vote: u8, // 1 = accept, 0 = reject
        score: u16,
        reason_hash: [u8; 32],
    ) -> Result<()> {
        let job = &mut ctx.accounts.job_account;
        let validator = &mut ctx.accounts.validator_account;

        require!(
            job.status == JobStatus::ArtifactsSubmitted as u8
                || job.status == JobStatus::VotingOpen as u8,
            MembraError::InvalidJobStatus
        );
        require!(validator.active, MembraError::ValidatorInactive);
        require!(vote <= 1, MembraError::InvalidVoteValue);

        let vote_account = &mut ctx.accounts.vote_account;
        vote_account.job = job.key();
        vote_account.validator = validator.key();
        vote_account.vote = vote;
        vote_account.score = score;
        vote_account.reason_hash = reason_hash;
        vote_account.created_at = Clock::get()?.unix_timestamp;
        vote_account.bump = ctx.bumps.vote_account;

        // Update validator stats
        validator.total_votes = validator.total_votes.saturating_add(1);
        if vote == 1 {
            validator.accepted_votes = validator.accepted_votes.saturating_add(1);
        }

        // Transition job to voting open if first vote
        if job.status == JobStatus::ArtifactsSubmitted as u8 {
            job.status = JobStatus::VotingOpen as u8;
        }

        emit!(VoteSubmitted {
            job: job.key(),
            validator: validator.key(),
            vote,
            score,
        });

        Ok(())
    }

    // =========================================================================
    // 5. Finalize Consensus
    //    Checks quorum and writes ConsensusAccount.
    // =========================================================================
    pub fn finalize_consensus(
        ctx: Context<FinalizeConsensus>,
        yes_votes: u16,
        no_votes: u16,
    ) -> Result<()> {
        let job = &mut ctx.accounts.job_account;
        let config = &ctx.accounts.protocol_config;

        require!(
            job.status == JobStatus::VotingOpen as u8,
            MembraError::InvalidJobStatus
        );
        require!(
            job.creator == ctx.accounts.signer.key(),
            MembraError::Unauthorized
        );

        let total = yes_votes.saturating_add(no_votes);
        require!(total > 0, MembraError::NoVotes);

        // Compute ratio in basis points to avoid floating point
        let ratio_bps = (yes_votes as u64)
            .checked_mul(10000)
            .unwrap()
            .checked_div(total as u64)
            .unwrap() as u16;

        let accepted = ratio_bps >= config.consensus_threshold_bps;

        let consensus = &mut ctx.accounts.consensus_account;
        consensus.job = job.key();
        consensus.yes_votes = yes_votes;
        consensus.no_votes = no_votes;
        consensus.threshold_bps = config.consensus_threshold_bps;
        consensus.result = if accepted {
            ConsensusResult::Accepted as u8
        } else {
            ConsensusResult::Rejected as u8
        };
        consensus.finalized_at = Clock::get()?.unix_timestamp;
        consensus.bump = ctx.bumps.consensus_account;

        job.status = if accepted {
            JobStatus::ConsensusAccepted as u8
        } else {
            JobStatus::ConsensusRejected as u8
        };

        emit!(ConsensusFinalized {
            job: job.key(),
            consensus: consensus.key(),
            result: consensus.result,
            yes_votes,
            no_votes,
        });

        Ok(())
    }

    // =========================================================================
    // 6. Record Yield
    //    Stores artifact yield, validation yield, market yield, chain yield.
    // =========================================================================
    pub fn record_yield(
        ctx: Context<RecordYield>,
        artifact_yield: u16,
        validation_yield: u16,
        market_yield: u64,
        chain_yield: u64,
        total_score: u16,
    ) -> Result<()> {
        let job = &mut ctx.accounts.job_account;
        require!(
            job.status == JobStatus::ConsensusAccepted as u8,
            MembraError::InvalidJobStatus
        );
        require!(
            job.creator == ctx.accounts.signer.key(),
            MembraError::Unauthorized
        );

        let yield_account = &mut ctx.accounts.yield_account;
        yield_account.job = job.key();
        yield_account.artifact_yield = artifact_yield;
        yield_account.validation_yield = validation_yield;
        yield_account.market_yield = market_yield;
        yield_account.chain_yield = chain_yield;
        yield_account.total_score = total_score;
        yield_account.created_at = Clock::get()?.unix_timestamp;
        yield_account.bump = ctx.bumps.yield_account;

        job.status = JobStatus::YieldRecorded as u8;

        emit!(YieldRecorded {
            job: job.key(),
            yield_account: yield_account.key(),
            total_score,
        });

        Ok(())
    }

    // =========================================================================
    // 7. Record Settlement
    //    Stores external receipt hash, payment reference hash.
    //    v0.1: No token custody. No escrow. Just records.
    // =========================================================================
    pub fn record_settlement(
        ctx: Context<RecordSettlement>,
        payer: Pubkey,
        recipient: Pubkey,
        amount_lamports: u64,
        settlement_type: u8, // 0=bounty, 1=grant, 2=invoice, 3=stripe, 4=nft
        receipt_hash: [u8; 32],
    ) -> Result<()> {
        let job = &mut ctx.accounts.job_account;
        require!(
            job.status == JobStatus::YieldRecorded as u8
                || job.status == JobStatus::Settled as u8,
            MembraError::InvalidJobStatus
        );
        require!(
            job.creator == ctx.accounts.signer.key(),
            MembraError::Unauthorized
        );
        require!(settlement_type <= 4, MembraError::InvalidSettlementType);

        let settlement = &mut ctx.accounts.settlement_account;
        settlement.job = job.key();
        settlement.payer = payer;
        settlement.recipient = recipient;
        settlement.amount_lamports = amount_lamports;
        settlement.settlement_type = settlement_type;
        settlement.receipt_hash = receipt_hash;
        settlement.settled_at = Clock::get()?.unix_timestamp;
        settlement.bump = ctx.bumps.settlement_account;

        job.status = JobStatus::Settled as u8;

        emit!(SettlementRecorded {
            job: job.key(),
            settlement: settlement.key(),
            settlement_type,
            amount_lamports,
        });

        Ok(())
    }

    // =========================================================================
    // 8. Close or Archive Job
    //    Final state transition. Creator can close after settlement.
    // =========================================================================
    pub fn close_job(ctx: Context<CloseJob>) -> Result<()> {
        let job = &mut ctx.accounts.job_account;
        require!(
            job.creator == ctx.accounts.signer.key(),
            MembraError::Unauthorized
        );
        require!(
            job.status == JobStatus::Settled as u8
                || job.status == JobStatus::ConsensusRejected as u8,
            MembraError::InvalidJobStatus
        );

        job.status = JobStatus::Closed as u8;
        job.closed_at = Clock::get()?.unix_timestamp;

        emit!(JobClosed {
            job: job.key(),
            creator: job.creator,
        });

        Ok(())
    }

    // =========================================================================
    // 9. Register Validator (v0.1: no stake required, authority approval)
    // =========================================================================
    pub fn register_validator(
        ctx: Context<RegisterValidator>,
        authority: Pubkey,
    ) -> Result<()> {
        let validator = &mut ctx.accounts.validator_account;
        validator.authority = authority;
        validator.reputation_score = 0;
        validator.total_votes = 0;
        validator.accepted_votes = 0;
        validator.slashed_votes = 0;
        validator.active = true;
        validator.created_at = Clock::get()?.unix_timestamp;
        validator.bump = ctx.bumps.validator_account;

        emit!(ValidatorRegistered {
            validator: validator.key(),
            authority,
        });

        Ok(())
    }

    // =========================================================================
    // 10. Toggle Validator Status (authority only)
    // =========================================================================
    pub fn set_validator_status(
        ctx: Context<SetValidatorStatus>,
        active: bool,
    ) -> Result<()> {
        let validator = &mut ctx.accounts.validator_account;
        validator.active = active;
        Ok(())
    }

    // =========================================================================
    // 11. Pause/Unpause Protocol (authority only)
    // =========================================================================
    pub fn set_protocol_pause(ctx: Context<SetProtocolPause>, paused: bool) -> Result<()> {
        let config = &mut ctx.accounts.protocol_config;
        config.paused = paused;
        Ok(())
    }
}

// =============================================================================
// ENUMS
// =============================================================================

#[derive(Clone, Copy, PartialEq, AnchorSerialize, AnchorDeserialize)]
pub enum JobStatus {
    Created = 0,
    ArtifactsSubmitted = 1,
    VotingOpen = 2,
    ConsensusAccepted = 3,
    ConsensusRejected = 4,
    YieldRecorded = 5,
    Settled = 6,
    Closed = 7,
}

#[derive(Clone, Copy, PartialEq, AnchorSerialize, AnchorDeserialize)]
pub enum ConsensusResult {
    Rejected = 0,
    Accepted = 1,
}

// =============================================================================
// ACCOUNTS
// =============================================================================

#[account]
pub struct ProtocolConfig {
    pub authority: Pubkey,
    pub version: u8,
    pub bump: u8,
    pub validator_min_stake: u64, // v0.1: 0
    pub consensus_threshold_bps: u16, // default 6667 (66.67%)
    pub paused: bool,
}

#[account]
pub struct JobAccount {
    pub creator: Pubkey,
    pub job_id_hash: [u8; 32],
    pub chat_hash: [u8; 32],
    pub job_spec_hash: [u8; 32],
    pub status: u8,
    pub created_at: i64,
    pub closed_at: i64,
    pub bump: u8,
}

#[account]
pub struct ArtifactManifestAccount {
    pub job: Pubkey,
    pub manifest_hash: [u8; 32],
    pub artifact_root: [u8; 32],
    pub metadata_uri_hash: [u8; 32],
    pub artifact_count: u32,
    pub created_at: i64,
    pub bump: u8,
}

#[account]
pub struct ValidatorAccount {
    pub authority: Pubkey,
    pub reputation_score: u64,
    pub total_votes: u64,
    pub accepted_votes: u64,
    pub slashed_votes: u64,
    pub active: bool,
    pub created_at: i64,
    pub bump: u8,
}

#[account]
pub struct VoteAccount {
    pub job: Pubkey,
    pub validator: Pubkey,
    pub vote: u8,
    pub score: u16,
    pub reason_hash: [u8; 32],
    pub created_at: i64,
    pub bump: u8,
}

#[account]
pub struct ConsensusAccount {
    pub job: Pubkey,
    pub yes_votes: u16,
    pub no_votes: u16,
    pub threshold_bps: u16,
    pub result: u8,
    pub finalized_at: i64,
    pub bump: u8,
}

#[account]
pub struct YieldAccount {
    pub job: Pubkey,
    pub artifact_yield: u16,
    pub validation_yield: u16,
    pub market_yield: u64,
    pub chain_yield: u64,
    pub total_score: u16,
    pub created_at: i64,
    pub bump: u8,
}

#[account]
pub struct SettlementAccount {
    pub job: Pubkey,
    pub payer: Pubkey,
    pub recipient: Pubkey,
    pub amount_lamports: u64,
    pub settlement_type: u8,
    pub receipt_hash: [u8; 32],
    pub settled_at: i64,
    pub bump: u8,
}

// =============================================================================
// CONTEXTS (ACCOUNTS STRUCTS FOR EACH INSTRUCTION)
// =============================================================================

#[derive(Accounts)]
pub struct Initialize<'info> {
    #[account(mut)]
    pub payer: Signer<'info>,
    #[account(
        init,
        payer = payer,
        space = 8 + ProtocolConfig::INIT_SPACE,
        seeds = [b"protocol_config"],
        bump
    )]
    pub protocol_config: Account<'info, ProtocolConfig>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
#[instruction(job_id_hash: [u8; 32])]
pub struct CreateJob<'info> {
    #[account(mut)]
    pub creator: Signer<'info>,
    #[account(
        init,
        payer = creator,
        space = 8 + JobAccount::INIT_SPACE,
        seeds = [b"job", creator.key().as_ref(), &job_id_hash],
        bump
    )]
    pub job_account: Account<'info, JobAccount>,
    #[account(
        seeds = [b"protocol_config"],
        bump = protocol_config.bump,
    )]
    pub protocol_config: Account<'info, ProtocolConfig>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct SubmitArtifactManifest<'info> {
    #[account(mut)]
    pub signer: Signer<'info>,
    #[account(mut)]
    pub job_account: Account<'info, JobAccount>,
    #[account(
        init,
        payer = signer,
        space = 8 + ArtifactManifestAccount::INIT_SPACE,
        seeds = [b"artifact_manifest", job_account.key().as_ref()],
        bump
    )]
    pub artifact_manifest: Account<'info, ArtifactManifestAccount>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct SubmitValidatorVote<'info> {
    #[account(mut)]
    pub signer: Signer<'info>,
    #[account(mut)]
    pub job_account: Account<'info, JobAccount>,
    #[account(
        mut,
        has_one = authority @ MembraError::Unauthorized,
    )]
    pub validator_account: Account<'info, ValidatorAccount>,
    #[account(
        init,
        payer = signer,
        space = 8 + VoteAccount::INIT_SPACE,
        seeds = [b"vote", job_account.key().as_ref(), validator_account.key().as_ref()],
        bump
    )]
    pub vote_account: Account<'info, VoteAccount>,
    pub authority: Signer<'info>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct FinalizeConsensus<'info> {
    #[account(mut)]
    pub signer: Signer<'info>,
    #[account(mut, constraint = job_account.creator == signer.key() @ MembraError::Unauthorized)]
    pub job_account: Account<'info, JobAccount>,
    #[account(
        seeds = [b"protocol_config"],
        bump = protocol_config.bump,
    )]
    pub protocol_config: Account<'info, ProtocolConfig>,
    #[account(
        init,
        payer = signer,
        space = 8 + ConsensusAccount::INIT_SPACE,
        seeds = [b"consensus", job_account.key().as_ref()],
        bump
    )]
    pub consensus_account: Account<'info, ConsensusAccount>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct RecordYield<'info> {
    #[account(mut)]
    pub signer: Signer<'info>,
    #[account(mut, constraint = job_account.creator == signer.key() @ MembraError::Unauthorized)]
    pub job_account: Account<'info, JobAccount>,
    #[account(
        init,
        payer = signer,
        space = 8 + YieldAccount::INIT_SPACE,
        seeds = [b"yield", job_account.key().as_ref()],
        bump
    )]
    pub yield_account: Account<'info, YieldAccount>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct RecordSettlement<'info> {
    #[account(mut)]
    pub signer: Signer<'info>,
    #[account(mut, constraint = job_account.creator == signer.key() @ MembraError::Unauthorized)]
    pub job_account: Account<'info, JobAccount>,
    #[account(
        init,
        payer = signer,
        space = 8 + SettlementAccount::INIT_SPACE,
        seeds = [b"settlement", job_account.key().as_ref()],
        bump
    )]
    pub settlement_account: Account<'info, SettlementAccount>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct CloseJob<'info> {
    #[account(mut)]
    pub signer: Signer<'info>,
    #[account(mut, constraint = job_account.creator == signer.key() @ MembraError::Unauthorized)]
    pub job_account: Account<'info, JobAccount>,
}

#[derive(Accounts)]
pub struct RegisterValidator<'info> {
    #[account(mut)]
    pub payer: Signer<'info>,
    pub authority: Signer<'info>,
    #[account(
        init,
        payer = payer,
        space = 8 + ValidatorAccount::INIT_SPACE,
        seeds = [b"validator", authority.key().as_ref()],
        bump
    )]
    pub validator_account: Account<'info, ValidatorAccount>,
    pub system_program: Program<'info, System>,
}

#[derive(Accounts)]
pub struct SetValidatorStatus<'info> {
    #[account(mut, has_one = authority)]
    pub validator_account: Account<'info, ValidatorAccount>,
    pub authority: Signer<'info>,
}

#[derive(Accounts)]
pub struct SetProtocolPause<'info> {
    #[account(mut, has_one = authority)]
    pub protocol_config: Account<'info, ProtocolConfig>,
    pub authority: Signer<'info>,
}

// =============================================================================
// SPACE CALCULATIONS (Anchor 0.30 uses INIT_SPACE via derive macro)
// =============================================================================

impl ProtocolConfig {
    pub const INIT_SPACE: usize =
        32 + 1 + 1 + 8 + 2 + 1; // authority + version + bump + min_stake + threshold + paused
}

impl JobAccount {
    pub const INIT_SPACE: usize =
        32 + 32 + 32 + 32 + 1 + 8 + 8 + 1; // creator + 3 hashes + status + 2 timestamps + bump
}

impl ArtifactManifestAccount {
    pub const INIT_SPACE: usize =
        32 + 32 + 32 + 32 + 4 + 8 + 1; // job + 3 hashes + count + timestamp + bump
}

impl ValidatorAccount {
    pub const INIT_SPACE: usize =
        32 + 8 + 8 + 8 + 8 + 1 + 8 + 1; // authority + 4 u64s + bool + timestamp + bump
}

impl VoteAccount {
    pub const INIT_SPACE: usize =
        32 + 32 + 1 + 2 + 32 + 8 + 1; // job + validator + vote + score + hash + timestamp + bump
}

impl ConsensusAccount {
    pub const INIT_SPACE: usize =
        32 + 2 + 2 + 2 + 1 + 8 + 1; // job + 3 u16s + result + timestamp + bump
}

impl YieldAccount {
    pub const INIT_SPACE: usize =
        32 + 2 + 2 + 8 + 8 + 2 + 8 + 1; // job + 3 u16s + 2 u64s + u16 + timestamp + bump
}

impl SettlementAccount {
    pub const INIT_SPACE: usize =
        32 + 32 + 32 + 8 + 1 + 32 + 8 + 1; // job + 2 pubkeys + amount + type + hash + timestamp + bump
}

// =============================================================================
// EVENTS
// =============================================================================

#[event]
pub struct JobCreated {
    pub job: Pubkey,
    pub creator: Pubkey,
    pub job_id_hash: [u8; 32],
    pub chat_hash: [u8; 32],
}

#[event]
pub struct ArtifactManifestSubmitted {
    pub job: Pubkey,
    pub manifest: Pubkey,
    pub artifact_root: [u8; 32],
    pub artifact_count: u32,
}

#[event]
pub struct VoteSubmitted {
    pub job: Pubkey,
    pub validator: Pubkey,
    pub vote: u8,
    pub score: u16,
}

#[event]
pub struct ConsensusFinalized {
    pub job: Pubkey,
    pub consensus: Pubkey,
    pub result: u8,
    pub yes_votes: u16,
    pub no_votes: u16,
}

#[event]
pub struct YieldRecorded {
    pub job: Pubkey,
    pub yield_account: Pubkey,
    pub total_score: u16,
}

#[event]
pub struct SettlementRecorded {
    pub job: Pubkey,
    pub settlement: Pubkey,
    pub settlement_type: u8,
    pub amount_lamports: u64,
}

#[event]
pub struct JobClosed {
    pub job: Pubkey,
    pub creator: Pubkey,
}

#[event]
pub struct ValidatorRegistered {
    pub validator: Pubkey,
    pub authority: Pubkey,
}

// =============================================================================
// ERRORS
// =============================================================================

#[error_code]
pub enum MembraError {
    #[msg("Protocol is paused")]
    ProtocolPaused,
    #[msg("Invalid job status for this operation")]
    InvalidJobStatus,
    #[msg("Unauthorized")]
    Unauthorized,
    #[msg("Validator is inactive")]
    ValidatorInactive,
    #[msg("Invalid vote value")]
    InvalidVoteValue,
    #[msg("No votes recorded")]
    NoVotes,
    #[msg("Invalid settlement type")]
    InvalidSettlementType,
    #[msg("Consensus already finalized")]
    ConsensusAlreadyFinalized,
    #[msg("Job already closed")]
    JobAlreadyClosed,
}
