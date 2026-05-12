"""Worker Client — Polls brain server for tasks over LAN, executes locally, returns results.

Usage:
    python3 -m membra_sdk.worker_client \
        --brain http://192.168.1.20:7777 \
        --worker-id m1-pro-worker \
        --model llama3.2:3b \
        --role reviewer
"""
import argparse
import json
import sys
import time

import requests

from membra_sdk.worker.worker_node import WorkerNode


class WorkerClient:
    """Client that connects to a remote brain server and polls for tasks."""

    def __init__(self, brain_url: str, worker_id: str, model: str, role: str):
        self.brain_url = brain_url.rstrip("/")
        self.worker_id = worker_id
        self.model = model
        self.role = role
        self.worker = WorkerNode(worker_id=worker_id)
        self.running = True

    def register(self) -> bool:
        """Register with the brain server."""
        try:
            resp = requests.post(
                f"{self.brain_url}/register-worker",
                json={
                    "worker_id": self.worker_id,
                    "role": self.role,
                    "models": [self.model],
                    "memory_gb": self.worker.capabilities.memory_gb,
                    "hostname": self.worker.capabilities.hostname,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                print(f"[worker:{self.worker_id}] Registered with brain at {self.brain_url}")
                return True
            else:
                print(f"[worker:{self.worker_id}] Registration failed: {resp.text}")
                return False
        except Exception as e:
            print(f"[worker:{self.worker_id}] Cannot reach brain: {e}")
            return False

    def heartbeat(self):
        """Send heartbeat to brain."""
        try:
            requests.post(
                f"{self.brain_url}/worker/heartbeat",
                json={
                    "worker_id": self.worker_id,
                    "status": "idle",
                    "current_task": None,
                },
                timeout=5,
            )
        except Exception:
            pass

    def poll_and_work(self):
        """Poll for next task, execute it, submit result."""
        try:
            resp = requests.get(
                f"{self.brain_url}/worker/next-task",
                params={"worker_id": self.worker_id, "capability": self.role},
                timeout=10,
            )
            data = resp.json()
            task = data.get("task")

            if not task:
                return False  # No task available

            task_id = task["task_id"]
            payload = task["payload"]
            print(f"[worker:{self.worker_id}] Claimed task {task_id[:20]}...")

            # Execute the task locally
            result = self._execute_task(payload)

            # Submit result back to brain
            submit_resp = requests.post(
                f"{self.brain_url}/worker/submit-result",
                json={
                    "worker_id": self.worker_id,
                    "task_id": task_id,
                    "result": result,
                },
                timeout=30,
            )

            if submit_resp.status_code == 200:
                print(f"[worker:{self.worker_id}] Submitted result for {task_id[:20]}...")
            else:
                print(f"[worker:{self.worker_id}] Submit failed: {submit_resp.text}")

            return True

        except Exception as e:
            print(f"[worker:{self.worker_id}] Error during poll/work: {e}")
            return False

    def _execute_task(self, payload: dict) -> dict:
        """Execute a task locally using the worker's capabilities."""
        # Build role-specific prompt
        description = payload.get("description", "")
        items = payload.get("items", [])
        prompt_text = items[0] if items else description

        role_prompts = {
            "coder": f"Write code for: {prompt_text}",
            "reviewer": f"Review and improve: {prompt_text}",
            "tester": f"Write tests for: {prompt_text}",
            "docs": f"Write documentation for: {prompt_text}",
            "security": f"Security review of: {prompt_text}",
            "planner": f"Create plan for: {prompt_text}",
            "critic": f"Critique and score: {prompt_text}",
        }

        prompt = role_prompts.get(self.role, f"Task: {prompt_text}")

        return self.worker._run_prompt({
            "prompt": prompt,
            "model": self.model,
        })

    def run(self, poll_interval: float = 2.0):
        """Main loop: register, then poll for tasks forever."""
        if not self.register():
            print(f"[worker:{self.worker_id}] Could not register. Exiting.")
            return 1

        print(f"[worker:{self.worker_id}] Starting poll loop (interval: {poll_interval}s)")
        print(f"[worker:{self.worker_id}] Press Ctrl+C to stop")

        try:
            while self.running:
                worked = self.poll_and_work()
                if not worked:
                    self.heartbeat()
                    time.sleep(poll_interval)
        except KeyboardInterrupt:
            print(f"\n[worker:{self.worker_id}] Stopping.")

        stats = self.worker.get_status()
        print(f"[worker:{self.worker_id}] Stats:")
        print(f"  Tasks claimed: {stats['stats']['tasks_claimed']}")
        print(f"  Tasks completed: {stats['stats']['tasks_completed']}")
        print(f"  Estimated earnings: ${stats['stats']['total_earnings']:.2f}")
        return 0


def main():
    parser = argparse.ArgumentParser(description="MEMBRA Worker Client")
    parser.add_argument("--brain", required=True, help="Brain server URL (e.g., http://192.168.1.20:7777)")
    parser.add_argument("--worker-id", required=True, help="Unique worker ID")
    parser.add_argument("--model", default="llama3.2:3b", help="Ollama model to use")
    parser.add_argument("--role", default="general", help="Worker role (coder, reviewer, tester, docs)")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Poll interval in seconds")
    args = parser.parse_args()

    client = WorkerClient(
        brain_url=args.brain,
        worker_id=args.worker_id,
        model=args.model,
        role=args.role,
    )
    return client.run(poll_interval=args.poll_interval)


if __name__ == "__main__":
    sys.exit(main())
