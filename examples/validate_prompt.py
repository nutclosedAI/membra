#!/usr/bin/env python3
"""
Example: Validate Prompt via LLM

Runs LLM inference on a prompt and hashes the output.
The hash becomes a consensus vote.

Usage:
    python3 examples/validate_prompt.py "Analyze this smart contract"
"""
import argparse
import hashlib
import sys

sys.path.insert(0, "/Users/alep/Downloads/membra-sdk")

from membra_sdk.consensus.poy import ProofOfYieldConsensus


def main():
    parser = argparse.ArgumentParser(description="Validate prompt via LLM")
    parser.add_argument("prompt", help="Prompt to validate")
    args = parser.parse_args()

    print("=" * 60)
    print("  MEMBRA LLM VALIDATOR")
    print("  Inference output → hash → consensus vote")
    print("=" * 60)
    print()

    consensus = ProofOfYieldConsensus(agent_id="demo-validator")
    inference = consensus._call_llm(args.prompt)
    inf_hash = hashlib.sha256(inference.encode()).hexdigest()

    print(f"Prompt: {args.prompt}")
    print()
    print(f"Inference: {inference}")
    print()
    print(f"Hash: {inf_hash}")
    print()
    print("  This hash can be used as a PoY consensus vote.")
    print("  See docs/PROOF_OF_YIELD.md for the full doctrine.")


if __name__ == "__main__":
    main()
