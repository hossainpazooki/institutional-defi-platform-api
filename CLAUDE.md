# institutional-defi-platform-api

Unified institutional DeFi platform API — merged from three source projects:
- **applied-ai-regulatory-workbench** — Regulatory rule engine, verification, analytics, RAG, embeddings, decoder
- **crypto-portfolio-risk-console** — Trading, risk, technology monitoring, feature store, JPM scenarios
- **digital-assets-cross-border** — API contract (frontend only; no backend migrated)

## Rules (CRITICAL)
1. Sequential file operations — one edit/write at a time, wait for completion
2. Never assume file contents — read before writing, verify after changes
3. Run tests after every batch of changes
3a. Run `mypy src/ --strict` after making code changes — type errors are CI-blocking
4. Do not provide meta-commentary on your own thinking process unless requested
5. When compacting, preserve: file list, import patterns, test commands, and current task state
6. Autocompact at 50% context usage — proactively run /compact when context reaches ~50% to avoid hitting limits mid-task
7. Do not execute git commit/push. Output git commit commands for the user to run manually. Do not wait for commits — continue working. Other CLI tools (kubectl, docker, aws, helm) are fine to run directly.

## Current Phase
DEV DEPLOYED ON EKS — migration complete (28 steps, 457 tests, ruff clean). API running on EKS dev environment. Worker scaled to 0 (Temporal not deployed to EKS yet). Infrastructure in separate repo.

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
