"""KYI (Know Your Identity) Notary Layer — Identity attestation and flagged value verification.

The doctrine:
- Notary before disputed value.
- KYI reviews flagged events before they enter monetization.
- Identity is attested, not stored in full.
"""
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class IdentityAttestation:
    """An attestation of user identity without storing full PII."""
    attestation_id: str
    user_id: str
    method: str              # "email", "phone", "government_id", "biometric", "wallet"
    status: str              # "pending", "verified", "rejected", "expired"
    identity_hash: str       # Hash of identity document (not the document itself)
    timestamp: float
    expires_at: Optional[float] = None
    metadata: Dict = field(default_factory=dict)


class KYINotary:
    """Know Your Identity notary for verifying identity and attesting to value events."""

    def __init__(self):
        self.attestations: Dict[str, IdentityAttestation] = {}
        self.flagged_events: List[Dict] = []
        self.review_log: List[Dict] = []

    def request_attestation(self, user_id: str, method: str,
                          identity_document: str = None) -> IdentityAttestation:
        """Request identity attestation. Document is hashed, not stored."""
        identity_hash = ""
        if identity_document:
            identity_hash = hashlib.sha256(identity_document.encode()).hexdigest()

        attestation = IdentityAttestation(
            attestation_id=f"att-{user_id}-{int(time.time())}",
            user_id=user_id,
            method=method,
            status="pending",
            identity_hash=identity_hash,
            timestamp=time.time(),
            expires_at=time.time() + 86400 * 365,  # 1 year
        )
        self.attestations[attestation.attestation_id] = attestation
        return attestation

    def verify_attestation(self, attestation_id: str, verifier_notes: str = "") -> bool:
        """Notary verifies the attestation (manual or automated review)."""
        att = self.attestations.get(attestation_id)
        if not att:
            return False
        att.status = "verified"
        self.review_log.append({
            "attestation_id": attestation_id,
            "action": "verify",
            "verifier_notes": verifier_notes,
            "timestamp": time.time(),
        })
        return True

    def flag_event(self, event_id: str, event_type: str, reason: str,
                   user_id: str) -> Dict:
        """Flag an event for notary review before monetization."""
        flag = {
            "flag_id": f"flag-{event_id}",
            "event_id": event_id,
            "event_type": event_type,
            "reason": reason,
            "user_id": user_id,
            "status": "pending_review",
            "timestamp": time.time(),
        }
        self.flagged_events.append(flag)
        return flag

    def review_flag(self, flag_id: str, approved: bool, notary_notes: str = "") -> bool:
        """Notary reviews a flagged event."""
        for flag in self.flagged_events:
            if flag["flag_id"] == flag_id:
                flag["status"] = "approved" if approved else "rejected"
                flag["notary_notes"] = notary_notes
                flag["reviewed_at"] = time.time()
                self.review_log.append({
                    "flag_id": flag_id,
                    "action": "approve" if approved else "reject",
                    "notes": notary_notes,
                    "timestamp": time.time(),
                })
                return True
        return False

    def is_identity_verified(self, user_id: str) -> bool:
        """Check if user has a valid identity attestation."""
        for att in self.attestations.values():
            if att.user_id == user_id and att.status == "verified":
                if att.expires_at and time.time() > att.expires_at:
                    continue
                return True
        return False

    def get_attestation(self, user_id: str) -> Optional[IdentityAttestation]:
        """Get user's most recent attestation."""
        latest = None
        for att in self.attestations.values():
            if att.user_id == user_id:
                if latest is None or att.timestamp > latest.timestamp:
                    latest = att
        return latest

    def get_stats(self) -> Dict:
        """Notary statistics."""
        verified = sum(1 for a in self.attestations.values() if a.status == "verified")
        pending = sum(1 for a in self.attestations.values() if a.status == "pending")
        flagged = len(self.flagged_events)
        reviewed = sum(1 for f in self.flagged_events if f.get("status") in ("approved", "rejected"))

        return {
            "total_attestations": len(self.attestations),
            "verified": verified,
            "pending": pending,
            "flagged_events": flagged,
            "reviewed": reviewed,
            "pending_review": flagged - reviewed,
        }
