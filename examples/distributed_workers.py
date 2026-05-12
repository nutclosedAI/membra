#!/usr/bin/env python3
"""
Example: Distributed MEMBRA Workers — Mac A + Mac B + Coordinator

Demonstrates honest job parallelism across two machines:
  - Mac A runs worker A (Ollama + task processor)
  - Mac B runs worker B (Ollama + task processor)
  - Coordinator splits a batch of prompts into independent tasks
  - Each worker claims tasks, runs locally, returns results + proof hash
  - Coordinator verifies hashes, runs consensus, queues payments

HONEST LIMITATION:
  This is JOB PARALLELISM (many independent tasks), NOT MODEL PARALLELISM.
  Two MacBooks cannot merge into one faster GPU for a single prompt.
  They CAN process 2x as many prompts per minute as one MacBook.

Usage:
  Terminal 1 (coordinator):
    python3 examples/distributed_workers.py coordinator

  Terminal 2 (Mac A worker):
    python3 examples/distributed_workers.py worker --id mac-a --capability prompt

  Terminal 3 (Mac B worker):
    python3 examples/distributed_workers.py worker --id mac-b --capability prompt
"""
import argparse
import sys
import time

sys.path.insert(0, "/Users/alep/Downloads/membra-sdk")

from membra_sdk.coordinator.coordinator import Coordinator
from membra_sdk.worker.worker_node import WorkerNode


def demo_coordinator():
    print("=" * 70)
    print("  MEMBRA DISTRIBUTED COORDINATOR")
    print("  Honest job parallelism: more total jobs/min, not one faster answer")
    print("=" * 70)
    print()

    coord = Coordinator()

    # Simulate registering two workers (share coordinator's queue)
    worker_a = WorkerNode(worker_id="mac-a", queue=coord.queue)
    worker_b = WorkerNode(worker_id="mac-b", queue=coord.queue)
    coord.register_worker(worker_a)
    coord.register_worker(worker_b)
    print("Workers registered:")
    print(f"  Mac A: {worker_a.capabilities.models}, {worker_a.capabilities.memory_gb}GB")
    print(f"  Mac B: {worker_b.capabilities.models}, {worker_b.capabilities.memory_gb}GB")
    print()

    # Submit a batch of 6 prompts
    prompts = [
        "Summarize quantum computing in one sentence",
        "Explain Rust ownership in simple terms",
        "Write a Python function to reverse a string",
        "Describe Solana proof of history",
        "Generate a Dockerfile for a Python app",
        "Explain what a Merkle tree is",
    ]

    print(f"[JOB] Submitting batch of {len(prompts)} prompts...")
    job_id = coord.submit_job(
        job_type="prompt",
        payload={"items": prompts, "description": "Batch prompt processing"},
        split_strategy="by_item",
    )
    print(f"  Job ID: {job_id}")
    print()

    # Simulate workers running tasks (in real usage, each worker runs on its own machine)
    print("[WORKERS] Simulating distributed execution...")
    for worker in [worker_a, worker_b]:
        while True:
            result = worker.claim_and_run("prompt")
            if not result:
                break
            print(f"  {worker.worker_id} completed: {result['task_id'][:20]}... proof={result['proof_hash'][:12]}...")

    print()

    # Coordinator collects and verifies
    print("[COORDINATOR] Collecting and verifying results...")
    final = coord.collect_results(job_id)
    print(f"  Job status: {final['status']}")
    print(f"  Tasks: {final['total_tasks']}")
    print(f"  Verified: {final['verified']}")
    print(f"  Payments ready: {final['payments_ready']}")
    print()

    # Distribute payments
    if final['payments_ready'] > 0:
        payments = coord.distribute_payments()
        total_paid = sum(p['amount_usd'] for p in payments)
        print("[PAYMENT] Distributed:")
        for p in payments[:5]:  # Show first 5
            print(f"  {p['worker_id']}: ${p['amount_usd']:.2f} → {p['status']}")
        print(f"  Total simulated payout: ${total_paid:.2f}")
        print("  ⚠️  Real payout requires Stripe Connect + verified work + external funding")

    print()
    print("=" * 70)
    print("  DISTRIBUTED DEMO COMPLETE")
    print("=" * 70)
    print()
    print("Honest throughput comparison:")
    print("  1 MacBook: ~6 prompts / 60s = 1 prompt/10s (serial)")
    print("  2 MacBooks: ~6 prompts / 30s = 1 prompt/5s (parallel)")
    print("  This is 2x throughput for BATCH jobs, NOT 2x speed per prompt.")


def demo_worker(worker_id: str, capability: str):
    print(f"[{worker_id}] MEMBRA Worker starting...")
    worker = WorkerNode(worker_id=worker_id)
    print(f"  Models: {worker.capabilities.models}")
    print(f"  Memory: {worker.capabilities.memory_gb}GB")
    print(f"  CPUs: {worker.capabilities.cpu_cores}")
    print(f"  GPU: {worker.capabilities.has_gpu}")
    print()
    print(f"  Waiting for tasks from coordinator...")
    print(f"  Capability: {capability}")
    print("  Press Ctrl+C to stop")

    try:
        while True:
            result = worker.claim_and_run(capability)
            if result:
                print(f"  Completed: {result['task_id'][:20]}...")
            else:
                time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n[{worker_id}] Stopped.")
        stats = worker.get_status()
        print(f"  Tasks claimed: {stats['stats']['tasks_claimed']}")
        print(f"  Tasks completed: {stats['stats']['tasks_completed']}")
        print(f"  Estimated earnings: ${stats['stats']['total_earnings']:.2f}")


def main():
    parser = argparse.ArgumentParser(description="MEMBRA Distributed Workers")
    parser.add_argument("role", choices=["coordinator", "worker"],
                        help="Run as coordinator or worker")
    parser.add_argument("--id", default="worker-1", help="Worker ID")
    parser.add_argument("--capability", default="prompt",
                        help="Task capability this worker accepts")
    args = parser.parse_args()

    if args.role == "coordinator":
        demo_coordinator()
    else:
        demo_worker(args.id, args.capability)


if __name__ == "__main__":
    main()
