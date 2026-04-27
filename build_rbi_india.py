#!/usr/bin/env python3
"""build_rbi_india.py - Reserve Bank of India press releases.

India is the world's 5th-largest economy (#3 by PPP) and the single
largest EM-policy gap in the 412-spoke inventory. RBI drives INR
(USDINR), Indian sovereign yields (10y GSec), and all US-listed Indian
ADRs (INFY WIT HDB IBN RDY SIFY MMYT) + iShares MSCI India (INDA
INDY SMIN EPI). No existing `rbi_`, `india_`, or `inr_` build_*.py
in inventory.

10-kind priority-ordered classifier on title:
- mpc          : Monetary Policy Committee, repo rate, SDF, MSF, bank rate
- auction      : State/Government security auction, SDL, T-bill, gilt
- fx_ops       : FX swap, USD/INR, spot intervention, forward book
- liquidity    : LAF, variable rate, VRRR, term repo, reverse repo
- gold         : Sovereign Gold Bond, SGB, IIB redemption/issue
- reg          : Master Direction, circular, notification, guidelines
- enforcement  : penalty imposed, licence cancellation, action against
- supervision  : priority sector, SLR, CRR, banking supervision
- inflation    : WPI, CPI, inflation report
- press        : fallback

Source: rbi.org.in/pressreleases_rss.xml (RSS 2.0, 10-item rolling,
free, no key). pubDate has NO tz — parsed as IST (UTC+5:30) and
converted to UTC. Output: rbi_india.csv
Columns: filed, kind, title, url, captured_at
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "rbi_india.csv"
FEED = "https://www.rbi.org.in/pressreleases_rss.xml"
UA = "CatalystEdge/1.0 (opensource@example.com)"

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

KIND_RULES: list[tuple[str, list[str]]] = [
    ("mpc",         ["monetary policy", "mpc ", "repo rate", "standing deposit",
                     "marginal standing facility", "msf ", " sdf ",
                     "bank rate", "policy rate", "reverse repo rate"]),
    ("auction",     ["auction of government of india", "auction of state government",
                     "auction of treasury bills", "auction result",
                     "conversion/switch", "sdl ", "state development loan",
                     "gilt ", "g-sec", "dated securities"]),
    ("fx_ops",      ["fx swap", "usd/inr", "usd-inr", "forex", "foreign exchange",
                     "forward book", "dollar-rupee", "rupee intervention"]),
    ("liquidity",   ["laf", "variable rate", "vrrr", "vrr ", "term repo",
                     "reverse repo", "liquidity adjustment", "omo purchase",
                     "omo sale", "open market operation"]),
    ("gold",        ["sovereign gold bond", "sgb ", "sgb-", "gold bond",
                     "inflation indexed bond", "iib "]),
    ("reg",         ["master direction", "circular", "notification",
                     "guidelines", "regulation", "framework on",
                     "prudential norms"]),
    ("enforcement", ["penalty imposed", "monetary penalty", "licence cancel",
                     "license cancel", "cancellation of", "action against",
                     "direction issued"]),
    ("supervision", ["priority sector", "slr ", "crr ", "banking supervision",
                     "on-site inspection", "financial stability"]),
    ("inflation",   ["wpi ", "cpi ", "inflation report", "inflation expectation",
                     "price stability"]),
]


def classify(title: str) -> str:
    hay = " " + title.lower() + " "
    for kind, keys in KIND_RULES:
        for key in keys:
            if key in hay:
                return kind
    return "press"


def _strip_cdata(value: str) -> str:
    match = re.match(r"<!\[CDATA\[(.*)\]\]>", value, re.S)
    return match.group(1) if match else value


def _parse_ist(raw: str) -> str | None:
    raw = raw.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S", "%a, %d %b %Y %H:%M"):
        try:
            naive = dt.datetime.strptime(raw, fmt)
            return naive.replace(tzinfo=IST).astimezone(
                dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return None


def fetch_items() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"rbi_india fetch: {exc}")
        return []

    items: list[dict] = []
    for chunk in re.findall(r"<item>(.*?)</item>", body, re.S):
        t = re.search(r"<title>(.*?)</title>", chunk, re.S)
        d = re.search(r"<pubDate>(.*?)</pubDate>", chunk, re.S)
        l = re.search(r"<link>(.*?)</link>", chunk, re.S)
        if not (t and d and l):
            continue
        title = html.unescape(_strip_cdata(t.group(1)).strip())
        filed = _parse_ist(_strip_cdata(d.group(1)))
        if not filed:
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
        print(f"rbi_india: no rows; preserved {OUT_CSV.name}")
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
    print(f"rbi_india: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
