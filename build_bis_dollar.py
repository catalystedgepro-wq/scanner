#!/usr/bin/env python3
"""build_bis_dollar.py — BIS US dollar effective exchange rate.

Monthly BIS broad dollar index (64 economies) — nominal and real.
Purer FX-weighted dollar read than DXY (which is stuck on 6 currencies
with 58% EUR concentration).

Signal: BIS broad $ rising = global USD tightening → EM stress, commod
de-rate, Fed easing pressure. Falling = risk-on, EM tailwind, gold bid.

Drives:
- EM equity exposure (EEM, VWO, EEMA, EMXC)
- Commodity exporters (CLF, FCX, BHP, VALE, RIO, PBR)
- Currency ETFs (UUP, UDN, FXE, FXY, FXA)
- Gold / precious (GLD, SLV, GDX)
- US multinationals with FX-exposed earnings (AAPL, KO, PG, MSFT)

Source: stats.bis.org/api/v1/data/WS_EER (free, no key).
Output: bis_dollar.csv
Columns: period, nominal_index, real_index, nominal_yoy,
         real_yoy, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "bis_dollar.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL_NOM = "https://stats.bis.org/api/v1/data/WS_EER/M.N.B.US/all?format=csv"
URL_REAL = "https://stats.bis.org/api/v1/data/WS_EER/M.R.B.US/all?format=csv"


def _fetch(url: str) -> list[list[str]]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", errors="ignore")
    out: list[list[str]] = []
    reader = csv.reader(text.splitlines())
    for row in reader:
        out.append(row)
    return out


def _parse(rows: list[list[str]]) -> dict[str, float]:
    if not rows or len(rows) < 2:
        return {}
    header = rows[0]
    try:
        period_idx = header.index("TIME_PERIOD")
        value_idx = header.index("OBS_VALUE")
    except ValueError:
        return {}
    out: dict[str, float] = {}
    for row in rows[1:]:
        if len(row) <= max(period_idx, value_idx):
            continue
        period = row[period_idx]
        try:
            val = float(row[value_idx])
        except (TypeError, ValueError):
            continue
        if period:
            out[period] = val
    return out


def main() -> None:
    try:
        nom_rows = _fetch(URL_NOM)
        real_rows = _fetch(URL_REAL)
    except Exception as e:
        print(f"bis_dollar: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"bis_dollar: keeping existing {OUT_CSV.name}")
        return

    nom = _parse(nom_rows)
    real = _parse(real_rows)

    if not nom and not real:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"bis_dollar: empty, keeping existing {OUT_CSV.name}")
        return

    periods = sorted(set(nom.keys()) | set(real.keys()), reverse=True)
    # Keep most recent 60 months (5 years).
    periods = periods[:60]

    rows: list[dict] = []
    for period in periods:
        n_val = nom.get(period)
        r_val = real.get(period)
        # YoY = same-period-12mo-ago
        try:
            ymo = int(period[:4])
            mo = period[5:7]
            prev_period = f"{ymo - 1}-{mo}"
        except (ValueError, IndexError):
            prev_period = ""
        n_yoy = ""
        r_yoy = ""
        if n_val is not None and prev_period in nom and nom[prev_period]:
            n_yoy = f"{(n_val / nom[prev_period] - 1) * 100:+.2f}"
        if r_val is not None and prev_period in real and real[prev_period]:
            r_yoy = f"{(r_val / real[prev_period] - 1) * 100:+.2f}"
        rows.append({
            "period": period,
            "nominal_index": f"{n_val:.3f}" if n_val is not None else "",
            "real_index": f"{r_val:.3f}" if r_val is not None else "",
            "nominal_yoy": n_yoy,
            "real_yoy": r_yoy,
        })

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["period", "nominal_index", "real_index", "nominal_yoy",
                  "real_yoy", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest = rows[0] if rows else {}
    print(f"bis_dollar: {len(rows)} months | latest {latest.get('period')} "
          f"nom={latest.get('nominal_index')} real={latest.get('real_index')} "
          f"nom_yoy={latest.get('nominal_yoy')}% -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
