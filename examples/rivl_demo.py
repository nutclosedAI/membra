#!/usr/bin/env python3
"""
RIVL Demo — Reinforcement Inverted Validator Learning

Demonstrates:
  1. Prompt submitted to RIVL Brain
  2. Punishment Memory retrieves past failures
  3. Specialist workers execute with memory warnings
  4. Verifier Stack checks all outputs
  5. Reward Engine scores: +reward for pass, -punishment for fail
  6. Events logged to memory for future learning
  7. Synthesizer merges only verified outputs
  8. Final artifact with reward score and provenance

Usage:
    python3 examples/rivl_demo.py

Then check:
    cat ~/.membra/reward_events.jsonl
"""
import sys
sys.path.insert(0, "/Users/alep/Downloads/membra-sdk")

from membra_sdk.rivl.rivl_brain import RIVLBrain
from membra_sdk.worker.worker_node import WorkerNode


def main():
    print("=" * 70)
    print("  MEMBRA RIVL — Reinforcement Inverted Validator Learning")
    print("  Verifier-first. Punishment is evidence. Reward is proof.")
    print("=" * 70)
    print()

    brain = RIVLBrain()

    # Register workers
    brain.register_worker(WorkerNode(worker_id="mac-planner"), role="planner")
    brain.register_worker(WorkerNode(worker_id="mac-coder"), role="coder")
    brain.register_worker(WorkerNode(worker_id="mac-security"), role="security")
    brain.register_worker(WorkerNode(worker_id="mac-tester"), role="tester")
    brain.register_worker(WorkerNode(worker_id="mac-docs"), role="docs")

    print("Workers registered:")
    for wid, w in brain.workers.items():
        print(f"  {wid} → {getattr(w, 'specialist_role', 'general')}")
    print()

    # Run two prompts — one good, one with security issues
    prompts = [
        "Build a Python function to calculate Fibonacci numbers with error handling",
        "Write a script that uses eval() to process user input and stores API keys in code",
    ]

    for prompt in prompts:
        print("-" * 70)
        print(f"PROMPT: {prompt}")
        print("-" * 70)

        result = brain.process(prompt)

        rivl = result.get("rivl", {})
        print()
        print(f"Artifact Hash: {result.get('artifact_hash', 'N/A')[:16]}...")
        print(f"Total Reward: {rivl.get('total_reward', 0):.0f}")
        print(f"Verification: {'PASS' if rivl.get('overall_passed') else 'FAIL'}")

        events = rivl.get("reward_events", [])
        if events:
            print("\nReward Events:")
            for e in events:
                verdict = "✅" if e.get("verdict") == "accepted" else "❌"
                print(f"  {verdict} {e.get('reason', '')}: reward={e.get('reward', 0):.0f}")

        print()

    # Show stats
    print("=" * 70)
    print("  RIVL STATISTICS")
    print("=" * 70)
    stats = brain.get_stats()
    reward_stats = stats["reward_engine"]
    print(f"Total Events: {reward_stats.get('total_events', 0)}")
    print(f"Accepted: {reward_stats.get('accepted', 0)}")
    print(f"Punished: {reward_stats.get('punished', 0)}")
    print(f"Accept Rate: {reward_stats.get('accept_rate', 0):.1%}")
    print(f"Avg Reward: {reward_stats.get('avg_reward', 0):.1f}")
    print(f"Max Reward: {reward_stats.get('max_reward', 0):.0f}")
    print(f"Min Reward: {reward_stats.get('min_reward', 0):.0f}")
    print()

    print("Memory file:")
    print("  ~/.membra/reward_events.jsonl")
    print()

    print("=" * 70)
    print("  RIVL DOCTRINE")
    print("=" * 70)
    print("  Punishment is not violence. Punishment is negative evidence.")
    print("  Reward is not fantasy profit. Reward is verified success.")
    print("  Yield is not model confidence. Yield is settled external value.")


if __name__ == "__main__":
    main()
