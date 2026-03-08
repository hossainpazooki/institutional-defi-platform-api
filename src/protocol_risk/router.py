"""Protocol risk assessment API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from src.protocol_risk import service
from src.protocol_risk.schemas import (
    ProtocolRiskAssessment,
    ProtocolRiskRequest,
)

router = APIRouter()


@router.post("/assess", response_model=ProtocolRiskAssessment)
async def assess_protocol_risk(request: ProtocolRiskRequest) -> ProtocolRiskAssessment:
    """Assess blockchain protocol risk."""
    return service.assess_protocol_risk(
        protocol_id=request.protocol_id,
        consensus=request.consensus,
        finality_type=request.finality_type,
        validator_count=request.validator_count,
        nakamoto_coefficient=request.nakamoto_coefficient,
        finality_time_seconds=request.finality_time_seconds,
        tps_average=request.tps_average,
        tps_peak=request.tps_peak,
        uptime_30d_pct=request.uptime_30d_pct,
        major_incidents_12m=request.major_incidents_12m,
        has_bug_bounty=request.has_bug_bounty,
        audit_count=request.audit_count,
        time_since_last_upgrade_days=request.time_since_last_upgrade_days,
        top_10_stake_pct=request.top_10_stake_pct,
        total_staked_usd=request.total_staked_usd,
        slashing_enabled=request.slashing_enabled,
    )


@router.get("/protocols")
async def list_protocol_defaults() -> dict[str, list[str]]:
    """List available protocol default configurations."""
    return {"protocols": service.list_protocol_defaults()}


@router.get("/protocols/{protocol_id}")
async def get_protocol_config(protocol_id: str) -> dict[str, Any]:
    """Get default configuration for a known protocol."""
    config = service.get_protocol_defaults(protocol_id)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol '{protocol_id}' not found. Available: {service.list_protocol_defaults()}",
        )
    return {"protocol_id": protocol_id, **config}


@router.post("/protocols/{protocol_id}/assess", response_model=ProtocolRiskAssessment)
async def assess_known_protocol(protocol_id: str) -> ProtocolRiskAssessment:
    """Assess a known protocol using its default configuration."""
    config = service.get_protocol_defaults(protocol_id)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol '{protocol_id}' not found. Available: {service.list_protocol_defaults()}",
        )

    return service.assess_protocol_risk(
        protocol_id=protocol_id,
        consensus=config["consensus"],
        finality_type=config["finality_type"],
        validator_count=config["validator_count"],
        nakamoto_coefficient=config["nakamoto_coefficient"],
        finality_time_seconds=config["finality_time_seconds"],
        tps_average=config["tps_average"],
        tps_peak=config["tps_peak"],
        uptime_30d_pct=config.get("uptime_30d_pct", 99.9),
        major_incidents_12m=config.get("major_incidents_12m", 0),
        has_bug_bounty=config.get("has_bug_bounty", True),
        audit_count=config.get("audit_count", 0),
        time_since_last_upgrade_days=config.get("time_since_last_upgrade_days", 30),
        top_10_stake_pct=config.get("top_10_stake_pct", 50.0),
        total_staked_usd=config.get("total_staked_usd"),
        slashing_enabled=config.get("slashing_enabled", True),
    )


@router.get("/consensus-types")
async def list_consensus_types() -> dict[str, list[str]]:
    """List available consensus mechanism types."""
    return {"consensus_types": service.list_consensus_types()}
