"""Constants and configurations for JPM Scenarios."""

from __future__ import annotations

from typing import TypedDict

from src.protocol_risk.constants import CHAIN_RISK_PROFILES as CHAIN_PROFILES


class ScenarioConfig(TypedDict):
    """Configuration for a JPM scenario."""

    id: str
    name: str
    description: str
    chain: str
    instrument_type: str
    jurisdictions: list[str]
    defi_protocols: list[str]


# Pre-configured JPM tokenization scenarios
SCENARIOS: dict[str, ScenarioConfig] = {
    "jpmd_base": {
        "id": "jpmd_base",
        "name": "JPMD on Base",
        "description": "JPM Coin deposit token on Base L2",
        "chain": "base",
        "instrument_type": "deposit_token",
        "jurisdictions": ["US", "EU", "UK", "SG"],
        "defi_protocols": [],
    },
    "jpmd_canton": {
        "id": "jpmd_canton",
        "name": "JPMD on Canton",
        "description": "JPM Coin on Canton permissioned network",
        "chain": "canton",
        "instrument_type": "deposit_token",
        "jurisdictions": ["US", "EU", "UK", "SG"],
        "defi_protocols": [],
    },
    "mony_ethereum": {
        "id": "mony_ethereum",
        "name": "MONY on Ethereum",
        "description": "Tokenized money market fund on Ethereum",
        "chain": "ethereum",
        "instrument_type": "tokenized_fund",
        "jurisdictions": ["US", "EU", "UK"],
        "defi_protocols": [],
    },
    "cp_solana": {
        "id": "cp_solana",
        "name": "CP on Solana",
        "description": "Tokenized commercial paper on Solana",
        "chain": "solana",
        "instrument_type": "tokenized_bond",
        "jurisdictions": ["US"],
        "defi_protocols": [],
    },
    "project_guardian": {
        "id": "project_guardian",
        "name": "Project Guardian",
        "description": "Institutional DeFi (Aave + Uniswap on Polygon)",
        "chain": "polygon",
        "instrument_type": "defi_position",
        "jurisdictions": ["US", "EU", "SG"],
        "defi_protocols": ["aave_v3", "uniswap_v3"],
    },
}

__all__ = ["CHAIN_PROFILES", "SCENARIOS", "ScenarioConfig"]
