#!/usr/bin/env python3
"""build_banrep_colombia.py — Banco de la Republica de Colombia FX tape.

Data.gov.co Socrata resource mcec-87by publishes the official TRM
(Tasa Representativa del Mercado) USD/COP spot series, updated daily.

Economic readthrough:
- Colombia is Latin America's 4th-largest economy, oil + coffee + gold
  export-driven. ECO (Ecopetrol ADR) is most-watched Colombian equity.
- COP is petro-currency (brent beta); weakens on oil selloffs, risk-off,
  or Petro-admin fiscal headlines.
- Long-term TRM averaged 3,800-4,500 COP/USD during 2022-2024 stress;
  <3,800 = bullish commodity cycle / risk-on EM rotation.
- Colombian-linked US equities: ECO (Ecopetrol), CIB (Bancolombia),
  AVH (Avianca) — all move with COP.

Source: datos.gov.co /resource/mcec-87by.json (Socrata Open Data API)
Output: banrep_colombia.csv

Covers ~200 business days of daily TRM (≈10 months). Computes MoM and
YoY delta when enough history is present.
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "banrep_colombia.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

RESOURCE = "mcec-87by"  # TRM USD/COP


def _fetch() -> list[dict]:
    params = {"$limit": "400", "$order": "vigenciadesde DESC"}
    url = (f"https://www.datos.gov.co/resource/{RESOURCE}.json?"
           + urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    try:
        raw = _fetch()
    except Exception as e:
        print(f"banrep_colombia: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"banrep_colombia: keeping {OUT_CSV.name}")
        return

    # Normalize: date + TRM value.  Socrata emits midnight-anchored datetimes.
    pts: list[tuple[str, float]] = []
    for rec in raw:
        if not isinstance(rec, dict):
            continue
        d = (rec.get("vigenciadesde") or "")[:10]
        try:
            v = float(rec.get("valor") or 0)
        except (TypeError, ValueError):
            continue
        if d and v > 0:
            pts.append((d, v))
    if not pts:
        return

    pts.sort()  # ascending
    date_to_val = {d: v for d, v in pts}
    dates = [d for d, _ in pts]

    rows: list[dict] = []
    for i, (d, v) in enumerate(pts):
        # 1-month back (approx 22 trading days)
        mom = None
        if i >= 22:
            prev_v = pts[i - 22][1]
            if prev_v:
                mom = round((v - prev_v) / prev_v * 100, 3)
        yoy = None  # generally not enough history at 200d window
        rows.append({
            "date": d,
            "usd_cop_trm": round(v, 3),
            "chg_mom_pct": mom if mom is not None else "",
            "captured_at": now_iso,
        })

    rows.sort(key=lambda r: r["date"], reverse=True)
    fieldnames = ["date", "usd_cop_trm", "chg_mom_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest = rows[0]
    # 30-day high/low
    last30 = rows[:30]
    hi = max(last30, key=lambda r: r["usd_cop_trm"])
    lo = min(last30, key=lambda r: r["usd_cop_trm"])
    print(f"banrep_colombia: {len(rows)} days | "
          f"latest {latest['date']} TRM={latest['usd_cop_trm']} "
          f"mom={latest['chg_mom_pct']}% | "
          f"30d hi={hi['usd_cop_trm']} lo={lo['usd_cop_trm']} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
