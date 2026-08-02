# institutional-defi-platform-api

> **DECOMMISSIONED (2026-08-02).** This repo is archived and out of scope for new
> work. Its EKS `api`/`worker` deployments, ECR repositories, ingress routes and
> CD pipelines were removed from `institutional-defi-platform-infra`; the shared
> platform (VPC, EKS, ElastiCache, Secrets Manager) stays up for
> `regulatory-workbench`. The pending EKS→Vercel cross-border cutover was
> abandoned, not completed. Nothing below this banner is maintained — it is kept
> as a historical description of what the service was.
>
> Its last consumer had already moved on: COMPASS
> (`cross-border-compliance-navigator`) records this API as historical and out of
> its dependency graph, and never used `/v2/intents` from here.

Unified institutional DeFi platform API — backend for the institutional digital-asset compliance, risk, rationale, and credit stack.

## Sibling repos (historical — as of decommission)

- **`institutional-defi-platform-api`** (this repo) — FastAPI app, worker, Alembic migrations, all domain modules.
- **`institutional-defi-platform-infra`** — Terraform (VPC, EKS, RDS, ElastiCache, ECR, Secrets Manager) + Kustomize overlays (`local`/`dev`/`prod`) + Temporal Helm values. Cross-border on Vercel via same-origin rewrites; `/v2/ws/*` routes to api-dev for live trading sessions.
- **`cross-border-compliance-navigator`** (npm name `compliance-navigator`) — Vite + React + TypeScript + Tailwind frontend on Vercel. Consumes `POST /v2/intents`, `GET /v2/intents/{id}`, `WS /v2/ws/trade/{intent_id}`, and `GET /audit/{intent_id}`.

Out of scope (do not include in plans, briefs, or test orchestration):

- **`regulatory-rule-engine`** (internally `ke-workbench`; formerly `applied-ai-regulatory-workbench`) — out of scope as of 2026-05-25. The ATLAS artifact pipeline (signed RegimePacks + registry verification) is **not consumed in this repo**: ATLAS and `cross-border-compliance-navigator` (COMPASS) run as an **independent producer→consumer pair** — COMPASS verifies ATLAS artifacts directly via the ATLAS WASM verifier (`@platform/atlas-artifact`). No `ke-artifact` / `ke_artifact_py` consumption code lands here; if you find a `ke_artifact_py` install in `.venv`, it is a stray dev leftover, not a dependency.
- **`crypto-portfolio-risk-console`** — code already merged into this repo; no standalone work.

> Global working rules (file-op style, git default, verification, workflows,
> shared agents) are loaded from `~/.claude/` — not repeated here. This file is
> platform-API-specific only.

## Repo-specific rules (CRITICAL)
1. **Run tests after every batch of changes**: `pytest tests/ -x`.
2. **Run `mypy src/ --strict` after code changes** — type errors are CI-blocking.
3. Git follows the global default (output commit commands, don't run them; keep
   working). kubectl/docker/aws/helm are fine to run directly.

## Current Phase
DEV DEPLOYED ON EKS — SHA `c6d6526` deployed (2026-03-10). Migration complete (28 steps, 457 tests, ruff clean). API running on EKS dev environment. Worker scaled to 0 (Temporal not deployed to EKS yet). Commit `d4d0079` adds credit domain (not yet deployed). 3 frontend pods (regulatory-workbench, risk-console, cross-border) have placeholder INITIAL tags — no images built yet. Infrastructure in separate repo.

## Directory Structure
```
src/
├── __init__.py
├── main.py                    # FastAPI app (create_app), router registration, middleware
├── config.py                  # Global Settings(BaseSettings), env loading
├── database.py                # PostgreSQL + TimescaleDB engine, session DI
├── models.py                  # CustomBaseModel, shared SQLModel base
├── exceptions.py              # Global exception hierarchy + HTTP factories
│
├── ontology/                  # Shared domain types (jurisdiction, instrument, scenario, types, relations)
├── middleware/                # HTTP middleware (audit, security, auth)
├── telemetry/                 # Observability (tracing, metrics, logging)
│
├── rules/                     # Rule engine — YAML rules, RuleLoader, DecisionEngine
├── verification/              # 5-tier consistency checks (schema, semantic, NLI, cross-rule, human)
├── analytics/                 # Rule analytics, drift detection, error patterns, visualization
├── decoder/                   # UNIFIED decoder — template engine + LLM (Anthropic)
├── rag/                       # Legal corpus RAG — BM25 + optional vector search
├── embeddings/                # Rule embeddings — 4-type (semantic, structural, entity, legal) + graph
├── jurisdiction/              # UNIFIED jurisdiction — navigation, conflicts, pathway, compliance
├── market_risk/               # UNIFIED market risk — VaR, stress testing, correlation
├── defi_risk/                 # UNIFIED DeFi risk — protocol scoring, tokenomics, research
├── token_compliance/          # Token classification — Howey test, GENIUS Act analysis
├── protocol_risk/             # Blockchain risk — protocol profiles, chain risk scoring
├── trading/                   # Trading desk — exposure, PnL, funding rates
├── technology/                # Chain/RPC monitoring — status, health checks
├── features/                  # Feature Store — TimescaleDB hypertable, risk features
├── jpm_scenarios/             # JPM scenarios — 5 preset scenarios, memo generation
├── workflows/                 # Temporal orchestration — compliance, verification, drift, counterfactual
├── credit/                    # Credit decisioning — PydanticAI agents, LlamaIndex RAG, Temporal workflow
├── production/                # Compiled IR execution — compiler, optimizer, runtime, cache
└── ke/                        # Knowledge Engineering workbench — orchestrates rules/verification/analytics

```

