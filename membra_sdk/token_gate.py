"""
MEMBRA Token and Liquidity Production Gate

This module enforces the hard gate that prevents the agent from
auto-creating tokens, pools, or executing swaps without explicit
human or multisig approval.

Rules:
- The agent may PREPARE transactions.
- The agent may NOT AUTO-SIGN mainnet transactions.
- The agent may NOT HOLD private keys.
- The agent may NOT call appraisals liquid cash.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class TokenLaunchState:
    """Represents the state required for token + liquidity launch."""
    agent_online: bool = False
    dashboard_online: bool = False
    corpus_indexed: bool = False
    proof_manifest_published: bool = False
    wallet_connected: bool = False
    human_or_multisig_approval: bool = False
    treasury_sol: float = 0.0
    treasury_usdc: float = 0.0
    no_private_keys_stored: bool = True
    mainnet_policy_enabled: bool = False
    # Staking-specific
    treasury_staking_policy_enabled: bool = False
    staking_allocation_bps: int = 0  # basis points, e.g. 5000 = 50%

    def __post_init__(self):
        if self.staking_allocation_bps < 0 or self.staking_allocation_bps > 10000:
            raise ValueError("staking_allocation_bps must be 0-10000")


def can_begin_token_and_liquidity(state: TokenLaunchState) -> bool:
    """
    Hard gate for token + liquidity launch.
    All conditions must be True.
    """
    return all([
        state.agent_online is True,
        state.dashboard_online is True,
        state.corpus_indexed is True,
        state.proof_manifest_published is True,
        state.wallet_connected is True,
        state.human_or_multisig_approval is True,
        state.treasury_sol >= 0.25,
        state.treasury_usdc >= 500.0,
        state.no_private_keys_stored is True,
        state.mainnet_policy_enabled is True,
    ])


def can_stake_treasury_sol(state: TokenLaunchState) -> bool:
    """
    Hard gate for treasury SOL liquid staking.
    """
    return all([
        state.treasury_staking_policy_enabled is True,
        state.treasury_sol >= 1.0,
        state.staking_allocation_bps <= 5000,
        state.human_or_multisig_approval is True,
    ])


def get_missing_conditions(state: TokenLaunchState) -> list[str]:
    """Return human-readable list of conditions that are NOT met."""
    missing = []
    if not state.agent_online:
        missing.append("Agent is not online")
    if not state.dashboard_online:
        missing.append("Dashboard is not online")
    if not state.corpus_indexed:
        missing.append("Corpus is not indexed")
    if not state.proof_manifest_published:
        missing.append("Proof manifest is not published")
    if not state.wallet_connected:
        missing.append("Wallet is not connected")
    if not state.human_or_multisig_approval:
        missing.append("Human or multisig approval not granted")
    if state.treasury_sol < 0.25:
        missing.append(f"Treasury SOL too low: {state.treasury_sol} < 0.25")
    if state.treasury_usdc < 500.0:
        missing.append(f"Treasury USDC too low: {state.treasury_usdc} < 500")
    if not state.no_private_keys_stored:
        missing.append("Private keys are stored (security violation)")
    if not state.mainnet_policy_enabled:
        missing.append("Mainnet policy is not enabled")
    return missing


def get_state_summary(state: TokenLaunchState) -> dict:
    """Return a summary of launch readiness."""
    ready = can_begin_token_and_liquidity(state)
    return {
        "ready": ready,
        "missing": get_missing_conditions(state) if not ready else [],
        "treasury_sol": state.treasury_sol,
        "treasury_usdc": state.treasury_usdc,
        "phase": _determine_phase(state),
    }


def _determine_phase(state: TokenLaunchState) -> str:
    """Determine which phase of the launch state machine we are in."""
    if not state.agent_online:
        return "AGENT_READY"
    if not state.corpus_indexed:
        return "AGENT_READY → CORPUS_INDEXED"
    if not state.proof_manifest_published:
        return "CORPUS_INDEXED → PROOF_MANIFEST_PUBLISHED"
    if not state.wallet_connected:
        return "PROOF_MANIFEST_PUBLISHED → WALLET_CONNECTED"
    if state.treasury_sol < 0.25 or state.treasury_usdc < 500.0:
        return "WALLET_CONNECTED → TREASURY_FUNDED"
    if not state.mainnet_policy_enabled:
        return "TREASURY_FUNDED → MAINNET_POLICY_ENABLED"
    if not state.human_or_multisig_approval:
        return "MAINNET_MINT_PREPARED → HUMAN_OR_MULTISIG_APPROVED"
    return "READY_FOR_TOKEN_CREATION"


# --- Invalid claim enforcement ---

INVALID_CLAIMS = {
    "files_are_liquidity": False,
    "appraisal_is_cash": False,
    "token_mint_is_profit": False,
    "testnet_is_settlement": False,
    "staking_rewards_guaranteed": False,
    "lp_tokens_risk_free": False,
    "agent_can_auto_mint": False,
    "agent_can_auto_create_pools": False,
    "running_agent_creates_money": False,
}


def assert_valid_claim(claim_name: str) -> None:
    """Raise if the claim is known to be invalid."""
    if claim_name in INVALID_CLAIMS and not INVALID_CLAIMS[claim_name]:
        raise ValueError(
            f"INVALID CLAIM: '{claim_name}' is documented as false. "
            "See docs/TOKEN_AND_LIQUIDITY_RUNBOOK.md"
        )


# --- Production parameters ---

TOKEN_PARAMS = {
    "symbol": "MEMBRA",
    "chain": "Solana",
    "network": "mainnet-beta",  # only after devnet proof
    "decimals": 6,
    "initial_supply": "fixed",  # published before mint
    "mint_authority": "multisig_or_hardware_wallet",
    "freeze_authority": "disabled",
}

LIQUIDITY_PARAMS = {
    "pair": "MEMBRA/USDC",
    "venue": "Raydium",
    "minimum_first_lp_usdc": 500,
    "treasury_sol_reserve_min": 0.25,
    "treasury_sol_reserve_max": 1.00,
}

STAKING_PARAMS = {
    "applies_to": "treasury_sol_only",
    "user_opt_in_required": True,
    "max_allocation_bps": 5000,  # 50%
    "protocols": ["Marinade"],
    "risk_disclosure": "smart_contract_depeg_liquidity",
}
