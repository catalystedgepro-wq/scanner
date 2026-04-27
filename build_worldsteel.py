#!/usr/bin/env python3
"""build_worldsteel.py - World Steel Association press RSS.

Global steel industry tape: monthly crude steel production (primary
signal, China-weighted because China produces ~50% of global), Short
Range Outlook forecasts (twice yearly Apr/Oct), sustainability /
decarbonization initiatives, LCA eco-profiles. Pairs with
build_aisi_steel.py (US-focused) as the non-US / global layer.

Signal class: drives iron-ore players VALE RIO BHP FMG.AX plus
integrated steel X NUE STLD CLF RS MT CMC. China crude-steel MoM
inflection flips iron-ore demand curve ~6-8 weeks later.

7-kind priority-ordered classifier:
- production     : "crude steel production", monthly MoM/YoY
- outlook        : "Short Range Outlook", SRO, forecast
- sustainability : climate, decarbonization, sustainability, LCA, green
- governance     : member, director, leadership, chairman
- research       : eco-profile, study, whitepaper, report
- event          : congress, forum, conference, summit
- press          : fallback

Source: worldsteel.org/feed/ (WordPress RSS 2.0, 10-item rolling, free).
Output: worldsteel.csv
Columns: filed, kind, title, url, captured_at
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import re
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "worldsteel.csv"
FEED = "https://worldsteel.org/feed/"
UA = "CatalystEdge/1.0 (opensource@example.com)"

KIND_RULES: list[tuple[str, list[str]]] = [
    ("production",     ["crude steel production", "steel production",
                        "production data", "monthly production"]),
    ("outlook",        ["short range outlook", "sro", "forecast",
                        "outlook"]),
    ("sustainability", ["sustainability", "decarbonization", "climate",
                        "green steel", "emissions", "carbon",
                        "sustainability champion", "eco-profile",
                        "environmental product"]),
    ("governance",     ["member", "director general", "leadership",
                        "chairman", "board", "appointed"]),
    ("research",       ["lca", "life cycle", "study", "whitepaper",
                        "report", "research"]),
    ("event",          ["congress", "forum", "conference", "summit",
                        "steelchallenge"]),
]


def classify(title: str) -> str:
    lower = title.lower()
    for kind, keys in KIND_RULES:
        for key in keys:
            if key in lower:
                return kind
    return "press"


def _strip_cdata(value: str) -> str:
    match = re.match(r"<!\[CDATA\[(.*)\]\]>", value, re.S)
    return match.group(1) if match else value


def fetch_items() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"worldsteel fetch: {exc}")
        return []

    items = []
    for chunk in re.findall(r"<item>(.*?)</item>", body, re.S):
        t = re.search(r"<title>(.*?)</title>", chunk, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", chunk, re.S)
        l = re.search(r"<link>(.*?)</link>", chunk, re.S)
        if not (t and d and l):
            continue
        title = html.unescape(_strip_cdata(t.group(1)).strip())
        try:
            filed = parsedate_to_datetime(d.group(1).strip()).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            continue
        url = _strip_cdata(l.group(1)).strip()
        items.append({
            "filed": filed,
            "kind": classify(title),
            "title": title,
            "url": url,
        })
    return items


def main() -> None:
    items = fetch_items()
    if not items and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"worldsteel: no rows; preserved {OUT_CSV.name}")
        return

    now = dt.datetime.utcnow().replace(microsecond=0).isoformat()
    fields = ["filed", "kind", "title", "url", "captured_at"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in items:
            row["captured_at"] = now
            writer.writerow(row)

    tally: dict[str, int] = {}
    for row in items:
        tally[row["kind"]] = tally.get(row["kind"], 0) + 1
    summary = " ".join(f"{k}={v}" for k, v in sorted(
        tally.items(), key=lambda kv: -kv[1]))
    print(f"worldsteel: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
