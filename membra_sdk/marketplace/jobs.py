"""Build Bounty Marketplace — Users post tasks, agents build artifacts, validators confirm delivery.

⚠️ SIMULATION: This module uses in-memory/local JSON storage. For production,
replace with PostgreSQL + Stripe Connect + real payment webhooks.

Revenue Source 1: Build Bounty Marketplace
- Users post tasks: apps, dashboards, bots, contracts, research, automation
- MEMBRA agents build them
- Payment goes into escrow
- Validators confirm delivery
- Yield is released
"""
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class JobStatus(Enum):
    OPEN = "open"               # Posted, waiting for builder
    CLAIMED = "claimed"         # Builder assigned
    BUILDING = "building"       # Agent working on it
    DELIVERED = "delivered"     # Artifact submitted, tests running
    TESTED = "tested"           # Tests passed
    APPROVED = "approved"       # Buyer approved delivery
    PAID = "paid"               # Payment settled
    FINALIZED = "finalized"     # Validators confirmed receipt, yield distributed
    DISPUTED = "disputed"       # Buyer/builder disagreement
    CANCELLED = "cancelled"     # Job cancelled, escrow refunded


@dataclass
class BuildJob:
    job_id: str
    title: str
    description: str
    requirements: List[str]
    deliverables: List[str]
    budget_usd: float
    buyer_id: str
    builder_id: Optional[str] = None
    artifact_hash: Optional[str] = None
    artifact_path: Optional[str] = None
    test_result: Optional[Dict] = None
    payment_receipt: Optional[Dict] = None
    status: JobStatus = JobStatus.OPEN
    created_at: float = field(default_factory=time.time)
    delivered_at: Optional[float] = None
    approved_at: Optional[float] = None
    finalized_at: Optional[float] = None
    validator_votes: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "description": self.description,
            "requirements": self.requirements,
            "deliverables": self.deliverables,
            "budget_usd": self.budget_usd,
            "buyer_id": self.buyer_id,
            "builder_id": self.builder_id,
            "artifact_hash": self.artifact_hash,
            "test_result": self.test_result,
            "payment_receipt": self.payment_receipt,
            "status": self.status.value,
            "created_at": self.created_at,
            "validator_votes": self.validator_votes,
        }


class JobBoard:
    """Marketplace where buyers post build jobs and agents claim them."""

    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or "/tmp/membra_jobs.jsonl"
        self.jobs: Dict[str, BuildJob] = {}
        self._load()

    def post_job(self, title: str, description: str, requirements: List[str],
                 deliverables: List[str], budget_usd: float, buyer_id: str) -> BuildJob:
        """Buyer posts a new build job."""
        job = BuildJob(
            job_id=f"job-{uuid.uuid4().hex[:12]}",
            title=title,
            description=description,
            requirements=requirements,
            deliverables=deliverables,
            budget_usd=budget_usd,
            buyer_id=buyer_id,
        )
        self.jobs[job.job_id] = job
        self._persist()
        return job

    def claim_job(self, job_id: str, builder_id: str) -> Optional[BuildJob]:
        """Builder claims an open job."""
        job = self.jobs.get(job_id)
        if not job or job.status != JobStatus.OPEN:
            return None
        job.builder_id = builder_id
        job.status = JobStatus.CLAIMED
        self._persist()
        return job

    def submit_artifact(self, job_id: str, artifact_path: str, artifact_hash: str) -> Optional[BuildJob]:
        """Builder submits completed artifact."""
        job = self.jobs.get(job_id)
        if not job or job.status not in (JobStatus.CLAIMED, JobStatus.BUILDING):
            return None
        job.artifact_path = artifact_path
        job.artifact_hash = artifact_hash
        job.status = JobStatus.DELIVERED
        job.delivered_at = time.time()
        self._persist()
        return job

    def submit_tests(self, job_id: str, test_result: Dict) -> Optional[BuildJob]:
        """Validator submits test results for the artifact."""
        job = self.jobs.get(job_id)
        if not job or job.status != JobStatus.DELIVERED:
            return None
        job.test_result = test_result
        job.status = JobStatus.TESTED if test_result.get("passed") else JobStatus.DELIVERED
        self._persist()
        return job

    def buyer_approve(self, job_id: str) -> Optional[BuildJob]:
        """Buyer approves delivery. Triggers payment release."""
        job = self.jobs.get(job_id)
        if not job or job.status != JobStatus.TESTED:
            return None
        job.status = JobStatus.APPROVED
        job.approved_at = time.time()
        self._persist()
        return job

    def submit_payment_receipt(self, job_id: str, receipt: Dict) -> Optional[BuildJob]:
        """Payment processor submits settlement receipt."""
        job = self.jobs.get(job_id)
        if not job or job.status != JobStatus.APPROVED:
            return None
        job.payment_receipt = receipt
        job.status = JobStatus.PAID
        self._persist()
        return job

    def validator_vote(self, job_id: str, validator_id: str, vote: Dict) -> Optional[BuildJob]:
        """Validator votes on payment receipt and delivery."""
        job = self.jobs.get(job_id)
        if not job or job.status != JobStatus.PAID:
            return None
        vote["validator_id"] = validator_id
        vote["timestamp"] = time.time()
        job.validator_votes.append(vote)
        # Check if 2/3 validators agree on receipt validity
        if self._check_validator_consensus(job):
            job.status = JobStatus.FINALIZED
            job.finalized_at = time.time()
        self._persist()
        return job

    def _check_validator_consensus(self, job: BuildJob) -> bool:
        if len(job.validator_votes) < 3:
            return False
        valid_votes = sum(1 for v in job.validator_votes if v.get("receipt_valid"))
        return valid_votes * 3 >= len(job.validator_votes) * 2

    def list_open(self) -> List[BuildJob]:
        return [j for j in self.jobs.values() if j.status == JobStatus.OPEN]

    def list_finalized(self) -> List[BuildJob]:
        return [j for j in self.jobs.values() if j.status == JobStatus.FINALIZED]

    def get_job(self, job_id: str) -> Optional[BuildJob]:
        return self.jobs.get(job_id)

    def _persist(self):
        with open(self.storage_path, "a") as f:
            for job in self.jobs.values():
                f.write(json.dumps(job.to_dict()) + "\n")

    def _load(self):
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path) as f:
                for line in f:
                    data = json.loads(line)
                    job_id = data.get("job_id")
                    if job_id:
                        self.jobs[job_id] = BuildJob(**data)
        except Exception:
            pass
