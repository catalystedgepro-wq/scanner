#!/usr/bin/env python3
"""build_finra_short_volume.py — FINRA Reg SHO daily short volume.

FINRA publishes consolidated short sale volume by ticker each trading
day via Reg SHO. Signal: tickers with sudden spike in short_ratio
(ShortVolume/TotalVolume) are pre-squeeze candidates — the squeeze
hunter is already populated by separate data, but this gives the
*build-up* tape before the squeeze pill flips.

Economic readthrough:
- short_ratio > 55% with rising day-over-day -> short-side crowding.
- short_ratio dropping -7d while total volume surging -> covering.
- Pairs well with insider_cluster + Russell 2000 gap list.

Source: cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt
Format: Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market

Output: finra_short_volume.csv
Lookback: last 5 trading days (walks back weekends/holidays).
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "finra_short_volume.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"
LOOKBACK_DAYS = 5
MIN_VOL = 500_000


def _fetch_day(day: dt.date) -> list[dict] | None:
    url = (f"https://cdn.finra.org/equity/regsho/daily/"
           f"CNMSshvol{day.strftime('%Y%m%d')}.txt")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    lines = data.splitlines()
    if len(lines) < 2:
        return None
    out: list[dict] = []
    for ln in lines[1:]:
        parts = ln.split("|")
        if len(parts) < 6:
            continue
        try:
            sv = float(parts[2])
            sev = float(parts[3])
            tv = float(parts[4])
        except ValueError:
            continue
        if tv < MIN_VOL:
            continue
        ratio = (sv / tv) if tv > 0 else 0.0
        out.append({
            "date": parts[0],
            "ticker": parts[1],
            "short_vol": int(sv),
            "exempt_vol": int(sev),
            "total_vol": int(tv),
            "short_ratio": round(ratio, 4),
            "market": parts[5],
        })
    return out


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    rows: list[dict] = []
    days_fetched = 0
    d = dt.date.today()
    tries = 0
    while days_fetched < LOOKBACK_DAYS and tries < 14:
        tries += 1
        d = d - dt.timedelta(days=1)
        if d.weekday() >= 5:
            continue
        batch = _fetch_day(d)
        if batch is None:
            continue
        rows.extend(batch)
        days_fetched += 1

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"finra_short_volume: no fetch, keeping {OUT_CSV.name}")
        return

    for r in rows:
        r["captured_at"] = now_iso
    rows.sort(key=lambda r: (r["date"], -r["short_ratio"]), reverse=True)
    fieldnames = ["date", "ticker", "short_vol", "exempt_vol",
                  "total_vol", "short_ratio", "market", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest_date = max(r["date"] for r in rows)
    latest = [r for r in rows if r["date"] == latest_date]
    hot = sorted(latest, key=lambda r: -r["short_ratio"])[:10]
    blurb = " ".join(f"{r['ticker']}={r['short_ratio']:.2f}" for r in hot)
    print(f"finra_short_volume: {len(rows)} rows, {days_fetched}d | "
          f"latest={latest_date} top10 [{blurb}] -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
