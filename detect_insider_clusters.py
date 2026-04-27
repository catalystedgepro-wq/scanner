#!/usr/bin/env python3
"""Detect insider cluster buying from Form 4 filings in today's SEC feed.

A cluster = 2+ separate Form 4 filings for the same ticker within today's scan.
Cross-references with classified CSVs to confirm buy direction.
Outputs: insider_clusters.csv
"""
from __future__ import annotations
import csv
import datetime as dt
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent


def main() -> int:
    catalyst_path = ROOT / "sec_catalyst_latest.csv"
    if not catalyst_path.exists():
        print("insider_clusters: sec_catalyst_latest.csv not found")
        return 1

    # Group Form 4 entries by ticker
    form4_by_ticker: dict[str, list[dict]] = defaultdict(list)
    with catalyst_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("form") == "4":
                ticker = row.get("ticker", "").strip().upper()
                if ticker:
                    form4_by_ticker[ticker].append(row)

    clusters = {t: rows for t, rows in form4_by_ticker.items() if len(rows) >= 2}

    # Load price/tag data from classified CSVs
    price_data: dict[str, dict] = {}
    tag_data: dict[str, str] = {}
    for fname in ["sec_clean_gappers.csv", "sec_clean_value.csv", "sec_clean_moat_core.csv",
                  "sec_top_gappers.csv", "sec_top_value.csv"]:
        path = ROOT / fname
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = row.get("ticker", "").upper()
                if t and t not in price_data:
                    price_data[t] = {
                        "price": row.get("price", ""),
                        "avg_vol_3m": row.get("avg_vol_3m", ""),
                        "market_cap": row.get("market_cap", ""),
                        "link": row.get("link", ""),
                    }
                if t and row.get("tags"):
                    tag_data[t] = row["tags"]

    out_rows: list[dict] = []
    for ticker, filings in sorted(clusters.items(), key=lambda x: -len(x[1])):
        tags = tag_data.get(ticker, "")
        is_buy = "+insider_buy_p" in tags.lower()
        latest_utc = max((f.get("updated_utc", "") for f in filings), default="")
        # Use link from first filing that has one, or from classified data
        primary_link = next((f["link"] for f in filings if f.get("link")), price_data.get(ticker, {}).get("link", ""))
        all_links = "|".join(f.get("link", "") for f in filings if f.get("link"))
        pdata = price_data.get(ticker, {})
        out_rows.append({
            "ticker": ticker,
            "filing_count": len(filings),
            "confirmed_buy": "1" if is_buy else "0",
            "latest_utc": latest_utc,
            "price": pdata.get("price", ""),
            "avg_vol_3m": pdata.get("avg_vol_3m", ""),
            "market_cap": pdata.get("market_cap", ""),
            "tags": tags,
            "primary_link": primary_link,
            "all_links": all_links,
        })

    out_rows.sort(key=lambda r: (-int(r["confirmed_buy"]), -int(r["filing_count"])))

    out_path = ROOT / "insider_clusters.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ticker","filing_count","confirmed_buy","latest_utc",
                                               "price","avg_vol_3m","market_cap","tags","primary_link","all_links"])
        writer.writeheader()
        writer.writerows(out_rows)

    confirmed = sum(1 for r in out_rows if r["confirmed_buy"] == "1")
    print(f"insider_clusters: {len(clusters)} clusters found, {confirmed} confirmed buys → {out_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
