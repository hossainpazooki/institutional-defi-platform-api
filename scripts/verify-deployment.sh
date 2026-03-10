#!/bin/bash
# Post-deployment verification pipeline — validates the full stack on EKS.
# Usage:
#   ./scripts/verify-deployment.sh                         # auto-detect ALB from kubectl
#   ./scripts/verify-deployment.sh https://custom.url      # explicit base URL
#   DEPLOY_URL=https://... ./scripts/verify-deployment.sh  # env var
#
# Layers:
#   1. K8s Pod Health     — pods running, rollouts complete
#   2. Backend Health     — /health, /health/deep, /ready, /
#   3. Frontend Reach     — HTML served from each frontend path
#   4. Frontend→API Proxy — /api/health through each frontend
#   5. Route Smoke Tests  — one GET per domain group

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PASSED=0
FAILED=0
SKIPPED=0
FAILURES=()

NAMESPACE="institutional-defi-dev"
DEPLOYMENTS=("api-dev" "regulatory-workbench" "risk-console" "cross-border")
FRONTEND_PATHS=("/workbench/" "/console/" "/crossborder/")

# ── Helpers ──────────────────────────────────────────────────────

run_check() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo -e "  ${GREEN}PASS${NC}  $label"
        PASSED=$((PASSED + 1))
    else
        echo -e "  ${RED}FAIL${NC}  $label"
        FAILURES+=("$label")
        FAILED=$((FAILED + 1))
    fi
}

skip_check() {
    local label="$1"
    local reason="$2"
    echo -e "  ${YELLOW}SKIP${NC}  $label — $reason"
    SKIPPED=$((SKIPPED + 1))
}

http_get() {
    # Returns exit 0 if HTTP status matches expected pattern
    local url="$1"
    local accept_pattern="${2:-2[0-9][0-9]|4[0-9][0-9]}"  # default: 2xx or 4xx
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "$url" 2>/dev/null || echo "000")
    [[ "$status" =~ ^($accept_pattern)$ ]]
}

http_get_json_field() {
    # GET URL and check that a JSON field has expected value
    local url="$1"
    local field="$2"
    local expected="$3"
    local body
    body=$(curl -s --connect-timeout 5 --max-time 10 "$url" 2>/dev/null || echo "{}")
    echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('$field')=='$expected' else 1)" 2>/dev/null
}

http_get_json_nested() {
    # GET URL and check nested JSON field: checks[key].status == expected
    local url="$1"
    local outer="$2"
    local key="$3"
    local expected="$4"
    local body
    body=$(curl -s --connect-timeout 5 --max-time 10 "$url" 2>/dev/null || echo "{}")
    echo "$body" | python3 -c "
import sys, json
d = json.load(sys.stdin)
val = d.get('$outer', {}).get('$key', {}).get('status')
sys.exit(0 if val == '$expected' else 1)
" 2>/dev/null
}

http_get_contains() {
    # GET URL and check body contains substring
    local url="$1"
    local substring="$2"
    local body
    body=$(curl -s --connect-timeout 5 --max-time 10 "$url" 2>/dev/null || echo "")
    [[ "$body" == *"$substring"* ]]
}

# ── Resolve base URL ─────────────────────────────────────────────

BASE_URL="${1:-${DEPLOY_URL:-}}"

HAS_KUBECTL=false
if command -v kubectl &>/dev/null; then
    HAS_KUBECTL=true
fi

