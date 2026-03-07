"""Institutional DeFi Platform API — unified FastAPI application.

Registers all 18 domain routers, applies middleware, and provides
health/readiness endpoints.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.analytics.router import router as analytics_router
from src.config import get_settings
from src.decoder.router import counterfactual_router
from src.decoder.router import router as decoder_router
from src.defi_risk.router import defi_risk_router, research_router
from src.embeddings.router import router as embeddings_router
from src.features.router import router as features_router
from src.jpm_scenarios.router import router as jpm_router
from src.jurisdiction.router import compliance_router, navigate_router
from src.ke.router import router as ke_router
from src.market_risk.router import quant_router, risk_router

# ── Middleware ──────────────────────────────────────────────────────
from src.middleware.audit import AuditMiddleware
from src.middleware.auth import OptionalAuthMiddleware
from src.middleware.security import SecurityHeadersMiddleware
from src.production.router import router as production_router
from src.protocol_risk.router import router as protocol_risk_router
from src.rag.router import router as rag_router

# ── Domain routers ──────────────────────────────────────────────────
# Routers with built-in prefixes (included directly)
from src.rules.router import decide_router, rules_router
from src.technology.router import router as technology_router

# Routers without prefixes (mounted with prefix= at include time)
from src.token_compliance.router import router as token_compliance_router
from src.trading.router import router as trading_router
from src.verification.router import verification_router
from src.credit.router import router as credit_router
from src.workflows.router import router as workflows_router

# ── Lifespan ────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup / shutdown hooks."""
    # Startup: eagerly validate settings
    settings = get_settings()

    # Initialize structured logging
    try:
        from src.telemetry.logging import configure_logging

        configure_logging(log_level=settings.log_level, log_format=settings.log_format)
    except ImportError:
        pass

    yield

    # Shutdown: dispose DB engine
    from src.database import reset_engine

    reset_engine()


# ── App factory ─────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Unified institutional DeFi compliance, risk, and analytics platform.",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # ── Middleware (applied bottom-up: last added = outermost) ───────
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # Audit logging
    sensitive_paths = [p.strip() for p in (settings.audit_sensitive_paths or "").split(",") if p.strip()]
    app.add_middleware(
        AuditMiddleware,
        enabled=settings.enable_audit_logging,
        sensitive_paths=sensitive_paths or None,
    )

    # Optional API-key auth
    app.add_middleware(OptionalAuthMiddleware)

    # ── Routers with built-in prefixes ──────────────────────────────
    app.include_router(rules_router)
    app.include_router(decide_router)
    app.include_router(verification_router)
    app.include_router(analytics_router)
    app.include_router(decoder_router)
    app.include_router(counterfactual_router)
    app.include_router(rag_router)
    app.include_router(embeddings_router)
    app.include_router(navigate_router)
    app.include_router(compliance_router)
    app.include_router(risk_router)
    app.include_router(quant_router)
    app.include_router(defi_risk_router)
    app.include_router(research_router)
    app.include_router(workflows_router)
    app.include_router(production_router)
    app.include_router(ke_router)
    app.include_router(jpm_router)
    app.include_router(credit_router)

    # ── Routers needing prefix at mount time ────────────────────────
    app.include_router(
        token_compliance_router,
        prefix="/token-compliance",
        tags=["Token Compliance"],
    )
    app.include_router(
        protocol_risk_router,
        prefix="/protocol-risk",
        tags=["Protocol Risk"],
    )
    app.include_router(
        trading_router,
        prefix="/trading",
        tags=["Trading"],
    )
    app.include_router(
        technology_router,
        prefix="/technology",
        tags=["Technology"],
    )
    app.include_router(
        features_router,
        prefix="/features",
        tags=["Feature Store"],
    )

    # ── Root & Health endpoints ──────────────────────────────────────

    @app.get("/", tags=["Health"])
    async def root():
        return {
            "name": settings.app_name,
            "environment": settings.environment,
            "endpoints": [r.path for r in app.routes if hasattr(r, "path")],
        }

    @app.get("/health", tags=["Health"])
    async def health_check():
        return {
            "status": "healthy",
            "service": settings.app_name,
            "environment": settings.environment,
        }

    return app


app = create_app()
