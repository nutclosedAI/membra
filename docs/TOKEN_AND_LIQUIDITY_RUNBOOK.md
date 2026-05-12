# MEMBRA Token and Liquidity Runbook

> **MEMBRA begins token and liquidity only after the agent is operational, proof is published, treasury is funded, and a human or multisig signs the Solana transactions.**

## Rules

1. **The agent may prepare** token, pool, swap, and staking transactions.
2. **The agent may not** auto-sign mainnet transactions.
3. **The agent may not** hold private keys.
4. **The agent may not** call files, hashes, or appraisals liquid cash.
5. **The agent may not** execute any financial action without `HUMAN_OR_MULTISIG_APPROVED`.

## Start Conditions

All of the following must be `True` before any token or liquidity action:

| Condition | Why It Matters |
|-----------|----------------|
| `AGENT_ONLINE` | The MEMBRA validator agent is running and responsive |
| `DASHBOARD_ONLINE` | The monitoring dashboard is accessible and reporting |
| `CORPUS_INDEXED` | File corpus has been scanned, hashed, and indexed |
| `PROOF_MANIFEST_PUBLISHED` | Build artifacts, test results, and validator votes are published |
| `WALLET_CONNECTED` | A Solana wallet (hardware or multisig) is connected |
| `TREASURY_FUNDED` | Treasury holds ≥ 0.25 SOL and ≥ 500 USDC |
| `DEVNET_RECEIPT_RECORDED` | At least one proof-of-job has been anchored on devnet |
| `HUMAN_OR_MULTISIG_APPROVED` | Explicit approval from a human or multisig for mainnet action |
| `NO_PRIVATE_KEYS_STORED` | Agent has zero access to private keys |
| `MAINNET_POLICY_ENABLED` | Mainnet execution policy is explicitly enabled |

## Production Gate

```python
def can_begin_token_and_liquidity(state):
    return all([
        state.agent_online is True,
        state.dashboard_online is True,
        state.corpus_indexed is True,
        state.proof_manifest_published is True,
        state.wallet_connected is True,
        state.human_or_multisig_approval is True,
        state.treasury_sol >= 0.25,
        state.treasury_usdc >= 500,
        state.no_private_keys_stored is True,
        state.mainnet_policy_enabled is True,
    ])
```

## Launch State Machine

```
AGENT_READY
    ↓
CORPUS_INDEXED
    ↓
PROOF_MANIFEST_PUBLISHED
    ↓
WALLET_CONNECTED
    ↓
TREASURY_FUNDED
    ↓
DEVNET_RECEIPT_RECORDED
    ↓
MAINNET_MINT_PREPARED
    ↓
HUMAN_OR_MULTISIG_APPROVED
    ↓
MEMBRA_MINT_CREATED        ← requires signature
    ↓
SUPPLY_MINTED              ← requires signature
    ↓
MINT_POLICY_LOCKED         ← requires signature
    ↓
RAYDIUM_POOL_PREPARED
    ↓
HUMAN_OR_MULTISIG_APPROVED
    ↓
POOL_CREATED               ← requires signature
    ↓
LP_POSITION_RECORDED
    ↓
TREASURY_STAKING_POLICY_ENABLED
    ↓
OPTIONAL_LIQUID_STAKING_EXECUTED  ← requires signature
    ↓
SWAP_ROUTING_ENABLED
```

## Token Launch

### Parameters

| Parameter | Value | Justification |
|-----------|-------|---------------|
| Symbol | MEMBRA | Protocol-native utility token |
| Chain | Solana | Fast finality, low cost, Anchor tooling |
| Network | Mainnet-beta | Only after devnet proof |
| Decimals | 6 | Standard for USDC-compatible accounting |
| Initial supply | Fixed, published before mint | Transparency prevents surprise inflation |
| Mint authority | Multisig or hardware wallet | Prevents unauthorized minting |
| Freeze authority | Disabled | No arbitrary freezing without governance |

### Steps

1. **Create MEMBRA SPL mint.** The agent prepares the transaction. A human/multisig signs.
2. **Mint fixed supply.** All tokens minted at creation. No future inflation without governance.
3. **Publish metadata.** Name, symbol, URI, icon on-chain via Metaplex Token Metadata.
4. **Record mint address** in dashboard and proof ledger.
5. **Revoke or multisig-control mint authority.** Prevents future unauthorized supply changes.
6. **Record all transactions** in the proof ledger with hashes and explorer links.

## Liquidity Launch

### Parameters

