#!/usr/bin/env python3
"""
build_cftc.py — Commodity Futures Trading Commission (CFTC) tape.

Source: Federal Register API filtered on
  conditions[agencies][]=commodity-futures-trading-commission

CFTC regulates US futures, options, and swap markets — $600T notional
derivatives — and has independent enforcement authority for market
manipulation, spoofing, wash trades, and disruptive trading practices.
Every CFTC order, rule proposal, and enforcement release is published
in the Federal Register and moves the underlying commodity + exchange
equities.

Direct equity catalysts:
- DCM / SEF / DCO registration & rule approvals → CME/ICE/NDAQ/CBOE
  exchange fees.
- Position-limit rule-making → COT-sensitive tickers (USO, UNG, GLD).
- Crypto / digital-asset enforcement → COIN/HOOD/MSTR derivative impact.
- Energy-market manipulation penalty → XOM/CVX/OXY/MPC + midstream.
- Spoofing / wash trade enforcement → GS/MS/JPM/DB/BK prop-desk drag.
- Swap dealer / major swap participant designation → bank capital impact.
- Bitcoin / ether futures approval → CME/BITO/BTF/ETHE pathway.
- LIBOR / SOFR transition rule → banks NIM sensitivity.
- Foreign board of trade registration → cross-border flow.
- Customer-funds protection / broker-dealer → IBKR/SCHW/MKTX.

Output: cftc.csv — filed_utc, kind, title, link, summary.

Stdlib only.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://www.federalregister.gov/api/v1/documents"
PER_PAGE = 100
LOOKBACK_DAYS = 60
TIMEOUT = 20
USER_AGENT = "CerebroCatalystEdge/1.0 (admin@catalystedgescanner.com)"

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "cftc.csv"


def _classify(title: str, abstract: str) -> str:
    t = (title + " " + (abstract or "")).lower()

    # Crypto / digital assets
    if any(k in t for k in ("bitcoin", "ethereum", "digital asset",
                             "crypto", "stablecoin", "spot market")):
        return "crypto_derivatives"

    # Market manipulation / enforcement
    if "spoofing" in t or "wash trade" in t or "layering" in t:
        return "spoofing_enforcement"
    if "manipulation" in t and "market" in t:
        return "market_manipulation"
    if "disruptive trading" in t:
        return "disruptive_trading"
    if "civil monetary penalty" in t or "civil penalty" in t:
        return "enforcement_penalty"

    # Position limits
    if "position limit" in t:
        return "position_limits"
    if "position reporting" in t or "large trader" in t:
        return "position_reporting"

    # Swap / clearing
    if "swap dealer" in t or "major swap participant" in t:
        return "swap_dealer"
    if "swap execution" in t or "sef " in t.replace(",", " "):
        return "sef_rule"
    if "clearing organization" in t or " dco " in t.replace(",", " "):
        return "clearing_org"
    if "swap data" in t or "sdr " in t.replace(",", " "):
        return "swap_data_repo"

    # Exchange / DCM
    if "designated contract market" in t or "dcm " in t.replace(",", " "):
        return "dcm_rule"
    if "foreign board of trade" in t or " fbot " in t.replace(",", " "):
        return "foreign_board_trade"

    # Commodity types
    if "agricultural" in t or "grain" in t or "livestock" in t:
        return "ag_futures"
    if "energy" in t and "future" in t:
        return "energy_futures"
    if "metals" in t or "precious metal" in t:
        return "metals_futures"

    # Customer protection
    if "customer fund" in t or "segregation" in t:
        return "customer_protection"
    if "broker-dealer" in t or "introducing broker" in t or "futures commission merchant" in t:
        return "fcm_rule"

    # Whistleblower
    if "whistleblower" in t:
        return "whistleblower"

    # LIBOR / benchmark
    if "libor" in t or "sofr" in t or "benchmark" in t:
        return "benchmark_transition"

    # Climate / ESG
    if "climate" in t or "esg" in t:
        return "climate_esg"

    # Leadership / commissioner
    if "chairman" in t or "commissioner" in t or "nominat" in t or "sworn" in t:
        return "leadership_cftc"

    # Rule-making
    if "final rule" in t:
        return "final_rule"
    if "proposed rule" in t or "notice of proposed" in t:
        return "proposed_rule"
    if "advance notice" in t or "concept release" in t:
        return "concept_release"

    return "cftc_general"


def _fetch_window():
    today = dt.date.today()
    gte = (today - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    params = [
        ("conditions[agencies][]", "commodity-futures-trading-commission"),
        ("conditions[publication_date][gte]", gte),
        ("per_page", str(PER_PAGE)),
        ("order", "newest"),
    ]
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        print(f"[WARN] CFTC fetch failed: {exc}", file=sys.stderr)
        return {}


def _to_utc(pub_date: str) -> str:
    if not pub_date:
        return ""
    try:
        d = dt.date.fromisoformat(pub_date)
        return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return pub_date


def _summary(abstract: str | None, excerpts: str | None, cap: int = 400) -> str:
    text = abstract or excerpts or ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > cap:
        text = text[:cap].rsplit(" ", 1)[0] + "..."
    return text


def main() -> int:
    data = _fetch_window()
    results = data.get("results", []) if isinstance(data, dict) else []

    rows = []
    kinds: dict[str, int] = {}
    for r in results:
        title = (r.get("title") or "").strip()
        if not title:
            continue
        kind = _classify(title, r.get("abstract") or "")
        rows.append({
            "filed_utc": _to_utc(r.get("publication_date", "")),
            "kind": kind,
            "title": title,
            "link": r.get("html_url", "") or r.get("pdf_url", ""),
            "summary": _summary(r.get("abstract"), r.get("excerpts")),
        })
        kinds[kind] = kinds.get(kind, 0) + 1

    rows.sort(key=lambda x: x["filed_utc"], reverse=True)

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["filed_utc", "kind", "title", "link", "summary"])
        w.writeheader()
        w.writerows(rows)

    dist = ", ".join(f"{k}={v}" for k, v in sorted(kinds.items(), key=lambda x: -x[1])[:8])
    print(f"cftc: {len(rows)} rows | {dist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
