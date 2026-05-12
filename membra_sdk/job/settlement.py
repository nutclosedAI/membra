"""Settlement Adapter — Layer 5b of MEMBRA Proof-of-Job

Converts validated proof bundles into external value.

Supported settlement types:
  - invoice: Generate an invoice PDF from the proof bundle
  - bounty: Submit proof to a bounty platform
  - grant: Package proof for grant application
  - nft: Mint proof as an NFT (devnet only)
  - anchor: Anchor root hash to Solana devnet
  - receipt: Attach external payment receipt

MEMBRA measures and packages proof.
It does not manufacture external demand.
"""
import json
import time
from pathlib import Path
from typing import Dict, List, Optional


class SettlementAdapter:
    """Adapts proof bundles for external settlement."""

    def __init__(self):
        self.receipts: List[Dict] = []

    def add_receipt(self, receipt_type: str, amount: float,
                    currency: str = "USD", status: str = "confirmed",
                    processor: str = "", tx_id: str = "", metadata: Dict = None) -> Dict:
        """Add an external receipt to the settlement record."""
        receipt = {
            "type": receipt_type,
            "amount": amount,
            "currency": currency,
            "status": status,
            "processor": processor,
            "tx_id": tx_id,
            "timestamp": time.time(),
            "metadata": metadata or {},
        }
        self.receipts.append(receipt)
        return receipt

    def preview(self, proof_bundle: Dict) -> Dict:
        """Preview what settlement would look like for this proof."""
        yield_data = proof_bundle.get("yield", {})
        consensus = proof_bundle.get("consensus", {})

        if consensus.get("result") != "accepted":
            return {
                "settlable": False,
                "reason": "Consensus not reached",
                "suggested_actions": ["Fix rejection reasons", "Re-run validators"],
            }

        total_score = yield_data.get("total_score", 0)
        if total_score < 60:
            return {
                "settlable": True,
                "warning": "Low yield score — may not attract buyers",
                "suggested_actions": ["Improve tests", "Add documentation", "Run benchmarks"],
            }

        return {
            "settlable": True,
            "yield_score": total_score,
            "suggested_actions": [
                "Export proof bundle",
                "Submit to bounty platform",
                "Invoice customer",
                "Apply for grant",
            ],
        }

    def export_invoice(self, proof_bundle: Dict, rate_per_point: float = 1.0) -> Dict:
        """Generate an invoice preview from proof bundle yield."""
        yield_data = proof_bundle.get("yield", {})
        score = yield_data.get("total_score", 0)
        amount = round(score * rate_per_point, 2)

        return {
            "invoice_id": f"inv-{int(time.time())}",
            "amount": amount,
            "currency": "USD",
            "line_items": [
                {"description": "Artifact Yield", "score": yield_data.get("artifact_yield", 0), "amount": round(yield_data.get("artifact_yield", 0) * rate_per_point * 0.35, 2)},
                {"description": "Validation Yield", "score": yield_data.get("validation_yield", 0), "amount": round(yield_data.get("validation_yield", 0) * rate_per_point * 0.35, 2)},
                {"description": "Market Yield", "score": yield_data.get("market_yield", 0), "amount": round(yield_data.get("market_yield", 0) * rate_per_point * 0.15, 2)},
                {"description": "Chain Yield", "score": yield_data.get("chain_yield", 0), "amount": round(yield_data.get("chain_yield", 0) * rate_per_point * 0.15, 2)},
            ],
            "total": amount,
            "proof_root": proof_bundle.get("root_hash", "N/A")[:16] + "...",
        }

    def anchor_to_devnet(self, proof_bundle: Dict, solana_rpc: str = "https://api.devnet.solana.com") -> Dict:
        """Anchor proof root hash to Solana devnet (placeholder)."""
        # This would use solana-py to send a memo transaction
        # For now, return the instructions
        return {
            "status": "instruction_only",
            "network": "devnet",
            "rpc": solana_rpc,
            "root_hash": proof_bundle.get("root_hash", "N/A"),
            "instruction": "Use solana-py to send memo tx with root hash",
            "note": "Requires SOL devnet tokens and keypair",
        }
