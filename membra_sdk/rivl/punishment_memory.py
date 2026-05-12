"""Punishment Memory — Retrieves past failures to avoid repeating them.

Before generating new output, search memory:
  "Prompt: Build Stripe webhook"
  Memory finds:
    - Previous failure: did not verify Stripe signature
    - Previous failure: trusted client amount
    - Previous success: used construct_event with webhook secret
  Brain instruction becomes:
    "Do not repeat prior failures. Verify Stripe signature. Never trust client amount."

This gives learning without expensive training.
"""
import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional


class PunishmentMemory:
    """Retrieves past scored events to inform future generation."""

    def __init__(self, reward_path: str = None):
        self.reward_path = Path(reward_path or "~/.membra/reward_events.jsonl").expanduser()

    def search(self, prompt: str, limit: int = 10) -> Dict:
        """Search memory for related past events.

        Returns:
            {
                "failures": [list of failed events],
                "successes": [list of successful events],
                "warnings": [list of warnings to include in prompt],
                "suggestions": [list of suggestions from past successes],
            }
        """
        prompt_hash = self._hash(prompt)
        events = self._load_events()

        # Find events with similar prompt hash (first 16 chars)
        prefix = prompt_hash[:16]
        related = [e for e in events if e.get("prompt_hash", "").startswith(prefix)]

        # If no exact match, search by prompt keywords
        if not related:
            keywords = set(prompt.lower().split())
            related = []
            for e in events:
                # Simple heuristic: check if any word overlaps
                # In production, use embeddings
                event_reason = e.get("reason", "").lower()
                if any(kw in event_reason for kw in keywords):
                    related.append(e)

        failures = [e for e in related if e.get("verdict") == "punished"]
        successes = [e for e in related if e.get("verdict") == "accepted"]

        # Sort by most recent
        failures.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
        successes.sort(key=lambda e: e.get("timestamp", 0), reverse=True)

        # Generate warnings and suggestions
        warnings = self._extract_warnings(failures[:limit])
        suggestions = self._extract_suggestions(successes[:limit])

        return {
            "failures": failures[:limit],
            "successes": successes[:limit],
            "warnings": warnings,
            "suggestions": suggestions,
            "total_related": len(related),
        }

    def get_system_prompt_addon(self, prompt: str) -> str:
        """Generate instruction addon based on past failures/successes.

        This text is prepended to the LLM prompt to avoid past mistakes.
        """
        memory = self.search(prompt, limit=5)
        if memory["total_related"] == 0:
            return ""

        addon_parts = ["\n[RIVL Memory — Past Learnings]"]

        if memory["warnings"]:
            addon_parts.append("\nDo NOT repeat these past failures:")
            for w in memory["warnings"]:
                addon_parts.append(f"  • {w}")

        if memory["suggestions"]:
            addon_parts.append("\nApply these proven patterns:")
            for s in memory["suggestions"]:
                addon_parts.append(f"  • {s}")

        addon_parts.append("\n[End RIVL Memory]\n")
        return "\n".join(addon_parts)

    def _extract_warnings(self, failures: List[Dict]) -> List[str]:
        """Extract human-readable warnings from failure events."""
        warnings = []
        for f in failures:
            reasons = f.get("reason", "").split(",")
            for reason in reasons:
                reason = reason.strip()
                if reason == "tests_failed":
                    warnings.append("Ensure all tests pass before submitting")
                elif reason == "security_failed":
                    warnings.append("Run security scan — avoid hardcoded secrets, eval, os.system")
                elif reason == "payment_missing":
                    warnings.append("Verify payment receipt before delivering")
                elif reason == "consensus_missing":
                    warnings.append("Wait for validator consensus")
                elif reason == "financial_loss":
                    warnings.append("Simulate on testnet first — avoid real money loss")
                elif reason == "policy_violation":
                    warnings.append("Check policy gates before mainnet deployment")
                elif reason == "mainnet_without_approval":
                    warnings.append("NEVER deploy to mainnet without explicit approval")
                elif reason == "loss_of_funds":
                    warnings.append("CRITICAL: This pattern previously caused loss of funds")
                elif reason == "refund_requested":
                    warnings.append("Deliver what was promised — refunds hurt reputation")
                elif reason == "slippage_too_high":
                    warnings.append("Set slippage limits — protect against MEV")
                elif reason == "unauthorized_contract":
                    warnings.append("Verify contract addresses — unauthorized contracts are dangerous")
        return list(dict.fromkeys(warnings))  # Deduplicate while preserving order

    def _extract_suggestions(self, successes: List[Dict]) -> List[str]:
        """Extract proven patterns from successful events."""
        suggestions = []
        for s in successes:
            reasons = s.get("reason", "").split(",")
            for reason in reasons:
                reason = reason.strip()
                if reason == "tests_passed":
                    suggestions.append("Write comprehensive tests — they reliably earn reward")
                elif reason == "security_passed":
                    suggestions.append("Security-first approach pays off")
                elif reason == "payment_verified":
                    suggestions.append("Always verify Stripe receipt before marking complete")
                elif reason == "consensus_verified":
                    suggestions.append("Validator consensus strengthens proof")
                elif reason == "artifact_downloaded":
                    suggestions.append("Deliver clean, documented artifacts")
                elif reason == "verified_profit_after_fees":
                    suggestions.append("Account for all fees — net profit is what counts")
                elif reason == "receipt_confirmed_yield":
                    suggestions.append("Settlement confirmation before yield distribution")
        return list(dict.fromkeys(suggestions))

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def _load_events(self) -> List[Dict]:
        events = []
        if not self.reward_path.exists():
            return events
        with self.reward_path.open("r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return events
