"""Brain Server — REST API for coordinating MEMBRA workers over LAN.

Endpoints:
  POST /register-worker     — Worker registers with brain
  POST /submit-job          — Submit a new job
  GET  /workers             — List registered workers
  GET  /jobs/<job_id>       — Get job status and results
  POST /worker/heartbeat    — Worker heartbeat
  GET  /worker/next-task    — Worker polls for next task
  POST /worker/submit-result — Worker submits task result
  GET  /health              — Health check
"""
import hashlib
import json
import os
import time
from threading import Lock
from typing import Dict, List, Optional

from flask import Flask, jsonify, request

from membra_sdk.brain.router import RouterBrain
from membra_sdk.brain.judge import JudgeBrain
from membra_sdk.brain.synthesizer import SynthesizerBrain
from membra_sdk.scheduler.job_queue import JobQueue, TaskStatus


class BrainServer:
    """Flask-based brain server for distributed MEMBRA workers."""

    def __init__(self, host: str = "0.0.0.0", port: int = 7777):
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.queue = JobQueue()
        self.router = RouterBrain()
        self.judge = JudgeBrain()
        self.synthesizer = SynthesizerBrain()

        # Worker registry
        self.workers: Dict[str, dict] = {}
        self.worker_lock = Lock()

        # Job tracking
        self.jobs: Dict[str, dict] = {}
        self.job_lock = Lock()

        self._register_routes()

    def _register_routes(self):
        """Register all Flask routes."""

        @self.app.route("/health", methods=["GET"])
        def health():
            return jsonify({
                "status": "ok",
                "brain": "membra",
                "workers": len(self.workers),
                "jobs": len(self.jobs),
                "timestamp": time.time(),
            })

        @self.app.route("/register-worker", methods=["POST"])
        def register_worker():
            data = request.get_json() or {}
            worker_id = data.get("worker_id", "")
            role = data.get("role", "general")
            models = data.get("models", [])
            memory_gb = data.get("memory_gb", 16)
            hostname = data.get("hostname", "unknown")

            if not worker_id:
                return jsonify({"error": "worker_id required"}), 400

            with self.worker_lock:
                self.workers[worker_id] = {
                    "worker_id": worker_id,
                    "role": role,
                    "models": models,
                    "memory_gb": memory_gb,
                    "hostname": hostname,
                    "registered_at": time.time(),
                    "last_heartbeat": time.time(),
                    "status": "idle",
                    "current_task": None,
                }

            print(f"[brain] worker registered: {worker_id} role={role}")
            return jsonify({"status": "registered", "worker_id": worker_id})

        @self.app.route("/workers", methods=["GET"])
        def list_workers():
            # Clean stale workers (> 5 min no heartbeat)
            stale_threshold = time.time() - 300
            with self.worker_lock:
                active = {
                    wid: w for wid, w in self.workers.items()
                    if w["last_heartbeat"] > stale_threshold
                }
                self.workers = active
            return jsonify({
                "workers": list(active.values()),
                "count": len(active),
            })

        @self.app.route("/worker/heartbeat", methods=["POST"])
        def worker_heartbeat():
            data = request.get_json() or {}
            worker_id = data.get("worker_id", "")
            status = data.get("status", "idle")
            current_task = data.get("current_task", None)

            with self.worker_lock:
                if worker_id in self.workers:
                    self.workers[worker_id]["last_heartbeat"] = time.time()
                    self.workers[worker_id]["status"] = status
                    self.workers[worker_id]["current_task"] = current_task
                    return jsonify({"status": "ok"})

            return jsonify({"error": "worker not found"}), 404

        @self.app.route("/submit-job", methods=["POST"])
        def submit_job():
            data = request.get_json() or {}
            prompt = data.get("prompt", "")
            job_type = data.get("type", "general")
            buyer_email = data.get("buyer_email", "")

            if not prompt:
                return jsonify({"error": "prompt required"}), 400

            # Route the job
            plan = self.router.plan(prompt)
            job_id = plan["plan_id"]

            # Create tasks from plan subtasks
            tasks = []
            for subtask in plan["subtasks"]:
                task_items = [subtask["description"]]
                task_list = self.queue.submit_job(
                    job_type=subtask["role"],
                    payload={"items": task_items, "description": subtask["description"], "plan": plan},
                    split_strategy="by_item",
                )
                tasks.extend(task_list)

            with self.job_lock:
                self.jobs[job_id] = {
                    "job_id": job_id,
                    "prompt": prompt,
                    "type": job_type,
                    "buyer_email": buyer_email,
                    "plan": plan,
                    "tasks": [t.task_id for t in tasks],
                    "status": "accepted",
                    "created_at": time.time(),
                    "completed_at": None,
                    "results": [],
                    "final_artifact": None,
                }

            # Auto-assign tasks to workers
            self._dispatch_tasks()

            print(f"[brain] job accepted: {job_id} ({len(tasks)} tasks)")
            return jsonify({
                "status": "accepted",
                "job_id": job_id,
                "tasks": len(tasks),
                "plan": plan,
            })

        @self.app.route("/jobs/<job_id>", methods=["GET"])
        def get_job(job_id: str):
            with self.job_lock:
                job = self.jobs.get(job_id)
            if not job:
                return jsonify({"error": "job not found"}), 404

            # Get task statuses
            task_statuses = {}
            for tid in job.get("tasks", []):
                task = self.queue.tasks.get(tid)
                if task:
                    task_statuses[tid] = {
                        "status": task.status.value,
                        "worker": task.assigned_worker,
                        "result_preview": str(task.result)[:200] if task.result else None,
                    }

            return jsonify({
                "job_id": job_id,
                "status": job["status"],
                "prompt": job["prompt"],
                "tasks": task_statuses,
                "results": job.get("results", []),
                "final_artifact": job.get("final_artifact"),
            })

        @self.app.route("/worker/next-task", methods=["GET"])
        def next_task():
            worker_id = request.args.get("worker_id", "")
            capability = request.args.get("capability", "")

            with self.worker_lock:
                if worker_id in self.workers:
                    self.workers[worker_id]["last_heartbeat"] = time.time()

            # Find pending task matching capability
            for task in self.queue.list_pending():
                if not capability or task.task_type == capability:
                    # Claim it
                    claimed = self.queue.claim_task(worker_id, capability)
                    if claimed:
                        with self.worker_lock:
                            if worker_id in self.workers:
                                self.workers[worker_id]["status"] = "busy"
                                self.workers[worker_id]["current_task"] = claimed.task_id
                        return jsonify({
                            "task_id": claimed.task_id,
                            "job_id": claimed.job_id,
                            "task_type": claimed.task_type,
                            "payload": claimed.payload,
                        })

            return jsonify({"task": None})

        @self.app.route("/worker/submit-result", methods=["POST"])
        def submit_result():
            data = request.get_json() or {}
            worker_id = data.get("worker_id", "")
            task_id = data.get("task_id", "")
            result = data.get("result", {})

            success = self.queue.submit_result(task_id, worker_id, result)

            with self.worker_lock:
                if worker_id in self.workers:
                    self.workers[worker_id]["status"] = "idle"
                    self.workers[worker_id]["current_task"] = None

            if success:
                print(f"[brain] {worker_id} completed {task_id[:20]}...")
                # Check if job is complete
                self._check_job_completion(task_id)
                return jsonify({"status": "accepted", "task_id": task_id})

            return jsonify({"error": "task not found or not assigned"}), 400

    def _dispatch_tasks(self):
        """Assign pending tasks to idle workers."""
        pending = self.queue.list_pending()
        with self.worker_lock:
            idle_workers = [
                w for w in self.workers.values()
                if w["status"] == "idle" and w["last_heartbeat"] > time.time() - 300
            ]

        for task in pending:
            for worker in idle_workers:
                if not task.assigned_worker:
                    # Try to claim for this worker
                    claimed = self.queue.claim_task(worker["worker_id"], task.task_type)
                    if claimed:
                        with self.worker_lock:
                            self.workers[worker["worker_id"]]["status"] = "busy"
                            self.workers[worker["worker_id"]]["current_task"] = claimed.task_id
                        break

    def _check_job_completion(self, task_id: str):
        """Check if a job is complete after a task finishes."""
        task = self.queue.tasks.get(task_id)
        if not task:
            return

        job_id = task.job_id
        with self.job_lock:
            job = self.jobs.get(job_id)
            if not job:
                return

            # Check if all tasks done
            status = self.queue.get_job_status(job_id)
            if status.get("done"):
                job["status"] = "completed"
                job["completed_at"] = time.time()

                # Run judge + synthesizer
                self._finalize_job(job_id)

    def _finalize_job(self, job_id: str):
        """Run judge and synthesizer on completed job."""
        with self.job_lock:
            job = self.jobs.get(job_id)
            if not job:
                return

        # Collect outputs
        specialist_outputs = []
        judge_scores = {}
        for tid in job.get("tasks", []):
            task = self.queue.tasks.get(tid)
            if task and task.result:
                specialist_outputs.append({
                    "worker_id": task.assigned_worker or "unknown",
                    "role": task.task_type,
                    "task_id": tid,
                    "result": task.result,
                })
                # Judge score
                judgment = self.judge.score(
                    task.assigned_worker or "unknown",
                    task.task_type,
                    task.result,
                    task.payload.get("description", ""),
                )
                judge_scores[task.assigned_worker or "unknown"] = judgment["overall"]

        # Synthesize
        final = self.synthesizer.synthesize(
            job.get("plan", {}),
            specialist_outputs,
            judge_scores,
        )

        with self.job_lock:
            self.jobs[job_id]["final_artifact"] = final
            self.jobs[job_id]["results"] = specialist_outputs

        print(f"[brain] job finalized: {job_id} artifact={final['artifact_hash'][:16]}...")

    def run(self):
        """Start the Flask server."""
        print(f"[brain] MEMBRA Brain Server starting on {self.host}:{self.port}")
        print(f"[brain] Endpoints:")
        print(f"  GET  http://{self.host}:{self.port}/health")
        print(f"  GET  http://{self.host}:{self.port}/workers")
        print(f"  POST http://{self.host}:{self.port}/register-worker")
        print(f"  POST http://{self.host}:{self.port}/submit-job")
        print(f"  GET  http://{self.host}:{self.port}/jobs/<job_id>")
        print(f"  GET  http://{self.host}:{self.port}/worker/next-task")
        print(f"  POST http://{self.host}:{self.port}/worker/submit-result")
        print(f"[brain] Press Ctrl+C to stop")
        self.app.run(host=self.host, port=self.port, threaded=True)
