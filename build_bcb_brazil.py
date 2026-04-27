#!/usr/bin/env python3
"""build_bcb_brazil.py — Banco Central do Brasil macro snapshot.

Tracks:
- Selic target (série 432) — policy rate.  Key EM carry trade signal;
  Brazil offers top EM real rates (Selic 14.75% vs IPCA ~5%).
- USD/BRL PTAX spot (série 1).  Risk-off BRL weakens; commodity up
  (iron ore / soybean) BRL strengthens.  PBR/VALE/ITUB/BBD ADR beta.
- IPCA MoM inflation (série 433).  Next-rate-move guide.

Economic readthrough:
- Brazil is #3 EM by equity-index weight; BRL tops LatAm carry league.
- Iron ore beta → VALE, copper → FCX, soybean → ADM/BG, sugar/ethanol
  → PBR.
- Selic at 14.75% = wide real-rate spread, fund inflows into BRL
  carry; sudden rate cuts = unwind.

Source: https://api.bcb.gov.br/dados/serie/bcdata.sgs.{N}/dados/
Output: bcb_brazil.csv

Lookback: 60 days on each series.
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "bcb_brazil.csv"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 CatalystEdge/1.0")
BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{sid}/dados/ultimos/{n}?formato=json"

# N>20 triggers server-side HTML error page for daily series; keep
# daily N <= 10 and monthly/quarterly N <= 18.
SERIES = {
    "selic_target": (432, 10),
    "usd_brl_ptax": (1, 10),
    "ipca_mom": (433, 18),
    "cdi_daily": (12, 10),
    "ibc_br_activity": (24363, 12),
}


def _fetch(series_id: int, n: int) -> list[dict]:
    url = BASE.format(sid=series_id, n=n)
    last_err: Exception | None = None
    for attempt in range(3):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read().decode("utf-8", errors="ignore")
            if not body.lstrip().startswith("["):
                last_err = ValueError("non-JSON response")
                time.sleep(2.0)
                continue
            return json.loads(body)
        except Exception as e:
            last_err = e
            time.sleep(2.0)
    print(f"bcb_brazil: series {series_id}: {last_err}")
    return []


def _parse_date(s: str) -> str:
    try:
        dd, mm, yy = s.split("/")
        return f"{yy}-{mm.zfill(2)}-{dd.zfill(2)}"
    except Exception:
        return s


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    latest: dict[str, tuple[str, float]] = {}

    for name, (sid, n) in SERIES.items():
        data = _fetch(sid, n)
        time.sleep(1.2)  # polite pacing; BCB rate-limits bursts
        best = ("", 0.0)
        for rec in data:
            if not isinstance(rec, dict):
                continue
            d = _parse_date(rec.get("data", ""))
            try:
                v = float(rec.get("valor", ""))
            except (TypeError, ValueError):
                continue
            rows.append({
                "series": name,
                "series_id": sid,
                "date": d,
                "value": v,
                "captured_at": now_iso,
            })
            if d > best[0]:
                best = (d, v)
        latest[name] = best

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"bcb_brazil: no fetch, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["series"], r["date"]), reverse=True)

    fieldnames = ["series", "series_id", "date", "value",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    blurb = " | ".join(
        f"{k}={v[1]} ({v[0]})"
        for k, v in latest.items() if v[0])
    print(f"bcb_brazil: {len(rows)} rows across {len(SERIES)} series "
          f"| {blurb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
