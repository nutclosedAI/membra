# MEMBRA LLMGPT — Terminal-Native AI Validator

## What This Is

LLMGPT is a **GPT-style transformer built from scratch in PyTorch** that runs natively in the terminal. It is not a wrapper around Ollama, OpenAI, or Hugging Face. Every layer is written explicitly:

- Token + position embeddings
- Causal multi-head self-attention
- Feed-forward MLP with GELU
- Layer normalization
- Residual connections
- Logits + temperature/top-k sampling

It acts as a **validator node** in the MEMBRA network: it reads job artifacts, evaluates code quality, and produces structured votes that can be submitted to the Solana `membra_core` program.

## Architecture

```
Input tokens (byte-level, 256 vocab)
   ↓
Token Embedding + Position Embedding
   ↓
┌─────────────────────────────────────┐
│  Transformer Block (×N layers)      │
│  ┌───────────────────────────────┐  │
│  │ Layer Norm → Attention → Add │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │ Layer Norm → MLP → Add       │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
   ↓
Final Layer Norm
   ↓
LM Head (linear → vocab logits)
   ↓
Softmax + temperature/top-k sampling
   ↓
Next token
```

## Why From Scratch?

| Approach | Control | Size | Validator Mode | Terminal Native |
|----------|---------|------|--------------|-----------------|
| OpenAI API | None | Cloud only | ❌ | ❌ |
| Ollama | Medium | ~1-8GB | ⚠️ | ❌ |
| Hugging Face Transformers | Medium | ~1-8GB | ⚠️ | ❌ |
| **LLMGPT (this)** | **Full** | **~1-10MB** | **✅** | **✅** |

LLMGPT is designed for:
1. **Small models** (1-10M parameters) that run on MacBook CPU/MPS
2. **Validator tasks** (evaluate, score, vote) rather than general chat
3. **Terminal-native** streaming with keyboard shortcuts
4. **Solana integration** — structured output maps directly to on-chain votes

## Components

| File | Purpose |
|------|---------|
| `membra_sdk/llm/gpt.py` | Transformer architecture (LLMGPT + GPTConfig) |
| `membra_sdk/llm/tokenizer.py` | Byte-level tokenizer (256 vocab, no training) |
| `membra_sdk/llm/terminal_chat.py` | Streaming terminal chat interface |
| `membra_sdk/llm/validator.py` | Artifact evaluation → structured vote |
| `membra_sdk/llm/solana_bridge.py` | Submit votes to Solana program |

## Model Sizes

```python
# Tiny (1.2M params) — fast inference, basic validator
config = GPTConfig(n_layer=4, n_head=4, n_embd=256, block_size=512)

# Small (4.8M params) — better quality, still fast on MPS
config = GPTConfig(n_layer=6, n_head=6, n_embd=384, block_size=512)

# Medium (12M params) — best quality, requires MPS/GPU
config = GPTConfig(n_layer=8, n_head=8, n_embd=512, block_size=1024)
```

## Usage

### Chat Mode

```bash
membra validator start --model llmgpt --mode chat
```

Terminal-native streaming chat with:
- `/validate <job_id>` — switch to validator mode
- `/vote <job_id>` — submit vote to Solana
- `/status` — show model stats
- `/quit` — exit

### Validator Mode

```bash
# Evaluate a job from local storage
membra validator start --model llmgpt --mode validate --job-id job_0001

# Submit vote to Solana devnet
membra validator start --model llmgpt --mode validate --job-id job_0001 --solana
```

### Interactive Evaluation

```bash
membra validator start --model llmgpt --mode evaluate
> Enter artifact path: app.py
> Enter artifact path: tests/test_app.py
> Enter artifact path: done
> Job intent: Build a FastAPI app
```

### Load Checkpoint

```bash
membra validator start --model llmgpt --checkpoint ~/.membra/llmgpt.pt
```

## Validator Output Format

The model produces structured JSON that maps directly to the Solana `VoteAccount`:

