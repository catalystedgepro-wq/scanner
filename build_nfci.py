#!/usr/bin/env python3
"""build_nfci.py — Chicago Fed National Financial Conditions Index (weekly).

NFCI measures broad financial stress across 105 inputs: risk, credit,
leverage, money markets, equity/debt markets, banking/shadow banking.
Zero is historic average; positive = tighter than avg, negative = looser.
ANFCI is the same, adjusted for current macro regime (more sensitive).

Signal tripwires used by rates desks:
- NFCI > 0 for 2+ weeks: risk-off, TLT/XLU/XLP outperform
- NFCI dropping <-0.7: excess liquidity, small-caps (IWM) and crypto rally
- ANFCI positive while NFCI negative: regime-relative stress (hedge)
- Credit subindex spike: HYG/JNK selloff, flight to quality in LQD

Source: chicagofed.org/-/media/publications/nfci/nfci-data-series-csv.csv
Direct CSV, weekly Friday close, no auth, 1971→present. Stdlib-only.

Output: nfci.csv
Columns: friday, nfci, anfci, risk, credit, leverage, nonfin_leverage,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nfci.csv"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Chicago Fed direct CSV. Hash appended by CMS.
URL = (
    "https://www.chicagofed.org/-/media/publications/nfci/"
    "nfci-data-series-csv.csv?sc_lang=en"
    "&hash=4EFA8ECC816E4025BACB1FF7E7E5727B"
)


def fetch(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"nfci: {e}")
        return None


def parse_row(cells: list[str]) -> dict | None:
    """Convert 'MM/DD/YYYY' to ISO + cast numeric cols."""
    if len(cells) < 7:
        return None
    try:
        d = dt.datetime.strptime(cells[0].strip(), "%m/%d/%Y").date()
    except ValueError:
        return None
    try:
        vals = [float(c.strip()) if c.strip() else 0.0 for c in cells[1:7]]
    except ValueError:
        return None
    return {
        "friday": d.isoformat(),
        "nfci": f"{vals[0]:+.3f}",
        "anfci": f"{vals[1]:+.3f}",
        "risk": f"{vals[2]:+.3f}",
        "credit": f"{vals[3]:+.3f}",
        "leverage": f"{vals[4]:+.3f}",
        "nonfin_leverage": f"{vals[5]:+.3f}",
    }


def main() -> None:
    body = fetch(URL) or ""
    rows: list[dict] = []
    if body.strip() and not body.lstrip().startswith("<"):
        reader = csv.reader(body.splitlines())
        next(reader, None)  # header
        for cells in reader:
            parsed = parse_row(cells)
            if parsed:
                rows.append(parsed)
    if not rows and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"nfci: fetch empty, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return
    # Last 104 weeks (2 years) — keeps the file under 10KB.
    rows = rows[-104:]
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["friday", "nfci", "anfci", "risk", "credit",
                        "leverage", "nonfin_leverage", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[-1] if rows else {}
    print(f"nfci: {len(rows)} weeks | latest {latest.get('friday','?')} "
          f"nfci={latest.get('nfci','?')} anfci={latest.get('anfci','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
