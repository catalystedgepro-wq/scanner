#!/usr/bin/env python3
"""build_gdacs_disasters.py — GDACS global disaster alert tape.

GDACS = Global Disaster Alert Coordination System (UN/ECJRC). Tracks
earthquakes, tsunamis, tropical cyclones, floods, wildfires, volcanoes,
droughts in near-real-time with standardized alert levels (Green/Orange/Red).

Signal:
- Red/Orange alerts → reinsurance (RE/RNR/MMC) catalyst, property-cat risk
- Tropical cyclones (TC) → offshore E&P (RIG/VAL), Gulf platforms, shipping
- Floods (FL) in agri regions → ag commodities (DBA, CORN, SOYB)
- Earthquakes (EQ) near ports/supply chains → global logistics disruption
- Wildfires (WF) in CA/AUS → utility wildfire-liability (PCG, EIX, SRE)
- Volcanoes (VO) → aviation disruption (RYAAY, DAL), rare-earth mining

Source: gdacs.org/xml/rss.xml (RSS, no auth)
Output: gdacs_disasters.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "gdacs_disasters.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
FEED = "https://www.gdacs.org/xml/rss.xml"

EVENT_LABELS = {
    "EQ": "earthquake",
    "TC": "tropical_cyclone",
    "FL": "flood",
    "WF": "wildfire",
    "VO": "volcano",
    "DR": "drought",
    "TS": "tsunami",
}

ALERT_RANK = {"Red": 3, "Orange": 2, "Green": 1}


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"gdacs_disasters: {url[:80]}: {e}")
        return ""


def _field(block: str, tag: str) -> str:
    m = re.search(
        rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", block, re.S)
    return (m.group(1) if m else "").strip()


def _float(s: str) -> float | None:
    try:
        return float(s)
    except Exception:
        return None


def main() -> None:
    xml = _get(FEED)
    if not xml:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"gdacs_disasters: no fetch, keeping {OUT_CSV.name}")
        return
    items = re.findall(r"<item>(.*?)</item>", xml, re.S)
    if not items:
        return

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")

    rows: list[dict] = []
    for it in items:
        etype = _field(it, "gdacs:eventtype")
        alert = _field(it, "gdacs:alertlevel")
        score_s = _field(it, "gdacs:alertscore")
        score = _float(score_s)
        country = _field(it, "gdacs:country")
        event_id = _field(it, "gdacs:eventid")
        episode_id = _field(it, "gdacs:episodeid")
        is_current = _field(it, "gdacs:iscurrent")
        from_d = _field(it, "gdacs:fromdate")
        to_d = _field(it, "gdacs:todate")
        bbox = _field(it, "gdacs:bbox")
        title = _field(it, "title")
        desc = _field(it, "description")
        link = _field(it, "link")
        pub = _field(it, "pubDate")
        rows.append({
            "event_id": event_id,
            "episode_id": episode_id,
            "event_type": etype,
            "event_label": EVENT_LABELS.get(etype, etype.lower()),
            "alert_level": alert,
            "alert_rank": str(ALERT_RANK.get(alert, 0)),
            "alert_score": f"{score:.3f}" if score is not None else "",
            "country": country,
            "is_current": is_current,
            "from_date": from_d,
            "to_date": to_d,
            "pub_date": pub,
            "bbox": bbox,
            "title": title[:250],
            "description": desc[:300],
            "link": link,
            "captured_at": now_iso,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"gdacs_disasters: empty, keeping {OUT_CSV.name}")
        return

    # Red > Orange > Green, then by score desc.
    rows.sort(key=lambda r: (
        -int(r["alert_rank"] or 0),
        -(float(r["alert_score"]) if r["alert_score"] else 0.0),
        r["event_type"],
    ))

    fieldnames = ["event_id", "episode_id", "event_type", "event_label",
                  "alert_level", "alert_rank", "alert_score", "country",
                  "is_current", "from_date", "to_date", "pub_date",
                  "bbox", "title", "description", "link", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    red = sum(1 for r in rows if r["alert_level"] == "Red")
    orange = sum(1 for r in rows if r["alert_level"] == "Orange")
    green = sum(1 for r in rows if r["alert_level"] == "Green")
    by_type: dict[str, int] = {}
    for r in rows:
        by_type[r["event_type"]] = by_type.get(r["event_type"], 0) + 1
    top3 = sorted(by_type.items(), key=lambda x: -x[1])[:3]
    type_str = " ".join(f"{k}={v}" for k, v in top3)
    print(f"gdacs_disasters: {len(rows)} events | R={red} O={orange} "
          f"G={green} | {type_str} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
