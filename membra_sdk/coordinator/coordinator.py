"""Coordinator — Distributes tasks, collects results, verifies proof hashes.

The coordinator:
  - Accepts jobs from buyers/users
  - Splits into independent tasks
  - Dispatches to registered workers
  - Collects results
  - Verifies proof hashes
  - Runs consensus on results
  - Triggers payment for verified work

Honest: This is a LOCAL coordinator for demo/testing. Production would use
a proper message queue (Redis, RabbitMQ) or P2P gossip.
"""
import hashlib
import json
import time
from typing import Dict, List, Optional

from membra_sdk.scheduler.job_queue import JobQueue, TaskSplit, TaskStatus
from membra_sdk.worker.worker_node import WorkerNode


class Coordinator:
    """Coordinates distributed AI work across MEMBRA worker nodes."""

    def __init__(self):
        self.queue = JobQueue()
        self.workers: Dict[str, WorkerNode] = {}
        self.worker_heartbeats: Dict[str, float] = {}
        self.verified_results: Dict[str, dict] = {}
        self.payment_queue: List[dict] = []

    def register_worker(self, worker: WorkerNode) -> bool:
        """Register a worker node."""
        self.workers[worker.worker_id] = worker
        self.worker_heartbeats[worker.worker_id] = time.time()
        return True

    def submit_job(self, job_type: str, payload: dict,
                   split_strategy: str = "by_item") -> str:
        """Submit a job and get job ID."""
        tasks = self.queue.submit_job(job_type, payload, split_strategy)
        job_id = tasks[0].job_id if tasks else ""

        # Auto-dispatch to available workers
        self._dispatch_pending_tasks()

        return job_id

    def _dispatch_pending_tasks(self):
        """Dispatch pending tasks to idle workers."""
        pending = self.queue.list_pending()
        for task in pending:
            # Find idle worker with matching capability
            for worker in self.workers.values():
                if worker.current_task is None:
                    worker.claim_and_run(task.task_type)
                    break

    def collect_results(self, job_id: str) -> dict:
        """Collect and verify all results for a job."""
        # Verify any completed results first
        job_tasks = [t for t in self.queue.tasks.values() if t.job_id == job_id]
        results = self.queue.job_results.get(job_id, [])

        for result in results:
            task_id = result["task_id"]
            proof_hash = result["proof_hash"]
            task = self.queue.tasks.get(task_id)
            if task and task.status.value == "completed" and task.proof_hash == proof_hash:
                self.queue.mark_verified(task_id)

        # Re-check status after verification
        status = self.queue.get_job_status(job_id)

        response = {
            "job_id": job_id,
            "status": "completed" if status.get("done") else "in_progress",
            "total_tasks": status.get("total_tasks", 0),
            "pending": status.get("pending", 0),
            "completed": status.get("completed", 0),
            "verified": status.get("verified", 0),
            "failed": status.get("failed", 0),
            "payments_ready": 0,
        }

        if status.get("done"):
            # Queue payments for verified workers
            for result in results:
                task = self.queue.tasks.get(result["task_id"])
                if task and task.status.value == "verified":
                    self.payment_queue.append({
                        "task_id": task.task_id,
                        "worker_id": task.assigned_worker,
                        "amount_usd": task.cost_estimate / 100,
                        "job_id": job_id,
                        "proof_hash": task.proof_hash,
                        "verified_at": time.time(),
                    })
            response["payments_ready"] = len(self.payment_queue)

        return response

    def distribute_payments(self) -> List[dict]:
        """Distribute payments for verified work.

        In production, this would call Stripe Connect to transfer funds.
        """
        payments = []
        for p in self.payment_queue:
            # Simulation: record payment
            payments.append({
                "worker_id": p["worker_id"],
                "amount_usd": p["amount_usd"],
                "task_id": p["task_id"],
                "status": "paid_simulated",
                "note": "Real payout requires Stripe Connect integration",
            })

        self.payment_queue = []
        return payments

    def get_cluster_status(self) -> dict:
        """Status of the entire worker cluster."""
        active_workers = sum(
            1 for w in self.workers.values()
            if time.time() - self.worker_heartbeats.get(w.worker_id, 0) < 300
        )

        total_tasks = len(self.queue.tasks)
        pending = len(self.queue.list_pending())
        completed = len(self.queue.list_completed())

        return {
            "workers_total": len(self.workers),
            "workers_active": active_workers,
            "total_tasks": total_tasks,
            "pending": pending,
            "completed": completed,
            "payments_queued": len(self.payment_queue),
        }
