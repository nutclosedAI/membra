# MEMBRA MoA Brain — Mixture-of-Agents Architecture

## The Problem with Simple Distributed Workers

Naive distributed inference:
- Task queue splits prompts into batches
- Each worker processes independently
- No coordination, no quality control
- Results may conflict or have gaps

**The user still sees many disconnected outputs. Not one brain.**

## The MoA Solution

Instead of splitting a model or using dumb task queues, MEMBRA MoA Brain creates a **coordinated team of specialist agents** that function as one mind.

```
User Prompt
    ↓
[Router Brain] — Decomposes into subtasks, assigns specialists
    ↓
┌─────────────┬─────────────┬─────────────┬─────────────┐
│   Coder     │  Security   │   Tester    │    Docs     │
│  (Mac 1)    │   (Mac 2)   │   (Mac 3)   │   (Mac 4)   │
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┘
       │             │             │             │
       └─────────────┴──────┬──────┴─────────────┘
                            ↓
                   [Judge Brain] — Scores all outputs
                            ↓
                   [Synthesizer] — Merges best results
                            ↓
                   Final Artifact + Hash + Provenance
```

## Why This Is Better

| Goal | Naive Distributed | MoA Brain |
|------|---------------------|-----------|
| Single chat experience | ❌ Many disconnected outputs | ✅ One coherent artifact |
| Better answers | ❌ One model, one attempt | ✅ Multiple specialists + judge |
| More compute | ❌ Just more of the same | ✅ Parallel specialists with roles |
| Bigger context | ❌ Limited by single model | ✅ Shared memory + retrieval |
| Verified output | ❌ No verification | ✅ Tests + consensus hashes |
| Revenue | ❌ Unverified task completion | ✅ Paid artifacts with receipts |
| 70B model across Macs | ❌ WiFi tensor-parallel nightmare | ✅ Multiple smaller specialists |

## Architecture

### 1. Router Brain

Decomposes the prompt and creates an execution plan:

```python
router = RouterBrain()
plan = router.plan("Build a Telegram bot with tests and docs")

# Plan contains:
# - Subtasks: [plan, code, security_review, tests, docs, critic]
# - Worker assignments: {coder: Mac 2, security: Mac 3, ...}
# - Dependencies: tests depends on code, etc.
```

### 2. Specialist Workers

Each worker runs on its own Mac with a role-specific model:

| Role | Model | Mac | What It Does |
|------|-------|-----|--------------|
| Planner | llama3.1:8b | Any | Creates execution plan |
| Coder | qwen2.5-coder | Mac 2 | Writes main code |
| Security | deepseek-coder | Mac 3 | Reviews for vulnerabilities |
| Tester | llama3.1:8b | Mac 4 | Writes and runs tests |
| Docs | phi3:mini | Mac 1 | Writes README |
| Researcher | llama3.1:8b | Any | Finds relevant info |
| Critic | deepseek-r1 | Any | Scores and validates |

### 3. Shared Memory Layer

All agents read/write to the same SQLite database:

```python
memory = SharedMemory()
memory.store("coder-mac", "code_output", "fibonacci.py", content)
memory.retrieve(agent_id="coder-mac", memory_type="code_output")
```

**This is way more useful than shared GPU memory over WiFi.**

### 4. Judge Brain

Scores each specialist output:

```
Dimensions: accuracy, completeness, style, safety
Safety is a hard threshold — unsafe code is rejected immediately
Overall score must exceed threshold to be included in synthesis
```

### 5. Synthesizer Brain

Merges the best outputs into one artifact:

```python
synthesizer = SynthesizerBrain()
final = synthesizer.synthesize(plan, outputs, scores)
# final contains: code + docs + tests + hash + provenance
```

### 6. Consensus Hash

The final artifact is hashed with all component proofs:

```
sha256(router_plan + all_outputs + judge_scores + synthesis)
```

This hash can be anchored to Solana as proof of verified work.

## Speculative Draft/Verify Mode

For faster single responses, use a small fast model + large accurate model:

