"""Job Spec — Layer 2 of MEMBRA Proof-of-Job

A JobSpec is a structured, executable unit derived from chat.
It is auditable, versioned, and portable.

Every job has:
  - intent: what the user wants
  - runtime: container, model, tools
  - policy: safety gates
  - expected_outputs: what should be produced
  - yield_metric: how success is measured
"""
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class JobSpec:
    """A structured, executable job specification."""
    schema: str = "membra.job.v0.1"
    job_id: str = field(default_factory=lambda: f"job_{uuid.uuid4().hex[:8]}")
    intent: str = ""
    inputs: List[str] = field(default_factory=list)
    runtime: Dict = field(default_factory=dict)
    model_backend: str = "ollama:qwen2.5-coder"
    tools: List[str] = field(default_factory=list)
    policy: Dict = field(default_factory=dict)
    expected_outputs: List[str] = field(default_factory=list)
    yield_metric: str = "validated_artifact_output"
    prompt_hash: str = ""
    chat_summary: str = ""
    created_at: float = field(default_factory=time.time)
    status: str = "pending"  # pending | running | completed | failed

    def to_dict(self) -> Dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: str = None) -> str:
        """Save job spec to disk and return path."""
        if path is None:
            base = Path.home() / ".membra" / "jobs"
            base.mkdir(parents=True, exist_ok=True)
            path = base / f"{self.job_id}.json"
        else:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            f.write(self.to_json())
        return str(path)

    @classmethod
    def load(cls, path: str) -> "JobSpec":
        """Load job spec from disk."""
        with open(path, "r") as f:
            data = json.load(f)
        return cls(**data)

    def validate_structure(self) -> Dict:
        """Validate that the job spec is well-formed."""
        issues = []
        if not self.intent:
            issues.append("Missing intent")
        if not self.runtime.get("container"):
            issues.append("Missing runtime.container")
        if not self.expected_outputs:
            issues.append("Missing expected_outputs")
        if not self.policy:
            issues.append("Missing policy")
        if self.policy.get("mainnet") and not self.policy.get("funds") is False:
            issues.append("Mainnet enabled without explicit fund policy")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "job_id": self.job_id,
        }
