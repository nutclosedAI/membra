"""Judge Brain — Scores specialist outputs, blocks bad artifacts, enforces quality.

The judge:
  1. Receives all specialist outputs
  2. Scores each on accuracy, completeness, style, safety
  3. Identifies conflicts between specialists
  4. Blocks outputs that fail safety/security thresholds
  5. Provides improvement suggestions
"""
import re
import time
from typing import Dict, List


class JudgeBrain:
    """Scores and validates specialist outputs before synthesis."""

    SCORE_DIMENSIONS = ["accuracy", "completeness", "style", "safety"]

    def __init__(self, safety_threshold: float = 0.9):
        self.safety_threshold = safety_threshold
        self.judgment_log: List[Dict] = []

    def score(self, worker_id: str, role: str, output: any,
              expected_task: str) -> Dict:
        """Score a specialist output on multiple dimensions.

        Returns:
            {"overall": float, "dimensions": dict, "passed": bool, "safety_flags": list}
        """
        dimensions = {}

        # Safety check first — hard rules
        safety_flags = self._check_safety(output)
        dimensions["safety"] = 0.0 if safety_flags else 1.0

        # Completeness
        output_text = str(output)
        dimensions["completeness"] = self._score_completeness(output_text, expected_task)

        # Style
        dimensions["style"] = self._score_style(output_text, role)

        # Accuracy (placeholder — would need ground truth or LLM judge)
        dimensions["accuracy"] = 0.85  # Assume reasonable unless contradicted

        overall = sum(dimensions.values()) / len(dimensions)
        passed = (
            dimensions["safety"] >= self.safety_threshold and
            overall >= 0.6
        )

        judgment = {
            "judgment_id": f"jdg-{int(time.time())}-{worker_id}",
            "worker_id": worker_id,
            "role": role,
            "dimensions": dimensions,
            "overall": round(overall, 3),
            "passed": passed,
            "safety_flags": safety_flags,
            "created_at": time.time(),
        }

        self.judgment_log.append(judgment)
        return judgment

    def compare(self, outputs: List[Dict]) -> Dict:
        """Compare multiple specialist outputs and rank them.

        Returns consensus recommendation.
        """
        if not outputs:
            return {"consensus": None, "agreement": 0.0}

        # Score each output
        scores = {}
        for out in outputs:
            worker_id = out.get("worker_id", "unknown")
            role = out.get("role", "unknown")
            result = out.get("result", "")
            judgment = self.score(worker_id, role, result, "compare")
            scores[worker_id] = judgment["overall"]

        # Find best
        best_worker = max(scores, key=scores.get)
        best_score = scores[best_worker]

        # Check agreement (how many are close to best)
        agreement = sum(1 for s in scores.values() if s >= best_score - 0.15)
        agreement_rate = agreement / len(scores) if scores else 0

        return {
            "consensus": agreement_rate >= 0.66,
            "best_worker": best_worker,
            "best_score": best_score,
            "agreement_rate": round(agreement_rate, 2),
            "all_scores": scores,
        }

    def _check_safety(self, output: any) -> List[str]:
        """Check for safety issues in output."""
        flags = []
        text = str(output).lower()

        # Hardcoded patterns that should NEVER appear in code
        dangerous_patterns = [
            r"password\s*=\s*['\"]",
            r"api_key\s*=\s*['\"]",
            r"secret\s*=\s*['\"]",
            r"private_key\s*=\s*['\"]",
            r"token\s*=\s*['\"]sk-",
            r"eval\s*\(",
            r"exec\s*\(",
            r"subprocess\.call\s*\(\s*['\"]rm",
            r"os\.system\s*\(",
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, text):
                flags.append(f"Dangerous pattern detected: {pattern[:30]}...")

        return flags

    def _score_completeness(self, text: str, expected_task: str) -> float:
        """Score how complete the output is."""
        score = 0.5  # Base

        # Length heuristic
        if len(text) > 500:
            score += 0.2
        if len(text) > 1000:
            score += 0.1

        # Check for key sections
        if "def " in text or "class " in text:
            score += 0.1
        if "test" in text.lower():
            score += 0.05
        if "#" in text or "\"\"\"" in text:
            score += 0.05

        return min(score, 1.0)

    def _score_style(self, text: str, role: str) -> float:
        """Score style quality."""
        score = 0.7

        # Code formatting
        if role == "coder":
            if text.count("\n") > 5:
                score += 0.1
            if "    " in text or "\t" in text:
                score += 0.1
            if "# " in text:
                score += 0.05

        # Docs formatting
        if role == "docs":
            if "#" in text:
                score += 0.1
            if "```" in text:
                score += 0.1

        return min(score, 1.0)

    def get_stats(self) -> Dict:
        """Judge statistics."""
        total = len(self.judgment_log)
        passed = sum(1 for j in self.judgment_log if j["passed"])
        failed = total - passed
        avg_score = sum(j["overall"] for j in self.judgment_log) / total if total else 0

        return {
            "total_judged": total,
            "passed": passed,
            "failed": failed,
            "average_score": round(avg_score, 3),
            "pass_rate": round(passed / total, 3) if total else 0,
        }