Infrastructure (terraform/, kube/) is in the [institutional-defi-platform-infra](../institutional-defi-platform-infra) repo.

## Route Prefixes
| Domain | Prefix |
|--------|--------|
| rules | `/rules`, `/decide` |
| verification | `/verification` |
| analytics | `/analytics` |
| decoder | `/decoder`, `/counterfactual` |
| rag | `/qa` |
| embeddings | `/embedding/rules` |
| jurisdiction | `/navigate`, `/jurisdiction`, `/compliance` |
| market_risk | `/risk`, `/quant` |
| defi_risk | `/defi-risk`, `/research` |
| token_compliance | `/token-compliance` |
| protocol_risk | `/protocol-risk` |
| trading | `/trading` |
| technology | `/technology` |
| features | `/features` |
| jpm_scenarios | `/jpm` |
| workflows | `/workflows` |
| credit | `/credit` |
| production | `/v2` |
| ke | `/ke` |

## Import Conventions
```python
# Cross-domain
from src.rules import service as rules_service

# Within-domain
from src.rules.service import DecisionEngine

# Global
from src.config import get_settings
from src.database import get_session
from src.models import CustomBaseModel

# Ontology
from src.ontology.jurisdiction import JurisdictionCode
from src.ontology.instrument import InstrumentType
```

## Local Development
```bash
# Start local services (TimescaleDB on :5432, Redis on :6379, Temporal on :7233, Temporal UI on :8233)
docker compose up -d

# Install
pip install -e ".[dev]"

# Test
pytest tests/ -x

# Lint
ruff check src tests
ruff format src tests

# Run locally
uvicorn src.main:app --reload

# Database migrations (local)
alembic upgrade head
```

**Known issue:** Tests fail on Python 3.14 due to FastAPI/inspect incompatibility (`NameError: name 'Session' is not defined`). Use Python 3.11–3.13 for testing.

## EKS Deployment
```bash
# Cluster access
aws eks update-kubeconfig --name institutional-defi-eks --region us-east-1

# ECR login
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 547729607601.dkr.ecr.us-east-1.amazonaws.com

# Build and push (use git SHA as tag — ECR repos are IMMUTABLE, no :latest)
SHA=$(git rev-parse --short HEAD)
docker build -t 547729607601.dkr.ecr.us-east-1.amazonaws.com/institutional-defi-api:$SHA .
docker push 547729607601.dkr.ecr.us-east-1.amazonaws.com/institutional-defi-api:$SHA
# Worker uses same image, different ECR repo
docker tag 547729607601.dkr.ecr.us-east-1.amazonaws.com/institutional-defi-api:$SHA \
           547729607601.dkr.ecr.us-east-1.amazonaws.com/institutional-defi-worker:$SHA
docker push 547729607601.dkr.ecr.us-east-1.amazonaws.com/institutional-defi-worker:$SHA

# Update image tag in infra repo: kube/overlays/dev/kustomization.yaml → newTag: "<SHA>"

# Deploy
kubectl apply -k kube/overlays/dev/   # from infra repo

# Run migration on EKS (one-time pod against RDS)
kubectl run alembic-migrate -n institutional-defi-dev \
  --image=547729607601.dkr.ecr.us-east-1.amazonaws.com/institutional-defi-api:$SHA \
  --restart=Never \
  --overrides='{ "spec": { "serviceAccountName": "idpa-sa-dev", "containers": [{ "name": "alembic-migrate", "image": "547729607601.dkr.ecr.us-east-1.amazonaws.com/institutional-defi-api:'"$SHA"'", "command": ["alembic", "upgrade", "head"], "envFrom": [{"configMapRef": {"name": "api-config-dev"}}, {"secretRef": {"name": "api-secrets"}}], "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}], "securityContext": {"runAsNonRoot": true, "runAsUser": 1000, "readOnlyRootFilesystem": true, "allowPrivilegeEscalation": false} }], "volumes": [{"name": "tmp", "emptyDir": {}}] } }'
kubectl logs -n institutional-defi-dev alembic-migrate -f
kubectl delete pod -n institutional-defi-dev alembic-migrate

# Verify
kubectl get pods -n institutional-defi-dev
curl -s http://k8s-institut-institut-f9519fdd99-938355378.us-east-1.elb.amazonaws.com/health
```

