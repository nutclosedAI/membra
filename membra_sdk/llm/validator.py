"""MEMBRA LLMGPT Validator Engine — Artifact evaluation → structured vote.

The model reads job artifacts (code, tests, docs) and produces a structured
validator vote that maps directly to the Solana membra_core VoteAccount format.

Output format:
  {
    "vote": 1,           // 1 = accept, 0 = reject
    "score": 87,         // 0-100 quality score
    "reason": "...",     // human-readable reason
    "reason_hash": "...",// sha256 of reason text
    "checks": {
      "structure": true,
      "security": true,
      "usefulness": true,
      "tests": true,
      "policy": true
    }
  }

This combines LLM inference with deterministic checks.
"""
import hashlib
import json
import os
from typing import Dict, List, Optional

import torch

from .gpt import LLMGPT
from .tokenizer import ByteTokenizer


class ValidatorEngine:
    """Evaluate job artifacts and produce structured validator votes."""

    def __init__(self, model: LLMGPT, tokenizer: Optional[ByteTokenizer] = None, device: Optional[str] = None):
        self.model = model
        self.tokenizer = tokenizer or ByteTokenizer()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self.model.to(self.device)
        self.model.eval()

    def _hash_reason(self, reason: str) -> str:
        return hashlib.sha256(reason.encode()).hexdigest()

    def _build_validator_prompt(
        self,
        job_intent: str,
        artifacts: List[Dict],
        test_results: Optional[Dict] = None,
        policy: Optional[Dict] = None,
    ) -> str:
        """Build the prompt that asks the model to act as a validator."""
        prompt = f"""You are a MEMBRA validator. Evaluate the following job output.

JOB INTENT:
{job_intent}

ARTIFACTS:
"""
        for art in artifacts:
            path = art.get("path", "unknown")
            content = art.get("content", "")[:2000]  # truncate large files
            prompt += f"\n--- {path} ---\n{content}\n"

        if test_results:
            passed = test_results.get("passed", 0)
            total = test_results.get("total", 0)
            prompt += f"\nTESTS: {passed}/{total} passed\n"

        if policy:
            prompt += f"\nPOLICY: {json.dumps(policy)}\n"

        prompt += """
Evaluate on:
1. STRUCTURE: Does output match expected files?
2. SECURITY: Any secrets, eval(), os.system(), unsafe patterns?
3. USEFULNESS: Does it solve the stated intent?
4. TESTS: Do tests pass? Is coverage adequate?
5. POLICY: Does it comply with all policy gates?

Respond ONLY in this JSON format:
{
  "vote": 1,
  "score": 87,
  "reason": "One-line summary of evaluation",
  "checks": {
    "structure": true,
    "security": true,
    "usefulness": true,
    "tests": true,
    "policy": true
  }
}
"""
        return prompt

    def evaluate(
        self,
        job_intent: str,
        artifacts: List[Dict],
        test_results: Optional[Dict] = None,
        policy: Optional[Dict] = None,
        max_tokens: int = 512,
        temperature: float = 0.3,
    ) -> Dict:
        """Evaluate artifacts and return a structured vote."""
        prompt = self._build_validator_prompt(job_intent, artifacts, test_results, policy)
        tokens = self.tokenizer.encode(prompt)
        idx = torch.tensor([tokens], dtype=torch.long, device=self.device)

        # Generate response
        generated = []
        with torch.no_grad():
            for tok in self.model.generate_streaming(
                idx,
                max_new_tokens=max_tokens,
                temperature=temperature,
                top_k=20,
            ):
                generated.append(tok)
                # Stop at closing brace for JSON
                text_so_far = self.tokenizer.decode(generated)
                if text_so_far.strip().endswith("}"):
                    break

        response_text = self.tokenizer.decode(generated)

        # Try to parse JSON from response
        vote = self._parse_vote(response_text)

        # Fallback to deterministic checks if JSON parse fails
        if vote is None:
            vote = self._deterministic_vote(job_intent, artifacts, test_results, policy)

        # Add reason hash
        vote["reason_hash"] = self._hash_reason(vote["reason"])
        return vote

    def _parse_vote(self, text: str) -> Optional[Dict]:
        """Extract JSON vote from model output."""
        try:
            # Find JSON block
            start = text.find("{")
            end = text.rfind("}") + 1
            if start == -1 or end == 0:
                return None
            json_str = text[start:end]
            parsed = json.loads(json_str)

            # Validate structure
            vote = {
                "vote": 1 if parsed.get("vote", 0) >= 1 else 0,
                "score": max(0, min(100, int(parsed.get("score", 50)))),
                "reason": str(parsed.get("reason", "No reason provided")),
                "checks": parsed.get("checks", {}),
            }
            return vote
        except (json.JSONDecodeError, ValueError, TypeError):
            return None

    def _deterministic_vote(
        self,
        job_intent: str,
        artifacts: List[Dict],
        test_results: Optional[Dict],
        policy: Optional[Dict],
    ) -> Dict:
        """Fallback deterministic validator (no model required)."""
        checks = {
            "structure": len(artifacts) > 0,
            "security": True,
            "usefulness": len(job_intent) > 0,
            "tests": False,
            "policy": True,
        }

        # Security scan
        for art in artifacts:
            content = art.get("content", "")
            bad_patterns = ["eval(", "os.system(", "subprocess.call", "__import__", "exec("]
            for pat in bad_patterns:
                if pat in content:
                    checks["security"] = False
                    break

        # Test check
        if test_results:
            passed = test_results.get("passed", 0)
            total = test_results.get("total", 1)
            checks["tests"] = passed >= total
        else:
            checks["tests"] = True  # no tests required

        # Policy check
        if policy:
            if policy.get("secrets") == "blocked":
                for art in artifacts:
                    content = art.get("content", "")
                    if "API_KEY" in content or "SECRET" in content:
                        checks["policy"] = False

        score = sum(checks.values()) * 20  # 5 checks * 20 = 100 max
        vote_val = 1 if score >= 60 else 0

        reasons = []
        if not checks["structure"]:
            reasons.append("missing artifacts")
        if not checks["security"]:
            reasons.append("security flags")
        if not checks["usefulness"]:
            reasons.append("unclear intent")
        if not checks["tests"]:
            reasons.append("tests failed")
        if not checks["policy"]:
            reasons.append("policy violation")

        reason = "; ".join(reasons) if reasons else "all checks passed"

        return {
            "vote": vote_val,
            "score": score,
            "reason": reason,
            "checks": checks,
        }

    def evaluate_directory(self, job_intent: str, directory: str) -> Dict:
        """Evaluate all files in a directory as job artifacts."""
        artifacts = []
        for root, _, files in os.walk(directory):
            for fname in files:
                path = os.path.join(root, fname)
                try:
                    with open(path) as f:
                        content = f.read()
                    artifacts.append({"path": path, "content": content})
                except Exception:
                    pass

        return self.evaluate(job_intent, artifacts)
