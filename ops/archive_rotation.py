#!/usr/bin/env python3
"""Nightly archive rotation — keeps the catalyst pipeline disk-healthy.

Complements ops/cleanup_disk.sh which is bash-side coarse cleanup.
This script handles the file families produced by the wire spokes
(PRN/BW/GNW/FederalRegister/DOJ/AlphaVantage), which write daily
*.csv archives that need bounded retention.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
ARCHIVE_DIR = ROOT / "archive" / "wires"

# (glob, retain_days) — files older than retain_days get gzipped + moved to ARCHIVE_DIR.
RULES: list[tuple[str, int]] = [
    ("prnewswire_*.csv", 30),
    ("businesswire_*.csv", 30),
    ("globenewswire_*.csv", 30),
    ("federal_register_*.csv", 60),
    ("doj_press_*.csv", 60),
    ("alphavantage_news_*.csv", 30),
    ("sec_catalyst_*.csv", 60),  # already cleaned by cleanup_disk.sh, double-cover
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate catalyst archive CSVs.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.dry_run:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    today = dt.date.today()
    summary: list[str] = []
    bytes_freed = 0

    for pattern, retain_days in RULES:
        cutoff = today - dt.timedelta(days=retain_days)
        for path in sorted(ROOT.glob(pattern)):
            try:
                m = dt.date.fromisoformat(path.stem.split("_")[-1])
            except (ValueError, IndexError):
                continue
            if m >= cutoff:
                continue
            size = path.stat().st_size
            bytes_freed += size
            target = ARCHIVE_DIR / f"{path.name}.gz"
            if args.dry_run:
                summary.append(f"DRY: would archive {path.name} ({size} bytes)")
                continue
            with path.open("rb") as src, gzip.open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            path.unlink()
            summary.append(f"archived {path.name} → {target.relative_to(ROOT)}")

    print(f"archive_rotation: {len(summary)} files, freed {bytes_freed/1024/1024:.1f}MB")
    for s in summary[-20:]:
        print(f"  {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
