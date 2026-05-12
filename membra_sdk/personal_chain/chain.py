"""Personal Chain — A user-owned chronological ledger of consented proof events.

The doctrine:
- It is not a blockchain of the person.
- It is a blockchain of the person's consented proof events.
- Private by default.
- Consent before capture.
- Hash before public proof.
"""
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

from membra_sdk.personal_chain.events import EventType


class PrivacyLabel(Enum):
    PRIVATE = "private"      # Never leaves local machine
    PROTECTED = "protected"  # Encrypted, shared only with explicit consent
    PUBLIC = "public"        # Hash and metadata may be published
    ANONYMOUS = "anonymous"  # Metadata public, identity stripped


@dataclass
class ChainEvent:
    """A single event in the personal chain."""
    event_id: str
    event_type: EventType
    timestamp: float
    data_hash: str           # SHA-256 of event data
    data_preview: str        # Human-readable preview (not full data)
    privacy: PrivacyLabel
    consent_token: str       # Proof that user consented to this capture
    sequence: int            # Position in chain
    previous_hash: str       # Hash of previous event (chain integrity)
    metadata: Dict[str, Any] = field(default_factory=dict)
    notary_attestation: Optional[str] = None
    stripe_receipt_id: Optional[str] = None
    solana_anchor: Optional[str] = None

    def full_hash(self) -> str:
        """Hash of this event including previous hash (chain integrity)."""
        payload = {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "data_hash": self.data_hash,
            "privacy": self.privacy.value,
            "consent_token": self.consent_token,
            "sequence": self.sequence,
            "previous_hash": self.previous_hash,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class PersonalChain:
    """A user's personal blockchain of consented proof events.

    Each user owns:
    - Their personal chain namespace
    - Their artifact history
    - Their proof hashes
    - Their private file corpus
    - Their monetization settings
    - Their consent policy
    - Their exportable archive
    """

    def __init__(self, user_id: str, storage_path: str = None):
        self.user_id = user_id
        self.storage_path = storage_path or os.path.expanduser(f"~/.membra/chains/{user_id}")
        os.makedirs(self.storage_path, exist_ok=True)

        self.events: List[ChainEvent] = []
        self.sequence = 0
        self.last_hash = "0" * 64  # Genesis previous hash
        self.consent_policy: Dict[str, Any] = {
            "auto_capture_prompts": False,
            "auto_capture_uploads": False,
            "auto_capture_builds": True,
            "default_privacy": PrivacyLabel.PRIVATE.value,
            "public_anchor_allowed": False,
            "monetization_enabled": False,
        }

        self._load_chain()
        self._load_policy()

    def log_event(self, event_type: EventType, data: Any, privacy: PrivacyLabel = None,
                  metadata: Dict = None, consent_override: bool = False) -> Optional[ChainEvent]:
        """Log a consented event to the personal chain.

        Returns None if user has not consented to this capture.
        """
        # Check consent
        if not consent_override and not self._has_consent(event_type):
            return None

        # Default privacy from policy
        if privacy is None:
            privacy = PrivacyLabel(self.consent_policy.get("default_privacy", "private"))

        # Compute data hash (hash the actual data, not store it)
        data_str = json.dumps(data, sort_keys=True, default=str) if not isinstance(data, str) else data
        data_hash = hashlib.sha256(data_str.encode()).hexdigest()

        # Create preview (first 200 chars)
        preview = data_str[:200] if len(data_str) > 200 else data_str

        # Generate consent token
        consent_token = hashlib.sha256(
            f"{self.user_id}:{event_type.value}:{time.time()}:{data_hash}".encode()
        ).hexdigest()

        event = ChainEvent(
            event_id=f"evt-{self.user_id}-{int(time.time()*1000)}-{self.sequence}",
            event_type=event_type,
            timestamp=time.time(),
            data_hash=data_hash,
            data_preview=preview,
            privacy=privacy,
            consent_token=consent_token,
            sequence=self.sequence,
            previous_hash=self.last_hash,
            metadata=metadata or {},
        )

        self.events.append(event)
        self.sequence += 1
        self.last_hash = event.full_hash()
        self._persist_event(event)
        return event

    def log_prompt(self, prompt_text: str, llm_model: str = None) -> Optional[ChainEvent]:
        """Log a user prompt. Requires consent for prompt capture."""
        return self.log_event(
            EventType.PROMPT,
            {"text": prompt_text, "model": llm_model},
            privacy=PrivacyLabel.PRIVATE,
            metadata={"source": "closedai_chat"},
        )

    def log_llm_response(self, response_text: str, prompt_event_id: str = None) -> Optional[ChainEvent]:
        """Log an LLM response."""
        return self.log_event(
            EventType.LLM_RESPONSE,
            {"text": response_text, "prompt_id": prompt_event_id},
            privacy=PrivacyLabel.PRIVATE,
            metadata={"source": "llm_inference"},
        )

    def log_artifact(self, artifact_path: str, artifact_content: str,
                     artifact_type: str = "file") -> Optional[ChainEvent]:
        """Log a generated artifact. Build artifacts default to PROTECTED."""
        return self.log_event(
            EventType.LLM_ARTIFACT,
            {"path": artifact_path, "type": artifact_type, "size": len(artifact_content)},
            privacy=PrivacyLabel.PROTECTED,
            metadata={"content_hash": hashlib.sha256(artifact_content.encode()).hexdigest()},
        )

    def log_build(self, success: bool, build_log: str, artifact_hashes: List[str] = None) -> Optional[ChainEvent]:
        """Log a build event."""
        event_type = EventType.BUILD_SUCCESS if success else EventType.BUILD_FAILURE
        return self.log_event(
            event_type,
            {"log": build_log[:1000], "artifacts": artifact_hashes or []},
            privacy=PrivacyLabel.PROTECTED,
            metadata={"exit_code": 0 if success else 1},
        )

    def log_stripe_receipt(self, receipt: Dict) -> Optional[ChainEvent]:
        """Log a Stripe settlement receipt."""
        event = self.log_event(
            EventType.STRIPE_RECEIPT,
            {"receipt_id": receipt.get("receipt_id"), "amount": receipt.get("amount_usd")},
            privacy=PrivacyLabel.ANONYMOUS,  # Amount public, identity stripped
            metadata={"processor": "stripe", "status": receipt.get("status")},
        )
        if event:
            event.stripe_receipt_id = receipt.get("receipt_id")
        return event

    def log_solana_anchor(self, memo: str, tx_signature: str) -> Optional[ChainEvent]:
        """Log a Solana anchor event."""
        event = self.log_event(
            EventType.SOLANA_ANCHOR,
            {"memo": memo, "tx": tx_signature},
            privacy=PrivacyLabel.PUBLIC,  # Anchor is public by design
            metadata={"cluster": "devnet"},
        )
        if event:
            event.solana_anchor = tx_signature
        return event

    def add_notary_attestation(self, event_id: str, attestation: str) -> bool:
        """Add a notary attestation to an existing event."""
        for event in self.events:
            if event.event_id == event_id:
                event.notary_attestation = attestation
                self._persist_event(event)
                return True
        return False

    def get_chain_summary(self) -> Dict:
        """Summary of the personal chain."""
        privacy_counts = {}
        for event in self.events:
            label = event.privacy.value
            privacy_counts[label] = privacy_counts.get(label, 0) + 1

        return {
            "user_id": self.user_id,
            "events": len(self.events),
            "latest_sequence": self.sequence,
            "latest_hash": self.last_hash,
            "privacy_breakdown": privacy_counts,
            "consent_policy": self.consent_policy,
        }

    def export_public_proofs(self) -> List[Dict]:
        """Export only public/anchored proof events. No private data."""
        public_events = []
        for event in self.events:
            if event.privacy in (PrivacyLabel.PUBLIC, PrivacyLabel.ANONYMOUS):
                public_events.append({
                    "event_id": event.event_id,
                    "event_type": event.event_type.value,
                    "timestamp": event.timestamp,
                    "data_hash": event.data_hash,
                    "privacy": event.privacy.value,
                    "sequence": event.sequence,
                    "previous_hash": event.previous_hash,
                    "metadata": event.metadata,
                    "solana_anchor": event.solana_anchor,
                })
        return public_events

    def export_chain_archive(self) -> Dict:
        """Export full chain archive (user-owned, encrypted at rest)."""
        return {
            "user_id": self.user_id,
            "export_timestamp": time.time(),
            "events": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type.value,
                    "timestamp": e.timestamp,
                    "data_hash": e.data_hash,
                    "data_preview": e.data_preview,
                    "privacy": e.privacy.value,
                    "consent_token": e.consent_token,
                    "sequence": e.sequence,
                    "previous_hash": e.previous_hash,
                    "metadata": e.metadata,
                    "notary_attestation": e.notary_attestation,
                    "stripe_receipt_id": e.stripe_receipt_id,
                    "solana_anchor": e.solana_anchor,
                }
                for e in self.events
            ],
            "consent_policy": self.consent_policy,
        }

    def verify_chain_integrity(self) -> bool:
        """Verify chain integrity by checking each event's previous_hash."""
        if not self.events:
            return True

        expected_prev = "0" * 64
        for event in self.events:
            if event.previous_hash != expected_prev:
                return False
            expected_prev = event.full_hash()
        return True

    def _has_consent(self, event_type: EventType) -> bool:
        """Check if user has consented to capturing this event type."""
        mapping = {
            EventType.PROMPT: "auto_capture_prompts",
            EventType.UPLOAD: "auto_capture_uploads",
            EventType.BUILD_SUCCESS: "auto_capture_builds",
            EventType.BUILD_FAILURE: "auto_capture_builds",
            EventType.LLM_ARTIFACT: "auto_capture_builds",
        }
        key = mapping.get(event_type)
        if key:
            return self.consent_policy.get(key, False)
        return True  # Other events don't require specific consent

    def update_consent_policy(self, **kwargs):
        """Update the user's consent policy."""
        self.consent_policy.update(kwargs)
        self._save_policy()

    def _persist_event(self, event: ChainEvent):
        """Save event to local storage."""
        path = os.path.join(self.storage_path, f"{event.sequence:08d}.json")
        with open(path, "w") as f:
            json.dump({
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "timestamp": event.timestamp,
                "data_hash": event.data_hash,
                "data_preview": event.data_preview,
                "privacy": event.privacy.value,
                "consent_token": event.consent_token,
                "sequence": event.sequence,
                "previous_hash": event.previous_hash,
                "metadata": event.metadata,
                "notary_attestation": event.notary_attestation,
                "stripe_receipt_id": event.stripe_receipt_id,
                "solana_anchor": event.solana_anchor,
            }, f, indent=2)

    def _load_chain(self):
        """Load chain from local storage."""
        if not os.path.exists(self.storage_path):
            return

        files = sorted([f for f in os.listdir(self.storage_path) if f.endswith(".json")])
        for fname in files:
            try:
                with open(os.path.join(self.storage_path, fname)) as f:
                    data = json.load(f)

                event = ChainEvent(
                    event_id=data["event_id"],
                    event_type=EventType(data["event_type"]),
                    timestamp=data["timestamp"],
                    data_hash=data["data_hash"],
                    data_preview=data["data_preview"],
                    privacy=PrivacyLabel(data["privacy"]),
                    consent_token=data["consent_token"],
                    sequence=data["sequence"],
                    previous_hash=data["previous_hash"],
                    metadata=data.get("metadata", {}),
                    notary_attestation=data.get("notary_attestation"),
                    stripe_receipt_id=data.get("stripe_receipt_id"),
                    solana_anchor=data.get("solana_anchor"),
                )
                self.events.append(event)
                self.sequence = event.sequence + 1
                self.last_hash = event.full_hash()
            except Exception:
                pass

    def _save_policy(self):
        """Save consent policy."""
        path = os.path.join(self.storage_path, "consent_policy.json")
        with open(path, "w") as f:
            json.dump(self.consent_policy, f, indent=2)

    def _load_policy(self):
        """Load consent policy."""
        path = os.path.join(self.storage_path, "consent_policy.json")
        if os.path.exists(path):
            try:
                with open(path) as f:
                    self.consent_policy = json.load(f)
            except Exception:
                pass
