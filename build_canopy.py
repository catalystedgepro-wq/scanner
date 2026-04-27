#!/usr/bin/env python3
"""build_canopy.py — Domain 1: Institutional Canopy (ETF Holdings / Weights).

Assigns ETF membership weights via three free public sources (no API key):

  Phase 1 — Wikipedia S&P 500 constituent list  → SPY weight (0.05%)
  Phase 2 — Wikipedia Nasdaq-100 constituent list → QQQ weight (0.10%)
  Phase 3 — GICS sector classification from entity_master
             → sector ETF (XLK/XLF/XLV/XLE/XLB/XLI/XLU/XLRE/XLY/XLP/XLC)
             → semiconductor sub-industry also gets SMH weight
  Phase 4 — Cap tier (small/micro/nano) → IWM weight (0.01%)

Gravity formula:
    Gravity = (0.40 × log10(MarketCap)/13) + (0.60 × ETF_weights_sum)

Run: python3 build_canopy.py [--dry-run]
Pure stdlib — no requests/pandas/FMP.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).parent


def _get(url: str, timeout: int = 15) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; CatalystEdge/1.0)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as exc:
        print(f"  WARN: {exc}")
    return None


# ── Wikipedia S&P 500 constituent list ───────────────────────────────────────
def fetch_sp500_constituents() -> list[str]:
    """
    Fetch S&P 500 tickers from Wikipedia table (full 500 list, no weights).
    Used for binary SPY membership flag on tickers not in top 10.
    """
    url = ("https://en.wikipedia.org/w/api.php?action=parse"
           "&page=List_of_S%26P_500_companies&prop=wikitext&format=json")
    raw = _get(url)
    if not raw:
        return []
    try:
        d    = json.loads(raw)
        text = d["parse"]["wikitext"]["*"]
        # Extract tickers from the wikitable — they appear as [[NYSE:AAPL|AAPL]]
        import re
        tickers = re.findall(r'\|\s*([A-Z]{1,5})\s*\n', text)
        # Also match common pattern
        tickers += re.findall(r'\b([A-Z]{1,5})\b(?=\s*\|\|)', text)
        return list(set(t for t in tickers if 1 < len(t) <= 5))
    except Exception as exc:
        print(f"  WARN Wikipedia S&P 500: {exc}")
    return []


def fetch_nasdaq100_constituents() -> list[str]:
    """Fetch Nasdaq-100 tickers from Wikipedia."""
    url = ("https://en.wikipedia.org/w/api.php?action=parse"
           "&page=Nasdaq-100&prop=wikitext&format=json")
    raw = _get(url)
    if not raw:
        return []
    try:
        d    = json.loads(raw)
        text = d["parse"]["wikitext"]["*"]
        import re
        tickers = re.findall(r'\|\s*([A-Z]{1,5})\s*\n', text)
        return list(set(t for t in tickers if 1 < len(t) <= 5))
    except Exception as exc:
        print(f"  WARN Wikipedia Nasdaq-100: {exc}")
    return []


# ── Membership weight fallback ────────────────────────────────────────────────
# Index membership weights (average non-top-holding member weight)
_MEMBERSHIP_WEIGHT = {
    "SPY": 0.05,    # ~0.05% average for non-top-10 S&P 500 member
    "QQQ": 0.10,    # ~0.10% average for non-top-10 Nasdaq-100 member
    "IWM": 0.01,    # ~0.01% average for Russell 2000 member (1/2000)
}

# GICS sector short code (from entity_master["gics"]["s"]) → sector ETF + avg member weight
_GICS_SECTOR_ETF: dict[str, tuple[str, float]] = {
    "tech":        ("XLK",  0.20),
    "semis":       ("XLK",  0.20),   # semis are in XLK; also get SMH below
    "financials":  ("XLF",  0.15),
    "biotech":     ("XLV",  0.15),   # health care / biotech
    "energy":      ("XLE",  0.20),
    "materials":   ("XLB",  0.25),
    "industrials": ("XLI",  0.15),
    "utilities":   ("XLU",  0.25),
    "real_estate": ("XLRE", 0.30),
    "consumer":    ("XLY",  0.15),   # consumer discretionary
    "staples":     ("XLP",  0.20),
    "comms":       ("XLC",  0.15),
}


def main(dry_run: bool = False) -> None:
    em_path = ROOT / "entity_master.json"
    if not em_path.exists():
        print("build_canopy: entity_master.json not found")
        return
    entity_master: dict = json.loads(em_path.read_text(encoding="utf-8"))

    print("build_canopy: building institutional canopy via Wikipedia + GICS classification")

    if dry_run:
        print("  [DRY RUN] Would assign canopy via Wikipedia S&P500/NDX + GICS sectors + IWM")
        return

    canopy_map:   dict[str, float] = {}
    etf_coverage: dict[str, list]  = {}

    # ── Phase 1: S&P 500 full membership ─────────────────────────────────────
    print("  Fetching S&P 500 constituents from Wikipedia...")
    sp500 = set(fetch_sp500_constituents())
    print(f"  S&P 500: {len(sp500)} tickers")
    for ticker in sp500:
        canopy_map[ticker] = canopy_map.get(ticker, 0.0) + _MEMBERSHIP_WEIGHT["SPY"]
        etf_coverage.setdefault(ticker, []).append("SPY")
    time.sleep(0.5)

    # ── Phase 2: Nasdaq-100 membership ────────────────────────────────────────
    print("  Fetching Nasdaq-100 constituents from Wikipedia...")
    ndx = set(fetch_nasdaq100_constituents())
    print(f"  Nasdaq-100: {len(ndx)} tickers")
    for ticker in ndx:
        canopy_map[ticker] = canopy_map.get(ticker, 0.0) + _MEMBERSHIP_WEIGHT["QQQ"]
        if "QQQ" not in etf_coverage.get(ticker, []):
            etf_coverage.setdefault(ticker, []).append("QQQ")
    time.sleep(0.5)

    # ── Phase 3: GICS sector ETF membership ──────────────────────────────────
    print("  Assigning sector ETF membership from GICS classification...")
    sector_counts: dict[str, int] = {}
    for ticker, rec in entity_master.items():
        gics = rec.get("gics")
        if not isinstance(gics, dict):
            continue
        sector = gics.get("s", "")
        if not sector or sector not in _GICS_SECTOR_ETF:
            continue
        etf, weight = _GICS_SECTOR_ETF[sector]
        canopy_map[ticker] = canopy_map.get(ticker, 0.0) + weight
        if etf not in etf_coverage.get(ticker, []):
            etf_coverage.setdefault(ticker, []).append(etf)
        sector_counts[etf] = sector_counts.get(etf, 0) + 1

        # Semis sector → also SMH
        if sector == "semis" and "SMH" not in etf_coverage.get(ticker, []):
            canopy_map[ticker] = canopy_map.get(ticker, 0.0) + 0.15
            etf_coverage[ticker].append("SMH")
            sector_counts["SMH"] = sector_counts.get("SMH", 0) + 1

    for etf, cnt in sorted(sector_counts.items()):
        print(f"    {etf}: {cnt} tickers")

    # ── Phase 4: IWM (Russell 2000) — small/micro/nano cap ───────────────────
    print("  Assigning IWM to small/micro/nano-cap tickers...")
    iwm_count = 0
    for ticker, rec in entity_master.items():
        cap_tier = rec.get("mkt_cap_tier", "")
        if cap_tier in ("small", "micro", "nano"):
            canopy_map[ticker] = canopy_map.get(ticker, 0.0) + _MEMBERSHIP_WEIGHT["IWM"]
            if "IWM" not in etf_coverage.get(ticker, []):
                etf_coverage.setdefault(ticker, []).append("IWM")
            iwm_count += 1
    print(f"    IWM: {iwm_count} tickers")

    # ── Phase 5: Update entity_master ─────────────────────────────────────────
    updated = 0
    for ticker, total_weight in canopy_map.items():
        if ticker in entity_master:
            entity_master[ticker]["etf_weights_sum"] = round(total_weight, 6)
            entity_master[ticker]["canopy_etfs"]     = etf_coverage.get(ticker, [])
            updated += 1

    # ── Phase 6: Recompute gravity scores ─────────────────────────────────────
    try:
        from gravity_engine import compute_gravity_batch
        entity_master = compute_gravity_batch(entity_master)
        scored = sum(1 for r in entity_master.values() if r.get("gravity"))
        print(f"build_canopy: gravity recomputed for {scored} tickers")
    except ImportError:
        pass

    em_path.write_text(
        json.dumps(entity_master, indent=2, ensure_ascii=False),
        encoding="utf-8")

    with_canopy = sum(1 for r in entity_master.values()
                      if r.get("etf_weights_sum", 0) > 0)
    top = sorted([(t, r.get("etf_weights_sum", 0), r.get("gravity"))
                  for t, r in entity_master.items()
                  if r.get("etf_weights_sum", 0) > 0],
                 key=lambda x: -(x[1] or 0))[:15]

    print(f"\nbuild_canopy: complete")
    print(f"  Canopy tickers ingested : {len(canopy_map)}")
    print(f"  Matched in UEM          : {updated}")
    print(f"  With ETF weight in UEM  : {with_canopy}")
    print(f"\n  Top 15 by institutional weight:")
    for t, w, g in top:
        print(f"    {t:8s}  weight={w:.4f}%  gravity={g}")


if __name__ == "__main__":
    import sys
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
