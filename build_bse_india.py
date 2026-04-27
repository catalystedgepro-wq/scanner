#!/usr/bin/env python3
"""build_bse_india.py — BSE India corporate notices feed.

Bombay Stock Exchange publishes a public RSS at:
  https://www.bseindia.com/data/xml/notices.xml

Source captures circulars, market notices, listings, regulatory actions.
Catalyst-relevant for India ADRs trading in US:
  INFY (Infosys), WIT (Wipro), TTM (Tata Motors), HDB (HDFC Bank),
  IBN (ICICI Bank), RDY (Dr Reddy's), TCL (Tata Communications),
  SLB-india, MMYT (MakeMyTrip), AZRE (Azure Power), etc.

Output: bse_india.csv (filed_utc, kind, title, link, summary, captured_at)
Stdlib only.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT = ROOT / "bse_india.csv"

URL = "https://www.bseindia.com/data/xml/notices.xml"
UA = "Mozilla/5.0 (X11; Linux x86_64) CatalystEdge/1.0"
TIMEOUT = 15

# Map BSE notice keywords → catalyst kind tags
KIND_MAP = [
    (r"insider|sast|sebi|disclosure", "insider_disclosure"),
    (r"buyback|buy.back",             "buyback"),
    (r"merger|amalgamation|scheme of arrangement", "merger"),
    (r"acquisition|takeover",         "acquisition"),
    (r"open offer",                    "open_offer"),
    (r"delisting|delist",             "delisting"),
    (r"suspension|halt",              "trading_halt"),
    (r"resolution plan|insolvency|nclt|cirp", "insolvency"),
    (r"rating",                        "credit_rating"),
    (r"dividend",                      "dividend"),
    (r"bonus issue|stock split|sub-division", "corp_action"),
    (r"rights issue|rights offer",    "rights_issue"),
    (r"qip|preferential allotment",   "private_placement"),
    (r"results|financial result|earnings", "earnings"),
    (r"investigation|fraud|sec",      "regulatory_action"),
    (r"listing|new listing",          "new_listing"),
]


def classify(title: str, summary: str) -> str:
    blob = f"{title} {summary}".lower()
    for pattern, label in KIND_MAP:
        if re.search(pattern, blob):
            return label
    return "general"


def fetch() -> str:
    req = urllib.request.Request(URL, headers={"User-Agent": UA, "Accept": "application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


ITEM_RE     = re.compile(r"<item>(.+?)</item>", re.S)
TITLE_RE    = re.compile(r"<title>(.+?)</title>", re.S)
LINK_RE     = re.compile(r"<link>(.+?)</link>", re.S)
DESC_RE     = re.compile(r"<description>(.+?)</description>", re.S)
PUBDATE_RE  = re.compile(r"<pubDate>(.+?)</pubDate>", re.S)
CDATA_RE    = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
TAG_RE      = re.compile(r"<[^>]+>")


def _strip(s: str) -> str:
    if not s:
        return ""
    m = CDATA_RE.search(s)
    if m:
        return TAG_RE.sub("", m.group(1)).strip()
    return TAG_RE.sub("", s).strip()


def _to_utc_iso(pubdate: str) -> str:
    """RFC 822 → ISO UTC. BSE typically returns 'Thu, 24 Apr 2026 16:30:00 +0530'."""
    if not pubdate:
        return ""
    try:
        # Python's email.utils handles RFC 822
        from email.utils import parsedate_to_datetime
        d = parsedate_to_datetime(pubdate)
        return d.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except Exception:
        return pubdate


def main() -> int:
    try:
        xml = fetch()
    except Exception as e:
        print(f"bse_india: fetch failed: {e}")
        return 1

    items = ITEM_RE.findall(xml)
    rows: list[dict] = []
    captured_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    for blob in items:
        title = _strip((TITLE_RE.search(blob) or [None, ""])[1] if TITLE_RE.search(blob) else "")
        link  = _strip((LINK_RE.search(blob) or [None, ""])[1] if LINK_RE.search(blob) else "")
        desc  = _strip((DESC_RE.search(blob) or [None, ""])[1] if DESC_RE.search(blob) else "")
        pubd  = _strip((PUBDATE_RE.search(blob) or [None, ""])[1] if PUBDATE_RE.search(blob) else "")
        if not title:
            continue
        rows.append({
            "filed_utc": _to_utc_iso(pubd),
            "kind": classify(title, desc),
            "title": title[:240],
            "link": link[:300],
            "summary": desc[:480],
            "captured_at": captured_at,
        })

    rows.sort(key=lambda r: r["filed_utc"], reverse=True)

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["filed_utc","kind","title","link","summary","captured_at"])
        w.writeheader()
        w.writerows(rows)

    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    dist = ", ".join(f"{k}={v}" for k, v in sorted(kinds.items(), key=lambda x: -x[1])[:6])
    print(f"bse_india: {len(rows)} notices | {dist}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
