"""Build Artifact Tracker — Converts LLM output into verifiable yield records.

Doctrine:
- An LLM prompt is not yield.
- An LLM answer is not yield.
- A generated idea is not yield.
- A working artifact with proof, test results, hash, commit, deployment,
  receipt, or settlement can become yield.

This module tracks build artifacts, tests, and proofs so that PoY consensus
has evidence to validate, not just file scans.
"""
import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class BuildArtifact:
    artifact_id: str
    artifact_type: str      # "file", "test", "contract", "benchmark", "deployment"
    path: str
    content_hash: str       # sha256 of file contents
    build_log_hash: str     # sha256 of build/test output
    status: str             # "created", "compiled", "tested", "deployed"
    timestamp: float
    metadata: Dict = field(default_factory=dict)


class ArtifactTracker:
    """Tracks build artifacts from LLM output to verified yield records."""

    ARTIFACT_TYPES = ["file", "test", "contract", "benchmark", "deployment", "receipt"]

    def __init__(self, workspace: str = None):
        self.workspace = workspace or os.path.expanduser("~/.membra/artifacts")
        os.makedirs(self.workspace, exist_ok=True)
        self.artifacts: List[BuildArtifact] = []
        self.load_index()

    def _hash_file(self, path: str) -> str:
        """Compute SHA-256 of file contents."""
        hasher = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
        except FileNotFoundError:
            return ""
        return hasher.hexdigest()

    def _hash_string(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def register_file(self, path: str, artifact_type: str = "file") -> BuildArtifact:
        """Register a file as a build artifact."""
        content_hash = self._hash_file(path)
        artifact = BuildArtifact(
            artifact_id=f"art-{int(time.time()*1000)}-{hashlib.sha256(path.encode()).hexdigest()[:8]}",
            artifact_type=artifact_type,
            path=path,
            content_hash=content_hash,
            build_log_hash="",
            status="created",
            timestamp=time.time(),
            metadata={"size": os.path.getsize(path) if os.path.exists(path) else 0},
        )
        self.artifacts.append(artifact)
        self._save_index()
        return artifact

    def run_tests(self, artifact: BuildArtifact, command: List[str]) -> BuildArtifact:
        """Run tests on an artifact and record results."""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=os.path.dirname(artifact.path) if os.path.isfile(artifact.path) else artifact.path,
            )
            log = f"exit={result.returncode}\nstdout={result.stdout[:2000]}\nstderr={result.stderr[:1000]}"
            artifact.build_log_hash = self._hash_string(log)
            artifact.status = "tested" if result.returncode == 0 else "test_failed"
            artifact.metadata["test_exit_code"] = result.returncode
            artifact.metadata["test_log_preview"] = result.stdout[:500]
        except Exception as e:
            artifact.status = "test_error"
            artifact.metadata["test_error"] = str(e)

        self._save_index()
        return artifact

    def compile_contract(self, artifact: BuildArtifact, compiler: str = "solc") -> BuildArtifact:
        """Compile a smart contract and record binary hash."""
        try:
            result = subprocess.run(
                [compiler, "--bin", artifact.path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                # Extract binary from output
                lines = result.stdout.strip().split("\n")
                binary = lines[-1] if lines else ""
                artifact.content_hash = self._hash_string(binary)
                artifact.status = "compiled"
                artifact.metadata["compiler"] = compiler
            else:
                artifact.status = "compile_failed"
                artifact.metadata["compile_error"] = result.stderr[:500]
        except FileNotFoundError:
            artifact.status = "compiler_missing"
            artifact.metadata["compile_error"] = f"{compiler} not installed"
        except Exception as e:
            artifact.status = "compile_error"
            artifact.metadata["compile_error"] = str(e)

        self._save_index()
        return artifact

    def get_yield_evidence(self) -> List[Dict]:
        """Return artifacts that can be used as yield evidence in consensus."""
        evidence = []
        for art in self.artifacts:
            if art.status in ("tested", "compiled", "deployed"):
                evidence.append({
                    "id": art.artifact_id,
                    "type": art.artifact_type,
                    "path": art.path,
                    "content_hash": art.content_hash,
                    "build_log_hash": art.build_log_hash,
                    "status": art.status,
                    "timestamp": art.timestamp,
                })
        return evidence

    def get_stats(self) -> Dict:
        return {
            "total": len(self.artifacts),
            "tested": sum(1 for a in self.artifacts if a.status == "tested"),
            "compiled": sum(1 for a in self.artifacts if a.status == "compiled"),
            "failed": sum(1 for a in self.artifacts if "failed" in a.status or "error" in a.status),
            "yield_evidence": len(self.get_yield_evidence()),
        }

    def _save_index(self):
        """Save artifact index to JSON."""
        index_path = os.path.join(self.workspace, "index.json")
        data = [
            {
                "artifact_id": a.artifact_id,
                "artifact_type": a.artifact_type,
                "path": a.path,
                "content_hash": a.content_hash,
                "build_log_hash": a.build_log_hash,
                "status": a.status,
                "timestamp": a.timestamp,
                "metadata": a.metadata,
            }
            for a in self.artifacts
        ]
        with open(index_path, "w") as f:
            json.dump(data, f, indent=2)

    def load_index(self):
        """Load artifact index from JSON."""
        index_path = os.path.join(self.workspace, "index.json")
        if os.path.exists(index_path):
            try:
                with open(index_path) as f:
                    data = json.load(f)
                self.artifacts = [
                    BuildArtifact(
                        artifact_id=a["artifact_id"],
                        artifact_type=a["artifact_type"],
                        path=a["path"],
                        content_hash=a["content_hash"],
                        build_log_hash=a["build_log_hash"],
                        status=a["status"],
                        timestamp=a["timestamp"],
                        metadata=a.get("metadata", {}),
                    )
                    for a in data
                ]
            except Exception:
                pass
