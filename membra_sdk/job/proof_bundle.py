"""Proof Bundle — Layer 5 of MEMBRA Proof-of-Job

A portable, verifiable record that a job happened and produced valid output.

The proof bundle is the core product artifact. It can be:
  - Downloaded as a ZIP
  - Anchored to a blockchain
  - Sent to a customer
  - Used for grant applications
  - Stored as an audit record

Format:
  {
    "schema": "membra.proof_of_job.v0.1",
    "chat": {...},
    "job": {...},
    "container": {...},
    "artifacts": [...],
    "yield": {...},
    "consensus": {...},
    "settlement": {...},
    "root_hash": "sha256:..."
  }
"""
import hashlib
import json
import time
import zipfile
from pathlib import Path
from typing import Dict, List


class ProofBundle:
    """Creates and manages proof-of-job bundles."""

    SCHEMA = "membra.proof_of_job.v0.1"

    def __init__(self):
        self.data = {}

    def build(self, chat: Dict, job: Dict, container: Dict,
              artifacts: List[Dict], yield_report: Dict,
              consensus: Dict, settlement: Dict = None) -> Dict:
        """Build a complete proof bundle."""
        settlement = settlement or {"status": "unsettled", "external_receipts": []}

        bundle = {
            "schema": self.SCHEMA,
            "created_at": time.time(),
            "chat": chat,
            "job": job,
            "container": container,
            "artifacts": artifacts,
            "yield": yield_report,
            "consensus": consensus,
            "settlement": settlement,
        }

        # Compute root hash
        bundle["root_hash"] = self._compute_root_hash(bundle)
        self.data = bundle
        return bundle

    def _compute_root_hash(self, bundle: Dict) -> str:
        """Compute a deterministic root hash of the entire bundle."""
        # Serialize deterministically
        canonical = json.dumps(bundle, sort_keys=True, ensure_ascii=False)
        return f"sha256:{hashlib.sha256(canonical.encode()).hexdigest()}"

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.data, indent=indent, ensure_ascii=False)

    def save(self, path: str) -> str:
        """Save proof bundle as JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(self.to_json())
        return str(path)

    def export_zip(self, job_dir: str, output_path: str) -> str:
        """Export proof bundle + artifacts as a ZIP file."""
        job_dir = Path(job_dir)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add proof.json
            zf.writestr("proof.json", self.to_json())

            # Add all artifacts
            for artifact in self.data.get("artifacts", []):
                artifact_path = job_dir / artifact["path"]
                if artifact_path.exists():
                    zf.write(artifact_path, artifact["path"])

            # Add job spec
            job_json_path = job_dir / f"{self.data.get('job', {}).get('job_id', 'job')}.json"
            if job_json_path.exists():
                zf.write(job_json_path, "job.json")

        return str(output_path)

    def verify(self, bundle: Dict = None) -> Dict:
        """Verify that a proof bundle's root hash matches its contents."""
        bundle = bundle or self.data
        if not bundle:
            return {"valid": False, "reason": "Empty bundle"}

        stored_hash = bundle.get("root_hash", "")
        test_bundle = {k: v for k, v in bundle.items() if k != "root_hash"}
        computed = self._compute_root_hash(test_bundle)

        if computed == stored_hash:
            return {"valid": True, "reason": "Root hash matches"}
        return {
            "valid": False,
            "reason": "Root hash mismatch — bundle may be tampered",
            "stored": stored_hash,
            "computed": computed,
        }
