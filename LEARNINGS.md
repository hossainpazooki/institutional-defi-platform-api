# Learnings

Non-obvious patterns, gotchas, and operational knowledge for this codebase. Complements `CLAUDE.md` (structure, commands, deployment) with deeper insights.

---

## 1. Testing Gotchas

- **Two `client` fixture patterns** — `conftest.py` has a global `client` fixture using `TestClient(app)`. Embeddings tests use a separate fixture that overrides FastAPI dependencies (`app.dependency_overrides[get_session]`). Don't mix them.
- **`asyncio_mode = "auto"`** — set in `pyproject.toml`. No `@pytest.mark.asyncio` decorator needed on async test functions.
- **`get_settings()` is `@lru_cache`** — if you `monkeypatch.setenv()` in a test, you must call `get_settings.cache_clear()` afterward or the old cached settings persist.
- **Python 3.14 incompatibility** — FastAPI/inspect breaks with `NameError: name 'Session' is not defined`. Use Python 3.11–3.13.

## 2. Dependency & Import Patterns

Four distinct optional-import patterns coexist:

1. **`TYPE_CHECKING` guard** — import only for type hints, never at runtime
2. **Module-level `try/except` with flag** — e.g., `HAS_TRANSFORMERS = True` / `except: HAS_TRANSFORMERS = False`, then branch on the flag
3. **Lazy property** — class property that imports on first access
4. **Function-body `try/except`** — import inside the function, catch `ImportError` and fall back

Other dependency notes:
- **`temporalio` is guarded** in `service.py` and `__init__.py` — the app starts without `[temporal]` installed. `WorkflowClient.connect()` raises `RuntimeError` at call time if temporalio is missing. Worker/workflow modules (`worker.py`, `workflows.py`, `credit_decision.py`, `activities.py`) still have unguarded imports since they only run in the worker process.
- **ML fallbacks**: `sentence-transformers` → hash-based vectors; NLI → heuristics; LLM → stub text. Tests always use fallbacks.
- **`pydantic_ai`** (credit agents in `src/credit/`) → silent mock mode if not installed.
- **Shared SentenceTransformer singleton** — `config.py:get_sentence_transformer()` provides a single cached instance of `all-MiniLM-L6-v2`. Used by `embeddings/generator.py`, `verification/embeddings.py`, and `rag/service.py`. Returns `None` if sentence-transformers is not installed.

## 3. Database Split

Two completely different DB access patterns:

| Domain | Access pattern | Migration | FastAPI DI? |
|--------|---------------|-----------|-------------|
| Rules, Verification | Raw SQL via `get_db()` (context manager → raw connection) | `src/rules/migration.py` with `CREATE TABLE IF NOT EXISTS` | No — `get_db()` is a plain context manager, not a `Depends()` |
| Embeddings, Features | SQLModel ORM via `get_session()` (FastAPI DI generator) | Alembic (`alembic/versions/`) | Yes — use with `Depends(get_session)` |

- **Do not use `get_db()` as a FastAPI `Depends`** — it's a context manager, not a generator.
- **TimescaleDB hypertable** for `risk_features` must be initialized manually after Alembic migration: `init_timescaledb_hypertable("risk_features", "ts")`. Silently degrades to a plain PostgreSQL table if the TimescaleDB extension is absent.

## 4. Configuration Traps

- **`get_settings()` cached by `@lru_cache`** — env var changes after the first call are invisible unless you call `.cache_clear()`.
- **`api_keys` is a comma-separated string**, not a JSON list. Parsed by splitting on `,`.
- **`extra="ignore"` in Settings** — typos in environment variable names are silently ignored. You won't get an error if you set `DATABSE_URL` instead of `DATABASE_URL`.
- **`/docs` and `/redoc` disabled** unless `DEBUG=true`.
- **`rules_dir` and `data_dir` are relative paths** — the app must be run from the project root directory or these paths won't resolve.
- **`postgres://` → `postgresql://` normalization** is duplicated in both `database.py` and `alembic/env.py`. If you fix one, fix the other.

## 5. Middleware Order

Middleware is added bottom-up in `main.py` but executes outermost-first:

```
Request → OptionalAuth → Audit → SecurityHeaders → CORS → Route Handler
```

- **Auth is off by default** (`REQUIRE_AUTH=false`). When enabled, checks `X-API-Key` header against `api_keys`.
- **AuditMiddleware** binds a `request_id` to structlog context vars for the duration of the request. All log lines within that request share the ID.
- **Excluded paths** (`/health`, `/metrics`, `/docs`, `/redoc`, `/openapi.json`) skip audit logging.

## 6. Service Behavior