```
Mac 1 (Fast): phi3 or llama3.2:1b drafts tokens quickly
Mac 2 (Strong): llama3.1:70b verifies and corrects chunks
```

This is NOT tensor parallelism. It's **speculative decoding** with independent models:

| | Tensor Parallelism | Draft/Verify |
|---|---|---|
| Network | High-bandwidth, low-latency | Normal WiFi OK |
| Synchronization | Every layer | Only at chunk boundaries |
| Hardware | Identical GPUs | Any model on any Mac |
| Speedup | ~1.5-2x per added GPU | ~1.3-1.8x with good draft |

## Example: Build a Telegram Bot

```
User: "Build a Telegram bot, deploy it, write tests, and package the repo"

Router:
  → subtask 1: planner creates execution plan
  → subtask 2: researcher finds Telegram Bot API docs
  → subtask 3: coder writes bot.py + requirements.txt
  → subtask 4: security reviews for secrets, unsafe eval
  → subtask 5: tester writes pytest tests
  → subtask 6: docs writes README.md + DEPLOY.md
  → subtask 7: critic scores all outputs

Synthesizer:
  → merges code + tests + docs into repo/
  → adds manifest.json with hashes
  → creates ZIP for buyer

Buyer receives:
  → telegram_bot.zip (verified, tested, documented)
  → build_report.json (who did what, scores, hashes)
  → payment receipt (Stripe confirmed)
```

## Comparison

| Approach | What It Is | Good For | Bad For |
|----------|-----------|----------|---------|
| Naive task queue | Dumb batch processing | Many independent prompts | Complex multi-step tasks |
| Tensor parallelism | Split model layers across GPUs | One big model, fast interconnect | WiFi, different machines |
| **MoA Brain** | **Coordinated specialist agents** | **Complex tasks, verified quality, single answer** | **Simple single prompts (overkill)** |

## Real Deployment

```bash
# Mac 1 (Router + Planner + Docs)
python3 -m membra_sdk.worker --id mac-1 --role planner

# Mac 2 (Coder)
python3 -m membra_sdk.worker --id mac-2 --role coder

# Mac 3 (Security + Tester)
python3 -m membra_sdk.worker --id mac-3 --role security

# Mac 4 (Critic + Synthesizer)
python3 -m membra_sdk.worker --id mac-4 --role critic

# Coordinator (any machine)
python3 examples/moa_brain_demo.py
```

## Roadmap

### v1: Basic MoA (Current)
- Router + specialists + judge + synthesizer
- Shared SQLite memory
- Deterministic routing (keyword-based)

### v2: Smart Routing
- LLM-based router (not keyword)
- Dynamic specialist assignment based on worker load
- Draft/verify speculative decoding

### v3: Advanced
- Worker reputation tracking
- Adaptive model selection per task
- Cross-worker memory sharing (RAG)
- Payment integration per verified subtask

## Honest Limitations

| What Works | What Doesn't |
|-----------|-------------|
| Complex multi-step tasks | Real-time streaming chat |
| Verified code generation | 70B model inference |
| Parallel specialist work | Single-token latency reduction |
| Quality improvement via judge | Magic 10x speedup |

## The Bottom Line

> MEMBRA MoA Brain is **not** a faster single GPU.
> It is a **better single brain** built from multiple coordinated minds.
> Each specialist is an independent model on an independent Mac.
> They share memory, judge each other, and synthesize one final answer.
> This is buildable, useful, and honest.

## Files

| Module | File | Purpose |
|--------|------|---------|
| Router | `membra_sdk/brain/router.py` | Decomposes prompts, assigns specialists |
| Synthesizer | `membra_sdk/brain/synthesizer.py` | Merges outputs into artifact |
| Judge | `membra_sdk/brain/judge.py` | Scores outputs, enforces safety |
| Orchestrator | `membra_sdk/brain/moa_orchestrator.py` | Runs full pipeline |
| Shared Memory | `membra_sdk/memory/shared_memory.py` | SQLite + artifact store |
| Demo | `examples/moa_brain_demo.py` | End-to-end demo |
