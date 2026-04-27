#!/usr/bin/env python3
"""spoke_bedrock.py — FMP Fundamentals Layer (Phase 4 Data Tether).

Fetches company profiles and income statements from Financial Modeling Prep,
enriches entity_master.json and writes .fmp_bedrock_cache.json with:

  • Accurate sector / industry (fixes UNCLASSIFIED nodes)
  • Market-cap derived gravity (replaces static scores)
  • Live price + day change % (for HUD Intelligence Card)
  • Revenue / net income / EPS (for Claude Haiku AI context)

Architecture:
  Profiles fetched in batches of 100 (FMP supports CSV symbol lists)
  → ~20 HTTP calls for 2,000 tickers instead of 2,000 individual calls
  Income statements fetched only for top-N tickers by gravity (default 500)
  entity_master.json patched in-place so HUD picks up sectors immediately

Run:
  python3 spoke_bedrock.py                 — full sweep (resumes from cache)
  python3 spoke_bedrock.py --force         — ignore cache, re-fetch everything
  python3 spoke_bedrock.py --top=500       — top N by gravity only
  python3 spoke_bedrock.py --ticker=ACHR   — single ticker test
  python3 spoke_bedrock.py --dry-run       — plan only, no writes

Schedule: Nightly at midnight via cerebro-bedrock.timer
API key:  set FMP_API_KEY env var  OR  write to .fmp_env  (FMP_API_KEY=xxx)
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent

ENTITY_MASTER    = ROOT / "entity_master.json"
BEDROCK_CACHE    = ROOT / ".fmp_bedrock_cache.json"
FMP_ENV_FILE     = ROOT / ".fmp_env"

FMP_BASE         = "https://financialmodelingprep.com/stable"
FMP_V3_BASE      = "https://financialmodelingprep.com/api/v3"
INCOME_TOP_N     = 500    # Only fetch income statements for top N by gravity
ETF_TOP_N        = 300    # Only fetch ETF holders for top N by gravity
RATE_DELAY       = 0.5    # seconds between calls (~2 req/s, safe for FMP free/starter)
RETRY_DELAYS     = (5, 15)      # backoff on 429 — shorter to avoid blocking pipeline
REQUEST_TIMEOUT  = 20
ETF_429_LIMIT    = 10           # skip remaining ETF lookups after this many 429s
_etf_429_count   = 0            # global counter for consecutive ETF rate limits

# ── Sector normalisation → Cerebro internal names ────────────────────────────
_SECTOR_MAP = {
    "Technology":                "tech",
    "Information Technology":    "tech",
    "Semiconductors":            "semis",
    "Healthcare":                "biotech",
    "Biotechnology":             "biotech",
    "Financial Services":        "financials",
    "Financials":                "financials",
    "Energy":                    "energy",
    "Basic Materials":           "materials",
    "Materials":                 "materials",
    "Industrials":               "industrials",
    "Consumer Cyclical":         "consumer",
    "Consumer Defensive":        "staples",
    "Communication Services":    "comms",
    "Utilities":                 "utilities",
    "Real Estate":               "real_estate",
}

def _normalise_sector(fmp_sector: str) -> str:
    return _SECTOR_MAP.get(fmp_sector, fmp_sector.lower().replace(" ", "_") if fmp_sector else "unknown")

# ── Gravity / cap tier from market cap ───────────────────────────────────────
def _gravity_from_mcap(mcap: float) -> float:
    """Log-scale gravity: $1T → ~100, $10B → ~31, $1B → ~10, $100M → ~4"""
    if mcap <= 0:
        return 1.0
    return round(max(1.0, (mcap / 1_000_000) ** 0.3), 2)

def _cap_tier(mcap: float) -> str:
    if mcap >= 200e9: return "mega"
    if mcap >= 10e9:  return "large"
    if mcap >= 2e9:   return "mid"
    if mcap >= 300e6: return "small"
    return "micro"

# ── API key loading ───────────────────────────────────────────────────────────
def _load_api_key() -> str:
    key = os.environ.get("FMP_API_KEY", "")
    if key:
        return key
    if FMP_ENV_FILE.exists():
        for line in FMP_ENV_FILE.read_text().splitlines():
            if line.startswith("FMP_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""

# ── FMP fetchers ──────────────────────────────────────────────────────────────
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "CerebroBedrockSpoke/1.0"})

def _fetch_profile(ticker: str, api_key: str) -> dict:
    """Fetch profile for a single ticker with 429 backoff retry."""
    url = f"{FMP_BASE}/profile?symbol={ticker}&apikey={api_key}"
    for attempt, backoff in enumerate((0, *RETRY_DELAYS)):
        if backoff:
            print(f"  RATE LIMIT — waiting {backoff}s before retry {attempt}/{len(RETRY_DELAYS)} ({ticker})", file=sys.stderr)
            time.sleep(backoff)
        try:
            resp = _SESSION.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                continue  # backoff loop handles it
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0]
            if isinstance(data, dict) and data.get("Error Message"):
                print(f"  WARN FMP: {data['Error Message'][:80]}", file=sys.stderr)
            return {}
        except Exception as e:
            if "429" in str(e):
                continue
            print(f"  WARN profile {ticker}: {e}", file=sys.stderr)
            return {}
    print(f"  SKIP {ticker}: exhausted retries", file=sys.stderr)
    return {}


def _fetch_income(ticker: str, api_key: str) -> dict:
    """Fetch most recent annual income statement for a single ticker."""
    url = f"{FMP_BASE}/income-statement?symbol={ticker}&limit=1&apikey={api_key}"
    try:
        resp = _SESSION.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0]
    except Exception as e:
        print(f"  WARN income {ticker}: {e}", file=sys.stderr)
    return {}


def _fetch_etf_holders(ticker: str, api_key: str) -> list:
    """Fetch which ETFs hold this ticker (top holders by weight). FMP v3 endpoint."""
    global _etf_429_count
    if _etf_429_count >= ETF_429_LIMIT:
        return []  # circuit breaker: too many 429s, skip remaining
    url = f"{FMP_V3_BASE}/etf-holder/{ticker}?apikey={api_key}"
    for attempt, backoff in enumerate((0, *RETRY_DELAYS)):
        if backoff:
            print(f"  RATE LIMIT — waiting {backoff}s before ETF retry {attempt}/{len(RETRY_DELAYS)} ({ticker})", file=sys.stderr)
            time.sleep(backoff)
        try:
            resp = _SESSION.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                _etf_429_count += 1
                if _etf_429_count >= ETF_429_LIMIT:
                    print(f"  ETF circuit breaker tripped ({ETF_429_LIMIT} consecutive 429s) — skipping remaining ETF lookups", file=sys.stderr)
                    return []
                continue
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            _etf_429_count = 0  # reset on success
            data = resp.json()
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            if "429" in str(e):
                _etf_429_count += 1
                if _etf_429_count >= ETF_429_LIMIT:
                    print(f"  ETF circuit breaker tripped — skipping remaining ETF lookups", file=sys.stderr)
                    return []
                continue
            print(f"  WARN etf-holder {ticker}: {e}", file=sys.stderr)
            return []
    return []


def _search_ticker(query: str, api_key: str) -> str | None:
    """Convert a company name query → ticker symbol (used by name-search feature)."""
    url = f"{FMP_BASE}/search?query={requests.utils.quote(query)}&limit=1&apikey={api_key}"
    try:
        resp = _SESSION.get(url, timeout=REQUEST_TIMEOUT)
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0].get("symbol")
    except Exception:
        pass
    return None

# ── Main sweep ────────────────────────────────────────────────────────────────
def build_bedrock(top_n: int | None = None,
                  single_ticker: str | None = None,
                  dry_run: bool = False,
                  force: bool = False) -> None:

    api_key = _load_api_key()
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        print("ERROR: FMP_API_KEY not set. Add to .fmp_env or environment.", file=sys.stderr)
        sys.exit(1)

    # Load current entity master
    if not ENTITY_MASTER.exists():
        print("ERROR: entity_master.json not found.", file=sys.stderr)
        sys.exit(1)
    em: dict = json.loads(ENTITY_MASTER.read_text(encoding="utf-8"))

    # Load existing bedrock cache (for incremental updates)
    bedrock: dict = {}
    if BEDROCK_CACHE.exists():
        try:
            bedrock = json.loads(BEDROCK_CACHE.read_text())
        except Exception:
            pass

    # Determine target tickers
    if single_ticker:
        targets = [single_ticker.upper()]
    else:
        # Sort by existing gravity desc so high-priority tickers process first
        all_tickers = list(em.keys())
        all_tickers.sort(key=lambda t: -(em[t].get("gravity", 0) or 0))
        targets = all_tickers[:top_n] if top_n else all_tickers

    # Skip already-cached tickers unless --force (resume interrupted runs)
    if not force and not single_ticker:
        full_len = len(targets)
        targets = [t for t in targets if t not in bedrock]
        skipped = full_len - len(targets)
        if skipped:
            print(f"  Resume mode: skipping {skipped} already-cached tickers (--force to override)")

    print(f"[spoke_bedrock] {datetime.now(timezone.utc).isoformat()}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'LIVE'} | Targets: {len(targets)} tickers")

    if dry_run:
        print(f"  Would batch-fetch {math.ceil(len(targets)/BATCH_SIZE)} profile calls")
        print(f"  Would fetch {min(len(targets), INCOME_TOP_N)} income statements")
        return

    # ── Phase 1: Profile sweep (one call per ticker — stable API no CSV batch) ─
    print(f"\n  Phase 1: Profile sweep ({len(targets)} tickers)...")
    updated = 0
    for i, ticker in enumerate(targets):
        prof = _fetch_profile(ticker, api_key)
        if prof:
            mcap  = prof.get("marketCap") or 0
            price = prof.get("price") or 0.0
            chg   = prof.get("changePercentage") or 0.0
            sector_raw   = prof.get("sector", "")
            industry     = prof.get("industry", "")
            company_name = prof.get("companyName", "")

            bedrock.setdefault(ticker, {}).update({
                "sector_fmp": sector_raw,
                "sector":     _normalise_sector(sector_raw),
                "industry":   industry,
                "gravity":    _gravity_from_mcap(mcap),
                "cap_tier":   _cap_tier(mcap),
                "mcap":       mcap,
                "price":      round(price, 2),
                "day_change": round(chg, 3),
                "name":       company_name or em.get(ticker, {}).get("name", ""),
                "ts":         datetime.now(timezone.utc).isoformat(),
            })
            updated += 1

        # Progress + checkpoint every 100
        if (i + 1) % 100 == 0:
            pct = round((i + 1) / len(targets) * 100)
            print(f"    [{i+1}/{len(targets)}] {pct}% — {updated} profiles synced")
            BEDROCK_CACHE.write_text(json.dumps(bedrock, indent=2))

        time.sleep(RATE_DELAY)

    # ── Phase 2: Income statements for top tickers ────────────────────────────
    # Sort targets by new gravity desc, take top INCOME_TOP_N
    income_targets = sorted(
        [t for t in targets if bedrock.get(t, {}).get("gravity", 0) > 5],
        key=lambda t: -bedrock.get(t, {}).get("gravity", 0)
    )[:INCOME_TOP_N]

    print(f"\n  Phase 2: Income statements ({len(income_targets)} tickers)...")
    income_updated = 0
    etf_updated    = 0
    for j, ticker in enumerate(income_targets):
        inc = _fetch_income(ticker, api_key)
        if inc:
            bedrock[ticker]["financials"] = {
                "revenue":    inc.get("revenue", 0),
                "net_income": inc.get("netIncome", 0),
                "eps":        inc.get("eps", 0.0),
                "period":     inc.get("period", ""),
                "date":       inc.get("date", ""),
            }
            income_updated += 1

        if (j + 1) % 50 == 0:
            print(f"    [{j+1}/{len(income_targets)}] income statements fetched")
            BEDROCK_CACHE.write_text(json.dumps(bedrock, indent=2))
        time.sleep(RATE_DELAY)

    # ── Phase 2b: ETF canopy — which ETFs hold each top ticker ───────────────
    etf_targets = sorted(
        [t for t in targets if bedrock.get(t, {}).get("gravity", 0) > 5],
        key=lambda t: -bedrock.get(t, {}).get("gravity", 0)
    )[:ETF_TOP_N]

    print(f"\n  Phase 2b: ETF Canopy ({len(etf_targets)} tickers)...")
    etf_updated = 0
    for k, ticker in enumerate(etf_targets):
        # Skip if already cached (resume mode)
        if not force and "etf_overlords" in bedrock.get(ticker, {}):
            continue

        holders = _fetch_etf_holders(ticker, api_key)
        # field names vary by FMP version: 'etf' or 'asset'
        top_etfs = sorted(
            holders, key=lambda x: x.get("weightPercentage", 0) or 0, reverse=True
        )[:5]
        bedrock.setdefault(ticker, {})["etf_overlords"] = [
            {
                "etf":    e.get("etf") or e.get("asset", ""),
                "weight": round(e.get("weightPercentage", 0) or 0, 4),
            }
            for e in top_etfs
            if e.get("etf") or e.get("asset")
        ]
        if top_etfs:
            etf_updated += 1

        if (k + 1) % 50 == 0:
            print(f"    [{k+1}/{len(etf_targets)}] ETF holders fetched — {etf_updated} with data")
            BEDROCK_CACHE.write_text(json.dumps(bedrock, indent=2))
        time.sleep(RATE_DELAY)

    # ── Phase 3: Write back to entity_master.json ─────────────────────────────
    print(f"\n  Phase 3: Patching entity_master.json...")
    em_patched = 0
    for ticker, rec in bedrock.items():
        if ticker not in em:
            continue
        # Update sector (fixes UNCLASSIFIED)
        if rec.get("sector") and rec["sector"] != "unknown":
            old_sector = em[ticker].get("sector", "") or (em[ticker].get("gics") or {}).get("s", "")
            if old_sector != rec["sector"]:
                if isinstance(em[ticker].get("gics"), dict):
                    em[ticker]["gics"]["s"] = rec["sector"]
                else:
                    em[ticker]["sector"] = rec["sector"]
                em_patched += 1
        # Update gravity with market-cap derived value
        if rec.get("gravity"):
            em[ticker]["gravity"] = rec["gravity"]
            em[ticker]["gravity_source"] = "fmp_market_cap"
        if rec.get("mcap"):
            em[ticker]["mkt_cap_usd"] = rec["mcap"]
        # Update cap tier
        if rec.get("cap_tier"):
            em[ticker]["cap_tier"] = rec["cap_tier"]
            em[ticker]["mkt_cap_tier"] = rec["cap_tier"]
        # Update name if blank
        if rec.get("name") and not em[ticker].get("name"):
            em[ticker]["name"] = rec["name"]
        # Update ETF canopy + rogue flag
        # Rogue = no ETF tethers AND no known sector. A stock with a valid sector is never rogue.
        if "etf_overlords" in rec:
            em[ticker]["etf_overlords"] = rec["etf_overlords"]
            has_sector = bool((em[ticker].get("sector") or "").strip() not in ("", "unknown"))
            em[ticker]["is_rogue"] = len(rec["etf_overlords"]) == 0 and not has_sector

    if not dry_run:
        BEDROCK_CACHE.write_text(json.dumps(bedrock, indent=2))
        ENTITY_MASTER.write_text(json.dumps(em, indent=2))

    print(f"\n  ✅ Bedrock sweep complete")
    print(f"     Profiles synced     : {updated}")
    print(f"     Income fetched      : {income_updated}")
    print(f"     ETF canopy tethered : {etf_updated}")
    print(f"     entity_master patches : {em_patched} sector / gravity / ETF updates")
    print(f"     Cache               : {BEDROCK_CACHE}")


if __name__ == "__main__":
    single = next((a.split("=")[1] for a in sys.argv if a.startswith("--ticker=")), None)
    top    = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--top=")), 0)) or None
    dry    = "--dry-run" in sys.argv
    force  = "--force"   in sys.argv
    build_bedrock(top_n=top, single_ticker=single, dry_run=dry, force=force)
