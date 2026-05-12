"""Job Queue and Scheduler — Distributes independent AI tasks across workers.

⚠️ HONEST LIMITATION: This is JOB PARALLELISM, not MODEL PARALLELISM.
- Job parallelism: many independent tasks across machines ✓
- Model parallelism: one big model split across machines ✗ (requires fast interconnect)

What works well:
  - Many prompts (batch inference)
  - File analysis batches
  - Artifact generation queues
  - Code review across files
  - Document summarization
  - Embedding generation
  - Validator voting
  - Batch processing

What does NOT work well:
  - One single LLM response split across two MacBooks
  - Real-time chat with distributed workers (network latency)
  - Large model inference requiring shared memory
"""
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"


@dataclass
class TaskSplit:
    """A single independent task that can be run on any worker."""
    task_id: str
    job_id: str
    task_type: str      # "prompt", "file_analysis", "artifact_gen", "embedding", "review"
    payload: dict        # The actual work: prompt text, file path, etc.
    status: TaskStatus = TaskStatus.PENDING
    assigned_worker: Optional[str] = None
    result: Optional[dict] = None
    proof_hash: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    cost_estimate: float = 0.0  # Estimated compute cost in cents

    def compute_proof_hash(self) -> str:
        """Hash of task payload + result for verification."""
        data = f"{self.task_id}:{self.task_type}:{json.dumps(self.payload, sort_keys=True)}"
        if self.result:
            data += json.dumps(self.result, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()


class JobQueue:
    """Schedules and tracks distributed AI tasks across worker nodes."""

    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or "/tmp/membra_job_queue.json"
        self.tasks: Dict[str, TaskSplit] = {}
        self.job_results: Dict[str, List[dict]] = {}
        self._load()

    def submit_job(self, job_type: str, payload: dict, split_strategy: str = "single") -> List[TaskSplit]:
        """Submit a job and split into independent tasks.

        Args:
            job_type: Type of work (prompt_batch, file_batch, artifact_queue, etc.)
            payload: Job payload containing items to process
            split_strategy: How to split: "single", "by_item", "by_file"

        Returns:
            List of TaskSplit objects ready for workers
        """
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        tasks = []

        if split_strategy == "single":
            # One task = one job
            task = TaskSplit(
                task_id=f"{job_id}-0",
                job_id=job_id,
                task_type=job_type,
                payload=payload,
            )
            tasks.append(task)

        elif split_strategy == "by_item" and "items" in payload:
            # Split by individual items (prompts, files, etc.)
            for i, item in enumerate(payload["items"]):
                task = TaskSplit(
                    task_id=f"{job_id}-{i}",
                    job_id=job_id,
                    task_type=job_type,
                    payload={"item": item, "index": i, "total": len(payload["items"])},
                    cost_estimate=self._estimate_cost(job_type, item),
                )
                tasks.append(task)

        elif split_strategy == "by_file" and "files" in payload:
            # Split by files
            for i, fpath in enumerate(payload["files"]):
                task = TaskSplit(
                    task_id=f"{job_id}-{i}",
                    job_id=job_id,
                    task_type=job_type,
                    payload={"file": fpath, "index": i, "total": len(payload["files"])},
                    cost_estimate=self._estimate_cost(job_type, fpath),
                )
                tasks.append(task)

        else:
            # Fallback: single task
            task = TaskSplit(
                task_id=f"{job_id}-0",
                job_id=job_id,
                task_type=job_type,
                payload=payload,
            )
            tasks.append(task)

        for task in tasks:
            self.tasks[task.task_id] = task

        self._persist()
        return tasks

    def claim_task(self, worker_id: str, capability: str = None) -> Optional[TaskSplit]:
        """Worker claims an available task matching its capability."""
        for task in self.tasks.values():
            if task.status == TaskStatus.PENDING:
                if capability and task.task_type != capability:
                    continue
                task.status = TaskStatus.ASSIGNED
                task.assigned_worker = worker_id
                task.started_at = time.time()
                self._persist()
                return task
        return None

    def submit_result(self, task_id: str, worker_id: str, result: dict) -> bool:
        """Worker submits completed task result."""
        task = self.tasks.get(task_id)
        if not task or task.assigned_worker != worker_id:
            return False

        task.result = result
        task.proof_hash = task.compute_proof_hash()
        task.status = TaskStatus.COMPLETED
        task.completed_at = time.time()

        # Add to job results
        self.job_results.setdefault(task.job_id, []).append({
            "task_id": task_id,
            "worker": worker_id,
            "proof_hash": task.proof_hash,
            "result_preview": str(result)[:200],
        })

        self._persist()
        return True

    def mark_verified(self, task_id: str) -> bool:
        """Coordinator marks task result as verified."""
        task = self.tasks.get(task_id)
        if not task or task.status != TaskStatus.COMPLETED:
            return False
        task.status = TaskStatus.VERIFIED
        self._persist()
        return True

    def get_job_status(self, job_id: str) -> dict:
        """Get status of all tasks in a job."""
        job_tasks = [t for t in self.tasks.values() if t.job_id == job_id]
        total = len(job_tasks)
        completed = sum(1 for t in job_tasks if t.status == TaskStatus.COMPLETED)
        verified = sum(1 for t in job_tasks if t.status == TaskStatus.VERIFIED)
        failed = sum(1 for t in job_tasks if t.status == TaskStatus.FAILED)
        pending = sum(1 for t in job_tasks if t.status == TaskStatus.PENDING)

        return {
            "job_id": job_id,
            "total_tasks": total,
            "pending": pending,
            "completed": completed,
            "verified": verified,
            "failed": failed,
            "done": verified == total and total > 0,
            "results": self.job_results.get(job_id, []),
        }

    def list_pending(self) -> List[TaskSplit]:
        return [t for t in self.tasks.values() if t.status == TaskStatus.PENDING]

    def list_completed(self) -> List[TaskSplit]:
        return [t for t in self.tasks.values() if t.status == TaskStatus.COMPLETED]

    def _estimate_cost(self, task_type: str, item: any) -> float:
        """Rough cost estimate in cents."""
        estimates = {
            "prompt": 2.0,
            "file_analysis": 1.0,
            "artifact_gen": 5.0,
            "embedding": 0.5,
            "review": 3.0,
        }
        return estimates.get(task_type, 1.0)

    def _persist(self):
        try:
            data = {}
            for tid, t in self.tasks.items():
                data[tid] = {
                    "task_id": t.task_id,
                    "job_id": t.job_id,
                    "task_type": t.task_type,
                    "payload": t.payload,
                    "status": t.status.value,
                    "assigned_worker": t.assigned_worker,
                    "result": t.result,
                    "proof_hash": t.proof_hash,
                    "created_at": t.created_at,
                    "started_at": t.started_at,
                    "completed_at": t.completed_at,
                    "cost_estimate": t.cost_estimate,
                }
            with open(self.storage_path, "w") as f:
                json.dump({"tasks": data, "job_results": self.job_results}, f, indent=2, default=str)
        except Exception:
            pass

    def _load(self):
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path) as f:
                data = json.load(f)
            for tid, td in data.get("tasks", {}).items():
                self.tasks[tid] = TaskSplit(
                    task_id=td["task_id"],
                    job_id=td["job_id"],
                    task_type=td["task_type"],
                    payload=td["payload"],
                    status=TaskStatus(td.get("status", "pending")),
                    assigned_worker=td.get("assigned_worker"),
                    result=td.get("result"),
                    proof_hash=td.get("proof_hash"),
                    created_at=td["created_at"],
                    started_at=td.get("started_at"),
                    completed_at=td.get("completed_at"),
                    cost_estimate=td.get("cost_estimate", 0.0),
                )
            self.job_results = data.get("job_results", {})
        except Exception:
            pass
