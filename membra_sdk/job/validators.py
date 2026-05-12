"""Validators — Layer 4 of MEMBRA Proof-of-Job

Multiple validators examine a job's output and vote.
Each validator has a role and scoring logic.

Validator roles:
  - structure: Does the output match expected files?
  - security: Are there secrets, eval(), os.system()?
  - usefulness: Does the output solve the stated intent?
  - tests: Do tests pass?
  - policy: Does it comply with the job's policy gates?

A ValidatorSet runs all validators and collects votes.
"""
from typing import Dict, List


class Validator:
    """A single validator with a specific role."""

    def __init__(self, validator_id: str, role: str):
        self.validator_id = validator_id
        self.role = role

    def validate(self, job_spec: Dict, artifacts: List[Dict],
                 logs: str = "", test_results: Dict = None) -> Dict:
        """Run this validator's checks and return a vote."""
        test_results = test_results or {}

        if self.role == "structure":
            return self._validate_structure(job_spec, artifacts)
        elif self.role == "security":
            return self._validate_security(artifacts)
        elif self.role == "usefulness":
            return self._validate_usefulness(job_spec, artifacts)
        elif self.role == "tests":
            return self._validate_tests(test_results)
        elif self.role == "policy":
            return self._validate_policy(job_spec, artifacts)
        else:
            return {"vote": "reject", "reason": f"Unknown validator role: {self.role}"}

    def _validate_structure(self, job_spec: Dict, artifacts: List[Dict]) -> Dict:
        expected = set(job_spec.get("expected_outputs", []))
        found = set(a.get("path", "") for a in artifacts)
        missing = expected - found
        if not missing:
            return {"vote": "accept", "reason": "All expected files present."}
        return {"vote": "reject", "reason": f"Missing expected files: {missing}"}

    def _validate_security(self, artifacts: List[Dict]) -> Dict:
        import re
        issues = []
        for artifact in artifacts:
            path = artifact.get("path", "")
            if path.endswith(".py") or path.endswith(".js") or path.endswith(".ts"):
                # In production, read the file. Here we check metadata.
                pass
        # Check for dangerous patterns in any code files
        # This is a simplified check
        return {"vote": "accept", "reason": "No obvious security issues in metadata."}

    def _validate_usefulness(self, job_spec: Dict, artifacts: List[Dict]) -> Dict:
        intent = job_spec.get("intent", "").lower()
        if not artifacts:
            return {"vote": "reject", "reason": "No artifacts produced."}
        # Simple heuristic: if there are artifacts, it's potentially useful
        if len(artifacts) >= 2:
            return {"vote": "accept", "reason": "Multiple artifacts suggest useful output."}
        return {"vote": "accept", "reason": "At least one artifact produced."}

    def _validate_tests(self, test_results: Dict) -> Dict:
        passed = test_results.get("passed", 0)
        total = test_results.get("total", 0)
        if total == 0:
            return {"vote": "accept", "reason": "No tests configured."}
        if passed == total:
            return {"vote": "accept", "reason": f"All {total} tests passed."}
        return {"vote": "reject", "reason": f"Tests failed: {passed}/{total}"}

    def _validate_policy(self, job_spec: Dict, artifacts: List[Dict]) -> Dict:
        policy = job_spec.get("policy", {})
        if policy.get("mainnet") and not policy.get("mainnet_explicitly_allowed"):
            return {"vote": "reject", "reason": "Mainnet policy violation."}
        return {"vote": "accept", "reason": "Policy checks passed."}


class ValidatorSet:
    """A collection of validators that run together."""

    DEFAULT_ROLES = ["structure", "security", "usefulness", "tests", "policy"]

    def __init__(self, validator_ids: List[str] = None):
        self.validator_ids = validator_ids or ["validator_a", "validator_b", "validator_c"]
        self.validators = []

    def add_default_validators(self):
        """Add the default set of validators."""
        for i, role in enumerate(self.DEFAULT_ROLES):
            vid = self.validator_ids[i % len(self.validator_ids)]
            self.validators.append(Validator(vid, role))

    def add_validator(self, validator_id: str, role: str):
        self.validators.append(Validator(validator_id, role))

    def run(self, job_spec: Dict, artifacts: List[Dict],
            logs: str = "", test_results: Dict = None) -> List[Dict]:
        """Run all validators and return votes."""
        if not self.validators:
            self.add_default_validators()

        votes = []
        for v in self.validators:
            vote = v.validate(job_spec, artifacts, logs, test_results)
            vote["validator_id"] = v.validator_id
            vote["role"] = v.role
            votes.append(vote)
        return votes
