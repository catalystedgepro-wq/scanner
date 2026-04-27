#!/usr/bin/env python3
"""spoke_patents.py — Domain 4: Innovation Spark Ingestor (USPTO Patents).

Scans USPTO PatentsView API for recent patent grants matching companies in
entity_master.json. Injects +10 Velocity into scoring_engine.py with a
180-day exponential decay — the "Innovation Aura" around a node.

Physics:
    Patent grant detected → spark_velocity = +10.0
    Decay: k = log(2)/180 ≈ 0.00385 (half-life = 180 days)
    Visible in HUD as "Glowing IP Orbit" around the node.

Architecture:
    entity_master["name"] → USPTO PatentsView assignee search
    Results cached in patent_sparks.json
    Velocities written to spark_velocities.json (read by scoring_engine)

Data Source: USPTO PatentsView API v2 — free API key required.
    Register at https://patentsview.org/apis/purpose → get free key.
    Add PATENTSVIEW_API_KEY to .sec_email_env

Run: python3 spoke_patents.py [--limit=200] [--days=14] [--dry-run]
Schedule: Every Tuesday (USPTO weekly release day)
Pure stdlib — no requests/pandas.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent

ENTITY_MASTER   = ROOT / "entity_master.json"
PATENT_CACHE    = ROOT / "patent_sparks.json"
SPARK_VELOCITIES = ROOT / "spark_velocities.json"

# Physics constants
PATENT_VELOCITY  = 10.0    # +10 velocity boost per patent grant
PATENT_HALF_LIFE = 180     # days until half-strength
_DECAY_K = math.log(2) / PATENT_HALF_LIFE

# USPTO PatentsView API v2 (free key — register at patentsview.org)
_PV_BASE = "https://search.patentsview.org/api/v1/patent/"


def _load_patentsview_key() -> str:
    """Load PATENTSVIEW_API_KEY from env or .sec_email_env."""
    token = os.environ.get("PATENTSVIEW_API_KEY", "").strip()
    if token:
        return token
    env_path = ROOT / ".sec_email_env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("PATENTSVIEW_API_KEY="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                if token:
                    return token
    return ""


def _get_json(url: str, api_key: str, timeout: int = 20) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={
            "X-Api-Key":  api_key,
            "User-Agent": "CatalystEdge/1.0 contact@catalystedge.com",
            "Accept":     "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as exc:
        print(f"  WARN: {exc}")
    return None


def search_patents(org_name: str, since_date: str, per_page: int = 5,
                   api_key: str = "") -> list[dict]:
    """
    Search USPTO PatentsView v2 for recent patent grants to an organization.
    Returns list of {patent_id, title, date, assignees} dicts.
    """
    if not api_key:
        return []
    q = json.dumps({"_and": [
        {"_text_any": {"assignees.assignee_organization": org_name}},
        {"_gte": {"patent_date": since_date}},
    ]})
    params = urllib.parse.urlencode({
        "q": q,
        "f": json.dumps(["patent_id", "patent_title", "patent_date",
                          "assignees.assignee_organization"]),
        "s": json.dumps([{"patent_date": "desc"}]),
        "o": json.dumps({"size": per_page}),
    })
    url = f"{_PV_BASE}?{params}"
    raw = _get_json(url, api_key)
    if not raw:
        return []
    try:
        d = json.loads(raw)
        patents_list = d.get("patents") or []
        results = []
        for p in patents_list:
            assignees_raw = p.get("assignees") or []
            assignee_names = [
                a.get("assignee_organization", "")
                for a in assignees_raw if a.get("assignee_organization")
            ]
            results.append({
                "patent_id": p.get("patent_id", ""),
                "title":     p.get("patent_title", ""),
                "date":      p.get("patent_date", ""),
                "assignees": assignee_names,
            })
        return results
    except Exception as exc:
        print(f"  WARN: PatentsView parse error for {org_name}: {exc}")
    return []


def compute_patent_velocity(grant_date: str) -> float:
    """
    Compute current velocity contribution from a patent using exponential decay.
    grant_date: ISO date string 'YYYY-MM-DD'
    """
    try:
        gd   = date.fromisoformat(grant_date)
        days = (date.today() - gd).days
        if days < 0:
            days = 0
        return round(PATENT_VELOCITY * math.exp(-_DECAY_K * days), 4)
    except Exception:
        return 0.0


def load_spark_velocities() -> dict:
    if SPARK_VELOCITIES.exists():
        try:
            return json.loads(SPARK_VELOCITIES.read_text())
        except Exception:
            pass
    return {}


def main(limit: int = 200, days: int = 14, dry_run: bool = False) -> None:
    if not ENTITY_MASTER.exists():
        print("spoke_patents: entity_master.json not found")
        return

    entity_master: dict = json.loads(ENTITY_MASTER.read_text(encoding="utf-8"))
    since_date = (date.today() - timedelta(days=days)).isoformat()

    # Load existing patent cache
    patent_cache: dict = {}
    if PATENT_CACHE.exists():
        try:
            patent_cache = json.loads(PATENT_CACHE.read_text())
        except Exception:
            pass

    # Priority: active catalyst tickers + GICS classified
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

    # Select targets with a company name and CIK (US SEC filers)
    targets = [
        (t, r) for t, r in entity_master.items()
        if r.get("name") and r.get("cik") and not r.get("etf")
    ]
    targets.sort(key=lambda x: _priority(x[0]))
    targets = targets[:limit]

    api_key = _load_patentsview_key()
    if not api_key:
        print("spoke_patents: PATENTSVIEW_API_KEY not configured")
        print("  Get a free key: https://patentsview.org/apis/purpose")
        print("  Add to .sec_email_env: PATENTSVIEW_API_KEY=your_key")
        return

    print(f"spoke_patents: scanning {len(targets)} companies | since {since_date} | "
          f"{'DRY RUN' if dry_run else 'LIVE'}")

    if dry_run:
        for t, r in targets[:5]:
            print(f"  Would search: {r['name']} ({t})")
        return

    found_tickers: dict[str, list] = {}
    spark_velo = load_spark_velocities()

    for i, (ticker, rec) in enumerate(targets):
        name = rec.get("name", "")
        # Use first 3 words of company name for better fuzzy matching
        search_name = " ".join(name.split()[:3]).rstrip(".,;")

        # Skip if recently cached
        cached = patent_cache.get(ticker, {})
        if cached.get("checked") == date.today().isoformat():
            patents = cached.get("patents", [])
        else:
            patents = search_patents(search_name, since_date, api_key=api_key)
            patent_cache[ticker] = {
                "checked": date.today().isoformat(),
                "patents": patents,
                "name_searched": search_name,
            }
            time.sleep(0.4)  # rate limit courtesy

        if patents:
            found_tickers[ticker] = patents
            # Compute total velocity contribution
            total_velo = sum(compute_patent_velocity(p["date"]) for p in patents)
            spark_velo.setdefault(ticker, {})["patent"] = round(total_velo, 4)
            spark_velo[ticker]["patent_count"]  = len(patents)
            spark_velo[ticker]["latest_patent"] = patents[0]["date"] if patents else None
            print(f"  {ticker:8s}  {len(patents)} patents  "
                  f"velocity=+{total_velo:.2f}  '{patents[0]['title'][:60]}'")
        else:
            # Clear stale spark if no recent patents
            if ticker in spark_velo and "patent" in spark_velo[ticker]:
                del spark_velo[ticker]["patent"]

        if (i + 1) % 50 == 0:
            PATENT_CACHE.write_text(json.dumps(patent_cache, indent=2))
            SPARK_VELOCITIES.write_text(json.dumps(spark_velo, indent=2))
            print(f"  [{i+1}/{len(targets)}] patents found for {len(found_tickers)} tickers")

    # Final save
    PATENT_CACHE.write_text(json.dumps(patent_cache, indent=2))
    SPARK_VELOCITIES.write_text(json.dumps(spark_velo, indent=2))

    print(f"\nspoke_patents: complete")
    print(f"  Scanned   : {len(targets)} companies")
    print(f"  With patents (last {days}d): {len(found_tickers)}")
    print(f"  Top sparks:")
    top = sorted(found_tickers.items(), key=lambda x: -len(x[1]))[:10]
    for t, ps in top:
        velo = sum(compute_patent_velocity(p["date"]) for p in ps)
        print(f"    {t:8s}  {len(ps)} grants  +{velo:.2f} velocity")


if __name__ == "__main__":
    import sys
    lim     = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--limit=")), "200"))
    days    = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--days=")), "14"))
    dry_run = "--dry-run" in sys.argv
    main(limit=lim, days=days, dry_run=dry_run)
