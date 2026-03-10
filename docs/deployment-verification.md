# Full-Stack Deployment Verification Pipeline

Post-deployment verification for the institutional DeFi platform on EKS. Validates the full stack (API + 3 frontends) is healthy after any deployment.

## Architecture

```
ALB (k8s-institut-institut-f9519fdd99-*.elb.amazonaws.com)
 |-- /api/*          -> api-dev (FastAPI :8000)
 |-- /workbench/*    -> regulatory-workbench (nginx :8080)
 |-- /console/*      -> risk-console (nginx :8080)
 +-- /crossborder/*  -> cross-border (nginx :8080)

api-dev -> RDS PostgreSQL
api-dev -> ElastiCache Redis
api-dev -> (future) Temporal
```

Frontend nginx proxies `/api/*` to `http://api-dev:8000/` internally.

## Health Endpoints

### `GET /health` (liveness probe)

Fast, dependency-free liveness check. Returns static response.

```json
{ "status": "healthy", "service": "Institutional DeFi Platform API", "environment": "local" }
```

### `GET /health/deep` (deep health check)

Verifies database and cache connectivity. Returns per-component status.

```json
{
  "status": "healthy",
  "service": "Institutional DeFi Platform API",
  "environment": "local",
  "checks": {
    "database": { "status": "healthy" },
    "redis": { "status": "healthy" },
    "temporal": { "status": "not_installed" }
  }
}
```

- `status` is `"healthy"` if all required checks (database, redis) pass, `"degraded"` otherwise
- Temporal is optional -- `"not_installed"` or `"configured"` are both acceptable

### `GET /ready` (readiness probe)

K8s readiness probe. Returns 200 if database is reachable, 500 if not.

```json
{ "status": "ready" }
```

## Verification Script

### `scripts/verify-deployment.sh`

Main orchestration script with 5 verification layers.

```bash
# Auto-detect ALB from kubectl
./scripts/verify-deployment.sh

# Explicit base URL
./scripts/verify-deployment.sh https://custom.url

# Via environment variable
DEPLOY_URL=https://... ./scripts/verify-deployment.sh
```

### Layer 1: K8s Pod Health

- Checks rollout status for all 4 deployments (`api-dev`, `regulatory-workbench`, `risk-console`, `cross-border`)
- Verifies all pods are in `Running` state
- Skipped if `kubectl` is not available

### Layer 2: Backend Health

| Check | Endpoint | Validation |
|-------|----------|------------|
| Liveness | `GET /health` | 200, `status == "healthy"` |
| Deep health (DB) | `GET /health/deep` | `checks.database.status == "healthy"` |
| Deep health (Redis) | `GET /health/deep` | `checks.redis.status == "healthy"` |
| Readiness | `GET /ready` | 200 |
| Root | `GET /` | Body contains `"endpoints"` |

### Layer 3: Frontend Reachability

Verifies each frontend serves HTML via the ALB:

- `GET /workbench/` -- contains `<!DOCTYPE html`
- `GET /console/` -- contains `<!DOCTYPE html`
- `GET /crossborder/` -- contains `<!DOCTYPE html`

Skipped when targeting localhost (no frontends).

### Layer 4: Frontend-to-API Proxy

Validates nginx proxy_pass from each frontend to the API:

- `GET /workbench/api/health` -> proxied to `api-dev:8000/health`
- `GET /console/api/health` -> proxied to `api-dev:8000/health`
- `GET /crossborder/api/health` -> proxied to `api-dev:8000/health`

Skipped when targeting localhost.

### Layer 5: Route Smoke Tests

One representative GET endpoint per domain group. Accepts any 2xx or 4xx (route exists but may need parameters). Only 404/502/503 is a failure.

| Domain | Smoke Endpoint |
|--------|----------------|
| Rules | `GET /rules` |
| Analytics | `GET /analytics/summary` |
| Decoder | `GET /decoder/tiers` |
| RAG | `GET /qa/status` |
| Jurisdiction | `GET /navigate/jurisdictions` |
| Market Risk | `GET /risk/supported-assets` |
| DeFi Risk | `GET /defi-risk/categories` |
| Token Compliance | `GET /token-compliance/standards` |
| Protocol Risk | `GET /protocol-risk/consensus-types` |
| Trading | `GET /trading/exposure` |
| Technology | `GET /technology/chains` |
| Features | `GET /features/` |
| JPM Scenarios | `GET /jpm/scenarios` |
| KE | `GET /ke/analytics/summary` |
| Credit | `GET /credit/queue` |
| Production | `GET /v2/status` |
| Embeddings | `GET /embedding/rules` |

