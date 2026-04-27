#!/usr/bin/env python3
"""build_arxiv_cashtag.py — ArXiv AI/ML paper cashtag surface.

Breakthrough papers move AI stocks (NVDA, GOOGL, META, MSFT, AMD) on the
day of release or within 48h. Monitor arxiv cs.AI, cs.LG, cs.CL daily.

Output: arxiv_cashtag.csv
Columns: arxiv_id, published, title, authors, ticker_guess, summary, url
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "arxiv_cashtag.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
API = (
    "http://export.arxiv.org/api/query?"
    "search_query={q}&sortBy=submittedDate&sortOrder=descending&max_results={n}"
)

CATEGORIES = ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.CR"]

# Author-affiliation → ticker
AUTHOR_HINTS = {
    "GOOGLE": "GOOGL", "DEEPMIND": "GOOGL", "GOOGLE BRAIN": "GOOGL",
    "META AI": "META", "FAIR": "META", "FACEBOOK": "META",
    "MICROSOFT": "MSFT", "MSRA": "MSFT", "BING": "MSFT",
    "OPENAI": "", "ANTHROPIC": "",
    "APPLE": "AAPL", "NVIDIA": "NVDA", "AMD": "AMD",
    "IBM": "IBM", "AMAZON": "AMZN", "ALIBABA": "BABA",
    "BAIDU": "BIDU", "TENCENT": "", "BYTEDANCE": "",
    "HUAWEI": "", "SAMSUNG": "",
    "QUALCOMM": "QCOM", "INTEL": "INTC",
    "XAI": "",  # private
    "TESLA": "TSLA",
    "NETFLIX": "NFLX", "UBER": "UBER", "AIRBNB": "ABNB",
    "SNAP": "SNAP", "PINTEREST": "PINS",
    "SALESFORCE": "CRM", "PALANTIR": "PLTR", "DATABRICKS": "",
    "ORACLE": "ORCL", "SAP": "SAP",
    "ARM": "ARM",
}

ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.DOTALL)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
ID_RE = re.compile(r"<id>(.*?)</id>", re.DOTALL)
PUB_RE = re.compile(r"<published>(.*?)</published>", re.DOTALL)
SUMM_RE = re.compile(r"<summary>(.*?)</summary>", re.DOTALL)
AUTHOR_RE = re.compile(r"<author><name>(.*?)</name>.*?(?:<arxiv:affiliation>(.*?)</arxiv:affiliation>)?", re.DOTALL | re.I)
AFF_RE = re.compile(r"<arxiv:affiliation>(.*?)</arxiv:affiliation>", re.DOTALL | re.I)


def fetch(url: str, timeout: int = 25) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"arxiv: {e}")
        return None


def guess(text: str) -> str:
    up = (text or "").upper()
    for k, v in AUTHOR_HINTS.items():
        if k in up:
            return v
    return ""


def main():
    rows: list[dict] = []
    q = "+OR+".join(f"cat:{c}" for c in CATEGORIES)
    xml = fetch(API.format(q=q, n=100)) or ""
    for entry in ENTRY_RE.findall(xml):
        title = re.sub(r"\s+", " ", (TITLE_RE.search(entry).group(1) if TITLE_RE.search(entry) else "")).strip()
        arxiv_id_m = ID_RE.search(entry)
        arxiv_id = arxiv_id_m.group(1).strip() if arxiv_id_m else ""
        pub_m = PUB_RE.search(entry)
        pub = pub_m.group(1)[:10] if pub_m else ""
        summ_m = SUMM_RE.search(entry)
        summary = re.sub(r"\s+", " ", summ_m.group(1) if summ_m else "").strip()[:240]
        authors = [re.sub(r"<[^>]+>", "", a) for a in re.findall(r"<author>(.*?)</author>", entry, re.DOTALL)]
        authors_s = " | ".join(authors[:5])
        affiliations = " ".join(AFF_RE.findall(entry))
        combined = f"{authors_s} {affiliations} {summary}"
        ticker = guess(combined)
        rows.append({
            "arxiv_id": arxiv_id.rsplit("/", 1)[-1],
            "published": pub,
            "title": title[:240],
            "authors": authors_s[:200],
            "ticker_guess": ticker,
            "summary": summary[:240],
            "url": arxiv_id,
        })
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "arxiv_id", "published", "title", "authors",
                "ticker_guess", "summary", "url",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    with_tic = sum(1 for r in rows if r["ticker_guess"])
    print(f"arxiv_cashtag: {len(rows)} papers ({with_tic} ticker-tagged) -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
