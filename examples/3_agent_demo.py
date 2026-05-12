#!/usr/bin/env python3
"""
Example: 3-Agent Proof-of-Yield Consensus Demo

This demonstrates how multiple Membra validator agents reach consensus
by agreeing on both inference hashes AND yield estimates.

Usage:
    python3 examples/3_agent_demo.py
"""
import sys
sys.path.insert(0, "/Users/alep/Downloads/membra-sdk")

from membra_sdk.consensus.poy import ProofOfYieldConsensus, PoYVote


def demo():
    print("=" * 70)
    print("  EXAMPLE: 3-Agent Proof-of-Yield Consensus")
    print("  Agents must agree on BOTH inference hash AND yield hash")
    print("=" * 70)
    print()

    # Create 3 agents
    agents = [
        ProofOfYieldConsensus("agent-alpha"),
        ProofOfYieldConsensus("agent-beta"),
        ProofOfYieldConsensus("agent-gamma"),
    ]

    # Batch of operations
    batch = [
        {"file": "contract.sol", "yield_estimate": 0.08},
        {"file": "bridge.rs", "yield_estimate": 0.05},
        {"file": "network.go", "yield_estimate": 0.04},
    ]

    state_root = "0xabc123def456789"
    total_yield = sum(op["yield_estimate"] for op in batch)

    print(f"Batch: {len(batch)} operations")
    print(f"Total yield estimate: {total_yield:.4f}")
    print()

    # Each agent casts a vote
    print("  [PHASE 1] Agents run inference and cast votes...")
    votes = []
    for agent in agents:
        vote = agent.cast_vote(state_root, batch, total_yield)
        votes.append(vote)
        print(f"    {agent.agent_id}: inf_hash={vote.inference_hash[:12]}... yield_hash={vote.yield_hash[:12]}...")

    # Share votes between all agents
    print()
    print("  [PHASE 2] Gossiping votes...")
    for agent in agents:
        for vote in votes:
            agent.add_external_vote(vote)
        print(f"    {agent.agent_id} received {len(votes)} votes")

    # Check consensus
    print()
    print("  [PHASE 3] Checking consensus...")
    result = agents[0].get_round(state_root)

    if result.finalized:
        print(f"    ✅ CONSENSUS REACHED")
        print(f"       Votes: {len(result.votes)}")
        print(f"       Inference agreement: 2/3+")
        print(f"       Yield agreement: 2/3+")
    else:
        print(f"    ❌ No consensus (not enough matching votes)")

    print()
    print("=" * 70)
    print("  This proves: 2/3 agreement on BOTH dimensions finalizes batch.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