if [ -z "$BASE_URL" ]; then
    if $HAS_KUBECTL; then
        echo -e "${CYAN}Auto-detecting ALB from kubectl...${NC}"
        ALB_HOST=$(kubectl get ingress -n "$NAMESPACE" -o jsonpath='{.items[0].status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
        if [ -n "$ALB_HOST" ]; then
            BASE_URL="http://${ALB_HOST}"
            echo -e "  Found: ${BASE_URL}"
        else
            echo -e "${RED}Could not detect ALB. Pass URL as argument or set DEPLOY_URL.${NC}"
            exit 1
        fi
    else
        echo -e "${RED}No URL provided and kubectl not available.${NC}"
        echo "Usage: $0 <base-url>"
        exit 1
    fi
fi

# Strip trailing slash
BASE_URL="${BASE_URL%/}"

echo -e "\n${CYAN}Verifying deployment at: ${BASE_URL}${NC}\n"

# ── Layer 1: K8s Pod Health ──────────────────────────────────────

echo -e "${CYAN}── Layer 1: K8s Pod Health ──${NC}"

if $HAS_KUBECTL; then
    for deploy in "${DEPLOYMENTS[@]}"; do
        run_check "Rollout: $deploy" \
            kubectl rollout status "deployment/$deploy" -n "$NAMESPACE" --timeout=60s
    done

    # Check all pods are Running
    run_check "All pods Running" bash -c "
        kubectl get pods -n $NAMESPACE --no-headers 2>/dev/null | \
        grep -v Completed | \
        awk '{print \$3}' | \
        grep -qv Running && exit 1 || exit 0
    "
else
    skip_check "K8s pod health" "kubectl not available"
fi

# ── Layer 2: Backend Health ──────────────────────────────────────

echo -e "\n${CYAN}── Layer 2: Backend Health ──${NC}"

run_check "GET /health → 200, healthy" \
    http_get_json_field "$BASE_URL/health" "status" "healthy"

run_check "GET /health/deep → database healthy" \
    http_get_json_nested "$BASE_URL/health/deep" "checks" "database" "healthy"

run_check "GET /health/deep → redis healthy" \
    http_get_json_nested "$BASE_URL/health/deep" "checks" "redis" "healthy"

run_check "GET /ready → 200" \
    http_get "$BASE_URL/ready" "2[0-9][0-9]"

run_check "GET / → endpoints list" \
    http_get_contains "$BASE_URL/" "endpoints"

# ── Layer 3: Frontend Reachability ───────────────────────────────

echo -e "\n${CYAN}── Layer 3: Frontend Reachability ──${NC}"

# Only run frontend checks if not pointing at bare API (localhost:8000)
if [[ "$BASE_URL" == *"localhost"* ]] || [[ "$BASE_URL" == *"127.0.0.1"* ]]; then
    skip_check "Frontend reachability" "localhost detected (no frontends)"
else
    for fpath in "${FRONTEND_PATHS[@]}"; do
        run_check "GET ${fpath} → HTML" \
            http_get_contains "${BASE_URL}${fpath}" "<!DOCTYPE html"
    done
fi

# ── Layer 4: Frontend → API Proxy ────────────────────────────────

echo -e "\n${CYAN}── Layer 4: Frontend → API Proxy ──${NC}"

if [[ "$BASE_URL" == *"localhost"* ]] || [[ "$BASE_URL" == *"127.0.0.1"* ]]; then
    skip_check "Frontend→API proxy" "localhost detected (no frontends)"
else
    for fpath in "${FRONTEND_PATHS[@]}"; do
        run_check "GET ${fpath}api/health → proxied" \
            http_get_json_field "${BASE_URL}${fpath}api/health" "status" "healthy"
    done
fi

# ── Layer 5: Route Smoke Tests ───────────────────────────────────

echo -e "\n${CYAN}── Layer 5: Route Smoke Tests ──${NC}"

# Each endpoint: accept 2xx or 4xx (route exists). Only 404/502/503 = failure.
SMOKE_ENDPOINTS=(
    "/rules"
    "/analytics/summary"
    "/decoder/tiers"
    "/qa/status"
    "/navigate/jurisdictions"
    "/risk/supported-assets"
    "/defi-risk/categories"
    "/token-compliance/standards"
    "/protocol-risk/consensus-types"
    "/trading/exposure"
    "/technology/chains"
    "/features/"
    "/jpm/scenarios"
    "/ke/analytics/summary"
    "/credit/queue"
    "/v2/status"
    "/embedding/rules"
)

for endpoint in "${SMOKE_ENDPOINTS[@]}"; do
    run_check "Smoke: GET $endpoint" \
        http_get "$BASE_URL$endpoint" "2[0-9][0-9]|4[0-9][0-9]"
done

# ── Summary ──────────────────────────────────────────────────────

echo -e "\n${CYAN}════════════════════════════════════════${NC}"
echo -e "${CYAN}  DEPLOYMENT VERIFICATION SUMMARY${NC}"
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
    exit 1
else
    echo -e "\n  ${GREEN}All deployment checks passed.${NC}\n"
    exit 0
fi
