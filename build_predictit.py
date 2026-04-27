#!/usr/bin/env python3
"""build_predictit.py — PredictIt US political prediction markets.

PredictIt is a CFTC-approved academic political prediction
market (Victoria University of Wellington). 269 live markets
covering US elections, Congress, presidential nominations,
Fed chair, Supreme Court, and policy events.

Economic readthrough:
- Congressional seat counts -> regulatory agenda visibility
  (tax, healthcare, banking, energy bills probability shifts).
- Presidential nominee probabilities -> Trump/DJT correlation,
  private prison (GEO/CXW) policy signal.
- Speaker/majority leader markets -> legislative calendar flow.
- SCOTUS opinion markets -> case-specific ticker risk (abortion
  pills, student loans, chevron doctrine, 1a platform cases).

Source: PredictIt public marketdata feed
https://www.predictit.org/api/marketdata/all/

Output: predictit.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "predictit.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://www.predictit.org/api/marketdata/all/"


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            j = json.loads(r.read())
    except Exception as e:
        print(f"predictit: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"predictit: keeping {OUT_CSV.name}")
        return

    rows: list[dict] = []
    for m in j.get("markets", []):
        mname = (m.get("name") or "").strip()[:140]
        for c in m.get("contracts", []):
            last = c.get("lastTradePrice")
            by = c.get("bestBuyYesCost")
            if last is None:
                continue
            rows.append({
                "market_id": m.get("id"),
                "market": mname,
                "contract": (c.get("name") or "")[:60],
                "last": last,
                "yes": by if by is not None else "",
                "no": c.get("bestBuyNoCost") if c.get("bestBuyNoCost")
                      is not None else "",
                "prev_close": c.get("lastClosePrice") if
                              c.get("lastClosePrice") is not None else "",
                "date_end": (c.get("dateEnd") or "")[:10],
                "status": c.get("status", ""),
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"predictit: no rows, keeping {OUT_CSV.name}")
        return

    for r in rows:
        delta = ""
        try:
            if r["prev_close"] and isinstance(r["prev_close"], (int, float)):
                delta = round(float(r["last"]) - float(r["prev_close"]), 3)
        except (TypeError, ValueError):
            pass
        r["delta"] = delta
        r["captured_at"] = now_iso

    rows.sort(key=lambda r: (abs(r["delta"]) if isinstance(r["delta"],
                              (int, float)) else 0,
                              float(r["last"])), reverse=True)
    fieldnames = ["market_id", "market", "contract", "last", "yes", "no",
                  "prev_close", "delta", "date_end", "status",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    markets_ct = len(set(r["market_id"] for r in rows))
    movers = [r for r in rows if isinstance(r["delta"], (int, float))
              and abs(r["delta"]) >= 0.02][:5]
    ms = " | ".join(
        f"{r['contract'][:30]} {r['last']:.2f} ({r['delta']:+.02f})"
        for r in movers)
    print(f"predictit: {len(rows)} contracts ({markets_ct} mkts) | "
          f"top moves: [{ms}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
