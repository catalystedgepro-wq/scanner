#!/usr/bin/env python3
"""build_who_health.py - World Health Organization news RSS.

Global health policy + disease outbreak + pandemic preparedness tape.
Drives vaccine/biotech (PFE MRNA BNTX JNJ MRK), disease-test and PPE
(DGX TMO ABT), pandemic-exposure REITs and travel (MAR H), and emerging
market health funds. No existing spoke covers WHO (no who_ or disease_
outbreak file in inventory).

10-kind priority-ordered classifier:
- outbreak       : disease outbreaks — Ebola/Marburg/H5N1/cholera/mpox
- pandemic       : IHR, pandemic agreement, preparedness, emergency
- tb             : tuberculosis programs and diagnostics
- vaccine        : immunization, vaccine access, rollout
- child_health   : child mortality, maternal, newborn
- conflict       : Sudan/Gaza/Ukraine health crises
- refugee        : refugee/migrant/displaced health
- policy         : WHA, negotiations, member states, guidelines
- partnership    : WHO Forum, collaborating centres, One Health
- press          : fallback

Source: who.int/rss-feeds/news-english.xml (RSS 2.0, 25-item rolling,
free, no key). Output: who_health.csv
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
OUT_CSV = ROOT / "who_health.csv"
FEED = "https://www.who.int/rss-feeds/news-english.xml"
UA = "CatalystEdge/1.0 (opensource@example.com)"

KIND_RULES: list[tuple[str, list[str]]] = [
    ("outbreak",     ["outbreak", "ebola", "marburg", "h5n1", "h5n", "avian",
                      "bird flu", "cholera", "mpox", "monkeypox", "polio",
                      "measles", "yellow fever", "dengue", "zika", "plague",
                      "disease x"]),
    ("pandemic",     ["pandemic", "pandemic agreement", "ihr", "health emergency",
                      "preparedness", "response fund", "pheic"]),
    ("tb",           ["tuberculosis", " tb ", "tb "]),
    ("vaccine",      ["vaccine", "immunization", "immunisation", "vaccination"]),
    ("child_health", ["child death", "child health", "child mortality",
                      "maternal", "newborn", "under five", "age five"]),
    ("conflict",     ["conflict", "sudan", "gaza", "ukraine", "war",
                      "humanitarian crisis", "besieged"]),
    ("refugee",      ["refugee", "migrant", "displaced", "idp"]),
    ("policy",       ["wha", "world health assembly", "member states",
                      "negotiations", "guidelines", "recommendations",
                      "resolution", "framework"]),
    ("partnership",  ["collaborating centre", "forum", "one health",
                      "partnership", "initiative", "call for action"]),
]


def classify(title: str) -> str:
    lower = " " + title.lower() + " "
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
        print(f"who_health fetch: {exc}")
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
        print(f"who_health: no rows; preserved {OUT_CSV.name}")
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
    print(f"who_health: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
