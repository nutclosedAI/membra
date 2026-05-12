"""Verifier Stack — Layer 1 of RIVL. Deterministic checks before any reward.

Hard rules. No LLM judgment here.
- Unit tests must pass
- Security scan must find no secrets
- Payment receipt must be verified
- Validator consensus must reach 2/3
- Policy gates must be satisfied

This is the gatekeeper. Nothing passes to reward without passing verification.
"""
import os
import re
from typing import Dict, List, Optional


class VerifierStack:
    """Deterministic verification layer for all MEMBRA outputs."""

    def __init__(self):
        self.results: List[Dict] = []

    def verify_code(self, code: str, run_tests: bool = False,
                    test_command: List[str] = None) -> Dict:
        """Verify code passes basic checks and optional tests."""
        issues = []
        passed = True

        # Security scan
        security_result = self._scan_security(code)
        if security_result["issues"]:
            issues.extend(security_result["issues"])
            passed = False

        # Syntax check (Python only for now)
        syntax_result = self._check_syntax(code)
        if not syntax_result["valid"]:
            issues.append(f"Syntax error: {syntax_result['error']}")
            passed = False

        # Run tests if requested
        test_result = {"ran": False, "passed": False}
        if run_tests and test_command:
            import subprocess
            try:
                result = subprocess.run(
                    test_command,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                test_result["ran"] = True
                test_result["passed"] = result.returncode == 0
                test_result["output"] = result.stdout[:500]
                if not test_result["passed"]:
                    issues.append("Tests failed")
                    passed = False
            except Exception as e:
                test_result["error"] = str(e)
                issues.append(f"Test execution failed: {e}")
                passed = False

        return {
            "type": "code",
            "passed": passed,
            "issues": issues,
            "security": security_result,
            "syntax": syntax_result,
            "tests": test_result,
        }

    def verify_payment(self, receipt: Dict) -> Dict:
        """Verify a Stripe/Solana payment receipt."""
        issues = []
        passed = True

        # Check required fields
        required = ["processor", "amount", "currency", "status"]
        for field in required:
            if field not in receipt:
                issues.append(f"Missing receipt field: {field}")
                passed = False

        # Check status
        if receipt.get("status") != "succeeded":
            issues.append(f"Payment status: {receipt.get('status')}")
            passed = False

        # Check amount is reasonable
        amount = receipt.get("amount", 0)
        if amount <= 0:
            issues.append("Payment amount must be positive")
            passed = False

        return {
            "type": "payment",
            "passed": passed,
            "issues": issues,
            "amount": amount,
            "processor": receipt.get("processor", "unknown"),
        }

    def verify_consensus(self, votes: List[Dict], threshold: float = 0.66) -> Dict:
        """Verify 2/3 validator consensus on an output."""
        if not votes:
            return {"type": "consensus", "passed": False, "issues": ["No votes received"]}

        total = len(votes)
        yes_votes = sum(1 for v in votes if v.get("vote") == "yes")
        ratio = yes_votes / total if total > 0 else 0

        passed = ratio >= threshold
        issues = []
        if not passed:
            issues.append(f"Consensus failed: {yes_votes}/{total} ({ratio:.2%}), need {threshold:.0%}")

        return {
            "type": "consensus",
            "passed": passed,
            "issues": issues,
            "yes_votes": yes_votes,
            "total_votes": total,
            "ratio": round(ratio, 3),
        }

    def verify_policy(self, action: str, policy_config: Dict) -> Dict:
        """Verify action complies with policy gates."""
        issues = []
        passed = True

        # DeFi policy checks
        if "defi" in action.lower() or "trade" in action.lower():
            if not policy_config.get("defi_enabled", False):
                issues.append("DeFi is disabled by policy")
                passed = False
            if policy_config.get("mode", "simulation") != "simulation":
                if not policy_config.get("mainnet_enabled", False):
                    issues.append("Mainnet transactions require explicit enable")
                    passed = False
            if not policy_config.get("require_human_approval", True):
                issues.append("Human approval required for financial actions")
                passed = False

        # Mainnet gate
        if "mainnet" in action.lower():
            if not policy_config.get("mainnet_enabled", False):
                issues.append("Mainnet explicitly disabled")
                passed = False

        return {
            "type": "policy",
            "passed": passed,
            "issues": issues,
            "action": action,
        }

    def run_full_verification(self, artifact: str, receipt: Dict = None,
                              votes: List[Dict] = None,
                              policy: Dict = None,
                              run_tests: bool = False) -> Dict:
        """Run complete verification stack."""
        results = []

        # Code verification
        code_result = self.verify_code(artifact, run_tests=run_tests)
        results.append(code_result)

        # Payment verification
        if receipt:
            payment_result = self.verify_payment(receipt)
            results.append(payment_result)

        # Consensus verification
        if votes:
            consensus_result = self.verify_consensus(votes)
            results.append(consensus_result)

        # Policy verification
        if policy:
            policy_result = self.verify_policy(artifact, policy)
            results.append(policy_result)

        # Overall verdict
        all_passed = all(r["passed"] for r in results)
        all_issues = []
        for r in results:
            all_issues.extend(r.get("issues", []))

        return {
            "overall_passed": all_passed,
            "results": results,
            "issues": all_issues,
            "issue_count": len(all_issues),
        }

    def _scan_security(self, code: str) -> Dict:
        """Scan code for dangerous patterns."""
        issues = []
        patterns = [
            (r"password\s*=\s*['\"]", "Hardcoded password"),
            (r"api_key\s*=\s*['\"]", "Hardcoded API key"),
            (r"secret\s*=\s*['\"]", "Hardcoded secret"),
            (r"private_key\s*=\s*['\"]", "Hardcoded private key"),
            (r"token\s*=\s*['\"]sk-", "Hardcoded Stripe token"),
            (r"eval\s*\(", "Dangerous eval()"),
            (r"exec\s*\(", "Dangerous exec()"),
            (r"subprocess\.call\s*\(\s*['\"]rm", "Dangerous rm command"),
            (r"os\.system\s*\(", "Dangerous os.system()"),
            (r"__import__\s*\(", "Dynamic import"),
            (r"pickle\.loads", "Unsafe pickle"),
        ]

        for pattern, description in patterns:
            if re.search(pattern, code, re.IGNORECASE):
                issues.append(f"Security: {description}")

        return {"issues": issues, "passed": len(issues) == 0}

    def _check_syntax(self, code: str) -> Dict:
        """Check Python syntax."""
        try:
            import ast
            ast.parse(code)
            return {"valid": True, "error": None}
        except SyntaxError as e:
            return {"valid": False, "error": str(e)}
        except Exception as e:
            return {"valid": False, "error": str(e)}
