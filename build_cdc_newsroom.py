#!/usr/bin/env python3
"""build_cdc_newsroom.py - CDC Online Newsroom (press releases).

Existing build_cdc_flu.py / build_cdc_fluview.py / build_cdc_hospital.py
/ build_cdc_wastewater.py cover epi surveillance data — NOT the CDC
Press Room / media-release tape. This spoke fills that gap.

CDC drives FDA/HHS policy, public-health advisories, and disease
outbreak comms — driving biotech PFE MRNA BNTX JNJ MRK, vaccine
makers, diagnostics DGX TMO ABT, hospitals HCA UHS THC, and pandemic-
exposed travel names MAR H DAL UAL.

10-kind priority-ordered classifier on title + summary:
- outbreak     : measles/ebola/bird flu/h5n1 etc. outbreak / cluster
- advisory     : HAN advisory, travel notice, health alert
- vaccine      : ACIP, immunization, vaccination recommendations
- emergency    : emergency response, preparedness
- funding      : grants, funding, award, appropriation
- personnel    : director appointments, resignations, leadership
- policy       : policy statement, guidance, new rule, regulation
- research     : study, MMWR, report, findings
- partnership  : collaboration, partnership, agreement
- press        : fallback

Source: tools.cdc.gov/podcasts/feed.asp?feedid=183 (Atom 1.0).
Output: cdc_newsroom.csv
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
OUT_CSV = ROOT / "cdc_newsroom.csv"
FEED = "https://tools.cdc.gov/podcasts/feed.asp?feedid=183"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

KIND_RULES: list[tuple[str, list[str]]] = [
    ("outbreak",    ["outbreak", "cluster", "measles", "ebola", "bird flu",
                     "h5n1", "h1n1", "mpox", "monkeypox", "avian",
                     "cholera", "mers", "sars", "zika", "polio"]),
    ("advisory",    ["health alert", "han advisory", "travel notice",
                     "travel advisory", "health notice", "clinician alert",
                     "warning", "urgent"]),
    ("vaccine",     ["vaccine", "vaccination", "immunization",
                     "acip ", "advisory committee on immunization",
                     "booster", "pediatric vaccine"]),
    ("emergency",   ["emergency response", "preparedness", "deployment",
                     "mobilization", "response team", "eoc"]),
    ("funding",     ["grant", "funding", "award", "appropriation",
                     "cooperative agreement", "financial assistance"]),
    ("personnel",   ["appointed", "resignation", "nomination",
                     "director ", "principal deputy", "secretary",
                     "named", "appoints", "succeeds"]),
    ("policy",      ["policy", "guidance", "new rule", "regulation",
                     "statement on", "recommendation", "updated ",
                     "guidelines"]),
    ("research",    ["study", "mmwr", "report", "findings",
                     "surveillance", "analysis", "data release"]),
    ("partnership", ["partnership", "collaboration", "agreement",
                     "joint ", "coalition", "alliance"]),
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


def _parse_updated(raw: str) -> str | None:
    raw = raw.strip()
    # Atom: 2026-03-11T04:00:00Z  (already ISO-8601 UTC)
    if re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", raw):
        try:
            cleaned = raw.replace("Z", "+00:00")
            parsed = dt.datetime.fromisoformat(cleaned)
            return parsed.astimezone(dt.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None
    return None


def fetch_items() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"cdc_newsroom fetch: {exc}")
        return []

    items: list[dict] = []
    for chunk in re.findall(r"<entry>(.*?)</entry>", body, re.S):
        t = re.search(r"<title>(.*?)</title>", chunk, re.S)
        u = re.search(r"<updated>(.*?)</updated>", chunk, re.S)
        i = re.search(r"<id>(.*?)</id>", chunk, re.S)
        s = re.search(r"<summary[^>]*>(.*?)</summary>", chunk, re.S)
        if not (t and u and i):
            continue
        title = html.unescape(_strip_cdata(t.group(1)).strip())
        filed = _parse_updated(_strip_cdata(u.group(1)))
        if not filed:
            continue
        url = _strip_cdata(i.group(1)).strip()
        summary = ""
        if s:
            summary = html.unescape(_strip_cdata(s.group(1)).strip())
        items.append({
            "filed": filed,
            "kind": classify(title + " " + summary),
            "title": title,
            "url": url,
        })
    return items


def main() -> None:
    items = fetch_items()
    if not items and OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
        print(f"cdc_newsroom: no rows; preserved {OUT_CSV.name}")
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
    print(f"cdc_newsroom: {len(items)} items | {summary}")


if __name__ == "__main__":
    main()
