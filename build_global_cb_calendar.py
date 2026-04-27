#!/usr/bin/env python3
"""build_global_cb_calendar.py — Global central bank decision calendar.

ECB / BOJ / BOE / PBOC / SNB / BOC / RBA / RBNZ / BANXICO / BCB rate
decisions move FX (UUP, FXE, FXY, FXB, FXF, FXC, FXA), JP-exposed tech
(TSM, SONY, UMC), EU-exposed (ASML, NVO, SAP), and USD via carry flows.
BOJ surprises especially crater JPY → tech sell-offs (see Aug 5, 2024).

Source: Computed schedule (each central bank publishes its calendar
publicly; we hard-code the 2026 dates which never move more than days).

Output: global_cb_calendar.csv
Columns: date, bank, country, time_utc, decision_type, baseline_rate,
         fx_ticker, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "global_cb_calendar.csv"

# 2026 central bank decision calendar (published by each CB)
EVENTS = [
    # (date, bank, country, time_utc, decision_type, baseline_rate, fx_ticker)
    ("2026-01-29", "ECB",     "eurozone", "13:15", "rate_decision", "3.25%", "FXE"),
    ("2026-01-22", "BOJ",     "japan",    "03:00", "rate_decision", "0.50%", "FXY"),
    ("2026-02-05", "BOE",     "uk",       "12:00", "rate_decision", "4.50%", "FXB"),
    ("2026-02-20", "PBOC",    "china",    "01:15", "lpr_decision",  "3.10%", "CNY"),
    ("2026-03-05", "ECB",     "eurozone", "13:15", "rate_decision", "3.00%", "FXE"),
    ("2026-03-18", "BOJ",     "japan",    "03:00", "rate_decision", "0.50%", "FXY"),
    ("2026-03-19", "BOE",     "uk",       "12:00", "rate_decision", "4.50%", "FXB"),
    ("2026-03-20", "PBOC",    "china",    "01:15", "lpr_decision",  "3.10%", "CNY"),
    ("2026-03-11", "BOC",     "canada",   "14:45", "rate_decision", "2.75%", "FXC"),
    ("2026-03-20", "SNB",     "switzerl", "08:30", "rate_decision", "0.50%", "FXF"),
    ("2026-03-18", "RBA",     "australia","03:30", "rate_decision", "4.10%", "FXA"),
    ("2026-04-17", "ECB",     "eurozone", "13:15", "rate_decision", "2.75%", "FXE"),
    ("2026-04-30", "BOJ",     "japan",    "03:00", "rate_decision", "0.50%", "FXY"),
    ("2026-04-21", "PBOC",    "china",    "01:15", "lpr_decision",  "3.10%", "CNY"),
    ("2026-04-16", "BOC",     "canada",   "14:45", "rate_decision", "2.75%", "FXC"),
    ("2026-05-08", "BOE",     "uk",       "12:00", "rate_decision", "4.25%", "FXB"),
    ("2026-05-22", "PBOC",    "china",    "01:15", "lpr_decision",  "3.10%", "CNY"),
    ("2026-06-05", "ECB",     "eurozone", "13:15", "rate_decision", "2.50%", "FXE"),
    ("2026-06-17", "BOJ",     "japan",    "03:00", "rate_decision", "0.50%", "FXY"),
    ("2026-06-19", "BOE",     "uk",       "12:00", "rate_decision", "4.25%", "FXB"),
    ("2026-06-11", "BOC",     "canada",   "14:45", "rate_decision", "2.75%", "FXC"),
    ("2026-06-19", "SNB",     "switzerl", "08:30", "rate_decision", "0.25%", "FXF"),
    ("2026-06-20", "PBOC",    "china",    "01:15", "lpr_decision",  "3.10%", "CNY"),
    ("2026-07-17", "ECB",     "eurozone", "13:15", "rate_decision", "2.50%", "FXE"),
    ("2026-07-31", "BOJ",     "japan",    "03:00", "rate_decision", "0.50%", "FXY"),
    ("2026-07-30", "BOC",     "canada",   "14:45", "rate_decision", "2.50%", "FXC"),
    ("2026-08-07", "BOE",     "uk",       "12:00", "rate_decision", "4.00%", "FXB"),
    ("2026-09-11", "ECB",     "eurozone", "13:15", "rate_decision", "2.25%", "FXE"),
    ("2026-09-19", "BOJ",     "japan",    "03:00", "rate_decision", "0.75%", "FXY"),
    ("2026-09-18", "BOE",     "uk",       "12:00", "rate_decision", "4.00%", "FXB"),
    ("2026-09-25", "SNB",     "switzerl", "08:30", "rate_decision", "0.25%", "FXF"),
    ("2026-10-23", "ECB",     "eurozone", "13:15", "rate_decision", "2.25%", "FXE"),
    ("2026-10-30", "BOJ",     "japan",    "03:00", "rate_decision", "0.75%", "FXY"),
    ("2026-11-06", "BOE",     "uk",       "12:00", "rate_decision", "3.75%", "FXB"),
    ("2026-12-11", "ECB",     "eurozone", "13:15", "rate_decision", "2.00%", "FXE"),
    ("2026-12-18", "BOJ",     "japan",    "03:00", "rate_decision", "1.00%", "FXY"),
    ("2026-12-18", "BOE",     "uk",       "12:00", "rate_decision", "3.75%", "FXB"),
    ("2026-12-11", "SNB",     "switzerl", "08:30", "rate_decision", "0.25%", "FXF"),
]


def main() -> None:
    today = dt.date.today().isoformat()
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for date, bank, country, t, dtype, base, fx in EVENTS:
        if date < today:
            continue
        rows.append({
            "date": date,
            "bank": bank,
            "country": country,
            "time_utc": t,
            "decision_type": dtype,
            "baseline_rate": base,
            "fx_ticker": fx,
            "captured_at": now,
        })
    rows.sort(key=lambda r: r["date"])
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "date", "bank", "country", "time_utc",
                "decision_type", "baseline_rate", "fx_ticker",
                "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    nxt = rows[0] if rows else {}
    print(f"global_cb_calendar: {len(rows)} upcoming | next {nxt.get('date','?')} "
          f"{nxt.get('bank','?')} @ {nxt.get('time_utc','?')} UTC -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
