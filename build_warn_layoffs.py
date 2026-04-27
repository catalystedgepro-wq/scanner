#!/usr/bin/env python3
"""build_warn_layoffs.py — WARN Act mass-layoff notices (state-level).

WARN Act requires 60-day notice for layoffs >=50 employees or plant
closure. Each US state publishes its own WARN list. Mass layoffs →
cost-cut rally (bullish) OR distress signal (bearish) depending on ratio
to headcount. Movers: TGT, WFM, AMZN, F, GM, SHOP, SNAP, META precedents.

Sources (free, state-level):
  - California EDD: edd.ca.gov/Jobs_and_Training/warn/Warn-Database.html
  - New York DOL: dol.ny.gov/warn-notices
  - Texas TWC: twc.texas.gov/businesses/warn-act-notices
  - Illinois IDES: ides.illinois.gov/resources/layoff-services/warn.html

CA and NY publish the most, fastest. TX/IL are quarterly laggards.

Output: warn_layoffs.csv
Columns: state, company, city, layoffs, effective_date, reason, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "warn_layoffs.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"


def fetch_ca() -> list[dict]:
    # California EDD publishes Excel; HTML table is harder to parse without pandas.
    # Use their JSON via Socrata-style data.ca.gov mirror.
    url = "https://data.edd.ca.gov/resource/jr5c-ya4g.json?$limit=500&$order=received_date%20DESC"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            import json
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"warn CA: {e}")
        return []
    out = []
    for rec in data if isinstance(data, list) else []:
        out.append({
            "state": "CA",
            "company": (rec.get("company") or rec.get("company_name") or "")[:100],
            "city": (rec.get("city") or "")[:60],
            "layoffs": str(rec.get("layoff_number") or rec.get("no_of_employees") or ""),
            "effective_date": rec.get("effective_date") or rec.get("layoff_date") or "",
            "reason": (rec.get("reason") or rec.get("notice_type") or "layoff")[:60],
        })
    return out


def fetch_ny() -> list[dict]:
    # NY DOL serves HTML; try the WARN JSON endpoint.
    # Fallback: skip if no endpoint responds
    url = "https://dol.ny.gov/warn-notices-by-year"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"warn NY: {e}")
        return []
    out = []
    # crude: table rows with 3+ columns
    rows = re.findall(r"<tr[^>]*>(.+?)</tr>", html, re.S)
    for tr in rows[:60]:
        cells = re.findall(r"<t[dh][^>]*>(.+?)</t[dh]>", tr, re.S)
        if len(cells) < 4:
            continue
        clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        if not any("20" in c for c in clean[:2]):
            continue
        out.append({
            "state": "NY",
            "company": clean[1][:100] if len(clean) > 1 else "",
            "city": "",
            "layoffs": clean[3] if len(clean) > 3 else "",
            "effective_date": clean[0] if clean else "",
            "reason": "warn",
        })
    return out


def main() -> None:
    rows: list[dict] = []
    rows.extend(fetch_ca()[:200])
    rows.extend(fetch_ny()[:80])
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    rows.sort(key=lambda r: r.get("effective_date", ""), reverse=True)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "state", "company", "city", "layoffs",
                "effective_date", "reason", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"warn_layoffs: {len(rows)} notices -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
