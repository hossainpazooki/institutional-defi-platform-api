#!/bin/bash
# Full-stack test orchestrator — runs checks across all 5 repos.
# Usage:
#   ./scripts/test-all.sh          # run all layers
#   ./scripts/test-all.sh backend  # backend only
#   ./scripts/test-all.sh frontend # all 3 frontends
#   ./scripts/test-all.sh infra    # terraform + kustomize
#   ./scripts/test-all.sh deploy   # post-deploy verification (needs DEPLOY_URL)
#   ./scripts/test-all.sh contract # API contract check

set -euo pipefail

BASE="/c/Users/hossa/dev"
API="$BASE/institutional-defi-platform-api"
INFRA="$BASE/institutional-defi-platform-infra"
WORKBENCH="$BASE/applied-ai-regulatory-workbench/frontend-react"
RISK_CONSOLE="$BASE/crypto-portfolio-risk-console/frontend"
CROSS_BORDER="$BASE/digital-assets-cross-border"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASSED=0
FAILED=0
SKIPPED=0
FAILURES=()

run_check() {
    local label="$1"
    shift
    echo -e "\n${CYAN}=== $label ===${NC}"
    if "$@" 2>&1; then
        echo -e "${GREEN}PASS${NC}: $label"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}FAIL${NC}: $label"
        FAILURES+=("$label")
        FAILED=$((FAILED + 1))
    fi
}

skip_check() {
    local label="$1"
    local reason="$2"
    echo -e "\n${YELLOW}SKIP${NC}: $label — $reason"
    SKIPPED=$((SKIPPED + 1))
}

# ── Layer 1: Backend ──────────────────────────────────────────────

run_backend() {
    echo -e "\n${CYAN}────────────────────────────────────────${NC}"
    echo -e "${CYAN}  LAYER 1: Backend (platform-api)${NC}"
    echo -e "${CYAN}────────────────────────────────────────${NC}"

    cd "$API"

    run_check "Backend: pytest" \
        python -m pytest tests/ -x --tb=short -q

    run_check "Backend: ruff check" \
        ruff check src tests

    run_check "Backend: ruff format" \
        ruff format --check src tests

    run_check "Backend: mypy" \
        mypy src/ --strict
}

# ── Layer 2: Frontends ────────────────────────────────────────────

run_frontend() {
    echo -e "\n${CYAN}────────────────────────────────────────${NC}"
    echo -e "${CYAN}  LAYER 2: Frontends${NC}"
    echo -e "${CYAN}────────────────────────────────────────${NC}"

    # Regulatory Workbench (has vitest)
    if [ -d "$WORKBENCH" ]; then
        cd "$WORKBENCH"
        run_check "Workbench: typecheck" npm run typecheck
        run_check "Workbench: lint" npm run lint
        run_check "Workbench: build" npm run build
        if grep -q '"test:run"' package.json 2>/dev/null; then
            run_check "Workbench: vitest" npm run test:run
        fi
    else
        skip_check "Workbench" "directory not found"
    fi

    # Crypto Risk Console
    if [ -d "$RISK_CONSOLE" ]; then
        cd "$RISK_CONSOLE"
        run_check "Risk Console: typecheck" npm run typecheck
        run_check "Risk Console: lint" npm run lint
        run_check "Risk Console: build" npm run build
    else
        skip_check "Risk Console" "directory not found"
    fi

    # Digital Assets Cross-Border
    if [ -d "$CROSS_BORDER" ]; then
        cd "$CROSS_BORDER"
        run_check "Cross-Border: typecheck" npm run typecheck
        run_check "Cross-Border: lint" npm run lint
        run_check "Cross-Border: build" npm run build
    else
        skip_check "Cross-Border" "directory not found"
    fi
}

# ── Layer 3: Infrastructure ───────────────────────────────────────

run_infra() {
    echo -e "\n${CYAN}────────────────────────────────────────${NC}"
    echo -e "${CYAN}  LAYER 3: Infrastructure${NC}"
    echo -e "${CYAN}────────────────────────────────────────${NC}"

    if [ -d "$INFRA/terraform" ]; then
        cd "$INFRA/terraform"
        if [ -d ".terraform" ]; then
            run_check "Infra: terraform validate" terraform validate
        else
            skip_check "Infra: terraform validate" "not initialized (run terraform init)"
        fi
    else
        skip_check "Infra: terraform" "directory not found"
    fi

    if [ -d "$INFRA/kube" ]; then
        cd "$INFRA"
        if command -v kustomize &>/dev/null; then
            run_check "Infra: kustomize build (local)" \
                kustomize build kube/overlays/local
        elif command -v kubectl &>/dev/null; then
            run_check "Infra: kubectl kustomize (local)" \
                kubectl kustomize kube/overlays/local
        else
            skip_check "Infra: kustomize" "neither kustomize nor kubectl found"
        fi
    fi
}

# ── Layer 4: Deployment Verification ─────────────────────────────

run_deploy() {
    echo -e "\n${CYAN}────────────────────────────────────────${NC}"
    echo -e "${CYAN}  LAYER 4: Deployment Verification${NC}"
    echo -e "${CYAN}────────────────────────────────────────${NC}"

    local script="$API/scripts/verify-deployment.sh"
    if [ -f "$script" ]; then
        if [ -n "${DEPLOY_URL:-}" ]; then
            run_check "Deploy: full-stack verification" \
                bash "$script" "$DEPLOY_URL"
        else
            skip_check "Deploy verification" "DEPLOY_URL not set"
        fi
    else
        skip_check "Deploy verification" "scripts/verify-deployment.sh not found"
    fi
}

# ── Layer 5: Contract Check ───────────────────────────────────────

run_contract() {
    echo -e "\n${CYAN}────────────────────────────────────────${NC}"
    echo -e "${CYAN}  LAYER 5: API Contract Validation${NC}"
    echo -e "${CYAN}────────────────────────────────────────${NC}"

    local script="$API/scripts/check-api-contracts.py"
    if [ -f "$script" ]; then
        cd "$API"
        run_check "Contract: frontend ↔ backend routes" \
            python "$script"
    else
        skip_check "Contract check" "scripts/check-api-contracts.py not found"
    fi
}

# ── Summary ───────────────────────────────────────────────────────

print_summary() {
    echo -e "\n${CYAN}════════════════════════════════════════${NC}"
    echo -e "${CYAN}  SUMMARY${NC}"
    echo -e "${CYAN}════════════════════════════════════════${NC}"
    echo -e "  ${GREEN}Passed${NC}:  $PASSED"
    echo -e "  ${RED}Failed${NC}:  $FAILED"
    echo -e "  ${YELLOW}Skipped${NC}: $SKIPPED"

    if [ ${#FAILURES[@]} -gt 0 ]; then
        echo -e "\n  ${RED}Failures:${NC}"
        for f in "${FAILURES[@]}"; do
            echo -e "    - $f"
        done
        echo ""
        return 1
    else
        echo -e "\n  ${GREEN}All checks passed.${NC}\n"
        return 0
    fi
}

# ── Main ──────────────────────────────────────────────────────────

TARGET="${1:-all}"

case "$TARGET" in
    backend)  run_backend ;;
    frontend) run_frontend ;;
    infra)    run_infra ;;
    deploy)   run_deploy ;;
    contract) run_contract ;;
    all)
        run_backend
        run_frontend
        run_infra
        run_deploy
        run_contract
        ;;
    *)
        echo "Usage: $0 {all|backend|frontend|infra|deploy|contract}"
        exit 1
        ;;
esac

print_summary
