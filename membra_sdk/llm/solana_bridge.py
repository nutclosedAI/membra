"""MEMBRA Solana Validator Bridge — Submit LLM validator votes to on-chain program.

Uses solana-py to interact with the membra_core Anchor program directly from Python.
If solana-py is not installed, falls back to calling the TypeScript client via subprocess.

Maps ValidatorEngine output → membra_core.submit_validator_vote instruction.
"""
import json
import os
import subprocess
from typing import Dict, Optional


class SolanaValidatorBridge:
    """Bridge between LLM validator output and Solana on-chain votes."""

    def __init__(
        self,
        cluster: str = "devnet",
        program_id: Optional[str] = None,
        wallet_path: Optional[str] = None,
    ):
        self.cluster = cluster
        self.program_id = program_id or "jApWwbd5HUBdw5vxF9pXZQQhgTLPrK1zYcJdSaw49h9"
        self.wallet_path = wallet_path or os.path.expanduser("~/.config/solana/id.json")
        self._has_solana_py = False

        # Try to import solana-py
        try:
            from solana.rpc.api import Client
            from solana.transaction import Transaction
            from solders.keypair import Keypair

            self._has_solana_py = True
            self._Client = Client
            self._Transaction = Transaction
            self._Keypair = Keypair
        except ImportError:
            self._has_solana_py = False

    def _get_rpc_url(self) -> str:
        if self.cluster == "devnet":
            return "https://api.devnet.solana.com"
        elif self.cluster == "mainnet":
            return "https://api.mainnet-beta.solana.com"
        return "http://127.0.0.1:8899"

    def _load_wallet(self):
        """Load Solana keypair from JSON."""
        import json as _json

        with open(self.wallet_path) as f:
            secret = _json.load(f)
        if self._has_solana_py:
            return self._Keypair.from_bytes(bytes(secret))
        return None

    def submit_vote_ts(
        self,
        job_pda: str,
        validator_pda: str,
        vote: int,
        score: int,
        reason_hash: str,
    ) -> Optional[str]:
        """Submit vote using TypeScript client (subprocess fallback)."""
        try:
            cmd = [
                "npx", "tsx",
                "scripts/submit_vote.ts",
                "--job", job_pda,
                "--validator", validator_pda,
                "--vote", str(vote),
                "--score", str(score),
                "--reason-hash", reason_hash,
                "--cluster", self.cluster,
            ]
            result = subprocess.run(
                cmd,
                cwd=os.path.expanduser("~/Downloads/membra-sdk"),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            print(f"TS client error: {result.stderr}")
            return None
        except FileNotFoundError:
            print("npx/tsx not found. Install Node.js dependencies.")
            return None
        except subprocess.TimeoutExpired:
            print("Submission timed out.")
            return None

    def submit_vote(
        self,
        job_pda: str,
        validator_pda: str,
        vote: int,
        score: int,
        reason_hash: str,
    ) -> Optional[str]:
        """Submit validator vote to Solana."""
        if self._has_solana_py:
            return self._submit_vote_python(job_pda, validator_pda, vote, score, reason_hash)
        return self.submit_vote_ts(job_pda, validator_pda, vote, score, reason_hash)

    def _submit_vote_python(
        self,
        job_pda: str,
        validator_pda: str,
        vote: int,
        score: int,
        reason_hash: str,
    ) -> Optional[str]:
        """Submit vote using solana-py (if available and Anchor IDL loaded)."""
        # This requires the Anchor Python bindings or manual transaction construction
        # For v0.1, we document the approach but use TS client as primary
        print("[Python Solana bridge: using TypeScript fallback for v0.1]")
        return self.submit_vote_ts(job_pda, validator_pda, vote, score, reason_hash)

    def submit_full_evaluation(
        self,
        job_pda: str,
        validator_pda: str,
        evaluation: Dict,
    ) -> Optional[str]:
        """Submit a complete validator evaluation to the chain."""
        vote = evaluation.get("vote", 0)
        score = evaluation.get("score", 0)
        reason_hash = evaluation.get("reason_hash", "")

        print(f"Submitting vote to Solana {self.cluster}...")
        print(f"  Job: {job_pda}")
        print(f"  Validator: {validator_pda}")
        print(f"  Vote: {'ACCEPT' if vote == 1 else 'REJECT'} (score: {score})")

        tx = self.submit_vote(job_pda, validator_pda, vote, score, reason_hash)
        if tx:
            print(f"  TX: {tx}")
        else:
            print("  Submission failed. See errors above.")
        return tx

    def get_job_status(self, job_pda: str) -> Optional[Dict]:
        """Fetch job account data from Solana."""
        if not self._has_solana_py:
            print("solana-py not installed. Cannot fetch on-chain data.")
            return None

        try:
            client = self._Client(self._get_rpc_url())
            resp = client.get_account_info(job_pda)
            if resp.value is None:
                return None

            # Decode account data (requires Anchor discriminator + struct layout)
            # For v0.1, return raw info
            return {
                "pubkey": job_pda,
                "lamports": resp.value.lamports,
                "owner": str(resp.value.owner),
                "data_len": len(resp.value.data),
            }
        except Exception as e:
            print(f"Error fetching job: {e}")
            return None

    def check_wallet_balance(self) -> Optional[float]:
        """Check wallet SOL balance."""
        if not self._has_solana_py:
            return None
        try:
            wallet = self._load_wallet()
            client = self._Client(self._get_rpc_url())
            resp = client.get_balance(wallet.pubkey())
            return resp.value / 1e9 if resp.value else 0.0
        except Exception:
            return None
