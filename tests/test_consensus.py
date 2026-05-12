#!/usr/bin/env python3
"""Test suite for Membra Proof-of-Yield consensus."""
import asyncio
import hashlib
import json
import sys

sys.path.insert(0, "/Users/alep/Downloads/membra-sdk")

from membra_sdk.consensus.poy import ProofOfYieldConsensus, PoYVote


def test_single_agent_no_consensus():
    """One agent alone cannot reach consensus."""
    c = ProofOfYieldConsensus("agent-1")
    vote = c.cast_vote("root-abc", [{"file": "x"}], 1.0)
    c.add_external_vote(vote)
    r = c.get_round("root-abc")
    assert not r.finalized, "Single agent should not finalize"
    print("✅ Single agent correctly does not finalize")


def test_two_agents_no_consensus():
    """Two agents still not enough (need 3+)."""
    c = ProofOfYieldConsensus("agent-1")
    for i in range(2):
        vote = PoYVote(
            agent_id=f"agent-{i}",
            state_root="root-abc",
            inference_hash="hash-same",
            yield_hash="yield-same",
            total_yield=1.0,
            confidence=0.95,
            timestamp=0.0,
        )
        c.add_external_vote(vote)
    r = c.get_round("root-abc")
    assert not r.finalized, "Two agents should not finalize"
    print("✅ Two agents correctly do not finalize")


def test_three_agents_consensus():
    """Three agreeing agents reach consensus."""
    c = ProofOfYieldConsensus("agent-1")
    for i in range(3):
        vote = PoYVote(
            agent_id=f"agent-{i}",
            state_root="root-abc",
            inference_hash="hash-same",
            yield_hash="yield-same",
            total_yield=1.0,
            confidence=0.95,
            timestamp=0.0,
        )
        c.add_external_vote(vote)
    r = c.get_round("root-abc")
    assert r.finalized, "Three agreeing agents should finalize"
    print("✅ Three agreeing agents reach consensus")


def test_three_agents_disagree():
    """Three agents with mismatching hashes do NOT reach consensus."""
    c = ProofOfYieldConsensus("agent-1")
    for i in range(3):
        vote = PoYVote(
            agent_id=f"agent-{i}",
            state_root="root-abc",
            inference_hash=f"hash-{i}",  # All different
            yield_hash=f"yield-{i}",
            total_yield=1.0,
            confidence=0.95,
            timestamp=0.0,
        )
        c.add_external_vote(vote)
    r = c.get_round("root-abc")
    assert not r.finalized, "Disagreeing agents should not finalize"
    print("✅ Disagreeing agents correctly do not finalize")


def test_two_of_three_consensus():
    """Two agree, one disagrees — 2/3 consensus reached."""
    c = ProofOfYieldConsensus("agent-1")

    # Agent 1 and 2 agree
    for i in range(2):
        vote = PoYVote(
            agent_id=f"agent-{i}",
            state_root="root-abc",
            inference_hash="hash-agree",
            yield_hash="yield-agree",
            total_yield=1.0,
            confidence=0.95,
            timestamp=0.0,
        )
        c.add_external_vote(vote)

    # Agent 3 disagrees
    vote = PoYVote(
        agent_id="agent-2",
        state_root="root-abc",
        inference_hash="hash-disagree",
        yield_hash="yield-disagree",
        total_yield=1.0,
        confidence=0.30,
        timestamp=0.0,
    )
    c.add_external_vote(vote)

    r = c.get_round("root-abc")
    assert r.finalized, "2/3 agreement should finalize"
    print("✅ 2/3 agreement reaches consensus")


def test_yield_dimension_matters():
    """Inference agrees but yield disagrees — NO consensus."""
    c = ProofOfYieldConsensus("agent-1")
    for i in range(3):
        vote = PoYVote(
            agent_id=f"agent-{i}",
            state_root="root-abc",
            inference_hash="hash-same",  # All agree on inference
            yield_hash=f"yield-{i}",      # But yield differs
            total_yield=1.0,
            confidence=0.95,
            timestamp=0.0,
        )
        c.add_external_vote(vote)
    r = c.get_round("root-abc")
    assert not r.finalized, "Yield disagreement should block consensus"
    print("✅ Yield disagreement correctly blocks consensus")


if __name__ == "__main__":
    print("=" * 60)
    print("  MEMBRA PROOF-OF-YIELD CONSENSUS TESTS")
    print("=" * 60)
    print()

    test_single_agent_no_consensus()
    test_two_agents_no_consensus()
    test_three_agents_consensus()
    test_three_agents_disagree()
    test_two_of_three_consensus()
    test_yield_dimension_matters()

    print()
    print("=" * 60)
    print("  ALL TESTS PASSED")
    print("=" * 60)
