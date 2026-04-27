#!/usr/bin/env python3
"""build_earnings_calendar.py — Nasdaq earnings calendar (free JSON).

Nasdaq publishes the full earnings calendar as JSON (undocumented but stable).
URL: https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD

Output: earnings_calendar.csv
Columns: ticker, company, report_date, time, eps_forecast, no_of_estimates,
         last_year_eps, last_year_report_date, market_cap
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "earnings_calendar.csv"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
API = "https://api.nasdaq.com/api/calendar/earnings?date={date}"


def fetch(url: str, timeout: int = 25) -> dict | None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nasdaq.com/market-activity/earnings",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"earnings: {url[-30:]} -> {e}")
        return None


def main():
    today = dt.date.today()
    rows: list[dict] = []
    # Pull the next 14 calendar days
    for d_off in range(0, 14):
        d = today + dt.timedelta(days=d_off)
        if d.weekday() > 4:
            continue  # skip weekends — no reports scheduled
        url = API.format(date=d.strftime("%Y-%m-%d"))
        data = fetch(url)
        if not data:
            continue
        rows_list = (data.get("data") or {}).get("rows") or []
        for r in rows_list:
            rows.append({
                "ticker": (r.get("symbol") or "").upper(),
                "company": r.get("name", "")[:120],
                "report_date": d.strftime("%Y-%m-%d"),
                "time": r.get("time", ""),
                "eps_forecast": r.get("epsForecast", ""),
                "num_estimates": r.get("noOfEsts", ""),
                "last_year_eps": r.get("lastYearEPS", ""),
                "last_year_report_date": r.get("lastYearRptDt", ""),
                "market_cap": r.get("marketCap", ""),
            })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "ticker", "company", "report_date", "time",
                "eps_forecast", "num_estimates", "last_year_eps",
                "last_year_report_date", "market_cap",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"earnings_calendar: {len(rows)} reports in next 14d -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
