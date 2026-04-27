#!/usr/bin/env python3
"""build_boi_israel.py — Bank of Israel policy rate + ILS FX.

Bank of Israel publishes policy interest rate and daily ILS FX
reference rates via PublicApi.  Israel is:
- A geopolitical-risk bellwether (Middle East conflict)
- Home to major chip/cybersecurity plays indirectly priced via ILS
  (CHKP, NICE, WIX, MNDY ADRs)
- Export-sensitive to USD strength

Captured:
- Policy rate (BOI key rate)
- Next rate-decision date
- ILS FX: USD, EUR, GBP, JPY, CHF, AUD, CAD

Source: boi.org.il/PublicApi/{GetInterest,GetExchangeRates}
Output: boi_israel.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "boi_israel.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
INT_URL = "https://www.boi.org.il/PublicApi/GetInterest"
FX_URL = "https://www.boi.org.il/PublicApi/GetExchangeRates"

TRACK = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD"}


def _get_json(url: str) -> object | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"boi_israel: {url[-15:]}: {e}")
        return None


def main() -> None:
    interest = _get_json(INT_URL)
    fx = _get_json(FX_URL)
    if not (isinstance(interest, dict) and isinstance(fx, dict)):
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"boi_israel: no fetch, keeping {OUT_CSV.name}")
        return

    rate = interest.get("currentInterest")
    next_date = interest.get("nextInterestDate", "")[:10]
    pub_date = interest.get("lastPublishedDate", "")[:10]

    rates = fx.get("exchangeRates", [])
    by_code = {r.get("key"): r for r in rates if isinstance(r, dict)}

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    row = {
        "as_of_date": pub_date,
        "policy_rate": f"{float(rate):.2f}" if rate is not None else "",
        "next_decision": next_date,
        "captured_at": now_iso,
    }
    for code in sorted(TRACK):
        rec = by_code.get(code)
        val = rec.get("currentExchangeRate") if rec else None
        chg = rec.get("currentChange") if rec else None
        row[f"ils_{code.lower()}"] = (f"{float(val):.4f}"
                                      if isinstance(val, (int, float))
                                      else "")
        row[f"ils_{code.lower()}_chg"] = (f"{float(chg):.4f}"
                                          if isinstance(chg, (int, float))
                                          else "")

    fieldnames = ["as_of_date", "policy_rate", "next_decision"]
    for code in sorted(TRACK):
        fieldnames.append(f"ils_{code.lower()}")
        fieldnames.append(f"ils_{code.lower()}_chg")
    fieldnames.append("captured_at")

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerow(row)

    print(f"boi_israel: policy={row['policy_rate']} "
          f"next={row['next_decision']} "
          f"ilsusd={row.get('ils_usd')} "
          f"ilseur={row.get('ils_eur')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
