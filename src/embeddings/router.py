"""API routes for embedding rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status

from src.database import get_session

from .schemas import RuleCreate, RuleList, RuleRead, RuleUpdate
from .service import EmbeddingRuleService

if TYPE_CHECKING:
    from sqlmodel import Session

router = APIRouter(prefix="/embedding/rules", tags=["Embeddings"])


def get_service(session: Session = Depends(get_session)) -> EmbeddingRuleService:
    return EmbeddingRuleService(session)


@router.post("", response_model=RuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(rule_data: RuleCreate, service: EmbeddingRuleService = Depends(get_service)) -> RuleRead:
    existing = service.get_rule_by_rule_id(rule_data.rule_id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Rule with rule_id '{rule_data.rule_id}' already exists",
        )
    rule = service.create_rule(rule_data)
    return RuleRead.model_validate(rule)


@router.get("", response_model=list[RuleList])
async def list_rules(
    skip: int = 0, limit: int = 100, service: EmbeddingRuleService = Depends(get_service)
) -> list[RuleList]:
    rules = service.get_rules(skip=skip, limit=limit)
    return [RuleList.model_validate(rule) for rule in rules]


@router.get("/{rule_id}", response_model=RuleRead)
async def get_rule(rule_id: str, service: EmbeddingRuleService = Depends(get_service)) -> RuleRead:
    rule = service.get_rule_by_rule_id(rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule '{rule_id}' not found")
    return RuleRead.model_validate(rule)


@router.get("/{rule_id}/full", response_model=RuleRead)
async def get_rule_full(rule_id: str, service: EmbeddingRuleService = Depends(get_service)) -> RuleRead:
    return await get_rule(rule_id, service)


@router.put("/{rule_id}", response_model=RuleRead)
async def update_rule(
    rule_id: str, rule_data: RuleUpdate, service: EmbeddingRuleService = Depends(get_service)
) -> RuleRead:
    rule = service.update_rule(rule_id, rule_data)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule '{rule_id}' not found")
    return RuleRead.model_validate(rule)


@router.delete("/{rule_id}", response_model=RuleRead)
async def delete_rule(rule_id: str, service: EmbeddingRuleService = Depends(get_service)) -> RuleRead:
    rule = service.soft_delete_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule '{rule_id}' not found")
    return RuleRead.model_validate(rule)
