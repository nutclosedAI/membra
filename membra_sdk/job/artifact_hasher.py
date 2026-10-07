"""Artifact Hasher — computes SHA-256 hashes for all job artifacts.

Every file produced by a job gets a cryptographic hash.
This creates an immutable audit trail.
"""

import hashlib
from pathlib import Path


class ArtifactHasher:
    """Hashes artifacts for proof-of-job bundles."""

    @staticmethod
    def hash_file(filepath: str) -> str:
        """Compute SHA-256 of a file."""
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return f"sha256:{h.hexdigest()}"

    @staticmethod
    def hash_text(text: str) -> str:
        """Compute SHA-256 of text."""
        return f"sha256:{hashlib.sha256(text.encode()).hexdigest()}"

    @classmethod
    def hash_directory(cls, directory: str, pattern: str = "*") -> list[dict]:
        """Hash all files in a directory."""
        results = []
        base = Path(directory)
        for path in base.rglob(pattern) if pattern == "*" else base.glob(pattern):
            if path.is_file():
                results.append(
                    {
                        "path": str(path.relative_to(base)),
                        "sha256": cls.hash_file(str(path)),
                        "bytes": path.stat().st_size,
                    }
                )
        return results

    @classmethod
    def root_hash(cls, artifacts: list[dict]) -> str:
        """Compute a Merkle-like root hash from all artifact hashes."""
        hashes = sorted(a["sha256"] for a in artifacts)
        combined = "".join(hashes)
        return f"sha256:{hashlib.sha256(combined.encode()).hexdigest()}"

    @classmethod
    def hash_job_outputs(cls, job_dir: str) -> dict:
        """Hash all outputs in a job directory and return bundle."""
        artifacts = cls.hash_directory(job_dir)
        root = cls.root_hash(artifacts)
        return {
            "artifacts": artifacts,
            "root_hash": root,
            "count": len(artifacts),
            "total_bytes": sum(a["bytes"] for a in artifacts),
        }
