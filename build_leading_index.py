#!/usr/bin/env python3
"""build_leading_index.py — State + national leading economic indices.

Conference Board LEI + state-level coincident indices = recession
probability gauge. LEI diffusion <50 for 3+ months = recession signal.
Moves defensive (XLP, XLU, XLV), gold (GLD, GDX), long duration bonds
(TLT). State indices flag regional banks under stress (KRE).

Source: FRED USSLIND (monthly), CFNAI (monthly), STLFSI4 (weekly),
USRECD (daily recession dummy). Prior implementation naive-joined
dates across different frequencies, producing +0.00 for every LEI
value. Fixed here by bucketing to year-month and taking last obs.

Output: leading_index.csv
Columns: month, lei, cfnai, stlfsi, recession_flag, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import subprocess
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "leading_index.csv"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

SERIES = [
    ("lei", "USSLIND"),       # monthly
    ("cfnai", "CFNAI"),       # monthly
    ("stlfsi", "STLFSI4"),    # weekly
    ("recession", "USRECD"),  # daily 0/1
]


def fetch(sid: str) -> list[tuple[str, float]]:
    """Fetch FRED series as list of (YYYY-MM-DD, value) pairs.
    Use curl shell-out with HTTP/1.1 and retry — urllib hangs and
    curl's HTTP/2 connection to fredgraph intermittently resets."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    txt = ""
    for attempt in range(3):
        try:
            txt = subprocess.check_output(
                ["curl", "-sSL", "--http1.1", "--max-time", "25",
                 "-A", UA, url],
                stderr=subprocess.DEVNULL,
                timeout=28,
            ).decode("utf-8", errors="ignore")
            if txt.strip():
                break
        except (subprocess.CalledProcessError,
                subprocess.TimeoutExpired) as e:
            if attempt == 2:
                print(f"lei {sid}: {e}")
                return []
    if not txt.strip():
        return []
    out: list[tuple[str, float]] = []
    for line in txt.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[1].strip()
        if v in {".", "", "NaN"} or len(d) < 10:
            continue
        try:
            out.append((d, float(v)))
        except ValueError:
            continue
    return out


def bucket_monthly(obs: list[tuple[str, float]]) -> dict[str, float]:
    """Reduce to one value per YYYY-MM (most recent within month)."""
    by_month: dict[str, float] = {}
    for d, v in obs:
        ym = d[:7]  # YYYY-MM
        by_month[ym] = v  # observations are date-sorted ascending, so last wins
    return by_month


def main() -> None:
    monthly = {alias: bucket_monthly(fetch(sid)) for alias, sid in SERIES}
    # Use LEI (primary signal) as the spine; only emit months where LEI exists.
    lei_months = sorted(monthly["lei"].keys(), reverse=True)[:36]
    rows: list[dict] = []
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for ym in lei_months:
        rows.append({
            "month": ym,
            "lei": f"{monthly['lei'].get(ym, 0):+.2f}",
            "cfnai": (f"{monthly['cfnai'][ym]:+.2f}"
                      if ym in monthly["cfnai"] else ""),
            "stlfsi": (f"{monthly['stlfsi'][ym]:+.2f}"
                       if ym in monthly["stlfsi"] else ""),
            "recession_flag": (f"{monthly['recession'][ym]:.0f}"
                               if ym in monthly["recession"] else ""),
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "lei", "cfnai", "stlfsi",
                "recession_flag", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"leading: {len(rows)} months | latest {latest.get('month','?')} "
          f"lei={latest.get('lei','?')} cfnai={latest.get('cfnai','?')} "
          f"stlfsi={latest.get('stlfsi','?')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
