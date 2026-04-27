#!/usr/bin/env python3
"""Cross-reference FINRA RegSHO short volume with today's pipeline picks.

Fetches prior-day short volume (NASDAQ + NYSE + OTC), aggregates by ticker,
and flags picks with short ratio ≥45% as squeeze candidates.
Outputs: short_interest.csv
"""
from __future__ import annotations
import csv, datetime as dt, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
UA = "CatalystEdge/1.0 (opensource@example.com)"
SQUEEZE_THRESHOLD = 0.45

FINRA_URLS = [
    "http://regsho.finra.org/FNSQshvol{date}.txt",
    "http://regsho.finra.org/FNYXshvol{date}.txt",
    "http://regsho.finra.org/FNTRFshvol{date}.txt",
]


def prev_trading_day() -> str:
    d = dt.date.today() - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d.strftime("%m%d%Y")


def fetch_finra(url: str) -> dict[str, dict]:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20
        ) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"short_interest: fetch failed — {e}")
        return {}
    out: dict[str, dict] = {}
    for line in raw.splitlines():
        parts = line.split("|")
        if len(parts) < 5 or parts[1] in ("SYMBOL", ""):
            continue
        sym = parts[1].strip().upper()
        try:
            sv, tv = int(parts[2]), int(parts[4])
        except (ValueError, IndexError):
            continue
        if tv <= 0:
            continue
        if sym in out:
            out[sym]["short_vol"] += sv
            out[sym]["total_vol"] += tv
        else:
            out[sym] = {"short_vol": sv, "total_vol": tv}
    return out


def main() -> int:
    trading_date = prev_trading_day()
    combined: dict[str, dict] = {}
    for url_tpl in FINRA_URLS:
        for sym, vals in fetch_finra(url_tpl.format(date=trading_date)).items():
            if sym in combined:
                combined[sym]["short_vol"] += vals["short_vol"]
                combined[sym]["total_vol"] += vals["total_vol"]
            else:
                combined[sym] = dict(vals)
    for sym in combined:
        sv, tv = combined[sym]["short_vol"], combined[sym]["total_vol"]
        combined[sym]["short_ratio"] = sv / tv if tv > 0 else 0.0
    print(f"short_interest: {len(combined)} symbols from FINRA ({trading_date})")

    our_tickers: dict[str, dict] = {}
    for fname in ["sec_clean_gappers.csv", "sec_clean_value.csv", "sec_clean_moat_core.csv"]:
        path = ROOT / fname
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row.get("ticker", "").upper()
                if t and t not in our_tickers:
                    our_tickers[t] = {k: row.get(k, "") for k in ("price", "avg_vol_3m", "tags", "link")}

    out_rows: list[dict] = []
    for ticker, pdata in our_tickers.items():
        si = combined.get(ticker)
        if not si:
            continue
        ratio = si["short_ratio"]
        out_rows.append({
            "ticker": ticker,
            "short_ratio": f"{ratio:.4f}",
            "short_pct": f"{ratio * 100:.1f}%",
            "short_vol": si["short_vol"],
            "total_vol": si["total_vol"],
            "squeeze_flag": "1" if ratio >= SQUEEZE_THRESHOLD else "0",
            "price": pdata.get("price", ""),
            "avg_vol_3m": pdata.get("avg_vol_3m", ""),
            "finra_date": trading_date,
            "link": pdata.get("link", ""),
        })
    out_rows.sort(key=lambda r: -float(r["short_ratio"]))

    out_path = ROOT / "short_interest.csv"
    fieldnames = ["ticker","short_ratio","short_pct","short_vol","total_vol",
                  "squeeze_flag","price","avg_vol_3m","finra_date","link"]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    high = sum(1 for r in out_rows if r["squeeze_flag"] == "1")
    print(f"short_interest: {len(out_rows)} matched, {high} squeeze candidates → {out_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