| Parameter | Value |
|-----------|-------|
| Pair | MEMBRA/USDC |
| Venue | Raydium (permissionless pool creation) |
| Initial price | Derived from actual LP deposit, not appraisal fantasy |
| Minimum first LP | $500–$5,000 USDC equivalent |
| Price source | Actual treasury allocation, not thesis value |

### Steps

1. **Choose MEMBRA/USDC pair.** Stable quote token reduces volatility illusion.
2. **Set initial price** from actual intended LP deposit. Not from `$9,251,500` appraisal.
3. **Create Raydium pool.** The agent prepares. Human/multisig signs.
4. **Add initial liquidity.** Deposit MEMBRA + USDC from treasury.
5. **Record LP token account.** Track position on-chain.
6. **Dashboard displays pool TVL** only from real on-chain balances.

## Liquid Staking

### Rules

- **Treasury SOL only.** User deposits are never staked without explicit opt-in.
- **Capped allocation.** Maximum % of treasury SOL may be staked, set by policy.
- **Smart-contract risk acknowledged.** Marinade or similar protocol may have bugs or depeg events.
- **Not guaranteed income.** Staking rewards are variable and subject to validator performance.
- **Recorded as treasury strategy.** Not marketed as "passive income" to users.

### Policy Gate

```python
def can_stake_treasury_sol(state):
    return all([
        state.treasury_staking_policy_enabled is True,
        state.treasury_sol >= 1.0,  # keep buffer
        state.staking_allocation_bps <= 5000,  # max 50% of treasury SOL
        state.human_or_multisig_approval is True,
    ])
```

## Swap Routing

### Integration

- **Primary aggregator:** Jupiter (Solana)
- **Agent role:** Quote and prepare transactions only
- **Execution:** Requires human/multisig signature
- **Condition:** Pool must have real TVL before swap routing is enabled

## Agent Command Set

| Command | Description | Signature Required |
|---------|-------------|-------------------|
| `agent status` | Show agent health and state | No |
| `corpus status` | Show corpus index and coverage | No |
| `proof publish` | Publish proof manifest | No |
| `wallet connect` | Connect Solana wallet | No |
| `treasury balance` | Show SOL and USDC balances | No |
| `token prepare-mainnet` | Prepare mint transaction | No |
| `token create-mint` | Submit mint creation | **Yes** |
| `token mint-supply` | Mint fixed supply | **Yes** |
| `token lock-authority` | Revoke or transfer mint authority | **Yes** |
| `pool quote` | Estimate pool parameters | No |
| `pool prepare-raydium` | Prepare Raydium pool transaction | No |
| `pool create` | Submit pool creation | **Yes** |
| `staking policy` | Show staking policy and caps | No |
| `staking stake-treasury` | Stake treasury SOL | **Yes** |
| `swap quote` | Get swap quote from Jupiter | No |
| `swap execute` | Submit swap transaction | **Yes** |

## Value Boundaries

| What It Is | What It Is NOT |
|------------|----------------|
| **Corpus/Appraisal Value** | `$9,251,500` thesis value — intellectual property, not liquidity |
| **Official Treasury** | Actual SOL + USDC wallet balance |
| **Pool TVL** | Actual deposited MEMBRA + USDC on-chain |
| **User Income** | Only from settled payments, accepted bounties, fees, or swaps |
| **Token Supply** | Fixed at launch; not "value" until traded |

## Invalid Claims

The following statements are **false** and must never be made:

- "Files are liquidity."
- "Appraisal is cash."
- "Token mint is profit."
- "Testnet is settlement."
- "Staking rewards are guaranteed."
- "LP tokens are risk-free."
- "The agent can auto-mint tokens."
- "The agent can auto-create pools."
- "Running the agent creates money."

## Risk Disclosures

### Smart Contract Risk
- Raydium, Jupiter, Marinade, and Metaplex contracts may contain bugs.
- Audits reduce but do not eliminate risk.
- Treasury exposure should be capped.

### Depeg Risk
- Liquid staking tokens (mSOL, etc.) may trade below SOL.
- Treasury policy should set maximum LST allocation.

### Liquidity Risk
- Low-TVL pools have high slippage.
- Large trades may move price significantly.
- Initial LP should be sized to expected trading volume.

### Regulatory Risk
- Token issuance may be classified as a security in some jurisdictions.
- Legal review required before public sale or marketing.
- KYC/AML may be required for certain jurisdictions.

## Launch Phrase

> **MEMBRA begins token and liquidity only after the agent is operational, proof is published, treasury is funded, and a human or multisig signs the Solana transactions.**

## Version

v0.1 — No-custody, no-token, no-pool, no-guarantee. All token actions require human/multisig approval.

Last updated: 2026-05-11
