#!/usr/bin/env python3
"""build_bts_border.py — BTS border-crossing truck volume (monthly).

Truck crossings at US-Canada + US-Mexico borders are the cleanest
real-economy freight signal before supply-chain data lags into CPI.
BTS updates monthly from CBP inspection counts.

Signals:
- YoY change by border: US-Mexico momentum = nearshoring proxy
  (ex-China manufacturing flowing to Mexico → KSU, CP, NSC, UNP all
  lifted); US-Canada decline = auto sector rollover risk (F, GM, STLA).
- Top-10 port momentum: Laredo/Detroit surges = autos + electronics;
  Otay Mesa = Tijuana EMS/contract-manufacturing (Foxconn/Flex).
- Delta spike > 15% MoM = policy shock (tariff, strike, weather).

Source: data.bts.gov/resource/keg4-3bc2.json — Socrata, no key required.

Output: bts_border.csv
Columns: port_name, state, border, date, trucks, prior_month,
         mom_delta_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "bts_border.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API = "https://data.bts.gov/resource/keg4-3bc2.json"


def fetch(limit: int = 3000) -> list[dict]:
    params = {
        "$limit": limit,
        "$where": "measure='Trucks'",
        "$order": "date DESC",
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"bts_border: {e}")
        return []


def main() -> None:
    rows_raw = fetch(limit=3000)
    if not rows_raw and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"bts_border: no data, keeping existing "
              f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    # Key: (port_code, date-month). Build a history per port.
    by_port: dict[str, list[tuple[str, int, str, str, str]]] = {}
    for r in rows_raw:
        port = r.get("port_name") or ""
        code = r.get("port_code") or ""
        if not port or not code:
            continue
        date = (r.get("date") or "")[:7]  # YYYY-MM
        try:
            trucks = int(r.get("value") or 0)
        except (TypeError, ValueError):
            continue
        border = r.get("border") or ""
        state = r.get("state") or ""
        by_port.setdefault(code, []).append(
            (date, trucks, port, state, border))

    rows: list[dict] = []
    for code, series in by_port.items():
        series.sort(reverse=True)
        if not series:
            continue
        latest = series[0]
        prior = series[1] if len(series) > 1 else None
        date, trucks, port, state, border = latest
        if trucks < 1000:
            continue
        prior_trucks = prior[1] if prior else 0
        if prior_trucks > 0:
            delta = (trucks - prior_trucks) / prior_trucks * 100
        else:
            delta = 0.0
        rows.append({
            "port_name": port,
            "state": state,
            "border": border,
            "date": date,
            "trucks": trucks,
            "prior_month": prior_trucks,
            "mom_delta_pct": f"{delta:.1f}",
        })

    rows.sort(key=lambda r: r["trucks"], reverse=True)
    rows = rows[:80]

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["port_name", "state", "border", "date", "trucks",
                  "prior_month", "mom_delta_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    total_trucks = sum(r["trucks"] for r in rows)
    mex = sum(r["trucks"] for r in rows if "Mexico" in r["border"])
    can = sum(r["trucks"] for r in rows if "Canada" in r["border"])
    top3 = " | ".join(f"{r['port_name']}={r['trucks']:,}" for r in rows[:3])
    print(f"bts_border: {len(rows)} ports | {total_trucks:,} trucks "
          f"(MX={mex:,} CA={can:,}) | top: {top3} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
