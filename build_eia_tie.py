#!/usr/bin/env python3
"""build_eia_tie.py - EIA Today In Energy narrative feed.

EIA's "Today In Energy" is the US government's authoritative daily
energy-market analysis — each article surfaces a single fundamental
(production, consumption, price, capacity, trade) with charts and
official sector data. Distinct from existing eia_grid_930 /
eia_natgas spokes which pull numeric series; TIE supplies narrative
direction that telegraphs weekly STEO + monthly export report.

No existing `eia_tie_`, `today_in_energy_`, or narrative EIA spoke.

TIE articles move:
- oil majors (XOM CVX COP OXY EOG PXD FANG MRO APA HES) on crude/refining tape
- refiners (VLO MPC PSX PBF DK HFC) on crack spread / gasoline formulation
- LNG export (LNG NFE FLNG TELL) on natgas export-capacity tape
- natgas E&P (SWN EQT AR CTRA RRC) on Henry Hub + demand pull
- pipelines (KMI ENB ET WMB TRP) on capacity expansion
- coal (BTU ARCH AMR HCC CEIX) on retirements + thermal share
- renewables (FSLR ENPH RUN SEDG NEE BEP NEP) on capacity additions
- nuclear (CEG CCJ UUUU URG SMR) on SMR + uranium + capacity factor
- utilities (DUK SO D NEE EXC AEP) on generation mix + retirement pipeline
- EV/efficiency (TSLA RIVN F GM STLA) on gasoline consumption trend

9-kind priority-ordered classifier on title:
- oil          : crude oil, petroleum, gasoline, refining, WTI, Brent, motor gasoline
- natgas       : natural gas, LNG, Henry Hub, pipeline, methane
- renewables   : solar, wind, hydropower, battery, biofuel, ethanol, renewable
- coal         : coal-fired, coal retirement, thermal coal
- nuclear      : nuclear, SMR, uranium, reactor
- electricity  : electricity generation, grid, transmission, generating capacity
- efficiency   : fuel efficiency, EV adoption, consumption decline, CAFE
- international: export, import, OPEC, international, trade
- press        : fallback

Source: eia.gov/rss/todayinenergy.xml (RSS 2.0, ~15-item rolling).
Output: eia_tie.csv
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
OUT_CSV = ROOT / "eia_tie.csv"
FEED = "https://www.eia.gov/rss/todayinenergy.xml"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

KIND_RULES: list[tuple[str, list[str]]] = [
    ("oil",           ["crude oil", "petroleum", " gasoline ",
                       "motor gasoline", " refining", "refinery",
                       " wti ", " brent ", "diesel", "jet fuel",
                       "distillate", "crack spread"]),
    ("natgas",        ["natural gas", " lng ", "henry hub",
                       "pipeline capacity", " methane ",
                       "gas export", "gas storage"]),
    ("renewables",    [" solar ", " wind ", "hydropower", " hydro ",
                       " battery ", "biofuel", " ethanol ",
                       "renewable", "geothermal", "offshore wind"]),
    ("coal",          ["coal-fired", "coal retirement", "coal fired",
                       "thermal coal", " coal ", "coal plant"]),
    ("nuclear",       [" nuclear ", " smr ", " uranium ",
                       " reactor ", "nuclear plant"]),
    ("electricity",   ["electricity generation", "electric grid",
                       "generating capacity", "power generation",
                       "transmission", " grid ", "capacity factor"]),
    ("efficiency",    ["fuel efficiency", "ev adoption",
                       "electric vehicle", "consumption decline",
                       " cafe ", "energy efficiency"]),
    ("international", [" export", " import", " opec ",
                       "international", "trade flow",
                       "foreign demand", "global demand"]),
]


def classify(blob: str) -> str:
    hay = " " + blob.lower() + " "
    for kind, keys in KIND_RULES:
        for key in keys:
            if key in hay:
                return kind
    return "press"


def _strip_cdata(value: str) -> str:
    match = re.match(r"<!\[CDATA\[(.*)\]\]>", value, re.S)
    return match.group(1) if match else value


def _parse_pub(raw: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", raw.strip())
    try:
        parsed = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_items() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"eia_tie fetch: {exc}")
        return []

    items: list[dict] = []
    for chunk in re.findall(r"<item>(.*?)</item>", body, re.S):
        t = re.search(r"<title>(.*?)</title>", chunk, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", chunk, re.S)
        l = re.search(r"<link>(.*?)</link>", chunk, re.S)
        if not (t and l):
            continue
        title = html.unescape(_strip_cdata(t.group(1)).strip())
        if not title or title.lower() == "eia logo":
            continue
        filed = _parse_pub(_strip_cdata(d.group(1))) if d else None
        if not filed:
            filed = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
        print(f"eia_tie: no rows; preserved {OUT_CSV.name}")
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
    print(f"eia_tie: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
