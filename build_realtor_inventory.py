#!/usr/bin/env python3
"""build_realtor_inventory.py — Realtor.com housing inventory + DOM.

Monthly housing-market inventory metrics from Realtor.com research
data. Fills the gap between Zillow home values (ZHVI) and Zillow
rents (ZORI): real-time supply/demand tension at the MLS level.

Signal:
- active_listing_count rising + median_days_on_market rising =
  cooling buyer demand → homebuilder risk (DHI, LEN, PHM, TOL)
- price_reduced_share > 0.40 = seller capitulation cycle →
  Zillow/Redfin traffic up → Z, COMP, RDFN revenue; mortgage
  refi volume impairment (RKT, UWMC, COOP)
- pending_listing_count YoY accel = closing velocity intact →
  title insurance (FNF, FAF, STC), realtor commissions (Z, RDFN)
- new_listing_count YoY surge = sellers unlocking (rate-lock thaw)

Drives:
- Homebuilders (DHI, LEN, PHM, NVR, TOL, MTH, KBH)
- Real-estate tech (Z, COMP, RDFN, EXPI, RMAX)
- Mortgage originators (RKT, UWMC, PFSI, COOP)
- Title insurance (FNF, FAF, STC, ITGR)
- Home improvement (HD, LOW, FND, TTS)
- Moving/storage (UHAL, PSA, EXR, LSI, CUBE)

Source: econdata.s3-us-west-2.amazonaws.com/Reports/Core/
        RDC_Inventory_Core_Metrics_Country.csv (+ Metro variant).
Output: realtor_inventory.csv
Columns: region, period, median_listing_price, median_listing_yoy_pct,
         active_listings, active_listings_yoy_pct, median_days_on_market,
         new_listing_count, pending_listing_count, price_reduced_share,
         captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import urllib.request
from io import StringIO
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "realtor_inventory.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
COUNTRY_URL = ("https://econdata.s3-us-west-2.amazonaws.com/"
               "Reports/Core/RDC_Inventory_Core_Metrics_Country_History.csv")
METRO_URL = ("https://econdata.s3-us-west-2.amazonaws.com/"
             "Reports/Core/RDC_Inventory_Core_Metrics_Metro.csv")

FOCUS_METROS = {
    "new york-newark-jersey city, ny-nj-pa",
    "los angeles-long beach-anaheim, ca",
    "chicago-naperville-elgin, il-in-wi",
    "dallas-fort worth-arlington, tx",
    "houston-the woodlands-sugar land, tx",
    "miami-fort lauderdale-pompano beach, fl",
    "atlanta-sandy springs-alpharetta, ga",
    "phoenix-mesa-chandler, az",
    "tampa-st. petersburg-clearwater, fl",
    "austin-round rock-georgetown, tx",
    "denver-aurora-lakewood, co",
    "seattle-tacoma-bellevue, wa",
    "san francisco-oakland-berkeley, ca",
    "boston-cambridge-newton, ma-nh",
    "washington-arlington-alexandria, dc-va-md-wv",
}


def _fetch(url: str) -> list[dict] | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"realtor_inventory: {url}: {e}")
        return None
    reader = csv.DictReader(StringIO(text))
    return list(reader)


def _fmt(v: str, digits: int = 2) -> str:
    if v in (None, "", "NaN"):
        return ""
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return ""


def _fmt_pct(v: str) -> str:
    if v in (None, "", "NaN"):
        return ""
    try:
        return f"{float(v) * 100:+.2f}"
    except (TypeError, ValueError):
        return ""


def main() -> None:
    rows: list[dict] = []

    country = _fetch(COUNTRY_URL) or []
    country.sort(key=lambda r: r.get("month_date_yyyymm", ""), reverse=True)
    for rec in country[:24]:  # 24 months
        period = rec.get("month_date_yyyymm", "")
        if len(period) == 6:
            period = f"{period[:4]}-{period[4:]}"
        rows.append({
            "region": "United States",
            "period": period,
            "median_listing_price": _fmt(rec.get("median_listing_price"), 0),
            "median_listing_yoy_pct": _fmt_pct(
                rec.get("median_listing_price_yy")),
            "active_listings": _fmt(rec.get("active_listing_count"), 0),
            "active_listings_yoy_pct": _fmt_pct(
                rec.get("active_listing_count_yy")),
            "median_days_on_market": _fmt(rec.get("median_days_on_market"), 0),
            "new_listing_count": _fmt(rec.get("new_listing_count"), 0),
            "pending_listing_count": _fmt(rec.get("pending_listing_count"), 0),
            "price_reduced_share": _fmt(rec.get("price_reduced_share"), 4),
        })

    # Metro: latest month only.
    metro = _fetch(METRO_URL) or []
    if metro:
        latest_period = max(
            (m.get("month_date_yyyymm", "") for m in metro), default="")
        for rec in metro:
            if rec.get("month_date_yyyymm") != latest_period:
                continue
            name = (rec.get("cbsa_title") or "").strip().lower()
            if name not in FOCUS_METROS:
                continue
            period = latest_period
            if len(period) == 6:
                period = f"{period[:4]}-{period[4:]}"
            rows.append({
                "region": rec.get("cbsa_title", name)[:60],
                "period": period,
                "median_listing_price": _fmt(
                    rec.get("median_listing_price"), 0),
                "median_listing_yoy_pct": _fmt_pct(
                    rec.get("median_listing_price_yy")),
                "active_listings": _fmt(rec.get("active_listing_count"), 0),
                "active_listings_yoy_pct": _fmt_pct(
                    rec.get("active_listing_count_yy")),
                "median_days_on_market": _fmt(
                    rec.get("median_days_on_market"), 0),
                "new_listing_count": _fmt(rec.get("new_listing_count"), 0),
                "pending_listing_count": _fmt(
                    rec.get("pending_listing_count"), 0),
                "price_reduced_share": _fmt(
                    rec.get("price_reduced_share"), 4),
            })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"realtor_inventory: empty, keeping existing "
                  f"{OUT_CSV.name}")
        return

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in rows:
        r["captured_at"] = now

    fieldnames = ["region", "period", "median_listing_price",
                  "median_listing_yoy_pct", "active_listings",
                  "active_listings_yoy_pct", "median_days_on_market",
                  "new_listing_count", "pending_listing_count",
                  "price_reduced_share", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Log: latest US + a couple of metros.
    us = next((r for r in rows if r["region"] == "United States"), None)
    bits = []
    if us:
        bits.append(f"US {us['period']}=${us['median_listing_price']} "
                    f"YoY={us['median_listing_yoy_pct']}% "
                    f"DOM={us['median_days_on_market']}d "
                    f"reduced={us['price_reduced_share']}")
    miami = next((r for r in rows if "Miami" in r["region"]), None)
    if miami:
        bits.append(f"Miami_YoY={miami['median_listing_yoy_pct']}%")
    austin = next((r for r in rows if "Austin" in r["region"]), None)
    if austin:
        bits.append(f"Austin_YoY={austin['median_listing_yoy_pct']}%")
    print(f"realtor_inventory: {len(rows)} rows | {' | '.join(bits)} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
