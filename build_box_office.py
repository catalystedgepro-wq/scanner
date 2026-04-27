#!/usr/bin/env python3
"""build_box_office.py — Weekly US box office totals (top 15 films).

Box office drives theatrical (CNK, AMC, IMAX), studios (DIS, CMCSA, WBD,
PARA, SONY, NFLX secondary), and ticket-platform (LYV partially). Huge
openers = studio beat next quarter; bombs = guidance cuts.

Source: boxofficemojo.com weekly HTML (free, scrape-friendly).
Output: box_office.csv
Columns: week_ending, rank, title, studio, weekly_gross, cumulative, theaters, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "box_office.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"

URL = "https://www.boxofficemojo.com/weekend/"


def fetch() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"box_office: {e}")
        return ""


def money_to_int(s: str) -> int:
    s = re.sub(r"[\$,\s]", "", s or "")
    try:
        return int(s)
    except Exception:
        return 0


def main() -> None:
    html = fetch()
    # find the first table with column headers
    table = re.search(r"<table[^>]*mojo-body-table[^>]*>(.+?)</table>", html, re.S)
    if not table:
        # try generic
        table = re.search(r"<table[^>]*>(.+?)</table>", html, re.S)
    body = table.group(1) if table else ""
    rows_html = re.findall(r"<tr[^>]*>(.+?)</tr>", body, re.S)
    rows: list[dict] = []
    now = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    today = dt.date.today().isoformat()
    for tr in rows_html[1:]:  # skip header
        cells = re.findall(r"<t[dh][^>]*>(.+?)</t[dh]>", tr, re.S)
        if len(cells) < 4:
            continue
        clean = [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ").strip() for c in cells]
        try:
            rank = int(re.sub(r"\D", "", clean[0]))
        except Exception:
            continue
        if rank > 25:
            continue
        rows.append({
            "week_ending": today,
            "rank": rank,
            "title": clean[1][:80] if len(clean) > 1 else "",
            "studio": clean[-1][:40] if clean else "",
            "weekly_gross": money_to_int(clean[3] if len(clean) > 3 else "0"),
            "cumulative": money_to_int(clean[7] if len(clean) > 7 else "0"),
            "theaters": re.sub(r"\D", "", clean[5] if len(clean) > 5 else ""),
            "captured_at": now,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "week_ending", "rank", "title", "studio",
                "weekly_gross", "cumulative", "theaters", "captured_at",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    top = rows[0] if rows else {}
    print(f"box_office: {len(rows)} films | #1 {top.get('title','?')} "
          f"${top.get('weekly_gross',0):,} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
