"""Event types for the personal chain.

Each event type represents a consented proof event in the user's digital life.
"""
from enum import Enum


class EventType(Enum):
    # Human intent events
    PROMPT = "prompt"                    # User typed a prompt
    UPLOAD = "upload"                    # User uploaded a file
    COMMAND = "command"                  # User ran a terminal command
    SPEECH = "speech"                    # User spoke (voice input)

    # LLM response events
    LLM_RESPONSE = "llm_response"        # LLM generated text
    LLM_ARTIFACT = "llm_artifact"        # LLM generated a file/buildable output
    LLM_TOOL_CALL = "llm_tool_call"      # LLM invoked a tool/function

    # Build events
    BUILD_START = "build_start"          # Build process started
    BUILD_SUCCESS = "build_success"      # Build completed successfully
    BUILD_FAILURE = "build_failure"      # Build failed
    TEST_PASS = "test_pass"              # Tests passed
    TEST_FAIL = "test_fail"              # Tests failed

    # File events
    FILE_SCAN = "file_scan"              # File was scanned/analyzed
    FILE_HASH = "file_hash"              # File hash computed
    FILE_INDEX = "file_index"            # File added to corpus index

    # Identity events
    KYI_ATTEST = "kyi_attest"            # Identity attestation completed
    NOTARY_REVIEW = "notary_review"      # Notary reviewed flagged event
    CONSENT_GRANT = "consent_grant"      # User granted consent for capture
    CONSENT_REVOKE = "consent_revoke"    # User revoked consent

    # Payment events
    STRIPE_RECEIPT = "stripe_receipt"    # Stripe payment receipt
    ESCROW_DEPOSIT = "escrow_deposit"    # Funds deposited to escrow
    ESCROW_RELEASE = "escrow_release"    # Funds released from escrow
    YIELD_DISTRIBUTE = "yield_distribute" # Yield distributed to stakeholders

    # Chain events
    BATCH_FORM = "batch_form"            # Batch of events formed
    BATCH_ROOT = "batch_root"            # Batch root hash computed
    CONSENSUS_VOTE = "consensus_vote"    # Validator cast vote
    CONSENSUS_FINAL = "consensus_final"  # Batch finalized by consensus

    # Anchor events
    SOLANA_ANCHOR = "solana_anchor"      # Hash anchored to Solana
    IPFS_PIN = "ipfs_pin"                # Artifact pinned to IPFS

    # Marketplace events
    JOB_POST = "job_post"                # Job posted to marketplace
    JOB_CLAIM = "job_claim"              # Job claimed by builder
    JOB_DELIVER = "job_deliver"          # Artifact delivered
    JOB_APPROVE = "job_approve"          # Buyer approved delivery

    # System events
    NODE_START = "node_start"            # MEMBRA node started
    NODE_STOP = "node_stop"              # MEMBRA node stopped
    SYNC = "sync"                        # Chain sync occurred
    EXPORT = "export"                    # User exported chain archive
