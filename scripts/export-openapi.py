#!/usr/bin/env python3
"""Export the FastAPI OpenAPI schema to a JSON file.

Usage:
    python scripts/export-openapi.py                    # writes to openapi.json
    python scripts/export-openapi.py --output spec.json # custom output path
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.main import create_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Export OpenAPI spec")
    parser.add_argument(
        "--output",
        "-o",
        default="openapi.json",
        help="Output file path (default: openapi.json)",
    )
    args = parser.parse_args()

    app = create_app()
    schema = app.openapi()
    output_path = Path(args.output)
    output_path.write_text(json.dumps(schema, indent=2))
    print(f"OpenAPI spec written to {output_path} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