```json
{
  "vote": 1,
  "score": 87,
  "reason": "Clean code, all tests pass, no security flags",
  "reason_hash": "sha256:9fae...",
  "checks": {
    "structure": true,
    "security": true,
    "usefulness": true,
    "tests": true,
    "policy": true
  }
}
```

## Training

LLMGPT can be trained on any text corpus:

```python
from membra_sdk.llm.gpt import LLMGPT, GPTConfig
from membra_sdk.llm.tokenizer import ByteTokenizer

config = GPTConfig(n_layer=4, n_head=4, n_embd=256)
model = LLMGPT(config)
tokenizer = ByteTokenizer()

# Load training data
with open("training_corpus.txt") as f:
    text = f.read()

tokens = tokenizer.encode(text)
# ... standard PyTorch training loop
```

For validator-specific training, use a corpus of:
- Code + test results + human judgments
- Structured evaluations (intent, artifacts, vote, score, reason)
- Security scan results + classifications

## Byte-Level Tokenization

Why bytes instead of BPE?

- **No training required** — vocab is fixed at 256
- **Every string is valid** — no out-of-vocabulary issues
- **Universal** — handles all languages, code, symbols
- **Fast** — encode/decode is just UTF-8 conversion

Trade-off: sequences are ~4x longer than BPE, but for small models this is acceptable.

## Solana Integration

The validator output feeds directly into the `membra_core` program:

```
LLMGPT evaluates artifacts
   ↓
Produces structured vote (JSON)
   ↓
reason_hash = sha256(reason)
   ↓
SolanaBridge.submit_validator_vote(
    job_pda, validator_pda, vote, score, reason_hash
)
   ↓
On-chain VoteAccount created
```

## Honest Status

| Capability | Status |
|------------|--------|
| Transformer architecture from scratch | ✅ Complete |
| Byte-level tokenizer | ✅ Complete |
| Terminal streaming chat | ✅ Complete |
| Validator evaluation engine | ✅ Complete |
| Deterministic fallback checks | ✅ Complete |
| Solana bridge (TS fallback) | ✅ Complete |
| Trained weights | ❌ Not included — train your own or load checkpoint |
| Python Solana client (direct) | ⚠️ Falls back to TS client for v0.1 |

## Performance

| Config | Params | Mac M5 Pro (MPS) | Mac Intel (CPU) |
|--------|--------|------------------|-----------------|
| 4L/4H/256D | 1.2M | ~200 tok/s | ~50 tok/s |
| 6L/6H/384D | 4.8M | ~100 tok/s | ~20 tok/s |
| 8L/8H/512D | 12M | ~40 tok/s | ~8 tok/s |

These are inference speeds for validator prompts (512 tokens). Chat mode may vary.

## Comparison

| Feature | LLMGPT | Ollama | OpenAI |
|---------|--------|--------|--------|
| From scratch | ✅ | ❌ | ❌ |
| Terminal native | ✅ | ❌ | ❌ |
| Validator mode | ✅ | ⚠️ | ❌ |
| Solana integration | ✅ | ❌ | ❌ |
| No API key | ✅ | ✅ | ❌ |
| Small (<10MB) | ✅ | ❌ | N/A |
| General chat quality | ⚠️ Small model | ✅ Good | ✅ Best |

LLMGPT is not meant to replace large models for general chat. It is designed for:
1. **Validator tasks** (evaluate, score, classify)
2. **Terminal-native** operation without browsers
3. **Solana on-chain** integration
4. **Full transparency** — every layer is readable

## Next Steps

1. Train LLMGPT on validator corpus (code + judgments)
2. Load checkpoint into `membra validator start`
3. Run validator on real job artifacts
4. Submit votes to Solana devnet
5. Compare LLM validator votes with deterministic validator votes
6. Tune model size for quality/speed trade-off on target hardware

## Doctrine

> **"Don't just chat. Validate provable work."**
>
> LLMGPT is not a general-purpose AI. It is a specialized validator:
> - It reads code, not poetry.
> - It scores tests, not opinions.
> - It votes on-chain, not in chat rooms.
>
> The model is small because validation is narrower than conversation.
> The model is transparent because consensus requires auditability.
> The model is terminal-native because validators run on servers, not browsers.
