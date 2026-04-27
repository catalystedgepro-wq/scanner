#!/usr/bin/env python3
"""build_nber.py — NBER New Working Papers firehose.

Source: nber.org/rss/new.xml (RSS 2.0 ~33-paper rolling, weekly Monday
release, no key, minimal schema: <title> embeds "Title -- by Author,
Author" pattern, <description> is extended abstract, <link>/<guid> carry
paper id via /papers/wNNNNN#fromrss path, NO <pubDate>).

NBER is the premier US academic macro/finance research outlet. 1,200+
affiliates; Fed Chair, FOMC members, Treasury Secretary, CBO Director
are traditionally NBER Research Associates. Working papers are heavily
cited in FOMC minutes, Treasury QRA, CBO projections. New-paper tape
telegraphs policy-consensus shifts 6-18 months ahead of public debate.

Taxonomy (priority-ordered, first-match-wins):
  monetary / fiscal / finance / labor / trade / health_policy /
  ai_tech / housing / macro / industrial_org / education /
  environment / demography / press
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import pathlib
import re
import urllib.request

FEED = "https://www.nber.org/rss/new.xml"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT = pathlib.Path(__file__).parent / "nber.csv"
FIELDS = ["filed_utc", "paper_id", "kind", "title", "authors", "link", "summary"]

KIND_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("monetary", re.compile(r"\b(monetary[- ]policy|Fed|FOMC|central bank|interest rate|inflation target|Taylor rule|zero lower bound|quantitative easing|QE|forward guidance|r[- ]star|neutral rate|Phillips curve|inflation expectations)\b", re.I)),
    ("fiscal", re.compile(r"\b(fiscal[- ]policy|tax|government spending|deficit|public debt|sovereign debt|Ricardian|Pigouvian|subsidy|transfer|stimulus|Medicare|Medicaid|Social Security|entitlement)\b", re.I)),
    ("finance", re.compile(r"\b(financial[- ]markets|asset pricing|equity premium|credit spread|banking|stress test|systemic|financial[- ]stability|insurance|pension|mutual fund|hedge fund|private equity|private credit|venture capital|VC|bankruptcy|default risk|stablecoin|crypto|DeFi)\b", re.I)),
    ("labor", re.compile(r"\b(labor[- ]market|employment|wages?|unemployment|job|hiring|workforce|labor force|participation|minimum wage|union|collective bargaining|immigration|human capital|occupation|skill)\b", re.I)),
    ("trade", re.compile(r"\b(international[- ]trade|tariff|export|import|trade[- ]war|FDI|foreign direct investment|supply[- ]chain|globalization|WTO|trade policy|trade balance|current account|exchange rate|currency)\b", re.I)),
    ("health_policy", re.compile(r"\b(health[- ]care|health insurance|hospital|pharmaceutical|drug price|Medicare Part D|Medicaid|vaccine|epidemic|pandemic|mortality|mental health|opioid|obesity|health policy|medical)\b", re.I)),
    ("ai_tech", re.compile(r"\b(artificial intelligence|\bAI\b|machine learning|automation|robot|productivity|innovation|patent|R&D|research and development|technology adoption|digitization|platform|big tech)\b", re.I)),
    ("housing", re.compile(r"\b(housing|home prices|rent|mortgage|real estate|property|zoning|land use|homeowner|eviction|foreclosure|house prices)\b", re.I)),
    ("macro", re.compile(r"\b(GDP|growth|productivity|business cycle|recession|expansion|output gap|potential output|total factor productivity|TFP|nowcast|DSGE|New Keynesian|RBC)\b", re.I)),
    ("industrial_org", re.compile(r"\b(antitrust|competition|monopoly|market power|merger|acquisition|market concentration|HHI|regulation|deregulation|industry structure|price discrimination|vertical integration)\b", re.I)),
    ("education", re.compile(r"\b(education|school|college|university|student|teacher|curriculum|test score|graduation|dropout|student loan|charter school|higher education|K-12)\b", re.I)),
    ("environment", re.compile(r"\b(climate|carbon|emission|greenhouse gas|environmental|pollution|natural disaster|energy policy|renewable|fossil fuel|oil|gas|electricity|green|ESG|sustainability)\b", re.I)),
    ("demography", re.compile(r"\b(fertility|aging|life expectancy|birth rate|death rate|migration|demographic|family|household|marriage|divorce|child|elderly|retirement|baby)\b", re.I)),
)


def _clean(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"<!\[CDATA\[|\]\]>", "", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _split_title_authors(raw: str) -> tuple[str, str]:
    if " -- by " in raw:
        title, authors = raw.split(" -- by ", 1)
        return title.strip(), authors.strip()
    return raw.strip(), ""


def _extract_paper_id(link: str) -> str:
    m = re.search(r"/papers/(w\d+)", link)
    return m.group(1) if m else ""


def _classify(title: str, summary: str) -> str:
    hay = f"{title} {summary}"
    for kind, pattern in KIND_PATTERNS:
        if pattern.search(hay):
            return kind
    return "press"


def _fetch() -> list[dict]:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA, "Accept": "application/rss+xml,*/*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict] = []
    for block in re.findall(r"<item[^>]*>(.*?)</item>", body, re.S):
        title_m = re.search(r"<title>(.*?)</title>", block, re.S)
        link_m = re.search(r"<link>(.*?)</link>", block, re.S)
        desc_m = re.search(r"<description>(.*?)</description>", block, re.S)

        raw_title = _clean(title_m.group(1)) if title_m else ""
        link = _clean(link_m.group(1)) if link_m else ""
        summary = _clean(desc_m.group(1)) if desc_m else ""
        title, authors = _split_title_authors(raw_title)
        paper_id = _extract_paper_id(link)

        if not title:
            continue

        rows.append(
            {
                "filed_utc": now,
                "paper_id": paper_id,
                "kind": _classify(title, summary),
                "title": title[:240],
                "authors": authors[:240],
                "link": link,
                "summary": summary[:400],
            }
        )

    rows.sort(key=lambda r: r["paper_id"], reverse=True)
    return rows


def main() -> int:
    try:
        rows = _fetch()
    except Exception as exc:
        print(f"[nber] fetch failed: {exc}")
        if OUT.exists() and OUT.stat().st_size > 200:
            print(f"[nber] preserving last-good {OUT}")
            return 0
        return 1

    if not rows:
        print("[nber] no items parsed")
        if OUT.exists() and OUT.stat().st_size > 200:
            return 0
        return 1

    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    tally = " ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0])))
    print(f"[nber] wrote {OUT.name} items={len(rows)} {tally}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
