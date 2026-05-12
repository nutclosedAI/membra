#!/usr/bin/env python3
"""
Example: Personal Chain from Prompt to Anchor

Demonstrates the complete flow:
  1. User types a prompt (ClosedAI Chat)
  2. LLM generates a response
  3. LLM generates a buildable artifact
  4. Artifact is hashed and tested
  5. Event is logged to personal chain with consent
  6. Stripe receipt is linked (if payment occurred)
  7. Hash is anchored to Solana devnet

Usage:
    python3 examples/personal_chain_demo.py
"""
import sys
sys.path.insert(0, "/Users/alep/Downloads/membra-sdk")

from membra_sdk.personal_chain.chain import PersonalChain, PrivacyLabel
from membra_sdk.personal_chain.events import EventType
from membra_sdk.kyi.notary import KYINotary


def main():
    print("=" * 70)
    print("  CLOSED AI + MEMBRA — Personal Chain Demo")
    print("  Prompt → Artifact → Hash → Chain → Anchor")
    print("=" * 70)
    print()

    # Initialize user's personal chain
    user_id = "user-demo-001"
    print(f"[INIT] Creating personal chain for {user_id}...")
    chain = PersonalChain(user_id)

    # User grants consent for builds (prompts stay private)
    chain.update_consent_policy(auto_capture_prompts=False, auto_capture_builds=True)
    print("  Consent: prompts=private, builds=protected")
    print()

    # 1. User types a prompt (ClosedAI Chat)
    print("[1] User types prompt into ClosedAI Chat...")
    prompt = "Create a Python function to compute Fibonacci numbers"
    prompt_event = chain.log_prompt(prompt, llm_model="gpt-4")
    if prompt_event:
        print(f"  Prompt logged: {prompt_event.event_id}")
        print(f"  Privacy: {prompt_event.privacy.value} (never leaves local machine)")
    print()

    # 2. LLM generates a response
    print("[2] LLM generates response...")
    response = """
def fibonacci(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
"""
    response_event = chain.log_llm_response(response, prompt_event_id=prompt_event.event_id if prompt_event else None)
    if response_event:
        print(f"  Response logged: {response_event.event_id}")
    print()

    # 3. LLM generates a buildable artifact
    print("[3] Artifact generated from response...")
    artifact_content = response.strip()
    artifact_event = chain.log_artifact("/tmp/fibonacci.py", artifact_content, "python_function")
    if artifact_event:
        print(f"  Artifact logged: {artifact_event.event_id}")
        print(f"  Content hash: {artifact_event.metadata.get('content_hash', 'N/A')[:16]}...")
        print(f"  Privacy: {artifact_event.privacy.value} (encrypted, shared with consent)")
    print()

    # 4. Build/test event
    print("[4] Running tests on artifact...")
    build_event = chain.log_build(
        success=True,
        build_log="pytest passed: test_fibonacci.py::test_fibonacci PASSED",
        artifact_hashes=[artifact_event.metadata.get("content_hash")] if artifact_event else [],
    )
    if build_event:
        print(f"  Build logged: {build_event.event_id}")
        print(f"  Status: {'PASS' if build_event.event_type == EventType.BUILD_SUCCESS else 'FAIL'}")
    print()

    # 5. KYI Notary review (for high-value events)
    print("[5] KYI Notary reviews flagged event...")
    notary = KYINotary()
    attestation = notary.request_attestation(user_id, method="email")
    notary.verify_attestation(attestation.attestation_id, verifier_notes="Email verified via OTP")
    print(f"  Identity attestation: {attestation.attestation_id}")
    print(f"  Status: {attestation.status}")

    if artifact_event:
        chain.add_notary_attestation(artifact_event.event_id, attestation.attestation_id)
        print(f"  Notary linked to artifact: {artifact_event.event_id}")
    print()

    # 6. Stripe receipt (if buyer paid)
    print("[6] Stripe settlement receipt...")
    stripe_event = chain.log_stripe_receipt({
        "receipt_id": "pi_demo_12345",
        "amount_usd": 5.00,
        "status": "succeeded",
    })
    if stripe_event:
        print(f"  Receipt logged: {stripe_event.event_id}")
        print(f"  Privacy: {stripe_event.privacy.value} (amount public, identity stripped)")
    print()

    # 7. Solana anchor
    print("[7] Anchoring proof hash to Solana devnet...")
    if artifact_event:
        memo = f"CLOSED_AI|ARTIFACT|{artifact_event.data_hash[:16]}|{user_id[:8]}"
        anchor_event = chain.log_solana_anchor(memo, tx_signature="simulated_tx_12345")
        if anchor_event:
            print(f"  Anchor logged: {anchor_event.event_id}")
            print(f"  Memo: {memo}")
            print(f"  TX: {anchor_event.solana_anchor}")
            print(f"  Privacy: {anchor_event.privacy.value} (public by design)")
    print()

    # Chain summary
    print("=" * 70)
    print("  PERSONAL CHAIN SUMMARY")
    print("=" * 70)
    summary = chain.get_chain_summary()
    print(f"  User: {summary['user_id']}")
    print(f"  Total events: {summary['events']}")
    print(f"  Latest sequence: {summary['latest_sequence']}")
    print(f"  Privacy breakdown:")
    for label, count in summary['privacy_breakdown'].items():
        print(f"    {label}: {count}")
    print(f"  Chain integrity: {'VERIFIED' if chain.verify_chain_integrity() else 'BROKEN'}")
    print()

    # Export public proofs
    print("  Public proofs (hashes only, no raw data):")
    public = chain.export_public_proofs()
    for proof in public:
        print(f"    {proof['event_type']} | seq={proof['sequence']} | hash={proof['data_hash'][:16]}...")
    print()

    print("=" * 70)
    print("  DEMO COMPLETE")
    print("=" * 70)
    print()
    print("  The personal chain is not a blockchain of the person.")
    print("  It is a blockchain of the person's consented proof events.")
    print("  Raw files stay private. Only hashes and metadata go public.")


if __name__ == "__main__":
    main()
