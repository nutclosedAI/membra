# MEMBRA Proof-of-Job Runtime

## Thesis

**Chat is the new shell. Containers are the new workers. Proof is the new invoice. Consensus is the new signature. Yield is the accepted output.**

MEMBRA turns chat into executable economic units.

A prompt becomes a containerized job.
The job produces artifacts.
Artifacts are scored as yield.
Validators reach consensus.
The resulting proof bundle can be sold, audited, anchored, or settled.

## Product Doctrine

```
CHAT
  becomes
CONTAINERIZED INTENT
CONTAINER
  becomes
EXECUTABLE JOB
JOB
  produces
ARTIFACT YIELD
YIELD
  requires
CONSENSUS VALIDATION
CONSENSUS
  creates
PROOF RECORD
PROOF RECORD
  can become
PAYMENT / REPUTATION / AUDIT / NFT / GRANT / BOUNTY / SALE PACKAGE
```

## Protocol Stack

| Layer | Name | Purpose |
|-------|------|---------|
| 5 | Settlement | Payments, bounties, grants, NFTs, devnet receipts, invoices |
| 4 | Consensus | Validator votes, quorum, rejection reasons, proof finality |
| 3 | Yield | Artifact score, test score, benchmark score, market score |
| 2 | Job | Container plan, model backend, tools, policy, expected outputs |
| 1 | Chat | Human intent, agent conversation, prompt chain, task context |

## Architecture Flow

```
User chat prompt
   ↓
Intent parser (Chat Compiler)
   ↓
Job spec
   ↓
Container plan
   ↓
Execution sandbox
   ↓
Artifacts + logs + tests
   ↓
Yield scoring
   ↓
Validator consensus
   ↓
Proof bundle
   ↓
Settlement adapter
```

## Core Objects

### Chat
A human instruction or agent conversation.

### Job
A structured executable unit derived from chat.

```json
{
  "schema": "membra.job.v0.1",
  "intent": "Build a Solana NFT appraisal API",
  "inputs": ["README.md", "research_notes.pdf"],
  "runtime": {
    "container": "python:3.11-slim",
    "model_backend": "ollama:qwen2.5-coder",
    "tools": ["pytest", "ruff", "git", "node"]
  },
  "policy": {
    "network": "restricted",
    "secrets": "blocked",
    "funds": "disabled",
    "mainnet": "blocked"
  },
  "expected_outputs": ["app.py", "README.md", "tests/", "proof.json"],
  "yield_metric": "validated_artifact_output"
}
```

### Container
A reproducible sandbox for running the job.

### Artifact
Any output: code, report, image, PDF, benchmark, transaction, dataset.

### Yield
The measured useful output of the job.

Four kinds:
1. **Artifact Yield** — files, code, docs produced
2. **Validation Yield** — tests, benchmarks, policy checks passed
3. **Market Yield** — bounty accepted, invoice paid, grant approved (external)
4. **Chain Yield** — blockchain receipt, escrow, staking (external)

### Validator
A local or remote checker that scores the job.

Roles:
- structure: Does output match expected files?
- security: Are there secrets, eval(), os.system()?
- usefulness: Does output solve the stated intent?
- tests: Do tests pass?
- policy: Does it comply with job policy gates?

### Consensus
Agreement among validators that the output is valid.

Rules:
- Threshold: 2/3 majority
- If consensus fails, job is rejected
- Rejection reasons preserved for retry

### Proof Bundle
Portable evidence that the job happened and produced valid output.

```json
{
  "schema": "membra.proof_of_job.v0.1",
  "chat": {"prompt_hash": "sha256:...", "summary": "Build a proof-of-job demo app"},
  "job": {"id": "job_0001", "runtime": "python:3.11", "model": "ollama:qwen2.5-coder"},
  "container": {"image": "python:3.11-slim", "commands": ["pytest -q"]},
  "artifacts": [{"path": "app.py", "sha256": "...", "bytes": 18422}],
  "yield": {
    "artifact_yield": 78.2,
    "validation_yield": 91.0,
    "market_yield": 0,
    "chain_yield": 0,
    "total_score": 84.6
  },
  "consensus": {
    "threshold": "2/3",
    "votes": ["accept", "accept", "reject"],
    "result": "accepted"
  },
  "settlement": {"status": "unsettled", "external_receipts": []},
  "root_hash": "sha256:..."
}
```

### Settlement
Optional conversion of proof into money, reputation, grant credit, bounty payout, NFT, or ledger entry.

## CLI

```bash
# Turn chat into job spec
membra chat "Build a Hugging Face app for my proof runtime"

# Create job from latest chat
membra job create --from-chat latest

# Run job (local CLI only)
membra job run --container python:3.11 --model ollama:qwen2.5-coder

# Score yield
membra yield score <job_id>

# Run consensus
membra consensus validate <job_id> --validators 3

# Export proof
membra proof export <job_id> --format zip

# Preview settlement
membra settle preview <job_id>
```

## Expected Output

```
MEMBRA JOB COMPLETE
Job ID: job_0001
Container: python:3.11
Model backend: ollama:qwen2.5-coder
Artifacts created: 7
Tests passed: 18/18
Security flags: 0
Consensus: 3/3 accepted
Yield score: 87.4
Economic settlement: not claimed
Proof root: sha256:9fae...
Export: membra-proof-job_0001.zip
```

## Hugging Face vs Local CLI

| Feature | Hugging Face Space | Local CLI |
|---------|-------------------|-----------|
| Chat -> Job Spec | ✅ | ✅ |
| Container Plan | ✅ | ✅ |
| Real Docker Execution | ❌ (dry run only) | ✅ |
| Artifact Validation | ✅ | ✅ |
| Yield Scoring | ✅ | ✅ |
| Consensus Simulation | ✅ | ✅ |
| Proof Export | ✅ | ✅ |
| Real Ollama Inference | ❌ (mock) | ✅ |
| Real Test Execution | ❌ (user inputs) | ✅ |

The Hugging Face Space is a **proof demo and artifact validator**.
The Local CLI runs **real containers, models, and tests**.

## The Competition

MEMBRA does not replace Docker or Ollama.

- Docker runs the container.
- Ollama runs the model.
- MEMBRA turns the run into a job ledger.
- Consensus turns the job ledger into proof.
- Proof turns output into claimable yield.

## Slogan

> **"Don't just chat. Ship provable work."**

## Doctrine

> **Punishment is not violence. Punishment is negative evidence.**
> **Reward is not fantasy profit. Reward is verified success.**
> **Yield is not model confidence. Yield is settled external value.**

## Safety

See [YIELD_DEFINITIONS.md](YIELD_DEFINITIONS.md) for legal protections and yield definitions.

See [SAFETY.md](SAFETY.md) for policy gates and DeFi rules.

## Files

| Module | File | Purpose |
|--------|------|---------|
| Chat Compiler | `membra_sdk/job/chat_compiler.py` | Turn chat into JobSpec |
| Job Spec | `membra_sdk/job/job_spec.py` | Structured executable unit |
| Artifact Hasher | `membra_sdk/job/artifact_hasher.py` | SHA-256 for all outputs |
| Yield Meter | `membra_sdk/job/yield_meter.py` | Score 4 yield types |
| Validators | `membra_sdk/job/validators.py` | Multi-role validation |
| Consensus | `membra_sdk/job/consensus.py` | Quorum evaluation |
| Proof Bundle | `membra_sdk/job/proof_bundle.py` | Portable proof export |
| Settlement | `membra_sdk/job/settlement.py` | External receipt adapter |
| Hugging Face Demo | `app.py` | 6-tab Gradio demo |
