"""Proof-of-Yield Consensus — LLM validates batch + yield estimate.

Traditional consensus: validators agree on block contents.
Proof-of-Yield: validators agree on BOTH:
1. The batch state root (cryptographic integrity)
2. The total yield estimate (economic value)

A batch only finalizes if 2/3 of validators agree on BOTH.
This ties consensus to actual economic productivity.
"""
import asyncio
import hashlib
import json
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PoYVote:
    agent_id: str
    state_root: str
    inference_hash: str  # hash of LLM output
    yield_hash: str      # hash of yield estimate
    total_yield: float
    confidence: float
    timestamp: float


@dataclass
class PoYRound:
    round_id: str
    state_root: str
    votes: List[PoYVote] = field(default_factory=list)
    threshold: float = 0.6667
    finalized: bool = False
    finality_time: float = 0.0


class ProofOfYieldConsensus:
    """Consensus where validators must agree on yield + inference."""

    CONSENSUS_PROMPT = """You are a Membra Proof-of-Yield validator.
Evaluate this batch for validity and economic value.

State Root: {state_root}
Total Yield Estimate: {total_yield:.6f}
Operations: {op_count}
Top Files: {files}

Respond in this exact format:
VALID|YIELD=<your_number> |REASON=<one_word>

Where <your_number> is your independent yield estimate for this batch.
Your response will be hashed and used as a consensus vote."""

    def __init__(self, agent_id: str, groq_key: str = ""):
        self.agent_id = agent_id
        self.groq_key = groq_key or os.environ.get("GROQ_API_KEY", "")
        self.rounds: Dict[str, PoYRound] = {}
        self.vote_history: List[Dict] = []

    def _call_llm(self, prompt: str) -> str:
        """Run inference via Groq or deterministic fallback."""
        if not self.groq_key:
            # Deterministic fallback for testing
            return f"VALID|YIELD={hash(prompt) % 1000 / 1000:.6f}|REASON=agreed"

        import requests
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are a precise validator. One line answers only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 30,
        }
        try:
            resp = requests.post("https://api.groq.com/openai/v1/chat/completions",
                                  headers=headers, json=data, timeout=20)
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return "VALID|YIELD=0.500000|REASON=default"

    def _hash_inference(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def _extract_yield(self, response: str) -> float:
        """Parse yield from LLM response."""
        try:
            if "YIELD=" in response:
                part = response.split("YIELD=")[1].split("|")[0].strip()
                return float(part)
        except (ValueError, IndexError):
            pass
        return 0.0

    def cast_vote(self, state_root: str, batch: list, total_yield: float) -> PoYVote:
        """Run LLM and cast a proof-of-yield vote."""
        files = ", ".join(op.get("file", "unknown") for op in batch[:5])
        prompt = self.CONSENSUS_PROMPT.format(
            state_root=state_root,
            total_yield=total_yield,
            op_count=len(batch),
            files=files[:200],
        )
        inference = self._call_llm(prompt)
        inf_hash = self._hash_inference(inference)
        yield_confirm = self._extract_yield(inference)
        yield_hash = self._hash_inference(f"{yield_confirm:.6f}")

        return PoYVote(
            agent_id=self.agent_id,
            state_root=state_root,
            inference_hash=inf_hash,
            yield_hash=yield_hash,
            total_yield=yield_confirm,
            confidence=0.95 if "VALID" in inference.upper() else 0.1,
            timestamp=time.time(),
        )

    def add_external_vote(self, vote: PoYVote):
        """Add vote from another agent."""
        if vote.state_root not in self.rounds:
            self.rounds[vote.state_root] = PoYRound(
                round_id=f"poy-{vote.state_root[:16]}",
                state_root=vote.state_root,
            )
        self.rounds[vote.state_root].votes.append(vote)
        self._check_consensus(vote.state_root)

    def _check_consensus(self, state_root: str):
        r = self.rounds.get(state_root)
        if not r or r.finalized or len(r.votes) < 3:
            return

        # Must agree on BOTH inference hash AND yield hash
        inf_counts = defaultdict(int)
        yield_counts = defaultdict(int)
        for v in r.votes:
            inf_counts[v.inference_hash] += 1
            yield_counts[v.yield_hash] += 1

        top_inf, inf_count = max(inf_counts.items(), key=lambda x: x[1])
        top_yield, yield_count = max(yield_counts.items(), key=lambda x: x[1])

        total = len(r.votes)
        # Exact 2/3 on BOTH dimensions
        if (inf_count * 3 >= total * 2) and (yield_count * 3 >= total * 2):
            r.finalized = True
            r.finality_time = time.time()
            self.vote_history.append({
                "state_root": state_root,
                "votes": total,
                "inf_agreement": inf_count / total,
                "yield_agreement": yield_count / total,
                "finality_ms": round((r.finality_time - r.votes[0].timestamp) * 1000, 2),
            })

    def get_round(self, state_root: str) -> PoYRound:
        return self.rounds.get(state_root, PoYRound(round_id="empty", state_root=state_root))

    async def run_poy_round(self, state_root: str, batch: list, total_yield: float) -> PoYRound:
        """Run full proof-of-yield consensus round."""
        our_vote = self.cast_vote(state_root, batch, total_yield)
        self.add_external_vote(our_vote)

        start = time.time()
        timeout = 10.0
        while time.time() - start < timeout:
            r = self.rounds.get(state_root)
            if r and r.finalized:
                break
            await asyncio.sleep(0.5)

        return self.rounds.get(state_root, PoYRound(round_id="empty", state_root=state_root))

    def get_stats(self) -> Dict:
        finalized = [r for r in self.rounds.values() if r.finalized]
        return {
            "agent_id": self.agent_id,
            "total_rounds": len(self.rounds),
            "finalized": len(finalized),
            "avg_finality_ms": round(
                sum(v.get("finality_ms", 0) for v in self.vote_history) / max(len(self.vote_history), 1), 2
            ),
            "recent": self.vote_history[-3:],
        }
