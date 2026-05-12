"""Chat Compiler — Layer 1 of MEMBRA Proof-of-Job

Turns a human chat prompt into a structured job spec.

Flow:
  User chat prompt
    ↓
  Intent extraction
    ↓
  JobSpec JSON

This is the entry point. Every MEMBRA job starts as chat.
"""
import hashlib
import json
from typing import Dict, List, Optional

from membra_sdk.job.job_spec import JobSpec


class ChatCompiler:
    """Compiles chat messages into structured JobSpec objects."""

    def __init__(self):
        self.version = "membra.job.v0.1"

    def compile(self, prompt: str, context: Dict = None) -> JobSpec:
        """Turn a chat prompt into a JobSpec.

        In production this calls an LLM to extract intent.
        For now, use keyword-based heuristics.
        """
        context = context or {}
        prompt_lower = prompt.lower()

        # Intent detection
        intent = self._extract_intent(prompt)

        # Runtime selection
        runtime = self._select_runtime(prompt_lower)

        # Model backend
        model = self._select_model(prompt_lower)

        # Policy
        policy = self._build_policy(prompt_lower, context)

        # Expected outputs
        outputs = self._infer_outputs(prompt_lower)

        # Inputs from context
        inputs = context.get("inputs", [])

        job = JobSpec(
            schema=self.version,
            intent=intent,
            inputs=inputs,
            runtime=runtime,
            model_backend=model,
            tools=runtime.get("tools", []),
            policy=policy,
            expected_outputs=outputs,
            yield_metric="validated_artifact_output",
            prompt_hash=self._hash(prompt),
            chat_summary=self._summarize(prompt),
        )
        return job

    def _extract_intent(self, prompt: str) -> str:
        """Extract the core intent from the prompt."""
        # Simple extraction — in production, use LLM
        lines = prompt.strip().split(".")
        first = lines[0].strip()
        return first if len(first) < 120 else first[:117] + "..."

    def _select_runtime(self, prompt_lower: str) -> Dict:
        """Select container runtime based on prompt keywords."""
        if any(k in prompt_lower for k in ["rust", "cargo", "tokio"]):
            return {"container": "rust:1.75", "tools": ["cargo", "clippy", "rustc"]}
        if any(k in prompt_lower for k in ["node", "npm", "typescript", "react"]):
            return {"container": "node:20-slim", "tools": ["npm", "node", "tsc"]}
        if any(k in prompt_lower for k in ["solana", "anchor"]):
            return {"container": "solana:1.17", "tools": ["anchor", "solana-cli", "cargo"]}
        # Default Python
        return {"container": "python:3.11-slim", "tools": ["pytest", "ruff", "mypy", "git"]}

    def _select_model(self, prompt_lower: str) -> str:
        """Select model backend based on task type."""
        if any(k in prompt_lower for k in ["code", "api", "function", "script", "app"]):
            return "ollama:qwen2.5-coder"
        if any(k in prompt_lower for k in ["review", "audit", "test", "check"]):
            return "ollama:llama3.2:3b"
        if any(k in prompt_lower for k in ["doc", "readme", "explain"]):
            return "ollama:llama3.1:8b"
        return "ollama:qwen2.5-coder"

    def _build_policy(self, prompt_lower: str, context: Dict) -> Dict:
        """Build safety policy from prompt and context."""
        policy = {
            "network": "restricted",
            "secrets": False,
            "funds": False,
            "mainnet": False,
        }
        # Allow mainnet only if explicitly requested AND context allows
        if context.get("allow_mainnet", False) and "mainnet" in prompt_lower:
            policy["mainnet"] = True
        if context.get("allow_funds", False):
            policy["funds"] = True
        return policy

    def _infer_outputs(self, prompt_lower: str) -> List[str]:
        """Infer expected outputs from prompt."""
        outputs = ["README.md", "proof.json"]
        if any(k in prompt_lower for k in ["app", "api", "server", "script"]):
            outputs.insert(0, "app.py")
            outputs.insert(1, "test_app.py")
        if any(k in prompt_lower for k in ["contract", "solana", "anchor"]):
            outputs.insert(0, "lib.rs")
            outputs.insert(1, "Cargo.toml")
        if any(k in prompt_lower for k in ["test", "pytest"]):
            if "test_app.py" not in outputs:
                outputs.insert(1, "tests/")
        return outputs

    def _summarize(self, prompt: str) -> str:
        """Create a short summary for the job record."""
        words = prompt.split()[:12]
        summary = " ".join(words)
        return summary + ("..." if len(prompt.split()) > 12 else "")

    def _hash(self, text: str) -> str:
        return f"sha256:{hashlib.sha256(text.encode()).hexdigest()}"
