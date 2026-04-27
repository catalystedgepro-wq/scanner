#!/usr/bin/env python3
"""build_cbr_russia.py — Central Bank of Russia daily FX table.

CBR publishes a daily JSON snapshot of RUB reference rates against
54 currencies at cbr-xml-daily.ru (unofficial mirror of the official
cbr.ru XML endpoint — same data, cleaner JSON).

Economic readthrough:
- RUB is sanctions-regime + oil-price bellwether (urals-brent
  discount tracking).
- Russia's $ reserve mix, gold holdings, energy-export revenue all
  feed into RUB fixing vs USD/EUR/CNY.
- Russian-linked US equities: LUKOY/OGZPY (ADRs delisted), FLOT,
  GMKN, NVTK (European listings).  Indirect exposure via global oil
  (XOM/CVX/BP/SHEL), LNG (LNG/TELL), wheat (ADM).
- CNY/RUB is key for BRICS trade settlement; PBOC-CBR swap line.

Source: https://www.cbr-xml-daily.ru/daily_json.js
Output: cbr_russia.csv

One-shot daily snapshot (API publishes current-day reference rate).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cbr_russia.csv"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "CatalystEdge/1.0")
URL = "https://www.cbr-xml-daily.ru/daily_json.js"

# Majors + sanctioned-proximate + CIS + BRICS partners.
KEEP = {"USD", "EUR", "CNY", "GBP", "JPY", "CHF", "CAD", "AUD",
        "HKD", "SGD", "INR", "BRL", "ZAR", "TRY", "KRW", "AED",
        "KZT", "BYN", "UAH", "AMD", "AZN", "GEL", "KGS", "UZS",
        "TJS", "TMT", "MDL"}


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            d = json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"cbr_russia: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"cbr_russia: keeping {OUT_CSV.name}")
        return

    date = (d.get("Date", "") or "")[:10]
    valute = d.get("Valute") or {}
    if not isinstance(valute, dict) or not valute:
        return

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    for code, rec in valute.items():
        if not isinstance(rec, dict):
            continue
        if code not in KEEP:
            continue
        try:
            value = float(rec.get("Value") or 0)
            prev = float(rec.get("Previous") or 0)
            nominal = int(rec.get("Nominal") or 1)
        except (TypeError, ValueError):
            continue
        # Normalize to per-1-unit rate.
        rub_per_unit = value / nominal if nominal else value
        prev_per_unit = prev / nominal if nominal else prev
        chg_pct = ((rub_per_unit - prev_per_unit) / prev_per_unit
                   * 100 if prev_per_unit else 0)
        rows.append({
            "code": code,
            "name": (rec.get("Name", "") or "")[:30],
            "date": date,
            "rub_per_unit": round(rub_per_unit, 4),
            "prev_rub_per_unit": round(prev_per_unit, 4),
            "chg_pct": round(chg_pct, 3),
            "captured_at": now_iso,
        })

    if not rows:
        return

    rows.sort(key=lambda r: r["code"])
    fieldnames = ["code", "name", "date", "rub_per_unit",
                  "prev_rub_per_unit", "chg_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    hl = {r["code"]: r["rub_per_unit"] for r in rows
          if r["code"] in ("USD", "EUR", "CNY", "GBP", "JPY")}
    biggest = sorted(rows, key=lambda r: abs(r["chg_pct"]),
                     reverse=True)[:3]
    hb = " ".join(f"{k}={v}" for k, v in hl.items())
    bb = " ".join(f"{r['code']}{r['chg_pct']:+.2f}%" for r in biggest)
    print(f"cbr_russia: {len(rows)} pairs @ {date} | {hb} | "
          f"movers: {bb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
