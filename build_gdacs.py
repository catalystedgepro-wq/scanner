#!/usr/bin/env python3
"""GDACS spoke — UN-coordinated global disaster alerts.

GDACS publishes earthquakes, tropical cyclones, floods, volcanoes, droughts.
Each alert has a severity (Green/Orange/Red) and affected population estimate.
Drives reinsurer (RNR, RGA), cat-bond, energy, and shipping signals.

Free public RSS feed; no auth.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent
OUT_CSV = ROOT / "gdacs_alerts.csv"
STATUS_JSON = ROOT / "gdacs_status.json"
FEED = "https://www.gdacs.org/xml/rss.xml"
USER_AGENT = "CatalystEdge/1.0 (opensource@example.com)"


def fetch_rss() -> str:
    req = urllib.request.Request(FEED, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_rss(xml_text: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    # GDACS uses default namespace + custom gdacs namespace; we keep it simple
    # and grab core fields from each item.
    ns = {"gdacs": "http://www.gdacs.org"}
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        try:
            ts = dt.datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z").astimezone(dt.timezone.utc)
            ts_iso = ts.isoformat()
        except ValueError:
            ts_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        # Severity is in the title prefix: "Green/Orange/Red <event_type>".
        severity = "green"
        for s in ("red", "orange", "green"):
            if s in title.lower():
                severity = s
                break
        # Event type heuristic from title.
        evt_type = "other"
        for k in ("earthquake", "cyclone", "flood", "volcano", "drought", "wildfire", "tsunami"):
            if k in title.lower():
                evt_type = k
                break
        # Country extraction: the first capitalized word block after "in"
        m = re.search(r"\bin\s+([A-Z][A-Za-z\s,]+?)(?:\.|,|\s*-|$)", title)
        country = m.group(1).strip()[:60] if m else ""
        out.append({
            "timestamp_utc": ts_iso,
            "severity": severity,
            "event_type": evt_type,
            "country": country,
            "title": title[:200],
            "summary": re.sub(r"<[^>]+>", "", desc)[:300],
            "link": link,
        })
    return out


def main() -> int:
    now_utc = dt.datetime.now(dt.timezone.utc)
    try:
        xml_text = fetch_rss()
    except Exception as e:
        STATUS_JSON.write_text(json.dumps({"status": "fetch_error", "error": str(e), "ts_utc": now_utc.isoformat()}))
        print(f"gdacs: fetch error {e}")
        return 0
    rows = parse_rss(xml_text)
    fields = ["timestamp_utc", "severity", "event_type", "country", "title", "summary", "link"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    sev_counts = {"red": 0, "orange": 0, "green": 0}
    for r in rows:
        sev_counts[r["severity"]] = sev_counts.get(r["severity"], 0) + 1
    STATUS_JSON.write_text(json.dumps({
        "status": "ok" if rows else "empty",
        "ts_utc": now_utc.isoformat(),
        "alerts": len(rows),
        "severity_counts": sev_counts,
    }, indent=2), encoding="utf-8")
    print(f"gdacs: {len(rows)} alerts (red={sev_counts['red']} orange={sev_counts['orange']} green={sev_counts['green']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
