#!/usr/bin/env python3
"""build_rba_rates.py — RBA Australia cash rate + AUD FX tape.

Reserve Bank of Australia is a key global commodity-currency signal:
- AUD is a high-beta proxy for China growth and iron ore demand
- RBA cash rate diverges from Fed → drives AUDUSD positioning
- RBA is often the canary for APAC rate cycles (moves before Fed)

Signals captured daily:
- Cash rate target (policy rate)
- Interbank overnight rate (market realized)
- 90d bank-bill, 6m OIS (short end of curve)
- AUDUSD + trade-weighted index
- AUDCNY (direct China proxy)
- AUDJPY (APAC carry)

Readthrough: iron ore majors (BHP, RIO, VALE, FCX),
China-linked US stocks (YUM, WYNN, LVS), APAC carry (JPY crosses).

Source: rba.gov.au/statistics/tables/csv/f1-data.csv (rates)
        rba.gov.au/statistics/tables/csv/f11-data.csv (FX)
Output: rba_rates.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "rba_rates.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
F1 = "https://www.rba.gov.au/statistics/tables/csv/f1-data.csv"
F11 = "https://www.rba.gov.au/statistics/tables/csv/f11-data.csv"

F1_COLS = {
    "cash_rate_target": "FIRMMCRTD",
    "overnight_cash": "FIRMMCRID",
    "bill_90d": "FIRMMBAB90D",
    "ois_6m": "FIRMMOIS6D",
}
F11_COLS = {
    "audusd": "FXRUSD",
    "aud_twi": "FXRTWI",
    "audcny": "FXRCR",
    "audjpy": "FXRJY",
    "audeur": "FXREUR",
}


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8-sig", errors="ignore")
    except Exception as e:
        print(f"rba_rates: {url[-15:]}: {e}")
        return ""


def _parse_table(text: str, want_cols: dict[str, str],
                 days: int) -> dict[str, dict[str, float]]:
    """Parse RBA CSV. Returns {iso_date: {key: value}} for last `days`."""
    lines = text.split("\n")
    if len(lines) < 15:
        return {}
    # Header rows: Title, Description, Frequency, Type, Units,
    #              blank, Source, Publication date, Series ID
    series_row_idx = -1
    for i, L in enumerate(lines[:20]):
        if L.startswith("Series ID,"):
            series_row_idx = i
            break
    if series_row_idx < 0:
        return {}
    series_ids = [c.strip() for c in
                  lines[series_row_idx].split(",")][1:]
    want_by_col: dict[int, str] = {}
    for key, sid in want_cols.items():
        if sid in series_ids:
            want_by_col[series_ids.index(sid)] = key

    cutoff = dt.date.today() - dt.timedelta(days=days)
    out: dict[str, dict[str, float]] = {}
    for L in lines[series_row_idx + 1:]:
        if not L.strip():
            continue
        cells = L.split(",")
        if len(cells) < 2:
            continue
        date_raw = cells[0].strip()
        try:
            d = dt.datetime.strptime(date_raw, "%d-%b-%Y").date()
        except Exception:
            continue
        if d < cutoff:
            continue
        iso = d.isoformat()
        row: dict[str, float] = {}
        for idx, key in want_by_col.items():
            if idx >= len(cells) - 1:
                continue
            v = cells[idx + 1].strip()
            if not v:
                continue
            try:
                row[key] = float(v)
            except ValueError:
                continue
        if row:
            out[iso] = row
    return out


def main() -> None:
    rates_raw = _get(F1)
    fx_raw = _get(F11)
    if not rates_raw and not fx_raw:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"rba_rates: no fetch, keeping {OUT_CSV.name}")
        return

    rates = _parse_table(rates_raw, F1_COLS, days=90) if rates_raw else {}
    fx = _parse_table(fx_raw, F11_COLS, days=90) if fx_raw else {}

    all_dates = sorted(set(rates) | set(fx), reverse=True)
    if not all_dates:
        return

    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    rows: list[dict] = []
    for iso in all_dates:
        r = rates.get(iso, {})
        f = fx.get(iso, {})
        rows.append({
            "date": iso,
            "cash_rate_target": f"{r['cash_rate_target']:.2f}"
                                if "cash_rate_target" in r else "",
            "overnight_cash": f"{r['overnight_cash']:.2f}"
                              if "overnight_cash" in r else "",
            "bill_90d": f"{r['bill_90d']:.2f}"
                        if "bill_90d" in r else "",
            "ois_6m": f"{r['ois_6m']:.2f}" if "ois_6m" in r else "",
            "audusd": f"{f['audusd']:.4f}" if "audusd" in f else "",
            "aud_twi": f"{f['aud_twi']:.2f}" if "aud_twi" in f else "",
            "audcny": f"{f['audcny']:.4f}" if "audcny" in f else "",
            "audjpy": f"{f['audjpy']:.2f}" if "audjpy" in f else "",
            "audeur": f"{f['audeur']:.4f}" if "audeur" in f else "",
            "captured_at": now_iso,
        })

    fieldnames = ["date", "cash_rate_target", "overnight_cash",
                  "bill_90d", "ois_6m", "audusd", "aud_twi",
                  "audcny", "audjpy", "audeur", "captured_at"]
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest_rate = next((r for r in rows if r["cash_rate_target"]), {})
    latest_fx = next((r for r in rows if r["audusd"]), {})
    print(f"rba_rates: {len(rows)} rows | "
          f"rate@{latest_rate.get('date')}={latest_rate.get('cash_rate_target')} "
          f"fx@{latest_fx.get('date')} audusd={latest_fx.get('audusd')} "
          f"twi={latest_fx.get('aud_twi')} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
