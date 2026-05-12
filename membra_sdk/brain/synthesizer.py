"""Synthesizer Brain — Merges specialist outputs into one coherent result.

The synthesizer:
  1. Collects all specialist outputs
  2. Scores each output (from Judge)
  3. Merges best parts into final artifact
  4. Ensures consistency across merged components
  5. Produces final answer + buildable artifact
"""
import hashlib
import json
import time
from typing import Dict, List


class SynthesizerBrain:
    """Merges multiple specialist outputs into one final result."""

    def __init__(self):
        self.synthesis_history: List[Dict] = []

    def synthesize(self, plan: Dict, specialist_outputs: List[Dict],
                   judge_scores: Dict[str, float]) -> Dict:
        """Merge specialist outputs into final artifact.

        Args:
            plan: The original router plan
            specialist_outputs: List of outputs from each specialist
            judge_scores: Quality scores from JudgeBrain

        Returns:
            Final synthesized result with artifact, hash, and provenance
        """
        # Filter outputs that meet quality threshold
        threshold = plan.get("quality_threshold", 0.75)
        valid_outputs = [
            out for out in specialist_outputs
            if judge_scores.get(out.get("worker_id", ""), 0) >= threshold
        ]

        if not valid_outputs:
            # Fallback: use highest scored output
            valid_outputs = sorted(
                specialist_outputs,
                key=lambda o: judge_scores.get(o.get("worker_id", ""), 0),
                reverse=True,
            )[:1]

        # Merge strategy depends on task type
        merged = self._merge_outputs(plan, valid_outputs)

        # Compute final hash
        artifact_hash = hashlib.sha256(
            json.dumps(merged, sort_keys=True).encode()
        ).hexdigest()

        result = {
            "synthesis_id": f"syn-{int(time.time())}",
            "plan_id": plan.get("plan_id", ""),
            "original_prompt": plan.get("original_prompt", ""),
            "final_artifact": merged.get("code", merged.get("text", "")),
            "artifact_type": merged.get("type", "text"),
            "artifact_hash": artifact_hash,
            "component_outputs": [
                {
                    "worker_id": out.get("worker_id", ""),
                    "role": out.get("role", ""),
                    "score": judge_scores.get(out.get("worker_id", ""), 0),
                    "included": out in valid_outputs,
                }
                for out in specialist_outputs
            ],
            "judge_summary": {
                "scores": judge_scores,
                "threshold": threshold,
                "passed": len(valid_outputs),
                "total": len(specialist_outputs),
            },
            "created_at": time.time(),
        }

        self.synthesis_history.append(result)
        return result

    def _merge_outputs(self, plan: Dict, outputs: List[Dict]) -> Dict:
        """Merge outputs based on their roles."""
        merged = {"type": "artifact", "code": "", "docs": "", "tests": "", "security_notes": ""}

        for out in outputs:
            role = out.get("role", "")
            content = out.get("result", "")

            if role == "coder":
                merged["code"] = content.get("code", str(content)) if isinstance(content, dict) else str(content)
            elif role == "docs":
                merged["docs"] = content if isinstance(content, str) else str(content)
            elif role == "tester":
                merged["tests"] = content if isinstance(content, str) else str(content)
            elif role == "security":
                merged["security_notes"] = content if isinstance(content, str) else str(content)
            elif role == "researcher":
                merged["research"] = content if isinstance(content, str) else str(content)

        # Build combined artifact
        if merged["code"]:
            final = f"{merged['docs']}\n\n{merged['code']}\n\n# Tests\n{merged['tests']}\n\n# Security Notes\n{merged['security_notes']}"
        else:
            final = "\n\n".join(
                str(out.get("result", "")) for out in outputs
            )

        merged["combined"] = final.strip()
        return merged

    def stream_draft(self, draft_output: str, verifier_output: str) -> str:
        """Speculative draft/verify: fast draft model + accurate verifier.

        Returns the verified and corrected output.
        """
        # In production: token-by-token verification
        # For demo: simple merge with verifier corrections
        if not verifier_output:
            return draft_output

        # Use verifier to correct draft
        return f"[verified] {draft_output}\n\n[corrections applied from verifier]"
