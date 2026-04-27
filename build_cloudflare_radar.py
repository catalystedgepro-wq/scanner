#!/usr/bin/env python3
"""Cloudflare Radar spoke — internet outage + traffic anomaly detector.

Pulls Cloudflare Radar's outage feed and traffic-anomaly endpoints to
detect ISP/datacenter/country-level disruptions that move telco/datacenter
REIT/cybersecurity stocks within hours.

Sector signal: any active outage → flag affected country/AS-org sectors
(telecom, datacenter REITs DLR/EQIX, cyber stocks if attributed to attack).

Output: cloudflare_radar.csv — feeds news_momentum via load_cloudflare_rows().

Free with API token (cfat_*). Token + account ID required in env:
    CLOUDFLARE_API_TOKEN
    CLOUDFLARE_ACCOUNT_ID  (used for token verification only)
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
OUT_CSV = ROOT / "cloudflare_radar.csv"
STATUS_JSON = ROOT / "cloudflare_radar_status.json"
TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
ACCOUNT = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
USER_AGENT = "CatalystEdge/1.0 (opensource@example.com)"

API_BASE = "https://api.cloudflare.com/client/v4"

# Country → sector tag map for outage routing.
COUNTRY_SECTORS = {
    "US": ["telecom", "datacenter"],
    "CN": ["telecom", "semis_ai"],
    "RU": ["telecom", "energy"],
    "IR": ["telecom", "energy"],
    "DE": ["telecom"],
    "JP": ["telecom", "semis_ai"],
    "KR": ["telecom", "semis_ai"],
    "IN": ["telecom"],
    "BR": ["telecom"],
    "TW": ["telecom", "semis_ai"],
}


def get(path: str) -> dict:
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"_error": str(e)}


def main() -> int:
    now_utc = dt.datetime.now(dt.timezone.utc)
    if not TOKEN:
        STATUS_JSON.write_text(json.dumps({
            "status": "skipped_no_token",
            "ts_utc": now_utc.isoformat(),
        }))
        print("cloudflare_radar: skipped (CLOUDFLARE_API_TOKEN not set)")
        return 0

    # Verify token (read-only, cheap).
    if ACCOUNT:
        verify = get(f"/accounts/{ACCOUNT}/tokens/verify")
        if not verify.get("success"):
            STATUS_JSON.write_text(json.dumps({
                "status": "token_invalid",
                "ts_utc": now_utc.isoformat(),
                "details": verify,
            }, indent=2))
            print(f"cloudflare_radar: token verify failed — {verify.get('errors')}")
            return 0

    # Fetch internet outage events for the last 7 days.
    # Endpoint: /radar/quality/iqi/timeseries_groups?dateRange=7d (latency)
    # We use /radar/annotations/outages?dateRange=7d for actual outage events.
    end = now_utc
    start = end - dt.timedelta(days=7)
    qs = urllib.parse.urlencode({
        "dateStart": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dateEnd": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "limit": "200",
    })
    data = get(f"/radar/annotations/outages?{qs}")
    annotations = (data.get("result") or {}).get("annotations") or []

    rows: list[dict] = []
    by_severity = {"high": 0, "medium": 0, "low": 0}
    for a in annotations:
        loc = (a.get("locations") or [{}])[0] if a.get("locations") else {}
        country = (loc.get("alpha2") or "").upper() if isinstance(loc, dict) else ""
        sectors = COUNTRY_SECTORS.get(country, ["telecom"])
        scope = (a.get("scope") or "").lower()  # network/region/country
        outage_type = (a.get("outageType") or "").strip().lower()
        # Severity heuristic from scope + duration
        try:
            ts_start = dt.datetime.fromisoformat((a.get("startDate") or "").replace("Z", "+00:00"))
            ts_end_str = a.get("endDate")
            if ts_end_str:
                ts_end = dt.datetime.fromisoformat(ts_end_str.replace("Z", "+00:00"))
            else:
                ts_end = now_utc
            duration_h = (ts_end - ts_start).total_seconds() / 3600.0
        except Exception:
            duration_h = 0
        if scope == "country" or duration_h > 12:
            sev = "high"
        elif scope == "region" or duration_h > 4:
            sev = "medium"
        else:
            sev = "low"
        by_severity[sev] = by_severity.get(sev, 0) + 1
        rows.append({
            "timestamp_utc": a.get("startDate") or now_utc.isoformat(),
            "severity": sev,
            "scope": scope,
            "outage_type": outage_type,
            "country": country,
            "asn": str(loc.get("asn", "") if isinstance(loc, dict) else ""),
            "duration_hours": f"{duration_h:.1f}",
            "description": (a.get("description") or "")[:240],
            "sector_tags": ";".join(sectors),
            "link": "https://radar.cloudflare.com/outage-center",
        })

    rows.sort(key=lambda r: r["timestamp_utc"], reverse=True)
    fields = ["timestamp_utc", "severity", "scope", "outage_type", "country",
              "asn", "duration_hours", "description", "sector_tags", "link"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    STATUS_JSON.write_text(json.dumps({
        "status": "ok" if rows else "empty",
        "ts_utc": now_utc.isoformat(),
        "outages_7d": len(rows),
        "by_severity": by_severity,
    }, indent=2), encoding="utf-8")
    print(f"cloudflare_radar: {len(rows)} outage events 7d (high={by_severity['high']} med={by_severity['medium']} low={by_severity['low']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
