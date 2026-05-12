# Distributed Inference — Honest Architecture

## What MEMBRA Distributed Workers Actually Are

**Job parallelism across multiple MacBooks.**

NOT model parallelism. NOT one giant shared GPU.

## What Works Well

| Workload | How It Scales | Realistic? |
|----------|---------------|------------|
| Batch prompt processing | 2 Macs = 2x prompts/minute | ✅ Yes |
| File corpus analysis | 2 Macs = 2x files/minute | ✅ Yes |
| Code review across files | 2 Macs = 2x files/minute | ✅ Yes |
| Document summarization | 2 Macs = 2x docs/minute | ✅ Yes |
| Embedding generation | 2 Macs = 2x vectors/minute | ✅ Yes |
| Validator voting | 2 Macs = 2x votes/minute | ✅ Yes |
| Artifact generation queue | 2 Macs = 2x artifacts/minute | ✅ Yes |

## What Does NOT Work Well

| Workload | Why Not | Realistic? |
|----------|---------|------------|
| One single LLM response across 2 Macs | Network latency > GPU speed | ❌ No |
| Real-time chat with distributed workers | 50-100ms LAN latency per token | ❌ No |
| 70B model split across 2 MacBooks | Each needs 40GB+ VRAM, no shared memory | ❌ No |
| Tensor-parallel inference | Requires NVLink / InfiniBand, not WiFi | ❌ No |

## The Math

### One MacBook (M5 Pro)
- Ollama llama3.1:8b: ~20 tokens/sec
- One prompt (100 tokens): ~5 seconds
- 6 prompts serial: ~30 seconds

### Two MacBooks (M5 Pro each)
- Each runs its own Ollama llama3.1:8b
- One prompt per Mac: ~5 seconds each
- 6 prompts parallel (3 per Mac): ~15 seconds total
- **Result: 2x throughput, same per-prompt latency**

### Honest Claim

> Two MacBooks can process **twice as many jobs per minute** as one MacBook.
> They cannot make **one job finish twice as fast**.

## Architecture

```
Buyer / User
    │
    ▼
[Coordinator] — Job queue, task splitting, result collection
    │
    ├──→ [Worker A on Mac A] — Ollama, task execution, proof hash
    │       ↓
    │   Result + hash returned
    │
    └──→ [Worker B on Mac B] — Ollama, task execution, proof hash
            ↓
        Result + hash returned
    │
    ▼
[Coordinator] — Verify hashes, consensus, payment queue
    │
    ▼
Stripe / Solana settlement
```

## Worker Node

Each worker is a **complete independent machine**:
- Runs its own Ollama instance
- Loads its own model weights (memory duplication)
- Claims tasks from the queue
- Executes locally
- Returns result + SHA-256 proof hash
- Earns payment for verified work

## Coordinator

The coordinator:
- Accepts batch jobs
- Splits into independent tasks
- Dispatches to available workers
- Collects results
- Verifies proof hash consistency
- Runs consensus if multiple workers process same task
- Queues payments

**Honest: The demo coordinator is local-only. Production needs Redis/RabbitMQ or P2P gossip.**

## Network Reality

| Connection | Latency | Impact |
|------------|---------|--------|
| Same Mac (localhost) | ~0.1ms | Negligible |
| LAN (Ethernet) | ~1ms | Fine for batch jobs |
| LAN (WiFi) | ~5-20ms | Fine for batch jobs |
| Internet (same city) | ~20-50ms | OK for non-real-time |
| Internet (cross-country) | ~50-150ms | Batch only |

For **single prompt inference** (5-10 seconds total), network overhead is negligible.
For **real-time streaming** (token-by-token), network latency is a dealbreaker.

## Memory Reality

| Model | Memory Per Worker | Two Workers |
|-------|-------------------|-------------|
| llama3.1:8b | ~6GB | ~12GB total |
| llama3.1:70b | ~40GB | ~80GB total |
| Mixtral 8x7b | ~26GB | ~52GB total |

Each worker loads its **own copy** of the model. There is no shared GPU memory across Macs.

## Best Use Cases for MEMBRA Distributed Workers

1. **Overnight batch jobs**
   - Process 10,000 files while you sleep
   - 2 Macs = done in half the time

2. **Build artifact queues**
   - 50 code generation tasks
   - 2 Macs = 2x artifacts per hour

3. **Validator networks**
   - 3+ nodes verify the same batch independently
   - Consensus requires independent execution anyway

4. **Embedding pipelines**
   - Generate embeddings for a document corpus
   - Embeddable tasks are embarrassingly parallel

## Worst Use Cases

1. **Real-time chatbot**
   - 50ms network latency per token ruins UX
   - One fast Mac beats two slow networked Macs

2. **Single large prompt**
   - "Write a novel" can't be split across machines
   - Must run on one machine

3. **Model-parallel training**
   - Requires gradient synchronization across layers
   - WiFi/LAN too slow for tensor communication

## Demo

```bash
# Terminal 1: Coordinator
python3 examples/distributed_workers.py coordinator

# Terminal 2: Worker A
python3 examples/distributed_workers.py worker --id mac-a --capability prompt

# Terminal 3: Worker B
python3 examples/distributed_workers.py worker --id mac-b --capability prompt
```

## Production Path

1. **Local testing** (current): All on one machine
2. **LAN cluster**: 2-3 Macs on same WiFi/Ethernet
3. **Cloud workers**: EC2/GCP instances as workers
4. **P2P network**: Gossip-based discovery and task routing
5. **Payment integration**: Stripe Connect payouts per verified task

## Honest Comparison

| System | What It Does | MEMBRA Equivalent |
|--------|--------------|-------------------|
| Ray (Anyscale) | Distributed Python tasks | Job queue + worker nodes |
| Celery | Task queue with workers | Redis-based job queue |
| vLLM | Fast single-node inference | One Ollama worker |
| TensorFlow Federated | Distributed training across devices | Not implemented (training != inference) |
| OpenAI API | Cloud inference | MEMBRA workers = local/private alternative |

## The Bottom Line

> MEMBRA distributed workers are **honest job parallelism**.
> They make your AI work cheaper and more private by spreading batch jobs across machines you already own.
> They do NOT make one single prompt faster.
> They do NOT combine two MacBooks into one supercomputer.
> They DO make two MacBooks process twice as many prompts per hour.

That's a real and valuable capability. Just not magic.
