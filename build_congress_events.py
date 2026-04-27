#!/usr/bin/env python3
"""build_congress_events.py — Congressional hearings, markups, nominations.

Live congressional calendar from Library of Congress api.congress.gov.
Committee hearings, scheduled markups, and pending nominations are
event-driven catalysts for the industries whose representatives testify
or whose regulators get confirmed.

Trade context:
- Armed Services Committee hearing on NDAA → LMT, GD, NOC, RTX tailwind
- Energy & Commerce hearing on drug pricing → LLY, PFE, MRK headline risk
- Finance Committee hearing on banks → JPM, BAC, WFC
- EPA administrator confirmation → regulated industrials (DOW, LYB)
- SEC commissioner confirmation → NKLA, TSLA, MSTR (crypto policy)
- FAA administrator confirmation → BA, SPR, LMT

Source: api.congress.gov v3 (free, no key when using DEMO_KEY, limited).

Output: congress_events.csv
Columns: event_type, chamber, congress, jacket_or_id, update_date,
         url, detail, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "congress_events.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
KEY = "DEMO_KEY"

ENDPOINTS = [
    ("hearing", f"https://api.congress.gov/v3/hearing?format=json&"
                f"limit=20&api_key={KEY}"),
    ("committee_meeting",
        f"https://api.congress.gov/v3/committee-meeting?format=json&"
        f"limit=20&api_key={KEY}"),
    ("nomination",
        f"https://api.congress.gov/v3/nomination?format=json&limit=20&"
        f"api_key={KEY}"),
]


def _fetch(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"congress_events {url[:60]}: {e}")
        return None


def main() -> None:
    rows: list[dict] = []

    keymap = {
        "hearing": ("hearings", "jacketNumber"),
        "committee_meeting": ("committeeMeetings", "eventId"),
        "nomination": ("nominations", "citation"),
    }

    for etype, url in ENDPOINTS:
        d = _fetch(url)
        if not d:
            continue
        field, id_key = keymap[etype]
        for item in (d.get(field) or []):
            if not isinstance(item, dict):
                continue
            detail = ""
            if etype == "nomination":
                detail = (item.get("description") or "")[:96]
                congress = str(item.get("congress") or "")
                chamber = "Senate"
                identifier = str(item.get(id_key) or "")
            else:
                congress = str(item.get("congress") or "")
                chamber = (item.get("chamber") or "")
                identifier = str(item.get(id_key) or "")
            rows.append({
                "event_type": etype,
                "chamber": chamber[:12],
                "congress": congress[:4],
                "jacket_or_id": identifier[:20],
                "update_date": (item.get("updateDate") or "")[:20],
                "url": (item.get("url") or "")[:120],
                "detail": detail,
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"congress_events: no data, keeping existing "
                  f"{OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["update_date"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["event_type", "chamber", "congress", "jacket_or_id",
                  "update_date", "url", "detail", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    per_type: dict[str, int] = {}
    for r in rows:
        per_type[r["event_type"]] = per_type.get(r["event_type"], 0) + 1
    breakdown = " ".join(f"{k}={v}" for k, v in sorted(per_type.items()))
    print(f"congress_events: {len(rows)} events | {breakdown} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
