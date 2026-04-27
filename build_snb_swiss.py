#!/usr/bin/env python3
"""build_snb_swiss.py — Swiss National Bank macro snapshot (FX / rates / yields).

SNB data cube API (data.snb.ch/api/cube/{cube}/data/csv/en).
- zimoma: monthly money-market rates (SARON, SOFR/SONIA/ESTR reference,
  policy-target 1TGT)
- devkum: monthly FX reference rates (CHF vs USD, EUR, GBP, JPY, CNY)
- rendoblid: monthly Confederation bond yield curve (1J..30J)

Switzerland = safe-haven FX flow signal.  Policy rate → CHF strength →
Switzerland-export names (NSRGY, ROG, NESN, NVS, UBS).  When CHF strength
spikes it's a global risk-off symptom.

Keeps last 24 months for each series.
Output: snb_swiss.csv (long-format: category, date, metric, value)
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "snb_swiss.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://data.snb.ch/api/cube/{cube}/data/csv/en?dateFrom={frm}"

# 24-month lookback sufficient for trend signal.
NOW = dt.date.today()
FROM = f"{NOW.year - 2}-{NOW.month:02d}"

RATE_KEEP = {"1TGT", "SARON", "SOFR", "SONIA", "ESTR"}
FX_KEEP = {"USD1", "EUR1", "GBP1", "JPY100", "CNY100"}
YIELD_KEEP = {"2J", "5J", "10J0", "30J"}


def _fetch(cube: str) -> str | None:
    url = BASE.format(cube=cube, frm=FROM)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8-sig", errors="ignore")
    except Exception as e:
        print(f"snb_swiss: {cube}: {e}")
        return None


def _parse(text: str, keep: set[str], is_fx: bool) -> list[dict]:
    """Parse an SNB CSV. Header row starts with 'Date'. FX has extra D1."""
    out: list[dict] = []
    in_data = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not in_data:
            if line.startswith('"Date"'):
                in_data = True
            continue
        parts = [p.strip().strip('"') for p in line.split(";")]
        if is_fx:
            if len(parts) < 4:
                continue
            date, _d0, d1, value = parts[0], parts[1], parts[2], parts[3]
            key = d1
        else:
            if len(parts) < 3:
                continue
            date, d0, value = parts[0], parts[1], parts[2]
            key = d0
        if key not in keep or not value:
            continue
        # SNB API ignores dateFrom — filter here. Keep last 24 months.
        if date < FROM:
            continue
        try:
            v = float(value.replace(",", "."))
        except (TypeError, ValueError):
            continue
        out.append({"date": date, "metric": key, "value": v})
    return out


def main() -> None:
    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []

    zima = _fetch("zimoma")
    if zima:
        for r in _parse(zima, RATE_KEEP, is_fx=False):
            rows.append({"category": "rate", **r, "captured_at": now_iso})

    dev = _fetch("devkum")
    if dev:
        for r in _parse(dev, FX_KEEP, is_fx=True):
            rows.append({"category": "fx", **r, "captured_at": now_iso})

    yld = _fetch("rendoblid")
    if yld:
        for r in _parse(yld, YIELD_KEEP, is_fx=False):
            rows.append({"category": "yield", **r, "captured_at": now_iso})

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"snb_swiss: no fetch, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["category"], r["metric"], r["date"]),
              reverse=True)

    fieldnames = ["category", "date", "metric", "value", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({"category": r["category"], "date": r["date"],
                        "metric": r["metric"],
                        "value": f"{r['value']:.4f}",
                        "captured_at": r["captured_at"]})

    # Summary: latest SARON + latest CHF/USD + latest 10Y yield.
    def latest(cat: str, metric: str) -> str:
        for r in rows:
            if r["category"] == cat and r["metric"] == metric:
                return f"{r['value']:.3f} ({r['date']})"
        return "n/a"

    print(f"snb_swiss: {len(rows)} rows | saron={latest('rate','SARON')} "
          f"1tgt={latest('rate','1TGT')} "
          f"chfusd={latest('fx','USD1')} "
          f"10y={latest('yield','10J0')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
