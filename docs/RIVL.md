# MEMBRA RIVL — Reinforcement Inverted Validator Learning

## What This Is

RIVL is a **verifier-guided learning system** where:
- **Failed outputs** become negative training examples
- **Verified revenue-producing artifacts** become positive reward examples
- **Punishment memory** prevents repeating past failures

## The Formula

```
reward = artifact_score
       + test_score
       + receipt_score
       + validator_consensus_score
       - security_penalty
       - hallucination_penalty
       - failed_test_penalty
       - unpaid_work_penalty
       - financial_loss_penalty
       - policy_violation_penalty
```

## Default Weights

| Event | Weight |
|-------|--------|
| Tests pass | +10 |
| Tests fail | **-25** |
| Security pass | +10 |
| Security fail | **-50** |
| Payment verified | +25 |
| Payment missing | -5 |
| Consensus verified | +15 |
| Consensus missing | -10 |
| Artifact downloaded | +5 |
| Refund requested | **-50** |
| Financial loss | **-100** |
| Policy violation | **-100** |
| Mainnet without approval | **-1000** |
| Loss of funds | **-10000** |
| Verified profit after fees | +50 |
| Receipt-confirmed yield | +100 |

## Architecture (3 Layers)

### Layer 1: Deterministic Verifier

Hard rules. No LLM judgment.
- Unit tests must pass
- Security scan finds no secrets
- Payment receipt verified
- Validator consensus reaches 2/3
- Policy gates satisfied

```python
verifier = VerifierStack()
result = verifier.verify_code(code)
# result: {passed: bool, issues: [...]}
```

### Layer 2: Reward Engine

Scores output quality and economic value.

```python
reward = RIVLRewardEngine()
event = reward.score(
    prompt=prompt,
    output=code,
    tests_passed=True,
    security_passed=True,
    payment_verified=False,
)
# event: {reward: 35, verdict: "accepted", reason: "tests_passed,security_passed"}
```

### Layer 3: Punishment Memory

Stores negative and positive examples. Later trains LoRA/DPO.

```python
memory = PunishmentMemory()
learnings = memory.search("Build Stripe webhook")
# Returns past failures and successes as prompt addons
```

## How Punishment Memory Works

Before generating new output:

```
Prompt: "Build Stripe webhook"
↓
Memory finds:
  - Previous failure: did not verify Stripe signature
  - Previous failure: trusted client amount
  - Previous success: used construct_event with webhook secret
↓
Brain instruction becomes:
  "Do not repeat prior failures.
   Verify Stripe signature.
   Never trust client amount."
```

This gives **learning without expensive training**.

## Semi-Deterministic Behavior

Control randomness with temperature:

| Mode | Temperature | Use Case |
|------|-------------|----------|
| Deterministic | 0.0 | Trading, contracts, payments |
| Semi-deterministic | 0.1–0.3 | Most MEMBRA tasks |
| Exploration | 0.7+ | Creative tasks only |

For DeFi, trading, and validators:
**Use deterministic or semi-deterministic mode only.**

## DeFi/Trading Punishment Rules

| Violation | Punishment |
|-----------|------------|
| Failed simulation | -25 |
| Slippage too high | -50 |
| Unauthorized contract | -100 |
| Mainnet without approval | **-1000** |
| Loss of funds | **-10000** |

Default config:
```yaml
defi:
  mode: testnet
  mainnet_enabled: false
  require_human_approval: true
  max_loss_usd: 0
  punish_unapproved_tx: -1000
```

## Integration with MoA Brain

```
User Prompt
    ↓
Punishment Memory retrieves past failures
    ↓
Router Brain plans subtasks
    ↓
Specialist workers execute (with memory warnings)
    ↓
Verifier Stack checks all outputs
    ↓
Reward Engine scores (+/-)
    ↓
Events logged to memory
    ↓
Synthesizer merges verified outputs only
    ↓
Final artifact + hash + reward score
```

## Data Format

```json
{
  "prompt_hash": "abc123...",
  "output_hash": "def456...",
  "reward": 35,
  "verdict": "accepted",
  "reason": "tests_passed,security_passed",
  "tests_passed": true,
  "security_passed": true,
  "payment_verified": false,
  "consensus_verified": true,
  "financial_loss": false,
  "policy_violation": false,
  "timestamp": 1715467200
}
```

## Files

| Module | File | Purpose |
|--------|------|---------|
| Reward Engine | `membra_sdk/rivl/reward_engine.py` | Score outputs with +/- weights |
| Punishment Memory | `membra_sdk/rivl/punishment_memory.py` | Retrieve past failures/successes |
| Verifier Stack | `membra_sdk/rivl/verifier_stack.py` | Deterministic code/security/policy checks |
| RIVL Brain | `membra_sdk/rivl/rivl_brain.py` | Full integration with MoA pipeline |
| Demo | `examples/rivl_demo.py` | End-to-end reward/punishment demo |

## Doctrine

> **Punishment is not violence. Punishment is negative evidence.**
> **Reward is not fantasy profit. Reward is verified success.**
> **Yield is not model confidence. Yield is settled external value.**

## Build Path

1. **Now**: LLM + verifier + reward log + negative memory
2. **Next**: Retrieval memory to avoid past mistakes
3. **Later**: Train a reward model from accumulated events
4. **Eventually**: LoRA/DPO fine-tuning with verified examples only

**Do not start with full RL training. That is expensive and unstable.**

Start with:
> LLM + verifier + reward log + negative memory
