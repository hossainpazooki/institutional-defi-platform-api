#!/bin/bash
# Generate TypeScript types from the backend OpenAPI spec for all 3 frontends.
#
# Prerequisites:
#   pip install -e ".[dev]"  (for the backend)
#   npm install -g @hey-api/openapi-ts  (or use npx)
#
# Usage:
#   ./scripts/generate-frontend-types.sh

set -euo pipefail

BASE="/c/Users/hossa/dev"
API="$BASE/institutional-defi-platform-api"
SPEC="$API/openapi.json"

WORKBENCH="$BASE/applied-ai-regulatory-workbench/frontend-react"
RISK_CONSOLE="$BASE/crypto-portfolio-risk-console/frontend"
CROSS_BORDER="$BASE/digital-assets-cross-border"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Step 1: Export the OpenAPI spec from the backend
echo -e "${CYAN}Exporting OpenAPI spec from backend...${NC}"
cd "$API"
python scripts/export-openapi.py --output "$SPEC"

# Step 2: Generate types for each frontend
for FRONTEND_DIR in "$WORKBENCH" "$RISK_CONSOLE" "$CROSS_BORDER"; do
    NAME=$(basename "$(dirname "$FRONTEND_DIR")")/$(basename "$FRONTEND_DIR")
    if [ ! -d "$FRONTEND_DIR" ]; then
        echo -e "${RED}SKIP${NC}: $NAME — directory not found"
        continue
    fi

    OUTPUT_DIR="$FRONTEND_DIR/src/api/generated"
    mkdir -p "$OUTPUT_DIR"

    echo -e "${CYAN}Generating types for ${NAME}...${NC}"
    cd "$FRONTEND_DIR"

    # Use npx so we don't require a global install
    npx @hey-api/openapi-ts \
        --input "$SPEC" \
        --output "$OUTPUT_DIR" \
        --client @hey-api/client-axios 2>&1

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}OK${NC}: $NAME → $OUTPUT_DIR"
    else
        echo -e "${RED}FAIL${NC}: $NAME"
    fi
done

echo -e "\n${GREEN}Done.${NC} Generated types are in src/api/generated/ in each frontend."
echo "Import types with: import type { SomeModel } from '@/api/generated'"
