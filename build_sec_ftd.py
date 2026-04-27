#!/usr/bin/env python3
"""build_sec_ftd.py — SEC fails-to-deliver data (bimonthly).

FTDs = shares sold but not delivered within T+1. Persistent FTDs
signal naked shorting / settlement failure = squeeze catalyst.
GME 2021 FTDs spiked 30× before the squeeze. AMC, BBBY, HKD all
flagged similarly. Pairs with build_squeeze_hunter on confirmed
short-pressure names.

Source: sec.gov/data/foiadocsfailsdatahtm (ZIP) — use latest monthly
file listing via HTML index scrape.
Output: sec_ftd.csv
Columns: settlement_date, cusip, symbol, quantity_failed, price,
         description, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import io
import re
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_ftd.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

INDEX_URL = "https://www.sec.gov/data/foiadocsfailsdatahtm"


def fetch_zip_list() -> list[str]:
    req = urllib.request.Request(INDEX_URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"sec_ftd index: {e}")
        return []
    return re.findall(r'href="(/files/data/fails-deliver-data/cnsfails\d{6}[ab]\.zip)"', html)


def fetch_zip(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            blob = r.read()
    except Exception as e:
        print(f"sec_ftd zip: {e}")
        return []
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
        name = z.namelist()[0]
        txt = z.read(name).decode("latin-1", errors="ignore")
    except Exception:
        return []
    rows: list[dict] = []
    for line in txt.splitlines()[1:]:
        parts = line.split("|")
        if len(parts) < 6:
            continue
        try:
            qty = int(parts[3] or 0)
        except Exception:
            qty = 0
        if qty < 10_000:
            continue
        rows.append({
            "settlement_date": parts[0],
            "cusip": parts[1],
            "symbol": parts[2],
            "quantity_failed": str(qty),
            "price": parts[4],
            "description": parts[5][:80],
        })
    return rows


def main() -> None:
    paths = fetch_zip_list()
    if not paths:
        OUT_CSV.write_text("settlement_date,cusip,symbol,quantity_failed,price,description,captured_at\n")
        print(f"sec_ftd: 0 files | -> {OUT_CSV.name}")
        return
    latest = sorted(paths)[-1]
    url = f"https://www.sec.gov{latest}"
    rows = fetch_zip(url)
    rows.sort(key=lambda r: int(r["quantity_failed"]), reverse=True)
    rows = rows[:300]
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for r in rows:
        r["captured_at"] = now
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["settlement_date", "cusip", "symbol",
                        "quantity_failed", "price", "description",
                        "captured_at"],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    print(f"sec_ftd: {len(rows)} biggest fails | #1 "
          f"{top.get('symbol','?')} {top.get('quantity_failed','?')} "
          f"-> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