## Infrastructure
| Resource | Detail |
|----------|--------|
| EKS cluster | `institutional-defi-eks`, us-east-1, 3 nodes (v1.29) |
| ECR repos | `institutional-defi-api`, `institutional-defi-worker` (IMMUTABLE tags) |
| ECR registry | `547729607601.dkr.ecr.us-east-1.amazonaws.com` |
| RDS | PostgreSQL (app DB + Temporal DB) |
| Redis | ElastiCache |
| Secrets | AWS Secrets Manager → External Secrets Operator → `api-secrets` K8s secret |
| ALB | `k8s-institut-institut-f9519fdd99-938355378.us-east-1.elb.amazonaws.com` |
| ACM certs | Issued, not yet attached to ALB |
| Namespace | `institutional-defi-dev` |
| Service account | `idpa-sa-dev` (IRSA) |
| Infra repo | `institutional-defi-platform-infra` (terraform/, kube/) |

### Cluster-level components (already installed)
- AWS Load Balancer Controller (ALB ingress)
- External Secrets Operator + ClusterSecretStore (`aws-secrets-manager`)
- EBS CSI driver
- Metrics server

### Image tagging convention
Git SHA tags only (e.g. `5c7c04a`). ECR repos use IMMUTABLE tag policy — once a tag is pushed it cannot be overwritten. Update `kube/overlays/dev/kustomization.yaml` `newTag` field to match.

## Database Notes
- **embeddings** and **features** domains use SQLModel tables with Alembic migrations
- Initial migration `001` creates all 7 tables (applied to RDS)
- **rules** and **verification** domains use raw SQL via repositories (YAML-sourced rules loaded at runtime)
- Legal corpus in `data/legal/` (MiCA, DLT Pilot, GENIUS Act)
- Local dev uses TimescaleDB via docker-compose; EKS uses RDS

## Optional Dependencies
- `[ml]` — sentence-transformers, chromadb (embedding generation; tests use hash-based fallback)
- `[llm]` — anthropic (LLM decoder)
- `[blockchain]` — web3 (chain/RPC monitoring)
- `[temporal]` — temporalio (workflow orchestration)
- `[telemetry]` — opentelemetry, prometheus-client
- `[all]` — everything above + dev tools

## Environment Variables
See `.env.example` for full list. Key variables:
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis for Celery/caching
- `ENVIRONMENT` — local, staging, production
- `ANTHROPIC_API_KEY` — LLM decoder (optional)
- `TEMPORAL_HOST` — Temporal server (optional)

On EKS, `DATABASE_URL`, `REDIS_URL`, and `ANTHROPIC_API_KEY` are injected via AWS Secrets Manager → ExternalSecret → `api-secrets` K8s secret. Non-secret config (ENVIRONMENT, etc.) comes from the `api-config-dev` ConfigMap defined in `kube/overlays/dev/configmap.yaml`.

## Scripts
| Script | Purpose |
|--------|---------|
| `scripts/test-all.sh` | Cross-repo test orchestration (runs tests across all 5 repos) |
| `scripts/verify-deployment.sh` | EKS deployment validation (pod health, endpoint checks) |
| `scripts/verify-contracts-live.py` | Live API contract verification against running endpoints |
| `scripts/check-api-contracts.py` | Static API contract checks (route/schema consistency) |
| `scripts/export-openapi.py` | OpenAPI spec export from FastAPI app |
| `scripts/generate-frontend-types.sh` | Frontend TypeScript type generation from OpenAPI spec |

## CI/CD
- Pipeline config: `.github/workflows/ci.yml`
- Steps: lint → typecheck → test → docker build → ECR push → kustomize update → kubectl apply → smoke test
- Docker cold build ~47min (large ML deps in `.[all]`) — cached builds much faster
- ECR push can fail transiently (Docker Desktop proxy) — retry works
