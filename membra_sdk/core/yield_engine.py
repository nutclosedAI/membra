"""Yield Engine — Estimates value from file corpus content.

Proof-of-Yield consensus requires that validators agree not just
on inference hashes, but on the economic value (yield) of the batch.

Yield is derived from:
- File size and complexity
- Code metrics (functions, imports, documentation)
- File type rarity
- Local resource cost to process
"""
import hashlib
import os
from typing import Dict


class YieldEngine:
    """Estimates yield from file content for proof-of-yield consensus."""

    # Base yield rates per file type (arbitrary units)
    TYPE_RATES = {
        ".rs": 0.05,    # Rust — high value
        ".sol": 0.08,   # Solidity — very high value
        ".go": 0.04,    # Go — medium value
        ".py": 0.03,    # Python — common
        ".js": 0.02,    # JavaScript — very common
        ".ts": 0.025,   # TypeScript — medium
        ".cpp": 0.04,   # C++ — high compute value
        ".c": 0.03,
        ".md": 0.01,    # Markdown — low
        ".json": 0.005, # JSON — very low
        ".yaml": 0.005,
        ".toml": 0.01,
    }

    def estimate(self, filepath: str, content: str) -> float:
        """Estimate yield from a single file."""
        ext = os.path.splitext(filepath)[1].lower()
        base_rate = self.TYPE_RATES.get(ext, 0.001)

        # Complexity factor
        lines = content.count("\n") + 1
        functions = content.count("def ") + content.count("fn ") + content.count("function ")
        imports = content.count("import ") + content.count("use ") + content.count("#include ")
        comments = content.count("//") + content.count("# ") + content.count("/*")

        # Scarcity factor (rarer types earn more)
        scarcity = 1.0 / (self.TYPE_RATES.get(ext, 0.001) * 100)
        scarcity = min(scarcity, 10.0)

        # Compute cost factor (more compute = more yield)
        compute_cost = (lines * 0.001) + (functions * 0.01)

        # Documentation bonus
        doc_bonus = 1.0 + (comments / max(lines, 1)) * 0.5

        yield_est = base_rate * scarcity * compute_cost * doc_bonus
        return round(min(yield_est, 10.0), 6)

    def batch_yield(self, operations: list) -> float:
        """Total yield for a batch of operations."""
        return sum(op.get("yield_estimate", 0) for op in operations)
