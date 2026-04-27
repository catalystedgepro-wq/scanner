#!/usr/bin/env python3
"""build_nyfed_soma.py — NY Fed SOMA securities holdings weekly.

System Open Market Account = the Fed's securities portfolio.
Weekly snapshots of holdings by security type (Treasury
notes/bonds/bills, MBS, CMBS, TIPS, agencies). This is the
Fed's balance sheet in one file.

Signal for trading:
- MBS holdings declining (QT) at faster pace → mortgage rates
  rising → NLY, AGNC, MFA (REIT mREITs) margin compression;
  homebuilders (DHI, LEN, NVR) multiple compression.
- Notes/Bonds declining = Fed stepping away from treasury
  market → term premium rising → bank net interest margin
  expansion (JPM, BAC, WFC).
- TIPS holdings vs notes ratio: rising TIPS = Fed repositioning
  for inflation → inflation-protected funds (TIP, STIP) bid.
- Bills holdings spike = Fed funding operations (often bridge
  liquidity) → tight liquidity regime.
- Total balance sheet trajectory = QT/QE state. Week-over-week
  slope reveals pace change before FOMC announcements.
- Runoff cap vs actual: if actual < cap during QT phase,
  signals Fed-side liquidity concern (halted runoff markers
  precede rate-cut cycles).

Source: markets.newyorkfed.org/api/soma/summary.json
  (no key, weekly as-of Wednesday).

Output: nyfed_soma.csv
Columns: as_of_date, bills_usd, notesbonds_usd, tips_usd,
         tips_infl_comp_usd, frn_usd, mbs_usd, cmbs_usd,
         agencies_usd, total_usd, wow_change_usd, yoy_change_pct,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "nyfed_soma.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
URL = "https://markets.newyorkfed.org/api/soma/summary.json"


def fetch() -> list[dict]:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"nyfed_soma: {e}")
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return data.get("soma", {}).get("summary", []) or []


def _to_float(s) -> float:
    if s is None or s == "":
        return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def main() -> None:
    items = fetch()

    if not items:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"nyfed_soma: no data, keeping existing "
                  f"{OUT_CSV.name} ({OUT_CSV.stat().st_size} bytes)")
        return

    # Sort ascending for WoW / YoY calcs.
    items.sort(key=lambda r: r.get("asOfDate", ""))

    # Compute rolling stats.
    by_date: dict[str, dict] = {}
    ordered: list[dict] = []
    for rec in items:
        d = rec.get("asOfDate", "")
        if not d:
            continue
        total = _to_float(rec.get("total"))
        by_date[d] = {
            "date": d, "total": total,
            "notesbonds": _to_float(rec.get("notesbonds")),
            "bills": _to_float(rec.get("bills")),
            "mbs": _to_float(rec.get("mbs")),
            "cmbs": _to_float(rec.get("cmbs")),
            "tips": _to_float(rec.get("tips")),
            "tips_infl": _to_float(
                rec.get("tipsInflationCompensation")),
            "frn": _to_float(rec.get("frn")),
            "agencies": _to_float(rec.get("agencies")),
        }
        ordered.append(by_date[d])

    # Only keep last 260 weeks (5 years).
    ordered = ordered[-260:]

    rows: list[dict] = []
    for i, rec in enumerate(ordered):
        prev = ordered[i - 1] if i > 0 else None
        wow = (rec["total"] - prev["total"]) if prev else 0.0
        # YoY: find record ~52 weeks ago.
        yoy_pct = None
        d = rec["date"]
        try:
            dy, dm, dd = map(int, d.split("-"))
            prior_date = dt.date(dy - 1, dm, dd).isoformat()
        except Exception:
            prior_date = ""
        # Find closest prior-year record.
        if prior_date:
            candidates = [r for r in ordered
                          if r["date"] >= prior_date[:7] + "-01"
                          and r["date"] <= prior_date]
            if candidates:
                py_total = candidates[-1]["total"]
                if py_total > 0:
                    yoy_pct = (rec["total"] - py_total) / py_total * 100
        rows.append({
            "as_of_date": rec["date"],
            "bills_usd": f"{rec['bills']:.0f}",
            "notesbonds_usd": f"{rec['notesbonds']:.0f}",
            "tips_usd": f"{rec['tips']:.0f}",
            "tips_infl_comp_usd": f"{rec['tips_infl']:.0f}",
            "frn_usd": f"{rec['frn']:.0f}",
            "mbs_usd": f"{rec['mbs']:.0f}",
            "cmbs_usd": f"{rec['cmbs']:.0f}",
            "agencies_usd": f"{rec['agencies']:.0f}",
            "total_usd": f"{rec['total']:.0f}",
            "wow_change_usd": f"{wow:+.0f}",
            "yoy_change_pct": (f"{yoy_pct:.2f}"
                               if yoy_pct is not None else ""),
        })

    # Output most-recent-first.
    rows.sort(key=lambda r: r["as_of_date"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["as_of_date", "bills_usd", "notesbonds_usd",
                  "tips_usd", "tips_infl_comp_usd", "frn_usd",
                  "mbs_usd", "cmbs_usd", "agencies_usd",
                  "total_usd", "wow_change_usd", "yoy_change_pct",
                  "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    latest = rows[0]
    total_t = float(latest["total_usd"]) / 1e12
    mbs_t = float(latest["mbs_usd"]) / 1e12
    nb_t = float(latest["notesbonds_usd"]) / 1e12
    wow_b = float(latest["wow_change_usd"]) / 1e9
    print(f"nyfed_soma: {len(rows)} weeks | {latest['as_of_date']} "
          f"total=${total_t:.3f}T (notes=${nb_t:.2f}T MBS=${mbs_t:.2f}T) "
          f"WoW={wow_b:+.1f}B yoy={latest['yoy_change_pct']}% "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
