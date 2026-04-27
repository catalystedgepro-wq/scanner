#!/usr/bin/env python3
"""build_nbp_fx.py — NBP Poland daily FX reference rates.

Narodowy Bank Polski publishes daily FX reference rates for 30+ pairs
plus bid/ask from table C.  PLN is a CEE/EM bellwether:
- USDPLN / EURPLN track EM risk-on/risk-off
- Poland sits at NATO/EU east flank (geopolitical sensitivity)
- CEE equity plays (IWN, Polish ADRs sparse but EM broad-read)

Captured pairs: USD, EUR, GBP, JPY, CHF, CAD, AUD, CNY, HUF, CZK.

Source: api.nbp.pl/api/exchangerates/tables/a/last/30/?format=json
Output: nbp_fx.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nbp_fx.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://api.nbp.pl/api/exchangerates/tables/a/last/30/?format=json"

TRACK = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "CNY",
         "HUF", "CZK"}


def main() -> None:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read().decode("utf-8",
                                                 errors="ignore"))
    except Exception as e:
        print(f"nbp_fx: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nbp_fx: keeping {OUT_CSV.name}")
        return

    if not isinstance(payload, list) or not payload:
        return

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    for table in payload:
        if not isinstance(table, dict):
            continue
        eff = table.get("effectiveDate", "")
        rates = table.get("rates", [])
        by_code = {r.get("code"): r for r in rates if isinstance(r, dict)}
        row = {"date": eff, "captured_at": now_iso}
        for code in TRACK:
            rec = by_code.get(code)
            row[f"pln_{code.lower()}"] = (
                f"{float(rec['mid']):.4f}"
                if rec and isinstance(rec.get("mid"), (int, float))
                else "")
        rows.append(row)

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nbp_fx: empty, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["date"], reverse=True)
    fieldnames = ["date"] + [f"pln_{c.lower()}"
                             for c in sorted(TRACK)] + ["captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest = rows[0]
    print(f"nbp_fx: {len(rows)} days | latest={latest['date']} "
          f"usd={latest.get('pln_usd')} eur={latest.get('pln_eur')} "
          f"gbp={latest.get('pln_gbp')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
