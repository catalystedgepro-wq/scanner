#!/usr/bin/env python3
"""build_finra_reg_sho.py — FINRA Reg SHO daily short sale volume.

Daily short sale volume by symbol across all FINRA venues. High short
volume ratio (>50% of reported volume) = borrow pressure = squeeze
risk if catalyst hits. Pairs with build_squeeze_hunter to elevate
names with real short activity, not just high SI.

Source: regsho.finra.org/CNMSshvol[YYYYMMDD].txt
Output: finra_reg_sho.csv
Columns: date, symbol, short_vol, total_vol, short_ratio, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "finra_reg_sho.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"


def fetch(d: dt.date) -> list[dict]:
    url = (
        f"https://cdn.finra.org/equity/regsho/daily/"
        f"CNMSshvol{d.year}{d.month:02d}{d.day:02d}.txt"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read().decode("utf-8", errors="ignore")
    except Exception:
        return []
    out: list[dict] = []
    lines = txt.splitlines()
    if not lines or "Symbol" not in lines[0]:
        return []
    for line in lines[1:]:
        if not line.strip() or line.startswith("Total"):
            continue
        parts = line.split("|")
        if len(parts) < 5:
            continue
        try:
            date_s, sym, sv, _stex, tv = parts[0], parts[1], parts[2], parts[3], parts[4]
            sv_f = float(sv or 0)
            tv_f = float(tv or 0)
            if tv_f <= 0:
                continue
            ratio = sv_f / tv_f
            out.append({
                "date": f"{date_s[:4]}-{date_s[4:6]}-{date_s[6:8]}",
                "symbol": sym[:10],
                "short_vol": f"{sv_f:.0f}",
                "total_vol": f"{tv_f:.0f}",
                "short_ratio": f"{ratio:.3f}",
            })
        except Exception:
            continue
    return out


def main() -> None:
    today = dt.date.today()
    rows: list[dict] = []
    for back in range(1, 8):
        d = today - dt.timedelta(days=back)
        rows = fetch(d)
        if rows:
            break
    rows = [r for r in rows if float(r["short_ratio"]) >= 0.40 and float(r["total_vol"]) >= 500_000]
    rows.sort(key=lambda r: float(r["total_vol"]), reverse=True)
    rows = rows[:400]
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "symbol", "short_vol", "total_vol",
                        "short_ratio", "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    print(f"finra_reg_sho: {len(rows)} high-short-ratio names | top "
          f"{top.get('symbol','?')} ratio={top.get('short_ratio','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
