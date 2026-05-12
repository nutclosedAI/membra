"""MEMBRA LLMGPT — Minimal GPT-style transformer built from scratch in PyTorch.

Not a wrapper around Hugging Face or Ollama. Every layer is written explicitly:
- token + position embeddings
- causal multi-head self-attention
- feed-forward MLP
- layer normalization
- residual connections
- logits + sampling

Designed for small models (~1-10M params) that run on a MacBook CPU/MPS.
"""
import json
import math
import os
from dataclasses import dataclass
from typing import List, Optional

import torch
import torch.nn as nn
from torch.nn import functional as F


@dataclass
class GPTConfig:
    block_size: int = 512      # max context length
    vocab_size: int = 256      # byte-level (0-255)
    n_layer: int = 4
    n_head: int = 4
    n_embd: int = 256
    dropout: float = 0.0
    bias: bool = True

    @property
    def param_count(self) -> int:
        return (
            self.vocab_size * self.n_embd  # token embedding
            + self.block_size * self.n_embd  # position embedding
            + self.n_layer * (
                4 * self.n_embd * self.n_embd  # 4 weight matrices per layer (attn q,k,v,o)
                + 2 * 4 * self.n_embd * self.n_embd  # MLP up + down (4x expansion)
                + 4 * self.n_embd  # 2 layer norms
            )
            + self.n_embd  # final layer norm
            + self.n_embd * self.vocab_size  # lm_head
        )


