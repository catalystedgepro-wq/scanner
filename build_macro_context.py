#!/usr/bin/env python3
"""Fetch key macro indicators from FRED public CSV API (no API key required).

Indicators: DGS10 (10Y Treasury), VIXCLS (VIX), SP500, FEDFUNDS, UNRATE
Outputs: macro_context.json
"""
from __future__ import annotations
import csv, io, json, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
MACRO_JSON = ROOT / "macro_context.json"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES_CONFIG: dict[str, dict] = {
    "DGS10":    {"label": "10Y Treasury",   "unit": "%",  "fmt": "{:.2f}"},
    "VIXCLS":   {"label": "VIX",            "unit": "",   "fmt": "{:.1f}"},
    "SP500":    {"label": "S&P 500",        "unit": "",   "fmt": "{:,.0f}"},
    "FEDFUNDS": {"label": "Fed Funds Rate", "unit": "%",  "fmt": "{:.2f}"},
    "UNRATE":   {"label": "Unemployment",   "unit": "%",  "fmt": "{:.1f}"},
}


def fetch_series(series_id: str) -> list[tuple[str, str]]:
    req = urllib.request.Request(
        FRED_CSV.format(series=series_id),
        headers={"User-Agent": UA, "Accept": "text/csv"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"macro: {series_id} failed: {e}")
        return []
    rows = list(csv.reader(io.StringIO(raw)))
    return [(r[0], r[1]) for r in rows[1:] if len(r) == 2 and r[1] not in ("", ".")]


def main() -> int:
    result: dict = {}
    for series_id, meta in SERIES_CONFIG.items():
        data = fetch_series(series_id)
        if not data:
            result[series_id] = {"label": meta["label"], "value": None, "date": None,
                                  "change": None, "unit": meta["unit"]}
            continue
        date, raw_val = data[-1]
        try:
            val = float(raw_val)
        except ValueError:
            result[series_id] = {"label": meta["label"], "value": None, "date": date,
                                  "change": None, "unit": meta["unit"]}
            continue
        change_str = None
        if len(data) >= 2:
            try:
                prev = float(data[-2][1])
                delta = val - prev
                change_str = f"{'+'if delta>=0 else ''}{delta:.2f}"
            except ValueError:
                pass
        formatted = meta["fmt"].format(val) + meta["unit"]
        result[series_id] = {
            "label": meta["label"], "value": formatted, "raw": val,
            "date": date, "change": change_str, "unit": meta["unit"],
        }
        print(f"macro: {series_id} = {formatted}  Δ{change_str or 'n/a'}  ({date})")

    MACRO_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"macro_context: saved → {MACRO_JSON.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
