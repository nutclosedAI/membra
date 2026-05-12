"""Worker Node — Runs on a Mac to process distributed AI tasks.

A worker node:
  - Registers with the coordinator
  - Reports capabilities (Ollama model, GPU, memory)
  - Claims tasks from the job queue
  - Runs inference/build/analysis locally
  - Returns results + proof hash
  - Earns payment for verified work

Honest limitations:
  - One MacBook is one worker. Cannot combine two Macs into one faster GPU.
  - Network latency between Macs is real. Best for batch jobs, not real-time chat.
  - Each worker needs its own Ollama model loaded (memory duplication).
"""
import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from membra_sdk.scheduler.job_queue import JobQueue, TaskSplit, TaskStatus


@dataclass
class WorkerCapabilities:
    """What this worker can do."""
    worker_id: str
    hostname: str
    models: List[str]            # e.g. ["llama3.1:8b", "llama3.1:70b"]
    memory_gb: float
    cpu_cores: int
    has_gpu: bool = False
    max_concurrent: int = 1
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)


class WorkerNode:
    """A MEMBRA worker that runs on a local Mac."""

    def __init__(self, worker_id: str = None, coordinator_url: str = None, queue: JobQueue = None):
        self.worker_id = worker_id or f"worker-{os.uname().nodename}-{int(time.time())}"
        self.coordinator_url = coordinator_url or "http://localhost:5000"
        self.queue = queue or JobQueue()  # Share queue with coordinator if provided
        self.capabilities = self._detect_capabilities()
        self.current_task: Optional[TaskSplit] = None
        self.stats = {
            "tasks_claimed": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_earnings": 0.0,
        }

    def _detect_capabilities(self) -> WorkerCapabilities:
        """Auto-detect what this machine can do."""
        hostname = os.uname().nodename

        # Check available Ollama models
        models = []
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n")[1:]:  # Skip header
                    parts = line.split()
                    if parts:
                        models.append(parts[0])
        except FileNotFoundError:
            pass  # Ollama not installed
        except Exception:
            pass

        # Memory
        memory_gb = 16.0  # Default guess
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                bytes_mem = int(result.stdout.strip())
                memory_gb = bytes_mem / (1024 ** 3)
        except Exception:
            pass

        # CPU cores
        cpu_cores = os.cpu_count() or 8

        # GPU check (Apple Silicon has Metal)
        has_gpu = False
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and "Metal" in result.stdout:
                has_gpu = True
        except Exception:
            pass

        return WorkerCapabilities(
            worker_id=self.worker_id,
            hostname=hostname,
            models=models or ["ollama-not-installed"],
            memory_gb=round(memory_gb, 1),
            cpu_cores=cpu_cores,
            has_gpu=has_gpu,
            max_concurrent=1,  # Conservative: one inference at a time
        )

    def heartbeat(self) -> dict:
        """Send heartbeat to coordinator."""
        self.capabilities.last_heartbeat = time.time()
        return {
            "worker_id": self.worker_id,
            "status": "idle" if self.current_task is None else "busy",
            "capabilities": {
                "models": self.capabilities.models,
                "memory_gb": self.capabilities.memory_gb,
                "cpu_cores": self.capabilities.cpu_cores,
                "has_gpu": self.capabilities.has_gpu,
            },
            "stats": self.stats,
        }

    def claim_and_run(self, capability: str = None) -> Optional[dict]:
        """Claim a task from the queue and execute it."""
        task = self.queue.claim_task(self.worker_id, capability)
        if not task:
            return None

        self.current_task = task
        self.stats["tasks_claimed"] += 1

        # Run the task locally
        result = self._execute_task(task)

        # Submit result back to queue
        success = self.queue.submit_result(task.task_id, self.worker_id, result)

        if success:
            self.stats["tasks_completed"] += 1
            # Estimate earning
            self.stats["total_earnings"] += task.cost_estimate / 100

        self.current_task = None
        return {
            "task_id": task.task_id,
            "success": success,
            "proof_hash": task.proof_hash,
            "result": result,
        }

    def _execute_task(self, task: TaskSplit) -> dict:
        """Execute a task locally."""
        task_type = task.task_type
        payload = task.payload

        if task_type == "prompt":
            return self._run_prompt(payload)
        elif task_type == "file_analysis":
            return self._run_file_analysis(payload)
        elif task_type == "artifact_gen":
            return self._run_artifact_gen(payload)
        elif task_type == "embedding":
            return self._run_embedding(payload)
        elif task_type == "review":
            return self._run_review(payload)
        else:
            return {"status": "unknown_task_type", "task_type": task_type}

    def _run_prompt(self, payload: dict) -> dict:
        """Run an LLM prompt via Ollama or deterministic fallback."""
        prompt = payload.get("item", payload.get("prompt", ""))
        model = payload.get("model", self.capabilities.models[0] if self.capabilities.models else "llama3.1:8b")

        # Try Ollama
        try:
            result = subprocess.run(
                ["ollama", "run", model, prompt],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                return {
                    "status": "success",
                    "output": result.stdout.strip(),
                    "model": model,
                    "source": "ollama",
                }
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "model": model}
        except Exception as e:
            return {"status": "error", "error": str(e)}

        # Fallback: deterministic hash-based response
        return {
            "status": "fallback",
            "output": f"[Worker {self.worker_id}] Processed prompt (hash: {hashlib.sha256(prompt.encode()).hexdigest()[:16]}...)",
            "model": model,
            "source": "deterministic_fallback",
        }

    def _run_file_analysis(self, payload: dict) -> dict:
        """Analyze a file."""
        fpath = payload.get("file", payload.get("item", ""))
        if not os.path.exists(fpath):
            return {"status": "file_not_found", "path": fpath}

        try:
            with open(fpath, "r", errors="ignore") as f:
                content = f.read()[:5000]
            return {
                "status": "success",
                "path": fpath,
                "size": len(content),
                "hash": hashlib.sha256(content.encode()).hexdigest(),
                "preview": content[:200],
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _run_artifact_gen(self, payload: dict) -> dict:
        """Generate a code artifact."""
        spec = payload.get("spec", {})
        artifact_type = spec.get("type", "python_script")

        # Generate simple artifact
        code = f"""# Generated by worker {self.worker_id}
# Task: {payload.get('description', 'artifact')}

def generated_function():
    return "Hello from MEMBRA worker"
"""
        return {
            "status": "success",
            "code": code,
            "type": artifact_type,
            "hash": hashlib.sha256(code.encode()).hexdigest(),
        }

    def _run_embedding(self, payload: dict) -> dict:
        """Generate embedding (placeholder)."""
        text = payload.get("text", payload.get("item", ""))
        return {
            "status": "success",
            "embedding_dim": 768,
            "text_hash": hashlib.sha256(text.encode()).hexdigest()[:16],
            "note": "Real embedding would use sentence-transformers or Ollama embeddings",
        }

    def _run_review(self, payload: dict) -> dict:
        """Review code (placeholder)."""
        code = payload.get("code", "")
        return {
            "status": "success",
            "issues_found": 0,
            "suggestions": ["Add docstrings", "Add type hints"],
            "code_hash": hashlib.sha256(code.encode()).hexdigest()[:16],
        }

    def get_status(self) -> dict:
        return {
            "worker_id": self.worker_id,
            "hostname": self.capabilities.hostname,
            "capabilities": {
                "models": self.capabilities.models,
                "memory_gb": self.capabilities.memory_gb,
                "cpu_cores": self.capabilities.cpu_cores,
                "has_gpu": self.capabilities.has_gpu,
            },
            "current_task": self.current_task.task_id if self.current_task else None,
            "stats": self.stats,
        }
