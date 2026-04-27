#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the latest sympathy burst status artifact.")
    parser.add_argument("--json", action="store_true", help="Print the raw JSON payload.")
    parser.add_argument(
        "--path",
        default=str(Path(__file__).resolve().parents[1] / "sympathy_burst_status.json"),
        help="Path to sympathy_burst_status.json",
    )
    args = parser.parse_args()

    status_path = Path(args.path)
    if not status_path.exists():
        print(f"sympathy burst status missing: {status_path}")
        return 1

    payload = json.loads(status_path.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        top_sector = payload.get("top_sector") or {}
        print(
            f"active_burst={payload.get('active_burst', False)} "
            f"ui_density_mode={payload.get('ui_density_mode', 'full')} "
            f"sector={top_sector.get('sector', 'none')} "
            f"count={top_sector.get('count', 0)} "
            f"leaders={','.join(top_sector.get('leaders', [])[:3]) or 'none'}"
        )
    return 10 if payload.get("active_burst") else 0


if __name__ == "__main__":
    raise SystemExit(main())
