#!/usr/bin/env python3
"""build_port_la_throughput.py — Port of LA/LB container throughput (TEU).

Ports of LA + Long Beach handle ~40% of US imports. Monthly TEU volume
leads retail sales by 30 days, moves trucking (KNX, LSTR, SAIA), rail
intermodal (UNP, CSX), big-box (COST, WMT, TGT), ocean carriers (MATX,
ZIM), cranes (AGX proxy).

Source: Port of LA publishes historical TEU at portoflosangeles.org; the
JSON/CSV endpoint is at /maritime/stats/container-statistics.

Output: port_la_throughput.csv
Columns: month, loaded_imports, loaded_exports, empty, total_teu, yoy_pct, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "port_la_throughput.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

URL = "https://www.portoflosangeles.org/business/statistics/container-statistics"


def fetch() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"port_la: {e}")
        return ""


def to_int(s: str) -> int:
    s = re.sub(r"[,\s]", "", s or "")
    try:
        return int(s)
    except Exception:
        return 0


def main() -> None:
    html = fetch()
    # Look for table rows: Month | Loaded Imports | Loaded Exports | Empty | Total
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    table = re.search(r"<table[^>]*>(.+?)</table>", html, re.S)
    if table:
        for tr in re.findall(r"<tr[^>]*>(.+?)</tr>", table.group(1), re.S):
            cells = re.findall(r"<t[dh][^>]*>(.+?)</t[dh]>", tr, re.S)
            if len(cells) < 5:
                continue
            clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if not re.match(r"^[A-Z]", clean[0]):
                continue
            rows.append({
                "month": clean[0][:20],
                "loaded_imports": to_int(clean[1]),
                "loaded_exports": to_int(clean[2]),
                "empty": to_int(clean[3]),
                "total_teu": to_int(clean[4]),
                "yoy_pct": clean[5] if len(clean) > 5 else "",
                "captured_at": now,
            })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "month", "loaded_imports", "loaded_exports",
                "empty", "total_teu", "yoy_pct", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    latest = rows[0] if rows else {}
    print(f"port_la_throughput: {len(rows)} months | latest {latest.get('month','?')} "
          f"total={latest.get('total_teu','?')} TEU -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
