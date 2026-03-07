#!/usr/bin/env python3
"""API contract validator — checks frontend API calls against backend routes.

Parses frontend API client files for endpoint URLs and compares them against
the FastAPI route definitions in platform-api. Reports mismatches.

Usage:
    python scripts/check-api-contracts.py
    python scripts/check-api-contracts.py --verbose
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent  # dev/

# ── Frontend repos and their API client directories ──────────────
# Each entry maps to a list of directories to scan (some repos have
# API clients spread across feature directories).

FRONTENDS: dict[str, list[Path]] = {
    "regulatory-workbench": [
        BASE / "applied-ai-regulatory-workbench" / "frontend-react" / "src" / "api",
    ],
    "risk-console": [
        BASE / "crypto-portfolio-risk-console" / "frontend" / "src" / "api",
    ],
    "cross-border": [
        BASE / "digital-assets-cross-border" / "src" / "shared" / "api",
        BASE / "digital-assets-cross-border" / "src" / "features",
    ],
}

# ── Known backend route prefixes (from src/main.py) ──────────────

BACKEND_PREFIXES = {
    "/rules",
    "/decide",
    "/verification",
    "/analytics",
    "/decoder",
    "/counterfactual",
    "/qa",
    "/embedding/rules",
    "/navigate",
    "/jurisdiction",
    "/compliance",
    "/risk",
    "/quant",
    "/defi-risk",
    "/research",
    "/token-compliance",
    "/protocol-risk",
    "/trading",
    "/technology",
    "/features",
    "/jpm",
    "/workflows",
    "/v2",
    "/ke",
    "/credit",
    "/health",
    "/",
}

# Patterns that match HTTP method calls in TypeScript/JavaScript API clients
# Matches: .get("/path"), .post("/path"), .put("/path"), .delete("/path"), .patch("/path")
# Also: .get<Type>("/path"), .get(`/path`), .get('/path')
ENDPOINT_PATTERN = re.compile(
    r"""\.(get|post|put|delete|patch)\s*(?:<[^>]*>)?\s*\(\s*[`"']([^`"'$]+)[`"']""",
    re.IGNORECASE,
)

# Pattern to extract the prefix (first path segment) from a route
PREFIX_PATTERN = re.compile(r"^(/[a-z][a-z0-9_-]*)(?:/|$)")


def extract_frontend_endpoints(api_dir: Path) -> list[tuple[str, str, int]]:
    """Extract endpoint paths from frontend API client files.

    Returns list of (file_name, endpoint_path, line_number).
    """
    endpoints = []
    if not api_dir.exists():
        return endpoints

    for f in api_dir.rglob("*"):
        if f.suffix not in (".ts", ".tsx", ".js", ".jsx"):
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue

        for i, line in enumerate(lines, 1):
            for match in ENDPOINT_PATTERN.finditer(line):
                path = match.group(2).strip()
                # Skip non-path strings
                if not path.startswith("/"):
                    continue
                # Normalize template params: /rules/{ruleId} → /rules/{id}
                path = re.sub(r"\$\{[^}]+\}", "{id}", path)
                endpoints.append((f.name, path, i))

    return endpoints


def get_prefix(path: str) -> str | None:
    """Extract the route prefix from a full path."""
    # Special case: exact matches
    if path in ("/", "/health"):
        return path

    m = PREFIX_PATTERN.match(path)
    if m:
        prefix = m.group(1)
        # Handle two-segment prefixes
        for known in BACKEND_PREFIXES:
            if "/" in known[1:] and path.startswith(known):
                return known
        return prefix
    return None


def check_contracts(verbose: bool = False) -> int:
    """Run contract validation. Returns number of issues found."""
    issues: list[str] = []
    total_endpoints = 0
    matched_endpoints = 0

    print("API Contract Validation")
    print("=" * 60)

    for frontend_name, api_dirs in FRONTENDS.items():
        endpoints = []
        any_found = False
        for api_dir in api_dirs:
            if api_dir.exists():
                any_found = True
                endpoints.extend(extract_frontend_endpoints(api_dir))

        if not endpoints:
            if any_found:
                print(f"\n  {frontend_name}: no endpoints found")
            else:
                print(f"\n  {frontend_name}: SKIP (directories not found)")
            continue

        print(f"\n  {frontend_name}: {len(endpoints)} endpoint calls")

        for file_name, path, line_no in endpoints:
            total_endpoints += 1
            prefix = get_prefix(path)

            if prefix and prefix in BACKEND_PREFIXES:
                matched_endpoints += 1
                if verbose:
                    print(f"    OK  {path}  ({file_name}:{line_no})")
            else:
                issues.append(f"    {frontend_name}/{file_name}:{line_no}  →  {path}  (prefix: {prefix})")
                if verbose:
                    print(f"    ERR {path}  ({file_name}:{line_no}) — no matching backend prefix")

    # ── Summary ───────────────────────────────────────────────────

    print("\n" + "=" * 60)
    print(f"  Total endpoints checked: {total_endpoints}")
    print(f"  Matched:                 {matched_endpoints}")
    print(f"  Unmatched:               {len(issues)}")

    if issues:
        print(f"\n  ISSUES ({len(issues)}):")
        for issue in issues:
            print(issue)
        print()
        return len(issues)

    print("\n  All frontend API calls match known backend routes.\n")
    return 0


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    issue_count = check_contracts(verbose=verbose)
    # Exit 0 even with issues — this is informational, not blocking
    sys.exit(0)
