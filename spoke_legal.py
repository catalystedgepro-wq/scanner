#!/usr/bin/env python3
"""spoke_legal.py — Domain 4: Legal Risk Spoke (PACER via CourtListener).

Scans CourtListener (free PACER mirror) for new federal litigation filings
naming companies from entity_master.json. Injects -5 Velocity penalty into
scoring_engine.py — the "Structural Crack" on a node.

Physics:
    New lawsuit detected → crack_velocity = -5.0
    Multiple suits stack: -5 per active suit (capped at -25)
    Decay: k = log(2)/90 (half-life = 90 days — lawsuits resolve faster)
    Visible in HUD as red "Structural Crack" fracture lines on the node.

Architecture:
    entity_master["name"] → CourtListener party name search
    Results cached in legal_risk_cache.json
    Penalties written to spark_velocities.json["legal"] (read by scoring_engine)

CourtListener REST API — free, no key required for basic use.
    https://www.courtlistener.com/api/rest/v4/

Run: python3 spoke_legal.py [--limit=200] [--days=30] [--dry-run]
Schedule: Daily (federal courts file continuously)
Pure stdlib — no requests/pandas.
"""
from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent

ENTITY_MASTER    = ROOT / "entity_master.json"
LEGAL_CACHE      = ROOT / "legal_risk_cache.json"
SPARK_VELOCITIES = ROOT / "spark_velocities.json"

# Physics constants
LAWSUIT_VELOCITY  = -5.0   # penalty per active lawsuit
LAWSUIT_CAP       = -25.0  # max stacked penalty
LAWSUIT_HALF_LIFE = 90     # days
_DECAY_K = math.log(2) / LAWSUIT_HALF_LIFE

import os

# CourtListener API v4
_CL_SEARCH = "https://www.courtlistener.com/api/rest/v4/search/"


def _load_cl_token() -> str:
    """Load CL_API_TOKEN from env or .sec_email_env."""
    token = os.environ.get("CL_API_TOKEN", "").strip()
    if token:
        return token
    env_path = ROOT / ".sec_email_env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("CL_API_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                if token:
                    return token
    return ""


def _get(url: str, token: str = "", timeout: int = 15) -> bytes | None:
    try:
        headers = {
            "User-Agent": "CatalystEdge/1.0 contact@catalystedge.com",
            "Accept":     "application/json",
        }
        if token:
            headers["Authorization"] = f"Token {token}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as exc:
        print(f"  WARN: {exc}")
    return None


def search_cases(company_name: str, since_date: str, per_page: int = 5,
                 token: str = "") -> list[dict]:
    """
    Search CourtListener v4 for federal cases naming the company.
    Returns list of {docket_number, case_name, date_filed, court, url}.
    """
    params = urllib.parse.urlencode({
        "q":            company_name,
        "type":         "d",
        "filed_after":  since_date,
        "order_by":     "score desc",
        "page_size":    per_page,
    })
    url = f"{_CL_SEARCH}?{params}"
    raw = _get(url, token=token)
    if not raw:
        return []
    try:
        d       = json.loads(raw)
        results = d.get("results") or []
        cases   = []
        for r in results:
            cases.append({
                "docket_number": r.get("docketNumber", ""),
                "case_name":     r.get("caseName", ""),
                "date_filed":    r.get("dateFiled", ""),
                "court":         r.get("court", ""),
                "url":           "https://www.courtlistener.com" + r.get("docket_absolute_url", ""),
            })
        return cases
    except Exception as exc:
        print(f"  WARN: CourtListener parse error for {company_name}: {exc}")
    return []


def compute_legal_velocity(cases: list[dict]) -> float:
    """
    Compute total legal velocity penalty. Each case contributes -5.0 × decay.
    Stacked penalties capped at LAWSUIT_CAP.
    """
    total = 0.0
    for case in cases:
        filed = case.get("date_filed", "")
        try:
            fd   = date.fromisoformat(filed)
            days = max(0, (date.today() - fd).days)
            total += LAWSUIT_VELOCITY * math.exp(-_DECAY_K * days)
        except Exception:
            total += LAWSUIT_VELOCITY
    return round(max(total, LAWSUIT_CAP), 4)


def load_spark_velocities() -> dict:
    if SPARK_VELOCITIES.exists():
        try:
            return json.loads(SPARK_VELOCITIES.read_text())
        except Exception:
            pass
    return {}