- **Feature Store is entirely mock data** — the `risk_features` table exists and has a schema, but nothing in the app writes real data to it. All feature queries return synthetic/example data.
- **LLM decoder returns stub text without error** when no `ANTHROPIC_API_KEY` is set — HTTP 200 with a fake explanation. Won't raise or return 4xx/5xx.
- **Verification always returns 200** even when individual checks crash internally. Failures become `fail` evidence records in the response payload. Check the evidence, not the status code.
- **`RuleLoader.load_directory()` silently skips malformed YAML** — prints a warning but raises no exception. Missing or corrupt rule files won't crash the app.
- **IR cache uses FIFO eviction** (not LRU) — the first-inserted compiled rules are evicted first, regardless of access frequency.
- **`Scenario.to_flat_dict()`** — the `extra` dict values can silently overwrite typed fields if keys collide.

## 7. Temporal / Workflow Specifics

Four workflow types:
1. **ComplianceCheck** — fan-out/fan-in across jurisdictions
2. **RuleVerification** — sequential saga through verification tiers
3. **CounterfactualAnalysis** — runs baseline, then parallel variant analyses
4. **DriftDetection** — batched parallel comparison of rule snapshots

Key details:
- Worker uses `SandboxedWorkflowRunner` with `src` and `pydantic` passed through the sandbox.
- **Activities re-load rules from YAML each time** — no shared in-memory cache between the API process and worker processes.
- `notify_drift_detected_activity` is a stub — logs only, no actual notification service connected.
- Task queue name: `compliance-workflows` (configurable via `TEMPORAL_TASK_QUEUE` env var).

## 8. Multi-Repo Test Orchestration (`scripts/test-all.sh`)

Five layers run across five repos:

| Layer | What runs | Common failures |
|-------|-----------|-----------------|
| 1 – Backend | `pytest`, `ruff check`, `ruff format` | Python 3.14 breaks FastAPI/inspect (`Session` not defined) — use 3.11–3.13 |
| 2 – Frontends | `eslint`, `tsc -b && vite build`, `vitest run` | See notes below |
| 3 – Worker | `ruff`, `mypy` | Temporal imports must be guarded |
| 4 – Infra | `kubectl kustomize` (local + dev overlays) | YAML drift |
| 5 – Contract | `python scripts/check-api-contracts.py` | Route prefix mismatches |

**Frontend lint patterns and fixes:**
- **ESLint v9 flat config** — Vite-generated projects now use `eslint.config.js` (flat config). If missing, ESLint v9 fails with "couldn't find an eslint.config" error. Create one using `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, and `globals`.
- **`import.meta.env` not typed** — add `/// <reference types="vite/client" />` in `src/vite-env.d.ts`. Symptom: `Property 'env' does not exist on type 'ImportMeta'`.
- **d3 zoom/brush `.call()` with `as any`** — `zoom.transform` and `brush.move` have TypeScript types that don't align with d3's `.call()` overloads. Suppress with `// eslint-disable-next-line @typescript-eslint/no-explicit-any` on the line before.
- **`react-refresh/only-export-components`** — fires when a file exports both a React component and a non-component (context, constant, utility). Suppress with `// eslint-disable-next-line react-refresh/only-export-components` on the export line; do not restructure unless the file is large.
- **`react-hooks/exhaustive-deps` with conditional derived state** — if a value like `transform` is derived from a conditional (props vs internal state), wrap it in `useMemo` to stabilize it. Callbacks that call `setTransform` need `setTransform` in their dep arrays.
- **`noUnusedLocals` / `noUnusedParameters` in tsconfig** — stale imports from copy-paste cause build failures. Remove the unused import from the destructured list; do not comment them out.
- **Missing types in shared `types/index.ts`** — if a component imports a type that doesn't exist yet (e.g., `CorrelationPair`), add the interface to `src/types/index.ts` based on the API response shape.
- **`Record<string, unknown>` deeply nested access** — when `results` is typed `Record<string, unknown>`, chaining `.protocol_risk?.profile` fails because each lookup returns `unknown`. Cast at the outermost level: `(results as { protocol_risk?: { profile?: Record<string, unknown> } }).protocol_risk?.profile`.

## 9. Docker / Deployment

- **Main `Dockerfile`** installs `[all]` extras. **`Dockerfile.worker`** installs only `[temporal]`.
- **`ENV HOME=/tmp`** in Dockerfiles is a PyTorch workaround — PyTorch tries to write to `$HOME` which is read-only for the non-root user (uid 1000).
- **Data files** (`data/`, `src/rules/data/`) are baked into the image via `COPY`, not mounted as volumes.
- **`docker-compose.yaml` is local infra only** — defines TimescaleDB, Redis, and Temporal. Does not include api or worker services.
- **Entrypoint `*` case** allows arbitrary commands: e.g., `docker run <image> alembic upgrade head`.
- **No auto-migration** — you must run `alembic upgrade head` before the first API start, both locally and on EKS.
