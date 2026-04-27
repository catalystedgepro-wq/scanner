#!/usr/bin/env python3
"""build_securities_litigation.py — federal securities class-action tape.

CourtListener (PACER aggregator) exposes all federal dockets via
their nature-of-suit code. NOS 850 = Securities / Commodities /
Exchange. Each hit is a new securities lawsuit filing — Class action
against a public company, SEC vs. defendant, or derivative suit.

Economic readthrough:
- New shareholder class action -> bearish overhang on named ticker
  (stock-drop discovery window usually 30-180d pre-filing).
- SEC enforcement civil action -> corroborates restatement risk.
- Derivative action -> governance/CEO-pay pressure.
- Southern/Eastern District NY and Delaware are key venues.

Source: CourtListener v4 search API
https://www.courtlistener.com/api/rest/v4/search/

Output: securities_litigation.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "securities_litigation.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

DEF_RE = re.compile(r"\bv\.\s+(.+)$", re.I)


def _defendant(case: str) -> str:
    if not case:
        return ""
    m = DEF_RE.search(case)
    if not m:
        return case[:60]
    return m.group(1).strip()[:60]


def _kind(case: str) -> str:
    up = case.upper()
    if "SECURITIES AND EXCHANGE" in up:
        return "sec_enforcement"
    if "RETIREMENT SYSTEM" in up or "PENSION" in up:
        return "institutional_class"
    if "DERIVATIVE" in up:
        return "derivative"
    return "class_action"


def _fetch() -> list[dict]:
    d_from = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    qs = urllib.parse.urlencode({
        "nature_of_suit": "850",
        "type": "d",
        "order_by": "dateFiled desc",
        "filed_after": d_from,
    })
    url = f"https://www.courtlistener.com/api/rest/v4/search/?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("results", [])
    except Exception as e:
        print(f"securities_litigation: fetch failed: {e}")
        return []


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    results = _fetch()

    rows: list[dict] = []
    for r in results:
        case = r.get("caseName", "") or ""
        filed = r.get("dateFiled", "") or ""
        if not case or not filed:
            continue
        rows.append({
            "date": filed,
            "kind": _kind(case),
            "defendant": _defendant(case),
            "case": case[:140],
            "court": r.get("court", "")[:50],
            "docket": r.get("docketNumber", "")[:30],
            "cause": (r.get("cause") or "")[:60],
            "docket_id": r.get("docket_id", ""),
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"securities_litigation: no fetch, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: r["date"], reverse=True)
    fieldnames = ["date", "kind", "defendant", "case", "court",
                  "docket", "cause", "docket_id", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    kb = " ".join(f"{k}={v}" for k, v in sorted(kinds.items(),
                                                 key=lambda x: -x[1]))
    defs = " | ".join(r["defendant"] for r in rows[:4])
    print(f"securities_litigation: {len(rows)} 30d | {kb} | "
          f"top defs: [{defs}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