# ── SEC Enforcement Fallback (no token required) ─────────────────────────────

_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
_EFTS_HEADERS = {
    "User-Agent": "CatalystEdge/1.0 contact@catalystedge.com",
    "Accept": "application/json",
}

def _fetch_sec_enforcement(since_date: str) -> list[dict]:
    """Fetch recent SEC enforcement actions from EDGAR Full-Text Search.
    Free, no API key required."""
    import re
    import sys

    results: list[dict] = []
    queries = [
        ("enforcement", "litigation+release"),
        ("admin", "administrative+proceeding"),
        ("suspension", "trading+suspension"),
    ]
    for category, query_term in queries:
        url = (
            f"{_EFTS_URL}?q=%22{query_term}%22"
            f"&dateRange=custom&startdt={since_date}&enddt={date.today().isoformat()}"
        )
        try:
            req = urllib.request.Request(url, headers=_EFTS_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            print(f"    SEC EFTS {category} error: {e}", file=sys.stderr)
            continue

        hits = data.get("hits", {}).get("hits", [])
        for hit in hits[:20]:
            source = hit.get("_source", {})
            display = source.get("display_names", [])
            title = display[0] if display else source.get("file_description", "")
            # Strip HTML tags
            title = re.sub(r"<[^>]+>", " ", str(title)).strip()

            results.append({
                "case_name": title[:120],
                "date_filed": source.get("file_date", ""),
                "url": source.get("file_url", ""),
                "category": category,
                "docket_number": "",
                "court": "SEC",
            })
        time.sleep(0.5)

    print(f"  SEC enforcement actions fetched: {len(results)}")
    return results


def _match_sec_enforcement(actions: list[dict], entity_master: dict) -> dict[str, list[dict]]:
    """Match SEC enforcement actions to entity_master tickers by company name."""
    import re

    name_index: dict[str, str] = {}
    for ticker, rec in entity_master.items():
        name = rec.get("name", "").strip()
        if not name or rec.get("etf"):
            continue
        name_lower = name.lower()
        words = name_lower.split()
        if len(words) >= 2:
            name_index[" ".join(words[:2])] = ticker
        if len(words) >= 3:
            name_index[" ".join(words[:3])] = ticker

    matches: dict[str, list[dict]] = {}
    for action in actions:
        text = action.get("case_name", "").lower()
        # Try ticker symbol patterns
        for ticker in entity_master:
            if len(ticker) < 2:
                continue
            if re.search(rf'\b{re.escape(ticker)}\b', text, re.IGNORECASE):
                matches.setdefault(ticker, []).append(action)
                break
        # Try company name matching
        for name_key, ticker in name_index.items():
            if len(name_key) >= 6 and name_key in text:
                if ticker not in matches or action not in matches.get(ticker, []):
                    matches.setdefault(ticker, []).append(action)

    return matches


def main(limit: int = 200, days: int = 30, dry_run: bool = False) -> None:
    if not ENTITY_MASTER.exists():
        print("spoke_legal: entity_master.json not found")
        return

    entity_master: dict = json.loads(ENTITY_MASTER.read_text(encoding="utf-8"))
    since_date = (date.today() - timedelta(days=days)).isoformat()

    # Load caches
    legal_cache: dict = {}
    if LEGAL_CACHE.exists():
        try:
            legal_cache = json.loads(LEGAL_CACHE.read_text())
        except Exception:
            pass

    # Priority sort: active catalyst tickers first
    active: set[str] = set()
    for fname in ("sec_catalyst_tickers.txt", "combined_priority_tickers.txt"):
        p = ROOT / fname
        if p.exists():
            active.update(l.strip().upper() for l in p.read_text().splitlines() if l.strip())

    def _priority(t: str) -> int:
        if t in active:
            return 0
        if entity_master.get(t, {}).get("gics"):
            return 1
        return 2

    targets = [
        (t, r) for t, r in entity_master.items()
        if r.get("name") and not r.get("etf")
    ]
    targets.sort(key=lambda x: _priority(x[0]))
    targets = targets[:limit]

    token = _load_cl_token()
    source = "courtlistener" if token else "sec_enforcement"

    if not token:
        print("spoke_legal: CL_API_TOKEN not set — using SEC enforcement RSS (free, no key)")
        print("  For richer data: register at courtlistener.com and add CL_API_TOKEN to .sec_email_env")

    print(f"spoke_legal: scanning {len(targets)} companies | since {since_date} | "
          f"source={source} | {'DRY RUN' if dry_run else 'LIVE'}")

    if dry_run:
        for t, r in targets[:5]:
            print(f"  Would search: {r['name']} ({t})")
        return

    risky_tickers: dict[str, list] = {}
    spark_velo = load_spark_velocities()

    # ── SEC Enforcement fallback (no key required) ──
    # Fetch recent SEC enforcement/litigation releases and match to tickers
    if not token:
        sec_actions = _fetch_sec_enforcement(since_date)
        if sec_actions:
            matched = _match_sec_enforcement(sec_actions, entity_master)
            for ticker, actions in matched.items():
                risky_tickers[ticker] = actions
                penalty = LAWSUIT_VELOCITY * len(actions)
                penalty = max(penalty, LAWSUIT_CAP)
                spark_velo.setdefault(ticker, {})["legal"] = round(penalty, 4)
                spark_velo[ticker]["legal_case_count"] = len(actions)
                spark_velo[ticker]["latest_case"] = actions[0].get("date_filed", date.today().isoformat())
                spark_velo[ticker]["latest_case_name"] = actions[0].get("case_name", "SEC Action")[:80]
                print(f"  ⚖️ {ticker:8s}  {len(actions)} SEC actions  "
                      f"penalty={penalty:.2f}  '{actions[0].get('case_name', '')[:55]}'")

        LEGAL_CACHE.write_text(json.dumps(legal_cache, indent=2))
        SPARK_VELOCITIES.write_text(json.dumps(spark_velo, indent=2))
        print(f"\nspoke_legal: complete (SEC enforcement mode)")
        print(f"  Matched tickers with actions: {len(risky_tickers)}")
        return

    for i, (ticker, rec) in enumerate(targets):
        name = rec.get("name", "")
        # Use first 2-3 words — legal filings use formal entity names
        search_name = " ".join(name.split()[:3]).rstrip(".,;")

        # Skip if recently cached (check daily)
        cached = legal_cache.get(ticker, {})
        if cached.get("checked") == date.today().isoformat():
            cases = cached.get("cases", [])
        else:
            cases = search_cases(search_name, since_date, token=token)
            legal_cache[ticker] = {
                "checked": date.today().isoformat(),
                "cases":   cases,
                "name_searched": search_name,
            }
            time.sleep(0.5)  # CourtListener rate limit

        if cases:
            risky_tickers[ticker] = cases
            penalty = compute_legal_velocity(cases)
            spark_velo.setdefault(ticker, {})["legal"]       = penalty
            spark_velo[ticker]["legal_case_count"]  = len(cases)
            spark_velo[ticker]["latest_case"]       = cases[0]["date_filed"]
            spark_velo[ticker]["latest_case_name"]  = cases[0]["case_name"][:80]
            print(f"  {ticker:8s}  {len(cases)} cases  "
                  f"penalty={penalty:.2f}  '{cases[0]['case_name'][:55]}'")
        else:
            if ticker in spark_velo and "legal" in spark_velo[ticker]:
                del spark_velo[ticker]["legal"]

        if (i + 1) % 50 == 0:
            LEGAL_CACHE.write_text(json.dumps(legal_cache, indent=2))
            SPARK_VELOCITIES.write_text(json.dumps(spark_velo, indent=2))
            print(f"  [{i+1}/{len(targets)}] legal risk on {len(risky_tickers)} tickers")

    # Final save
    LEGAL_CACHE.write_text(json.dumps(legal_cache, indent=2))
    SPARK_VELOCITIES.write_text(json.dumps(spark_velo, indent=2))

    print(f"\nspoke_legal: complete")
    print(f"  Scanned   : {len(targets)} companies")
    print(f"  With active cases (last {days}d): {len(risky_tickers)}")
    print(f"  Top penalties:")
    top = sorted(risky_tickers.items(),
                 key=lambda x: compute_legal_velocity(x[1]))[:10]
    for t, cs in top:
        pen = compute_legal_velocity(cs)
        print(f"    {t:8s}  {len(cs)} cases  {pen:.2f} velocity  "
              f"'{cs[0]['case_name'][:50]}'")


if __name__ == "__main__":
    import sys
    lim     = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--limit=")), "200"))
    days    = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--days=")), "30"))
    dry_run = "--dry-run" in sys.argv
    main(limit=lim, days=days, dry_run=dry_run)
