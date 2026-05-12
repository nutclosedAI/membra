"""MEMBRA Configuration — Production vs Simulation mode toggle.

Environment variables:
  MEMBRA_MODE=simulation|production    # Default: simulation
  STRIPE_SECRET_KEY=sk_...            # Required for production payments
  STRIPE_PUBLISHABLE_KEY=pk_...       # Required for production frontend
  SOLANA_RPC_URL=...                  # Default: devnet
  GROQ_API_KEY=...                    # Optional: for LLM inference

The mode toggle prevents accidental real money movement during development.
"""
import os
from enum import Enum


class MembraMode(Enum):
    SIMULATION = "simulation"
    PRODUCTION = "production"


class MembraConfig:
    """Central configuration for MEMBRA SDK.

    SIMULATION mode (default):
    - Mock payments, fake escrow, simulated receipts
    - No real money moves
    - Safe for development and demos

    PRODUCTION mode:
    - Real Stripe Connect payments
    - Real Solana settlement
    - Requires valid API keys and explicit acknowledgments
    """

    def __init__(self):
        self.mode = MembraMode(os.environ.get("MEMBRA_MODE", "simulation").lower())
        self.stripe_secret_key = os.environ.get("STRIPE_SECRET_KEY", "")
        self.stripe_publishable_key = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
        self.solana_rpc = os.environ.get("SOLANA_RPC_URL", "https://api.devnet.solana.com")
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")

    def is_simulation(self) -> bool:
        return self.mode == MembraMode.SIMULATION

    def is_production(self) -> bool:
        return self.mode == MembraMode.PRODUCTION

    def require_production(self, action: str):
        """Raise if trying to do a production action in simulation mode."""
        if self.is_simulation():
            raise RuntimeError(
                f"Action '{action}' requires MEMBRA_MODE=production. "
                f"Current mode: {self.mode.value}. "
                "Set MEMBRA_MODE=production and configure real API keys."
            )

    def get_status(self) -> dict:
        return {
            "mode": self.mode.value,
            "stripe_configured": bool(self.stripe_secret_key),
            "solana_rpc": self.solana_rpc,
            "groq_configured": bool(self.groq_api_key),
            "safe_for_development": self.is_simulation(),
        }
