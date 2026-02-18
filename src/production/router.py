"""Production API routes with compiled IR execution.

Endpoints for rule compilation, O(1) evaluation, cache management,
and premise index operations.

From Workbench core/api/routes_production.py.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from src.models import CustomBaseModel

from .cache import IRCache
from .compiler import RuleCompiler
from .executor import RuleRuntime
from .optimizer import optimize_rule
from .premise_index import PremiseIndexBuilder
from .schemas import RuleIR

router = APIRouter(prefix="/v2", tags=["Production API"])


# =============================================================================
# Shared State
# =============================================================================

_runtime: RuleRuntime | None = None
_premise_index: PremiseIndexBuilder | None = None
_ir_cache: IRCache | None = None


def get_runtime() -> RuleRuntime:
    """Get or create runtime executor."""
    global _runtime, _premise_index, _ir_cache
    if _runtime is None:
        _ir_cache = IRCache()
        _premise_index = PremiseIndexBuilder()
        _runtime = RuleRuntime(cache=_ir_cache, premise_index=_premise_index)
    return _runtime


def reset_caches() -> None:
    """Reset all cached state."""
    global _runtime, _premise_index, _ir_cache
    _runtime = None
    _premise_index = None
    _ir_cache = None


# =============================================================================
# Request/Response Models
# =============================================================================


class MigrationRequest(CustomBaseModel):
    """Request to migrate YAML rules to database."""

    clear_existing: bool = Field(default=False, description="Clear existing data before migration")


class MigrationResponse(CustomBaseModel):
    """Response from migration."""

    success: bool
    rules_migrated: int
    rules_updated: int
    verifications_migrated: int
    premise_keys_indexed: int
    errors: list[str]


class CompileRequest(CustomBaseModel):
    """Request to compile a rule."""

    optimize: bool = Field(default=True, description="Apply optimizations")


class CompileResponse(CustomBaseModel):
    """Response from rule compilation."""

    rule_id: str
    compiled: bool
    premise_keys: list[str]
    applicability_check_count: int
    decision_table_size: int
    compiled_at: str | None = None
    error: str | None = None


class CompileAllResponse(CustomBaseModel):
    """Response from compiling all rules."""

    total: int
    compiled: int
    failed: int
    errors: list[dict]


class EvaluateRequest(CustomBaseModel):
    """Request to evaluate a rule against facts."""

    facts: dict[str, Any] = Field(..., description="Fact values")
    include_trace: bool = Field(default=True, description="Include execution trace")


class EvaluateResponse(CustomBaseModel):
    """Response from rule evaluation."""

    rule_id: str
    applicable: bool
    decision: str | None = None
    obligations: list[dict] = Field(default_factory=list)
    trace: list[dict] | None = None


class BatchEvaluateRequest(CustomBaseModel):
    """Request to evaluate multiple rules against facts."""

    facts: dict[str, Any] = Field(..., description="Fact values")
    rule_ids: list[str] | None = Field(
        default=None,
        description="Specific rules to evaluate (all if not provided)",
    )
    include_trace: bool = Field(default=False, description="Include execution traces")


class BatchEvaluateResponse(CustomBaseModel):
    """Response from batch rule evaluation."""

    total_evaluated: int
    applicable_count: int
    results: list[EvaluateResponse]


class DatabaseStatsResponse(CustomBaseModel):
    """Response with database statistics."""

    rules_count: int
    compiled_rules_count: int
    verification_stats: dict[str, int]
    reviews_count: int
    premise_keys_count: int


class SystemConfigResponse(CustomBaseModel):
    """Response with system configuration (non-sensitive)."""

    features: dict
    observability: dict


# =============================================================================
# Migration Endpoints
# =============================================================================


@router.post("/migrate", response_model=MigrationResponse)
async def migrate_rules(request: MigrationRequest) -> MigrationResponse:
    """Migrate YAML rules from disk to database."""
    from src.config import get_settings
    from src.rules.migration import migrate_yaml_rules

    settings = get_settings()
    rules_dir = settings.rules_dir

    result = migrate_yaml_rules(rules_dir, clear_existing=request.clear_existing)

    reset_caches()

    return MigrationResponse(
        success=result["success"],
        rules_migrated=result["rules_migrated"],
        rules_updated=result["rules_updated"],
        verifications_migrated=result["verifications_migrated"],
        premise_keys_indexed=result["premise_keys_indexed"],
        errors=result["errors"],
    )


@router.get("/status", response_model=DatabaseStatsResponse)
async def get_database_status() -> DatabaseStatsResponse:
    """Get current database status and statistics."""
    from src.rules.migration import get_migration_status

    status = get_migration_status()

    return DatabaseStatsResponse(
        rules_count=status["rules_count"],
        compiled_rules_count=status["compiled_rules_count"],
        verification_stats=status["verification_stats"],
        reviews_count=status["reviews_count"],
        premise_keys_count=len(status["premise_keys"]),
    )


# =============================================================================
# Compilation Endpoints
# =============================================================================


@router.post("/rules/{rule_id}/compile", response_model=CompileResponse)
async def compile_rule_endpoint(rule_id: str, request: CompileRequest | None = None) -> CompileResponse:
    """Compile a single rule to IR."""
    if request is None:
        request = CompileRequest()

    from src.rules.migration import load_rules_from_db
    from src.rules.repository import RuleRepository

    repo = RuleRepository()
    record = repo.get_rule(rule_id)

    if record is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")

    try:
        rules = load_rules_from_db(repo)
        rule = rules.get(rule_id)

        if rule is None:
            raise HTTPException(status_code=404, detail=f"Failed to parse rule: {rule_id}")

        compiler = RuleCompiler()
        ir = compiler.compile(rule, record.content_yaml)

        if request.optimize:
            ir = optimize_rule(ir)

        repo.update_rule_ir(rule_id, ir.to_json())
        repo.update_premise_index(rule_id, ir.premise_keys)

        runtime = get_runtime()
        runtime._cache.put(rule_id, ir)
        runtime._premise_index.add_rule(ir)

        return CompileResponse(
            rule_id=rule_id,
            compiled=True,
            premise_keys=ir.premise_keys,
            applicability_check_count=len(ir.applicability_checks),
            decision_table_size=len(ir.decision_table),
            compiled_at=ir.compiled_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        return CompileResponse(
            rule_id=rule_id,
            compiled=False,
            premise_keys=[],
            applicability_check_count=0,
            decision_table_size=0,
            error=str(e),
        )


@router.post("/rules/compile", response_model=CompileAllResponse)
async def compile_all_rules(
    optimize: bool = Query(default=True),
) -> CompileAllResponse:
    """Compile all rules to IR."""
    from src.rules.migration import load_rules_from_db
    from src.rules.repository import RuleRepository

    repo = RuleRepository()
    rules = load_rules_from_db(repo)

    compiler = RuleCompiler()
    runtime = get_runtime()

    compiled = 0
    errors: list[dict] = []

    for rule_id, rule in rules.items():
        try:
            record = repo.get_rule(rule_id)
            yaml_content = record.content_yaml if record else None

            ir = compiler.compile(rule, yaml_content)

            if optimize:
                ir = optimize_rule(ir)

            repo.update_rule_ir(rule_id, ir.to_json())
            repo.update_premise_index(rule_id, ir.premise_keys)

            runtime._cache.put(rule_id, ir)
            runtime._premise_index.add_rule(ir)

            compiled += 1

        except Exception as e:
            errors.append({"rule_id": rule_id, "error": str(e)})

    return CompileAllResponse(
        total=len(rules),
        compiled=compiled,
        failed=len(errors),
        errors=errors,
    )


# =============================================================================
# Evaluation Endpoints
# =============================================================================


@router.post("/rules/{rule_id}/evaluate", response_model=EvaluateResponse)
async def evaluate_rule(rule_id: str, request: EvaluateRequest) -> EvaluateResponse:
    """Evaluate a rule against facts using compiled IR."""
    from src.rules.migration import load_rules_from_db
    from src.rules.repository import RuleRepository

    repo = RuleRepository()
    record = repo.get_rule(rule_id)

    if record is None:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")

    runtime = get_runtime()
    ir = runtime._cache.get(rule_id)

    if ir is None:
        ir_json = repo.get_rule_ir(rule_id)
        if ir_json:
            ir = RuleIR.from_json(ir_json)
            runtime._cache.put(rule_id, ir)
        else:
            rules = load_rules_from_db(repo)
            rule = rules.get(rule_id)
            if rule is None:
                raise HTTPException(status_code=404, detail=f"Failed to parse rule: {rule_id}")

            compiler = RuleCompiler()
            ir = compiler.compile(rule, record.content_yaml)
            ir = optimize_rule(ir)

            repo.update_rule_ir(rule_id, ir.to_json())
            runtime._cache.put(rule_id, ir)

    result = runtime.infer(ir, request.facts, include_trace=request.include_trace)

    trace = None
    if request.include_trace and result.trace:
        trace = result.trace.to_legacy_trace()

    return EvaluateResponse(
        rule_id=rule_id,
        applicable=result.applicable,
        decision=result.decision,
        obligations=result.obligations,
        trace=trace,
    )


@router.post("/evaluate", response_model=BatchEvaluateResponse)
async def evaluate_batch(request: BatchEvaluateRequest) -> BatchEvaluateResponse:
    """Evaluate multiple rules against facts."""
    from src.rules.repository import RuleRepository

    repo = RuleRepository()
    runtime = get_runtime()

    if request.rule_ids:
        rule_ids = request.rule_ids
    else:
        candidates = runtime.find_applicable_rules(request.facts)

        if not candidates:
            all_records = repo.get_all_rules()
            rule_ids = [r.rule_id for r in all_records]
        else:
            rule_ids = list(candidates)

    results: list[EvaluateResponse] = []
    applicable_count = 0

    for rule_id in rule_ids:
        ir = runtime._cache.get(rule_id)
        if ir is None:
            ir_json = repo.get_rule_ir(rule_id)
            if ir_json:
                ir = RuleIR.from_json(ir_json)
                runtime._cache.put(rule_id, ir)

        if ir is None:
            continue

        result = runtime.infer(ir, request.facts, include_trace=request.include_trace)

        if result.applicable:
            applicable_count += 1

        trace = None
        if request.include_trace and result.trace:
            trace = result.trace.to_legacy_trace()

        results.append(
            EvaluateResponse(
                rule_id=rule_id,
                applicable=result.applicable,
                decision=result.decision,
                obligations=result.obligations,
                trace=trace,
            )
        )

    return BatchEvaluateResponse(
        total_evaluated=len(results),
        applicable_count=applicable_count,
        results=results,
    )


# =============================================================================
# Cache Management Endpoints
# =============================================================================


@router.get("/cache/stats")
async def get_cache_stats() -> dict:
    """Get IR cache statistics."""
    runtime = get_runtime()
    return runtime._cache.get_stats()


@router.post("/cache/clear")
async def clear_cache() -> dict:
    """Clear the IR cache."""
    runtime = get_runtime()
    count = runtime._cache.invalidate_all()
    return {"cleared": count}


@router.post("/cache/preload")
async def preload_cache() -> dict:
    """Preload all compiled rules into cache."""
    from src.rules.repository import RuleRepository

    repo = RuleRepository()
    runtime = get_runtime()

    all_rules = repo.get_all_rules()
    loaded = 0

    for record in all_rules:
        if record.rule_ir:
            try:
                ir = RuleIR.from_json(record.rule_ir)
                runtime._cache.put(record.rule_id, ir)
                runtime._premise_index.add_rule(ir)
                loaded += 1
            except Exception:
                pass

    return {
        "total_rules": len(all_rules),
        "loaded_to_cache": loaded,
        "cache_stats": runtime._cache.get_stats(),
    }


# =============================================================================
# Premise Index Endpoints
# =============================================================================


@router.get("/index/stats")
async def get_index_stats() -> dict:
    """Get premise index statistics."""
    runtime = get_runtime()
    return runtime._premise_index.get_stats()


@router.post("/index/rebuild")
async def rebuild_index() -> dict:
    """Rebuild the premise index from database."""
    from src.rules.repository import RuleRepository

    repo = RuleRepository()
    runtime = get_runtime()

    all_keys = repo.get_all_premise_keys()

    runtime._premise_index._index.clear()

    for record in repo.get_all_rules():
        if record.rule_ir:
            try:
                ir = RuleIR.from_json(record.rule_ir)
                runtime._premise_index.add_rule(ir)
            except Exception:
                pass

    return {
        "keys_in_db": len(all_keys),
        "index_stats": runtime._premise_index.get_stats(),
    }


@router.get("/index/lookup")
async def lookup_rules(
    field: str = Query(..., description="Field name"),
    value: str = Query(..., description="Field value"),
) -> dict:
    """Look up rules by premise key."""
    from src.rules.repository import RuleRepository

    repo = RuleRepository()
    premise_key = f"{field}:{value}"

    rule_ids = repo.get_rules_by_premise(premise_key)

    return {
        "premise_key": premise_key,
        "matching_rules": rule_ids,
        "count": len(rule_ids),
    }


# =============================================================================
# System Configuration Endpoint
# =============================================================================


@router.get("/config", response_model=SystemConfigResponse)
async def get_system_config() -> SystemConfigResponse:
    """Get system configuration status (non-sensitive)."""
    from src.config import get_settings

    settings = get_settings()

    return SystemConfigResponse(
        features={
            "rate_limiting": getattr(settings, "enable_rate_limiting", False),
            "rate_limit": getattr(settings, "rate_limit_default", "100/minute"),
            "audit_logging": getattr(settings, "enable_audit_logging", True),
            "tracing": getattr(settings, "enable_tracing", False),
            "auth_required": getattr(settings, "require_auth", False),
        },
        observability={
            "log_format": getattr(settings, "log_format", "json"),
            "log_level": getattr(settings, "log_level", "INFO"),
            "service_name": getattr(settings, "app_name", "institutional-defi-platform-api"),
        },
    )
