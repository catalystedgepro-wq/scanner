#!/usr/bin/env python3
"""build_tech_status.py — Hyperscaler / AI / SaaS infrastructure
outage tape via Statuspage.io v2 APIs.

Statuspage.io is the dominant public-status vendor. Most major
tech companies expose a public /api/v2/incidents.json feed. A
"critical" incident at AWS or Google Cloud propagates into a
sector-wide latency / availability event that SaaS earnings will
reference the next quarter.

Economic readthrough:
- AWS / GCP / Azure critical incident -> immediate SaaS latency
  complaints (CRWD, NET, DDOG, SNOW, MDB, HUBS).
- OpenAI / Anthropic outage -> immediate AI-exposed ticker drag
  (MSFT, NVDA, CRM, NOW).
- GitHub outage -> developer productivity hit (MSFT).
- Shopify / Stripe outage -> DTC retail revenue loss window
  (SHOP, PYPL, FIS).

Source: Statuspage.io public v2 APIs (no auth)
https://<vendor>.statuspage.io/api/v2/incidents.json

Output: tech_status.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "tech_status.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

VENDORS = [
    # (vendor_key, statuspage url, ticker exposure)
    ("openai", "https://status.openai.com/api/v2/incidents.json",
     "MSFT|NVDA"),
    ("anthropic", "https://status.anthropic.com/api/v2/incidents.json",
     "GOOGL|AMZN"),
    ("cloudflare", "https://www.cloudflarestatus.com/api/v2/incidents.json",
     "NET"),
    ("github", "https://www.githubstatus.com/api/v2/incidents.json",
     "MSFT"),
    ("gcp", "https://status.cloud.google.com/incidents.json",
     "GOOGL"),
    ("discord", "https://discordstatus.com/api/v2/incidents.json",
     ""),
    ("twilio", "https://status.twilio.com/api/v2/incidents.json",
     "TWLO"),
    ("datadog", "https://status.datadoghq.com/api/v2/incidents.json",
     "DDOG"),
    ("okta", "https://status.okta.com/api/v2/incidents.json",
     "OKTA"),
    ("atlassian", "https://status.atlassian.com/api/v2/incidents.json",
     "TEAM"),
    ("shopify", "https://www.shopifystatus.com/api/v2/incidents.json",
     "SHOP"),
    ("zoom", "https://status.zoom.us/api/v2/incidents.json",
     "ZM"),
    ("snowflake", "https://status.snowflake.com/api/v2/incidents.json",
     "SNOW"),
    ("mongodb", "https://status.mongodb.com/api/v2/incidents.json",
     "MDB"),
    ("cloudflare_workers",
     "https://www.cloudflarestatus.com/api/v2/incidents.json",
     "NET"),  # duplicate filter downstream
]


def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            j = json.loads(r.read())
        if isinstance(j, list):
            return {"incidents": j}
        return j
    except Exception as e:
        print(f"tech_status: {url[:40]}... failed: {e}")
        return {}


IMPACT_ORDER = {"critical": 4, "major": 3, "minor": 2, "maintenance": 1,
                "none": 0}


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    rows: list[dict] = []
    seen_ids: set[str] = set()

    for vkey, url, tickers in VENDORS:
        data = _fetch(url)
        for inc in data.get("incidents", [])[:40]:
            iid = inc.get("id", "")
            if iid in seen_ids:
                continue
            seen_ids.add(iid)
            created = inc.get("created_at", "")
            try:
                dt_obj = dt.datetime.fromisoformat(
                    created.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt_obj < cutoff:
                continue
            rows.append({
                "vendor": vkey,
                "created_at": created[:19],
                "updated_at": (inc.get("updated_at") or "")[:19],
                "status": inc.get("status", ""),
                "impact": inc.get("impact", ""),
                "tickers": tickers,
                "name": (inc.get("name") or "")[:140],
                "url": inc.get("shortlink", "")[:80],
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"tech_status: no rows, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: (IMPACT_ORDER.get(r["impact"], 0),
                              r["created_at"]), reverse=True)
    fieldnames = ["vendor", "created_at", "updated_at", "status",
                  "impact", "tickers", "name", "url", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    impacts: dict[str, int] = {}
    for r in rows:
        impacts[r["impact"]] = impacts.get(r["impact"], 0) + 1
    ib = " ".join(f"{k}={v}" for k, v in sorted(impacts.items(),
                                                 key=lambda x: -x[1]))
    top = [r for r in rows if r["impact"] in ("critical", "major")][:3]
    tops = " | ".join(f"{r['vendor']}: {r['name'][:40]}" for r in top)
    vendors_count = len(set(r["vendor"] for r in rows))
    print(f"tech_status: {len(rows)} 30d ({vendors_count} vendors) | "
          f"{ib} | critical: [{tops}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
