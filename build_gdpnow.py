#!/usr/bin/env python3
"""build_gdpnow.py — Atlanta Fed GDPNow nowcast (quarterly).

GDPNow is the Atlanta Fed's real-time GDP growth estimate, updated 6-7x
per quarter as key indicators release. Institutional desks watch the
delta between GDPNow and consensus Blue Chip forecast as the primary
macro surprise gauge. When GDPNow diverges from consensus by >1pt, the
rate curve reprices and risk assets rotate (growth vs defensive).

Causal chain: GDPNow upward revision -> yields rise -> banks rally
(JPM/BAC/WFC), regional (KRE), tech growth de-rates (XLK). Downward ->
TLT rally, XLU/XLP defensive rotation, staples outperform.

Source: atlantafed.org/cqer/research/gdpnow.aspx — the page embeds the
full forecast history as an inline JavaScript array ('GDPNow forecast'
series in Highcharts config). Stdlib-only, no API key.

Output: gdpnow.csv
Columns: quarter, gdpnow_estimate, is_latest, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "gdpnow.csv"
PAGE_URL = "https://www.atlantafed.org/cqer/research/gdpnow.aspx"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# The series starts at Q1 2012 (first value in the inline array).
# Every quarter since has one entry; the tail is the live nowcast.
SERIES_START_YEAR = 2012
SERIES_START_Q = 1


def fetch_page() -> str | None:
    req = urllib.request.Request(PAGE_URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"gdpnow: {e}")
        return None


def parse_series(body: str) -> list[float]:
    """Extract the 'GDPNow forecast' numeric array from Highcharts init."""
    m = re.search(
        r"""GDPNow\s+forecast['"]\s*,\s*\[([^\]]+)\]""",
        body,
    )
    if not m:
        return []
    raw = m.group(1)
    out: list[float] = []
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(float(tok))
        except ValueError:
            continue
    return out


def quarter_label(index: int) -> str:
    """Map 0-based series index to 'YYYYqQ' label."""
    total = index  # offset from SERIES_START
    year = SERIES_START_YEAR + (SERIES_START_Q - 1 + total) // 4
    q = ((SERIES_START_Q - 1 + total) % 4) + 1
    return f"{year}-Q{q}"


def main() -> None:
    body = fetch_page() or ""
    vals = parse_series(body)
    if not vals:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 80:
            print(f"gdpnow: parse empty, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
            return
        # Write empty shell so downstream joins don't explode.
        vals = []
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    # Emit the most recent 12 quarters (3 years).
    start = max(0, len(vals) - 12)
    rows: list[dict] = []
    for i in range(start, len(vals)):
        rows.append({
            "quarter": quarter_label(i),
            "gdpnow_estimate": f"{vals[i]:+.2f}",
            "is_latest": "1" if i == len(vals) - 1 else "0",
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["quarter", "gdpnow_estimate",
                        "is_latest", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[-1] if rows else {}
    print(f"gdpnow: {len(rows)} quarters | latest "
          f"{latest.get('quarter','?')} = "
          f"{latest.get('gdpnow_estimate','?')}% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
