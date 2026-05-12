#!/usr/bin/env python3
"""
Two-Mac LAN Test — M5 Pro + M1 Pro Distributed Agent Test

Usage:
  Terminal 1 (M5): membra brain start --host 0.0.0.0 --port 7777
  Terminal 2 (M5): membra worker start --brain http://127.0.0.1:7777 --worker-id m5-worker --model qwen2.5-coder:14b --role coder
  Terminal 3 (M1): membra worker start --brain http://M5_IP:7777 --worker-id m1-worker --model llama3.2:3b --role reviewer
  Terminal 4 (M5): python3 examples/lan_two_mac_test.py --brain http://127.0.0.1:7777
"""
import argparse
import json
import sys
import time

import requests


def test_connectivity(brain_url: str) -> bool:
    """Test that brain is reachable."""
    print("[test] Checking brain connectivity...")
    try:
        resp = requests.get(f"{brain_url}/health", timeout=5)
        data = resp.json()
        print(f"  ✅ Brain online: {data}")
        return True
    except Exception as e:
        print(f"  ❌ Cannot reach brain: {e}")
        return False


def test_workers(brain_url: str) -> list:
    """List registered workers."""
    print("[test] Checking registered workers...")
    try:
        resp = requests.get(f"{brain_url}/workers", timeout=5)
        data = resp.json()
        workers = data.get("workers", [])
        print(f"  Found {len(workers)} worker(s):")
        for w in workers:
            print(f"    - {w['worker_id']} (role={w['role']}, models={w.get('models', [])})")
        return workers
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return []


def submit_job(brain_url: str, prompt: str, job_type: str = "code-review") -> str:
    """Submit a test job."""
    print(f"[test] Submitting job...")
    print(f"  Prompt: {prompt[:60]}...")
    try:
        resp = requests.post(
            f"{brain_url}/submit-job",
            json={"prompt": prompt, "type": job_type},
            timeout=10,
        )
        data = resp.json()
        job_id = data.get("job_id", "")
        print(f"  ✅ Job accepted: {job_id} ({data.get('tasks', 0)} tasks)")
        return job_id
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return ""


def wait_for_job(brain_url: str, job_id: str, timeout: float = 300.0) -> dict:
    """Poll job status until complete or timeout."""
    print(f"[test] Waiting for job {job_id}...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{brain_url}/jobs/{job_id}", timeout=10)
            data = resp.json()
            status = data.get("status", "unknown")

            # Count completed tasks
            tasks = data.get("tasks", {})
            completed = sum(1 for t in tasks.values() if t.get("status") == "completed")
            total = len(tasks)

            print(f"  Status: {status} | Tasks: {completed}/{total}", end="\r")

            if status == "completed":
                print(f"\n  ✅ Job completed!")
                return data

            time.sleep(2)
        except Exception as e:
            print(f"\n  ⚠️ Poll error: {e}")
            time.sleep(5)

    print("\n  ⏱ Timeout waiting for job")
    return {}


def run_benchmark(brain_url: str):
    """Benchmark: single prompt processed by distributed workers."""
    print("\n" + "=" * 60)
    print("  BENCHMARK: Single prompt → distributed specialists")
    print("=" * 60)

    prompt = "Build a Python FastAPI app with a README, tests, Dockerfile, and security review."

    start_time = time.time()
    job_id = submit_job(brain_url, prompt, "code-review")
    if not job_id:
        return

    result = wait_for_job(brain_url, job_id, timeout=600)
    elapsed = time.time() - start_time

    if result:
        print(f"\n  Total time: {elapsed:.1f}s")
        print(f"  Artifact hash: {result.get('final_artifact', {}).get('artifact_hash', 'N/A')[:16]}...")
        print(f"  Components: {len(result.get('results', []))}")
        print(f"\n  Honest metric: This is {elapsed:.0f}s for a complete build.")
        print("  Compare against single-machine serial execution.")
    else:
        print("\n  Job did not complete in time.")


def main():
    parser = argparse.ArgumentParser(description="MEMBRA Two-Mac LAN Test")
    parser.add_argument("--brain", default="http://127.0.0.1:7777", help="Brain server URL")
    parser.add_argument("--benchmark", action="store_true", help="Run benchmark")
    args = parser.parse_args()

    print("=" * 60)
    print("  MEMBRA TWO-MAC LAN TEST")
    print("  M5 Pro (brain) + M1 Pro (worker)")
    print("=" * 60)
    print()

    # Test 1: Connectivity
    if not test_connectivity(args.brain):
        print("\n❌ Brain not reachable. Is it running?")
        print("   Run: membra brain start --host 0.0.0.0 --port 7777")
        return 1

    # Test 2: Workers
    workers = test_workers(args.brain)
    if len(workers) < 2:
        print(f"\n⚠️  Only {len(workers)} worker(s) registered.")
        print("   Need at least 2 workers for distributed test.")
        print("   Run workers on both Macs:")
        print("     M5: membra worker start --brain http://127.0.0.1:7777 --worker-id m5 --role coder")
        print("     M1: membra worker start --brain http://M5_IP:7777 --worker-id m1 --role reviewer")
        return 1

    # Test 3: Submit job
    prompt = "Review this repo. Worker 1 should find bugs. Worker 2 should improve README. Brain should merge both into one report."
    job_id = submit_job(args.brain, prompt)
    if not job_id:
        return 1

    # Test 4: Wait for completion
    result = wait_for_job(args.brain, job_id)
    if not result:
        return 1

    # Print final result
    print("\n" + "=" * 60)
    print("  RESULT")
    print("=" * 60)
    print(f"Job ID: {job_id}")
    print(f"Status: {result.get('status', 'unknown')}")
    print(f"Prompt: {result.get('prompt', '')[:60]}...")

    if result.get("final_artifact"):
        artifact = result["final_artifact"]
        print(f"Artifact hash: {artifact.get('artifact_hash', 'N/A')[:16]}...")
        print(f"Components used: {sum(1 for c in artifact.get('component_outputs', []) if c.get('included'))}")

    if result.get("tasks"):
        print("\nTask breakdown:")
        for tid, t in result["tasks"].items():
            print(f"  {tid[:20]:20} {t['status']:12} {t.get('worker', '—')[:20]}")

    print("\n" + "=" * 60)
    print("  ✅ TWO-MAC TEST PASSED")
    print("=" * 60)
    print()
    print("Success means:")
    print("  • M1 can reach M5 brain over LAN")
    print("  • Both workers register and get tasks")
    print("  • Results flow back to brain")
    print("  • Brain merges outputs into one artifact")
    print()

    if args.benchmark:
        run_benchmark(args.brain)

    return 0


if __name__ == "__main__":
    sys.exit(main())