class CausalSelfAttention(nn.Module):
    """Multi-head causal self-attention with explicit Q, K, V projections."""

    def __init__(self, config: GPTConfig):
        super().__init__()
        assert config.n_embd % config.n_head == 0
        self.n_head = config.n_head
        self.n_embd = config.n_embd
        self.head_size = config.n_embd // config.n_head

        # q, k, v projections as one linear layer for efficiency
        self.c_attn = nn.Linear(config.n_embd, 3 * config.n_embd, bias=config.bias)
        self.c_proj = nn.Linear(config.n_embd, config.n_embd, bias=config.bias)
        self.attn_dropout = nn.Dropout(config.dropout)
        self.resid_dropout = nn.Dropout(config.dropout)

        # Causal mask: lower triangular
        self.register_buffer(
            "bias",
            torch.tril(torch.ones(config.block_size, config.block_size)).view(
                1, 1, config.block_size, config.block_size
            ),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, T, C = x.size()

        # QKV projection
        qkv = self.c_attn(x)  # (B, T, 3*C)
        q, k, v = qkv.split(self.n_embd, dim=2)

        # Reshape for multi-head: (B, T, C) -> (B, n_head, T, head_size)
        q = q.view(B, T, self.n_head, self.head_size).transpose(1, 2)
        k = k.view(B, T, self.n_head, self.head_size).transpose(1, 2)
        v = v.view(B, T, self.n_head, self.head_size).transpose(1, 2)

        # Attention scores: (B, n_head, T, head_size) @ (B, n_head, head_size, T) -> (B, n_head, T, T)
        att = (q @ k.transpose(-2, -1)) * (1.0 / math.sqrt(self.head_size))
        # Causal mask
        att = att.masked_fill(self.bias[:, :, :T, :T] == 0, float("-inf"))
        att = F.softmax(att, dim=-1)
        att = self.attn_dropout(att)

        # Weighted sum: (B, n_head, T, T) @ (B, n_head, T, head_size) -> (B, n_head, T, head_size)
        y = att @ v
        # Reshape back: (B, n_head, T, head_size) -> (B, T, C)
        y = y.transpose(1, 2).contiguous().view(B, T, C)

        # Output projection
        y = self.resid_dropout(self.c_proj(y))
        return y


class MLP(nn.Module):
    """Feed-forward: expand 4x, GELU, project back."""

    def __init__(self, config: GPTConfig):
        super().__init__()
        self.c_fc = nn.Linear(config.n_embd, 4 * config.n_embd, bias=config.bias)
        self.c_proj = nn.Linear(4 * config.n_embd, config.n_embd, bias=config.bias)
        self.dropout = nn.Dropout(config.dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.c_fc(x)
        x = F.gelu(x)
        x = self.c_proj(x)
        x = self.dropout(x)
        return x


class Block(nn.Module):
    """Transformer block: pre-norm attention + pre-norm MLP with residuals."""

    def __init__(self, config: GPTConfig):
        super().__init__()
        self.ln_1 = nn.LayerNorm(config.n_embd, bias=config.bias)
        self.attn = CausalSelfAttention(config)
        self.ln_2 = nn.LayerNorm(config.n_embd, bias=config.bias)
        self.mlp = MLP(config)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attn(self.ln_1(x))
        x = x + self.mlp(self.ln_2(x))
        return x


class LLMGPT(nn.Module):
    """MEMBRA LLMGPT — from-scratch GPT for terminal inference and validation."""

    def __init__(self, config: GPTConfig):
        super().__init__()
        self.config = config

        self.transformer = nn.ModuleDict(
            {
                "wte": nn.Embedding(config.vocab_size, config.n_embd),
                "wpe": nn.Embedding(config.block_size, config.n_embd),
                "drop": nn.Dropout(config.dropout),
                "h": nn.ModuleList([Block(config) for _ in range(config.n_layer)]),
                "ln_f": nn.LayerNorm(config.n_embd, bias=config.bias),
            }
        )
        self.lm_head = nn.Linear(config.n_embd, config.vocab_size, bias=False)

        # Weight tying: lm_head shares weights with token embedding
        self.transformer.wte.weight = self.lm_head.weight

        self.apply(self._init_weights)

        # Special scaled init for residual projections (GPT-2 style)
        for pn, p in self.named_parameters():
            if pn.endswith("c_proj.weight"):
                torch.nn.init.normal_(p, mean=0.0, std=0.02 / math.sqrt(2 * config.n_layer))

    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            torch.nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, idx: torch.Tensor, targets: Optional[torch.Tensor] = None):
        device = idx.device
        b, t = idx.size()
        assert t <= self.config.block_size, f"Sequence length {t} exceeds block size {self.config.block_size}"

        # Token + position embeddings
        tok_emb = self.transformer.wte(idx)  # (b, t, n_embd)
        pos = torch.arange(0, t, dtype=torch.long, device=device).unsqueeze(0)  # (1, t)
        pos_emb = self.transformer.wpe(pos)  # (1, t, n_embd)
        x = self.transformer.drop(tok_emb + pos_emb)

        # Transformer blocks
        for block in self.transformer.h:
            x = block(x)

        x = self.transformer.ln_f(x)
        logits = self.lm_head(x)  # (b, t, vocab_size)

        loss = None
        if targets is not None:
            loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.view(-1))

        return logits, loss

    @torch.no_grad()
    def generate(
        self,
        idx: torch.Tensor,
        max_new_tokens: int = 256,
        temperature: float = 1.0,
        top_k: Optional[int] = None,
        stop_tokens: Optional[List[int]] = None,
    ) -> torch.Tensor:
        """Generate tokens with temperature and top-k sampling."""
        self.eval()
        for _ in range(max_new_tokens):
            # Crop to block size
            idx_cond = idx if idx.size(1) <= self.config.block_size else idx[:, -self.config.block_size :]
            logits, _ = self(idx_cond)
            logits = logits[:, -1, :] / temperature

            if top_k is not None:
                v, _ = torch.topk(logits, min(top_k, logits.size(-1)))
                logits[logits < v[:, [-1]]] = float("-inf")

            probs = F.softmax(logits, dim=-1)
            idx_next = torch.multinomial(probs, num_samples=1)

            if stop_tokens and idx_next.item() in stop_tokens:
                break

            idx = torch.cat((idx, idx_next), dim=1)

        return idx

    @torch.no_grad()
    def generate_streaming(
        self,
        idx: torch.Tensor,
        max_new_tokens: int = 256,
        temperature: float = 1.0,
        top_k: Optional[int] = None,
        stop_tokens: Optional[List[int]] = None,
    ):
        """Yields tokens one at a time for streaming terminal output."""
        self.eval()
        for _ in range(max_new_tokens):
            idx_cond = idx if idx.size(1) <= self.config.block_size else idx[:, -self.config.block_size :]
            logits, _ = self(idx_cond)
            logits = logits[:, -1, :] / temperature

            if top_k is not None:
                v, _ = torch.topk(logits, min(top_k, logits.size(-1)))
                logits[logits < v[:, [-1]]] = float("-inf")

            probs = F.softmax(logits, dim=-1)
            idx_next = torch.multinomial(probs, num_samples=1)

            if stop_tokens and idx_next.item() in stop_tokens:
                break

            idx = torch.cat((idx, idx_next), dim=1)
            yield idx_next.item()

    def save_checkpoint(self, path: str):
        """Save model weights + config as a checkpoint."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        checkpoint = {
            "config": self.config.__dict__,
            "state_dict": self.state_dict(),
        }
        torch.save(checkpoint, path)

    @classmethod
    def load_checkpoint(cls, path: str, map_location="cpu") -> "LLMGPT":
        """Load model from a checkpoint file."""
        checkpoint = torch.load(path, map_location=map_location, weights_only=False)
        config = GPTConfig(**checkpoint["config"])
        model = cls(config)
        model.load_state_dict(checkpoint["state_dict"])
        return model

    def count_parameters(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def device_info(self) -> str:
        device = next(self.parameters()).device
        return f"{device} ({torch.cuda.get_device_name(device) if device.type == 'cuda' else 'CPU/MPS'})"