### Output

Uses colored PASS/FAIL/SKIP output with a summary:

```
-- Layer 1: K8s Pod Health --
  PASS  Rollout: api-dev
  PASS  Rollout: regulatory-workbench
  ...

-- Layer 5: Route Smoke Tests --
  PASS  Smoke: GET /rules
  PASS  Smoke: GET /analytics/summary
  ...

========================================
  DEPLOYMENT VERIFICATION SUMMARY
========================================
  Passed:  25
  Failed:  0
  Skipped: 0

  All deployment checks passed.
```

Exit code 0 on success, 1 if any check fails.

## Live Contract Validation

### `scripts/verify-contracts-live.py`

Validates frontend API client calls against the live OpenAPI spec.

```bash
# Against localhost
python scripts/verify-contracts-live.py

# Against deployed API
python scripts/verify-contracts-live.py --url https://alb.url

# Verbose (show all matches + uncalled routes)
python scripts/verify-contracts-live.py --verbose
```

**What it does:**

1. Fetches `GET /openapi.json` from the running API
2. Extracts all route paths from the OpenAPI spec
3. Scans frontend API client files (`.ts`, `.tsx`, `.js`, `.jsx`) for HTTP method calls
4. Matches each frontend endpoint against the live spec (full path, with parameterized path support)
5. Reports: matched, unmatched, and uncalled spec routes

**Compared to `scripts/check-api-contracts.py`:**

| | `check-api-contracts.py` | `verify-contracts-live.py` |
|---|---|---|
| Data source | Hardcoded prefix list | Live OpenAPI spec |
| Match type | Prefix only | Full path |
| Requires running API | No | Yes |
| Use case | Offline/CI static check | Post-deploy validation |

## Integration with test-all.sh

The verification script is integrated as Layer 4 in `scripts/test-all.sh`:

```bash
# Run all layers including deploy verification
DEPLOY_URL=http://alb.url ./scripts/test-all.sh

# Run deploy verification only
DEPLOY_URL=http://alb.url ./scripts/test-all.sh deploy
```

Skipped automatically when `DEPLOY_URL` is not set (normal pre-deploy CI).

### Layer order in test-all.sh

1. Backend (pytest, ruff, mypy)
2. Frontends (typecheck, lint, build)
3. Infrastructure (terraform validate, kustomize build)
4. **Deployment Verification** (post-deploy, needs `DEPLOY_URL`)
5. API Contract Validation (static prefix check)

## Infra Repo Changes

The following changes should be applied in `institutional-defi-platform-infra`:

### K8s readiness probe (`kube/base/api-deployment.yaml`)

```yaml
readinessProbe:
  httpGet:
    path: /ready       # was /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3
livenessProbe:
  httpGet:
    path: /health      # unchanged -- fast, no deps
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 15
```

### CD workflow (`.github/workflows/cd-dev.yml`)

Replace the single `curl /health` with the full verification pipeline:

```yaml
- name: Verify deployment
  run: |
    # Wait for rollouts
    kubectl rollout status deployment/api-dev -n institutional-defi-dev --timeout=120s
    kubectl rollout status deployment/regulatory-workbench -n institutional-defi-dev --timeout=60s
    kubectl rollout status deployment/risk-console -n institutional-defi-dev --timeout=60s
    kubectl rollout status deployment/cross-border -n institutional-defi-dev --timeout=60s

    # Clone API repo for verification script (or checkout as artifact)
    ALB_URL=$(kubectl get ingress -n institutional-defi-dev \
      -o jsonpath='{.items[0].status.loadBalancer.ingress[0].hostname}')
    DEPLOY_URL="http://${ALB_URL}" ./scripts/verify-deployment.sh
```

## Files

| File | Purpose |
|------|---------|
| `src/main.py` | `/health/deep` and `/ready` endpoints |
| `scripts/verify-deployment.sh` | Main 5-layer verification orchestrator |
| `scripts/verify-contracts-live.py` | Live OpenAPI contract validation |
| `scripts/test-all.sh` | Layer 4 integration |
| `scripts/check-api-contracts.py` | Existing static contract check (unchanged) |
