#!/usr/bin/env python3
"""Live API contract validator — checks frontend endpoints against deployed OpenAPI spec.

Fetches the OpenAPI spec from a running API instance and validates that every
endpoint called by frontend API clients exists in the live spec.

Usage:
    python scripts/verify-contracts-live.py                          # against localhost:8000
    python scripts/verify-contracts-live.py --url https://alb.url    # against deployed API
    python scripts/verify-contracts-live.py --verbose                # show all matches
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent  # dev/

# ── Frontend repos and their API client directories ──────────────

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

ENDPOINT_PATTERN = re.compile(
    r"""\.(get|post|put|delete|patch)\s*(?:<[^>]*>)?\s*\(\s*[`"']([^`"'$]+)[`"']""",
    re.IGNORECASE,
)


def fetch_openapi_spec(base_url: str) -> dict[str, object]:
    """Fetch OpenAPI spec from running API."""
    url = f"{base_url.rstrip('/')}/openapi.json"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode())  # type: ignore[no-any-return]
    except Exception as e:
        print(f"ERROR: Could not fetch OpenAPI spec from {url}: {e}", file=sys.stderr)
        sys.exit(1)


def extract_spec_routes(spec: dict[str, object]) -> set[str]:
    """Extract all route paths from an OpenAPI spec."""
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return set()
    return set(paths.keys())


def normalize_path(path: str) -> str:
    """Normalize frontend path for comparison with OpenAPI paths.

    Converts template literals like ${ruleId} to {ruleId} style.
    """
    return re.sub(r"\$\{([^}]+)\}", r"{\1}", path)


def path_matches_spec(frontend_path: str, spec_routes: set[str]) -> bool:
    """Check if a frontend path matches any spec route.

    Handles parameterized paths: /rules/{ruleId} matches /rules/{rule_id}.
    """
    normalized = normalize_path(frontend_path)

    # Exact match
    if normalized in spec_routes:
        return True

    # Parameterized match: replace {anything} with a regex
    pattern = re.sub(r"\{[^}]+\}", r"\\{[^}]+\\}", re.escape(normalized))
    pattern = pattern.replace(r"\{", "{").replace(r"\}", "}")
    # Unescape the regex groups we just created
    pattern = re.sub(r"\\\\(\{[^}]+\\})", r"\1", pattern)

    for spec_route in spec_routes:
        # Replace spec params with generic pattern too
        spec_normalized = re.sub(r"\{[^}]+\}", "{_}", spec_route)
        frontend_normalized = re.sub(r"\{[^}]+\}", "{_}", normalized)
        if spec_normalized == frontend_normalized:
            return True

    return False


def extract_frontend_endpoints(api_dir: Path) -> list[tuple[str, str, str, int]]:
    """Extract endpoint calls from frontend files.

    Returns list of (file_path, file_name, endpoint_path, line_number).
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
                if not path.startswith("/"):
                    continue
                endpoints.append((str(f), f.name, path, i))

    return endpoints


def run_validation(base_url: str, verbose: bool = False) -> int:
    """Run live contract validation. Returns number of unmatched endpoints."""
    print("Live API Contract Validation")
    print(f"API: {base_url}")
    print("=" * 60)

    # Fetch live spec
    print(f"\nFetching OpenAPI spec from {base_url}/openapi.json ...")
    spec = fetch_openapi_spec(base_url)
    spec_routes = extract_spec_routes(spec)
    print(f"  Found {len(spec_routes)} routes in spec\n")

    unmatched: list[str] = []
    total = 0
    matched = 0

    for frontend_name, api_dirs in FRONTENDS.items():
        endpoints: list[tuple[str, str, str, int]] = []
        any_found = False
        for api_dir in api_dirs:
            if api_dir.exists():
                any_found = True
                endpoints.extend(extract_frontend_endpoints(api_dir))

        if not endpoints:
            if any_found:
                print(f"  {frontend_name}: no endpoints found")
            else:
                print(f"  {frontend_name}: SKIP (directories not found)")
            continue

        print(f"  {frontend_name}: {len(endpoints)} endpoint calls")
        fe_unmatched = []

        for _file_path, file_name, path, line_no in endpoints:
            total += 1
            if path_matches_spec(path, spec_routes):
                matched += 1
                if verbose:
                    print(f"    OK  {path}  ({file_name}:{line_no})")
            else:
                fe_unmatched.append(f"    {file_name}:{line_no}  →  {path}")
                if verbose:
                    print(f"    ERR {path}  ({file_name}:{line_no}) — not in live spec")

        if fe_unmatched:
            unmatched.extend(fe_unmatched)

    # ── Unused spec routes (informational) ────────────────────────

    # Collect all frontend paths for coverage report
    all_fe_paths: set[str] = set()
    for api_dirs in FRONTENDS.values():
        for api_dir in api_dirs:
            for _, _, path, _ in extract_frontend_endpoints(api_dir):
                all_fe_paths.add(re.sub(r"\$\{[^}]+\}", "{_}", path))

    uncalled = []
    for route in sorted(spec_routes):
        # Skip health/docs/internal routes
        if route in ("/", "/health", "/health/deep", "/ready", "/openapi.json", "/docs", "/redoc"):
            continue
        if not any(path_matches_spec(fp, {route}) for fp in all_fe_paths):
            uncalled.append(route)

    # ── Summary ───────────────────────────────────────────────────

    print("\n" + "=" * 60)
    print(f"  Total frontend endpoints:  {total}")
    print(f"  Matched in live spec:      {matched}")
    print(f"  Unmatched:                 {len(unmatched)}")
    print(f"  Spec routes uncalled:      {len(uncalled)}")

    if unmatched:
        print(f"\n  UNMATCHED ({len(unmatched)}):")
        for u in unmatched:
            print(u)

    if verbose and uncalled:
        print(f"\n  UNCALLED SPEC ROUTES ({len(uncalled)}):")
        for r in uncalled:
            print(f"    {r}")

    if not unmatched:
        print("\n  All frontend API calls match the live spec.\n")

    return len(unmatched)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate frontend API calls against live OpenAPI spec")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the running API")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all matches and uncalled routes")
    args = parser.parse_args()

    issues = run_validation(args.url, verbose=args.verbose)
    # Exit 0 even with issues — informational, not blocking
    sys.exit(0)
