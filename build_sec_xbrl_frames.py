#!/usr/bin/env python3
"""build_sec_xbrl_frames.py — SEC XBRL cross-sectional fundamentals.

SEC XBRL frames API returns quarterly snapshots of a single
accounting concept across every filer who reported it. This pulls
Revenues and NetIncomeLoss for the latest available quarter,
merges by CIK, and joins tickers from the SEC master list.

Economic readthrough:
- Top-line ranks by revenue -> megacap visibility tape.
- Largest net-loss companies -> distress screening candidates.
- Margin pct (net_income / revenue) -> quality screen.
- Sudden ranking shifts (vs prior qtr) signal earnings beats/misses
  and guide-downs independent of analyst models.

Source:
- data.sec.gov/api/xbrl/frames/us-gaap/Revenues/USD/CYyyyyQq.json
- data.sec.gov/api/xbrl/frames/us-gaap/NetIncomeLoss/USD/CYyyyyQq.json
- sec.gov/files/company_tickers.json

Output: sec_xbrl_frames.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_xbrl_frames.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

FRAME_BASE = "https://data.sec.gov/api/xbrl/frames/us-gaap"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _pick_quarter() -> str:
    """Walk back quarters until we find one with data."""
    today = dt.date.today()
    year = today.year
    q = (today.month - 1) // 3 + 1
    for _ in range(6):
        q -= 1
        if q == 0:
            q = 4
            year -= 1
        tag = f"CY{year}Q{q}"
        url = f"{FRAME_BASE}/Revenues/USD/{tag}.json"
        try:
            j = _fetch_json(url)
            if j.get("data"):
                return tag
        except Exception:
            continue
    return ""


def _tickers() -> dict[int, str]:
    try:
        j = _fetch_json(TICKERS_URL)
        return {int(v["cik_str"]): v["ticker"] for v in j.values()}
    except Exception as e:
        print(f"sec_xbrl_frames: ticker map failed: {e}")
        return {}


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    tag = _pick_quarter()
    if not tag:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_xbrl_frames: no quarter, keeping {OUT_CSV.name}")
        return

    try:
        rev = _fetch_json(f"{FRAME_BASE}/Revenues/USD/{tag}.json")
        ni = _fetch_json(f"{FRAME_BASE}/NetIncomeLoss/USD/{tag}.json")
    except Exception as e:
        print(f"sec_xbrl_frames: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_xbrl_frames: keeping {OUT_CSV.name}")
        return

    tix = _tickers()
    ni_by_cik = {d["cik"]: d["val"] for d in ni.get("data", [])}

    merged: list[dict] = []
    for d in rev.get("data", []):
        cik = d.get("cik")
        val = d.get("val") or 0
        if val <= 0:
            continue
        nival = ni_by_cik.get(cik)
        margin = (nival / val * 100.0) if (nival is not None and val) else None
        merged.append({
            "quarter": tag,
            "ticker": tix.get(cik, ""),
            "cik": cik,
            "name": (d.get("entityName") or "")[:60],
            "loc": d.get("loc", ""),
            "revenue_q": val,
            "net_income_q": nival if nival is not None else "",
            "margin_pct": round(margin, 2) if margin is not None else "",
        })

    if not merged:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_xbrl_frames: no rows, keeping {OUT_CSV.name}")
        return

    merged.sort(key=lambda r: r["revenue_q"], reverse=True)
    top = merged[:300]

    for r in top:
        r["captured_at"] = now_iso
    fieldnames = ["quarter", "ticker", "cik", "name", "loc",
                  "revenue_q", "net_income_q", "margin_pct", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(top)

    with_t = sum(1 for r in top if r["ticker"])
    losses = [r for r in top if isinstance(r["net_income_q"], (int, float))
              and r["net_income_q"] < 0]
    losses.sort(key=lambda r: r["net_income_q"])
    loss_top = " | ".join(f"{r['ticker'] or r['name'][:10]}"
                          f"={r['net_income_q']/1e6:.0f}M"
                          for r in losses[:4])
    mega = " | ".join(f"{r['ticker'] or r['name'][:10]}"
                      f"={r['revenue_q']/1e9:.1f}B" for r in top[:4])
    print(f"sec_xbrl_frames: {tag} {len(top)} rows ({with_t} tix) | "
          f"top rev: [{mega}] | biggest losses: [{loss_top}] "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
