#!/usr/bin/env python3
"""build_boeing_press.py - Boeing News Releases RSS.

Commercial + defense + space order/delivery tape for BA directly plus
the aerospace supply chain: HWM SPR TDG HEI MOG.A WWD BWXT + defense
primes NOC LMT RTX GD LHX + commercial airline demand proxy (737/777/787
orders drive UAL AAL DAL LUV 5-10yr fleet spend). No existing boeing_,
airbus_, or aerospace_ build_*.py file in inventory.

7-kind priority-ordered classifier on title + description:
- orders      : {nation|army|navy|air force|airline} orders / order from / wins contract
- deliveries  : delivers / delivery / announces {quarter|YTD} deliveries
- space       : satellite / spacecraft / space / SLS / Artemis / Starliner
- defense     : F-15/F-18/F/A-18/Apache/Chinook/CH-47/V-22/KC-46/T-7
- commercial  : 737/747/767/777/787 MAX / commercial / widebody / narrowbody
- contract    : contract award / modification / DCMA / PCO
- press       : fallback

Source: boeing.mediaroom.com/news-releases-statements?pagetemplate=rss
(RSS 2.0, 5-item rolling, free, no key). Output: boeing_press.csv
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
OUT_CSV = ROOT / "boeing_press.csv"
FEED = "https://boeing.mediaroom.com/news-releases-statements?pagetemplate=rss"
UA = "CatalystEdge/1.0 (opensource@example.com)"

KIND_RULES: list[tuple[str, list[str]]] = [
    ("orders",     ["orders six", "orders five", "orders four", "orders three",
                    "orders two", "orders ten", "orders 6", "orders 5",
                    "orders 4", "orders 3", "orders 2", "orders 10",
                    "order from", "order for", "places order",
                    "firm order", "firm-order", "purchase agreement",
                    "wins contract", "awarded contract", "awarded a contract",
                    "order announcement", "selects boeing"]),
    ("deliveries", ["delivers", "delivery", "delivered", "first quarter deliveries",
                    "second quarter deliveries", "third quarter deliveries",
                    "fourth quarter deliveries", "announces deliveries",
                    "ytd deliveries"]),
    ("space",      ["satellite", "spacecraft", "space launch system", "sls",
                    "artemis", "starliner", "space", "lunar", "mars",
                    "gateway", "iss ", "international space station"]),
    ("defense",    ["f-15", "f/a-18", "f-18", "apache", "chinook", "ch-47",
                    "v-22", "osprey", "kc-46", "kc-767", "t-7", "mq-25",
                    "p-8", "e-7", "b-52", "b-1", "b-2", "b-21",
                    "wedgetail", "poseidon", "harpoon", "slam-er", "jdam",
                    "defense", "army", "navy", "air force", "marine corps"]),
    ("commercial", ["737 max", "737-", "747-", "767-", "777x", "777-",
                    "787-", "787 dreamliner", "dreamliner", "commercial",
                    "narrowbody", "narrow-body", "widebody", "wide-body",
                    "freighter"]),
    ("contract",   ["contract award", "contract modification", "dcma",
                    "idiq", "indefinite delivery", "indefinite-quantity",
                    "lrip", "low-rate initial production", "milestone"]),
]


def classify(title: str, description: str) -> str:
    hay = " " + (title + " " + description).lower() + " "
    for kind, keys in KIND_RULES:
        for key in keys:
            if key in hay:
                return kind
    return "press"


def _strip_cdata(value: str) -> str:
    match = re.match(r"<!\[CDATA\[(.*)\]\]>", value, re.S)
    return match.group(1) if match else value


def _strip_html(raw: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", raw))


def fetch_items() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"boeing_press fetch: {exc}")
        return []

    items: list[dict] = []
    for chunk in re.findall(r"<item>(.*?)</item>", body, re.S):
        t = re.search(r"<title>(.*?)</title>", chunk, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", chunk, re.S)
        l = re.search(r"<link>(.*?)</link>", chunk, re.S)
        desc = re.search(r"<description>(.*?)</description>", chunk, re.S)
        if not (t and d and l):
            continue
        title = html.unescape(_strip_cdata(t.group(1)).strip())
        try:
            filed = parsedate_to_datetime(d.group(1).strip()).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            continue
        url = _strip_cdata(l.group(1)).strip()
        description = _strip_html(_strip_cdata(desc.group(1))) if desc else ""
        items.append({
            "filed": filed,
            "kind": classify(title, description),
            "title": title,
            "url": url,
        })
    return items


def main() -> None:
    items = fetch_items()
    if not items and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"boeing_press: no rows; preserved {OUT_CSV.name}")
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
    print(f"boeing_press: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
