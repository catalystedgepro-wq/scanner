#!/usr/bin/env python3
"""build_bcrp_peru.py — Banco Central de Reserva del Peru macro snapshot.

BCRP publishes open CSV-over-HTTP series (monthly). Response is a single
HTML-wrapped CSV with rows separated by <br> — not standard CSV.

Tracks (monthly):
- Inflation YoY (Lima, IPC 12-mo pct change) — policy-rate anchor.
- Interbank USD/PEN spot avg — Peru is #2 world copper exporter; PEN
  strengthens on copper rally, weakens on China slowdown fear.
- EMBIG Peru spread (bps) — sovereign credit-risk proxy vs EM peers.
- Lima employment index (3-mo moving average) — domestic demand gauge.

Economic readthrough:
- Peru is #2 copper, #1 silver, #4 zinc, #8 gold. SCCO/HBM/BHP/RIO
  have major Peru operations. FCX indirect.
- SPY-EMB-EPU beta: PEN weakness → EEM drawdowns amplified.
- Political overhang (recurrent gov crises) drives EMBIG spread.

Source: estadisticas.bcrp.gob.pe/estadisticas/series/api/{sid}/csv/{from}/{to}
Output: bcrp_peru.csv

Note: many BCRP daily series return 403 for anonymous access; this spoke
is deliberately scoped to monthly series that work without a key.
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "bcrp_peru.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

SERIES = {
    "cpi_yoy_lima": "PN01273PM",
    "fx_usd_pen_avg": "PN01207PM",
    "embig_peru_bps": "PN01135XM",
    "lima_employment": "PN38063GM",
}

MONTHS_ES = {
    "Ene": "01", "Feb": "02", "Mar": "03", "Abr": "04", "May": "05",
    "Jun": "06", "Jul": "07", "Ago": "08", "Set": "09", "Sep": "09",
    "Oct": "10", "Nov": "11", "Dic": "12",
}


def _parse_date(raw: str) -> str:
    # e.g. "Ene.2024" → "2024-01"
    raw = raw.strip().strip('"')
    m = re.match(r"([A-Za-z]{3})\.(\d{4})", raw)
    if not m:
        return raw
    mm = MONTHS_ES.get(m.group(1))
    if not mm:
        return raw
    return f"{m.group(2)}-{mm}"


def _fetch(sid: str, date_from: str, date_to: str) -> list[tuple[str, float]]:
    url = (f"https://estadisticas.bcrp.gob.pe/estadisticas/series/api/"
           f"{sid}/csv/{date_from}/{date_to}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"bcrp_peru: {sid} fetch failed: {e}")
        return []
    # Response uses <br>-separated rows inside HTML wrapper.
    lines = body.replace("<br>", "\n").splitlines()
    out: list[tuple[str, float]] = []
    for ln in lines[1:]:  # skip header
        ln = ln.strip()
        if not ln:
            continue
        parts = [p.strip().strip('"') for p in ln.split(",", 1)]
        if len(parts) != 2:
            continue
        d = _parse_date(parts[0])
        try:
            v = float(parts[1])
        except (TypeError, ValueError):
            continue
        out.append((d, v))
    return out


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    today = dt.date.today()
    date_from = f"{today.year - 2}-1"
    date_to = f"{today.year + 1}-12"
    rows: list[dict] = []
    latest: dict[str, tuple[str, float]] = {}

    for metric, sid in SERIES.items():
        series_rows = _fetch(sid, date_from, date_to)
        for d, v in series_rows:
            rows.append({
                "metric": metric,
                "series_id": sid,
                "date": d,
                "value": round(v, 6),
                "captured_at": now_iso,
            })
        if series_rows:
            last = max(series_rows, key=lambda x: x[0])
            latest[metric] = last

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"bcrp_peru: no fetch, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: (r["metric"], r["date"]), reverse=True)
    fieldnames = ["metric", "series_id", "date", "value", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    blurb = " | ".join(
        f"{k}={v[1]:.4g} ({v[0]})" for k, v in latest.items())
    print(f"bcrp_peru: {len(rows)} rows across {len(SERIES)} series | "
          f"{blurb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
