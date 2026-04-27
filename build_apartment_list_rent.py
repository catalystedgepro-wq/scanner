#!/usr/bin/env python3
"""build_apartment_list_rent.py — Apartment List national rent index.

Apartment List rent estimates release ~10 days before Zillow ZORI.
Rising rent → REITs (AVB, EQR, ESS) tailwind; falling rent → home
builders under pressure (LEN, DHI, PHM) if cap rates compress.
Also proxies CPI shelter component (~35% of core CPI).

Source: apartmentlist.com/research/category/data — national CSV.
Output: apartment_list_rent.csv
Columns: date, location, rent_usd, yoy_pct, mom_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "apartment_list_rent.csv"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"


def fetch() -> list[list[str]]:
    """Discover the latest CSV URL from the research page and fetch it."""
    import re as _re
    page_url = "https://www.apartmentlist.com/research/category/data-rent-estimates"
    try:
        req = urllib.request.Request(page_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"apartment_list index: {e}")
        return []
    hits = _re.findall(
        r'https://[^"]*apartment[^"]*rent[^"]*\.csv', html, _re.I
    )
    if not hits:
        # Try Cloudfront research hostname
        hits = _re.findall(r'https://[^"]+/Rent_Estimates_\d{4}_\d{2}\.csv', html)
    for url in hits[:3]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                txt = r.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        reader = csv.reader(txt.splitlines())
        return list(reader)
    return []


def main() -> None:
    rows_raw = fetch()
    if not rows_raw:
        OUT_CSV.write_text("date,location,rent_usd,yoy_pct,mom_pct,captured_at\n")
        print(f"apartment_list_rent: 0 rows -> {OUT_CSV.name}")
        return
    header = rows_raw[0]
    # Typical long-format: location_name,year,month,rent_estimate
    date_cols = [c for c in header if re.match(r"\d{4}[_-]\d{1,2}", c)]
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    if date_cols:
        loc_idx = 0
        if "location_name" in header:
            loc_idx = header.index("location_name")
        for r in rows_raw[1:]:
            if len(r) < len(header):
                continue
            loc = r[loc_idx]
            for i, c in enumerate(header):
                if c not in date_cols:
                    continue
                v = r[i].strip()
                if not v:
                    continue
                try:
                    rent = float(v)
                except Exception:
                    continue
                d = c.replace("_", "-")
                if len(d) == 6:
                    d = f"{d[:4]}-0{d[5]}"
                rows.append({
                    "date": d,
                    "location": loc[:60],
                    "rent_usd": f"{rent:.0f}",
                    "yoy_pct": "",
                    "mom_pct": "",
                    "captured_at": now,
                })
    else:
        # Long format path
        idx = {name: i for i, name in enumerate(header)}
        for r in rows_raw[1:]:
            try:
                loc = r[idx.get("location_name", 0)]
                year = r[idx.get("year", 1)]
                month = r[idx.get("month", 2)]
                rent = r[idx.get("rent_estimate", 3)]
                if not rent:
                    continue
                rows.append({
                    "date": f"{year}-{int(month):02d}",
                    "location": loc[:60],
                    "rent_usd": f"{float(rent):.0f}",
                    "yoy_pct": "",
                    "mom_pct": "",
                    "captured_at": now,
                })
            except Exception:
                continue
    # Compute YoY and MoM for each location
    by_loc: dict[str, list[dict]] = {}
    for r in rows:
        by_loc.setdefault(r["location"], []).append(r)
    final: list[dict] = []
    for loc, series in by_loc.items():
        series.sort(key=lambda r: r["date"])
        for i, r in enumerate(series):
            try:
                cur = float(r["rent_usd"])
                if i >= 1:
                    prev = float(series[i - 1]["rent_usd"])
                    r["mom_pct"] = f"{(cur - prev) / prev * 100:+.2f}"
                if i >= 12:
                    y = float(series[i - 12]["rent_usd"])
                    r["yoy_pct"] = f"{(cur - y) / y * 100:+.2f}"
            except Exception:
                pass
        final.extend(series[-36:])
    final.sort(key=lambda r: r["date"], reverse=True)
    final = final[:600]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["date", "location", "rent_usd",
                        "yoy_pct", "mom_pct", "captured_at"],
        )
        w.writeheader()
        w.writerows(final)
    latest = final[0] if final else {}
    print(f"apartment_list_rent: {len(final)} rows | latest "
          f"{latest.get('location','?')[:20]} {latest.get('date','?')} "
          f"${latest.get('rent_usd','?')} yoy={latest.get('yoy_pct','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
