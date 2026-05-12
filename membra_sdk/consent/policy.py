"""Consent Manager — User controls what gets captured, when, and how.

The doctrine:
- Private by default.
- Consent before capture.
- Hash before public proof.
- User owns their consent policy and can export/revoke at any time.
"""
import json
import os
import time
from enum import Enum
from typing import Dict, List, Optional


class ConsentLevel(Enum):
    NONE = "none"           # No capture allowed
    PROMPT = "prompt"       # Ask each time
    BUILD = "build"         # Auto-capture builds only
    FULL = "full"           # Auto-capture all approved types


class ConsentManager:
    """Manages user consent for capture, privacy, and monetization."""

    CAPTURE_TYPES = [
        "prompts",
        "uploads",
        "builds",
        "file_scans",
        "llm_responses",
        "wallet_actions",
        "marketplace_activity",
        "stripe_receipts",
    ]

    def __init__(self, user_id: str, storage_path: str = None):
        self.user_id = user_id
        self.storage_path = storage_path or os.path.expanduser(f"~/.membra/consent/{user_id}")
        os.makedirs(self.storage_path, exist_ok=True)

        self.level = ConsentLevel.PROMPT
        self.approved_types: List[str] = ["builds"]  # Default: only builds auto-captured
        self.privacy_defaults: Dict[str, str] = {
            "prompts": "private",
            "uploads": "private",
            "builds": "protected",
            "file_scans": "private",
            "llm_responses": "private",
            "wallet_actions": "anonymous",
            "marketplace_activity": "public",
            "stripe_receipts": "anonymous",
        }
        self.monetization_enabled = False
        self.public_anchor_allowed = False
        self.consent_history: List[Dict] = []

        self._load()

    def grant(self, capture_type: str, privacy: str = None, duration: str = "permanent") -> bool:
        """Grant consent for a capture type."""
        if capture_type not in self.CAPTURE_TYPES:
            return False

        if capture_type not in self.approved_types:
            self.approved_types.append(capture_type)

        if privacy:
            self.privacy_defaults[capture_type] = privacy

        self.consent_history.append({
            "action": "grant",
            "capture_type": capture_type,
            "privacy": privacy or self.privacy_defaults.get(capture_type, "private"),
            "duration": duration,
            "timestamp": time.time(),
        })
        self._save()
        return True

    def revoke(self, capture_type: str) -> bool:
        """Revoke consent for a capture type."""
        if capture_type in self.approved_types:
            self.approved_types.remove(capture_type)

        self.consent_history.append({
            "action": "revoke",
            "capture_type": capture_type,
            "timestamp": time.time(),
        })
        self._save()
        return True

    def revoke_all(self):
        """Revoke all consents. Emergency privacy reset."""
        self.approved_types = []
        self.level = ConsentLevel.NONE
        self.monetization_enabled = False
        self.public_anchor_allowed = False
        self.consent_history.append({
            "action": "revoke_all",
            "timestamp": time.time(),
        })
        self._save()

    def is_approved(self, capture_type: str) -> bool:
        """Check if a capture type is approved."""
        return capture_type in self.approved_types

    def get_privacy(self, capture_type: str) -> str:
        """Get privacy default for a capture type."""
        return self.privacy_defaults.get(capture_type, "private")

    def can_monetize(self) -> bool:
        """Check if user has enabled monetization."""
        return self.monetization_enabled

    def can_anchor_publicly(self) -> bool:
        """Check if user allows public Solana anchors."""
        return self.public_anchor_allowed

    def export_consent_log(self) -> Dict:
        """Export full consent history (user-owned)."""
        return {
            "user_id": self.user_id,
            "export_timestamp": time.time(),
            "current_level": self.level.value,
            "approved_types": self.approved_types,
            "privacy_defaults": self.privacy_defaults,
            "monetization_enabled": self.monetization_enabled,
            "public_anchor_allowed": self.public_anchor_allowed,
            "consent_history": self.consent_history,
        }

    def _save(self):
        path = os.path.join(self.storage_path, "consent.json")
        with open(path, "w") as f:
            json.dump({
                "level": self.level.value,
                "approved_types": self.approved_types,
                "privacy_defaults": self.privacy_defaults,
                "monetization_enabled": self.monetization_enabled,
                "public_anchor_allowed": self.public_anchor_allowed,
                "consent_history": self.consent_history,
            }, f, indent=2)

    def _load(self):
        path = os.path.join(self.storage_path, "consent.json")
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self.level = ConsentLevel(data.get("level", "prompt"))
            self.approved_types = data.get("approved_types", ["builds"])
            self.privacy_defaults = data.get("privacy_defaults", self.privacy_defaults)
            self.monetization_enabled = data.get("monetization_enabled", False)
            self.public_anchor_allowed = data.get("public_anchor_allowed", False)
            self.consent_history = data.get("consent_history", [])
        except Exception:
            pass
