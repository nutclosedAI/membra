#!/usr/bin/env python3
"""
MEMBRA MoA Brain Demo — Single brain, multiple specialist agents.

Demonstrates:
  1. Router Brain decomposes prompt into subtasks
  2. Specialist workers execute in parallel (coder, security, tester, docs)
  3. Judge Brain scores outputs (safety, completeness, style)
  4. Synthesizer Brain merges best results
  5. Final artifact with hash + provenance

Usage:
    python3 examples/moa_brain_demo.py

Honest: This runs all workers on one machine for demo.
Real deployment: Each worker on a separate Mac.
"""
import sys
sys.path.insert(0, "/Users/alep/Downloads/membra-sdk")

from membra_sdk.brain.moa_orchestrator import MoAOrchestrator
from membra_sdk.brain.router import RouterBrain
from membra_sdk.worker.worker_node import WorkerNode
from membra_sdk.memory.shared_memory import SharedMemory, ArtifactStore


def main():
    print("=" * 70)
    print("  MEMBRA MoA BRAIN — Mixture of Agents Demo")
    print("  One brain. Many specialists. One answer.")
    print("=" * 70)
    print()

    # Initialize shared memory
    memory = SharedMemory()
    store = ArtifactStore()
    print("[INIT] Shared memory and artifact store ready")
    print()

    # Create orchestrator
    moa = MoAOrchestrator()

    # Register specialist workers
    # In real deployment, each runs on a different Mac
    planner = WorkerNode(worker_id="mac-planner")
    coder = WorkerNode(worker_id="mac-coder")
    security = WorkerNode(worker_id="mac-security")
    tester = WorkerNode(worker_id="mac-tester")
    docs = WorkerNode(worker_id="mac-docs")

    moa.register_worker(planner, role="planner")
    moa.register_worker(coder, role="coder")
    moa.register_worker(security, role="security")
    moa.register_worker(tester, role="tester")
    moa.register_worker(docs, role="docs")

    print("[WORKERS] Registered 5 specialist agents:")
    for wid, w in moa.workers.items():
        role = getattr(w, 'specialist_role', 'general')
        models = w.capabilities.models[:2]  # Show first 2
        print(f"  {wid} → {role} (models: {models})")
    print()

    # Example prompt
    prompt = "Build a Python function to calculate Fibonacci numbers with error handling, then write tests and README"

    print(f"[PROMPT] {prompt}")
    print()

    # Process through MoA pipeline
    result = moa.process(prompt)

    print()
    print("=" * 70)
    print("  RESULT")
    print("=" * 70)
    print()
    print(f"Artifact Hash: {result['artifact_hash']}")
    print(f"Artifact Type: {result['artifact_type']}")
    print(f"Components Used: {sum(1 for c in result['component_outputs'] if c['included'])}/{len(result['component_outputs'])}")
    print()

    print("Judge Scores:")
    for worker_id, score in result['judge_summary']['scores'].items():
        print(f"  {worker_id}: {score:.2f}")
    print(f"  Threshold: {result['judge_summary']['threshold']}")
    print(f"  Passed: {result['judge_summary']['passed']}/{result['judge_summary']['total']}")
    print()

    print("Consensus:")
    consensus = result.get('consensus', {})
    print(f"  Agreement: {consensus.get('agreement', 0):.2f}")
    print(f"  Reached: {'YES' if consensus.get('consensus_reached') else 'NO'}")
    print()

    print("Artifact Preview:")
    artifact = result.get('final_artifact', '')
    if len(artifact) > 500:
        print(f"  {artifact[:500]}...")
    else:
        print(f"  {artifact}")
    print()

    # Store in artifact store
    job_id = result.get('plan_id', 'demo')
    store.store(job_id, "artifact.py", artifact)
    hash_from_store = store.store(job_id, "report.json", str(result))
    print(f"[STORE] Artifacts stored at: ~/.membra/artifacts/{job_id}/")
    print(f"[STORE] Manifest hash: {hash_from_store[:16]}...")
    print()

    # Memory stats
    stats = memory.get_stats()
    print("[MEMORY] Shared memory stats:")
    print(f"  Memories stored: {stats['total_memories']}")
    print(f"  Tasks logged: {stats['total_tasks_logged']}")
    print(f"  Workers tracked: {stats['total_workers']}")
    print()

    print("=" * 70)
    print("  MoA BRAIN DEMO COMPLETE")
    print("=" * 70)
    print()
    print("What just happened:")
    print("  1. Router decomposed 'Fibonacci function' into 4 subtasks")
    print("  2. Coder wrote the function")
    print("  3. Security checked for unsafe patterns")
    print("  4. Tester wrote tests")
    print("  5. Docs wrote README")
    print("  6. Judge scored each output")
    print("  7. Synthesizer merged best parts into final artifact")
    print("  8. Consensus hash proves all agents agreed")
    print()
    print("Real deployment: Each specialist runs on a different Mac.")
    print("Shared memory keeps them coordinated.")


if __name__ == "__main__":
    main()
