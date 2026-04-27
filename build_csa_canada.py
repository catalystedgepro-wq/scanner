#!/usr/bin/env python3
"""build_csa_canada.py - Canadian Securities Administrators tape.

Source: CSA News Archive RSS
(https://www.securities-administrators.ca/news/feed/). 10-item rolling window,
stdlib only, no key.

CSA is the umbrella body for 13 provincial/territorial securities regulators
(OSC, AMF, BCSC, ASC, FCAA, FCNB, MSC, NSSC, NWT, NU, YT, PEI, NLSC). Its
publications drive pan-Canadian rulemaking (NI 51-102 continuous disclosure,
NI 43-101 mineral disclosure for TSX-V junior miners, NI 81-102 mutual funds,
NI 45-106 private placements). Most items are high-signal regulatory-change
events or investor alerts affecting:

  - TSX-listed banks (RY, TD, BMO, BNS, CM, NA)
  - TSX-V junior miners + exploration (hundreds of CDN-only tickers)
  - Cannabis (WEED, ACB, CRON, TLRY-Canada, APHA)
  - Canadian fintech/crypto (HUT, BTCC, QBTC)
  - Inter-listed US ADRs (GIB, SHOP, BAM, MFC, SU, CNQ, CP, CNI, CNR)

Kind taxonomy (keyword-matched, priority order):
  * investor_alert    — fraud/scam/ramp-and-dump warnings
  * rulemaking        — adopted amendments, final rules, new NI
  * consultation      — proposed amendments, invites comment, CP
  * review            — oversight reports, CIRO/CIPF audits
  * tokenization      — digital-asset / DLT / crypto initiative
  * prediction_market — event-contract / prediction-market guidance
  * reporting_change  — semi-annual / pilot reporting changes
  * fraud_disarm      — reports on shut-down fraudulent sites / investment-fraud takedown
  * enforcement       — orders, sanctions, administrative proceedings
  * press             — plain press-release fallback

Output: csa_canada.csv
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "csa_canada.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"
FEED = "https://www.securities-administrators.ca/news/feed/"

KIND_RULES = [
    ("investor_alert", ("investor alert", "ramp-and-dump", "ramp and dump",
                        "fraudulent investment", "scam alert",
                        "fraud warning", "beware of", "pump-and-dump")),
    ("enforcement", ("administrative proceeding", "order against",
                     "cease trade order", "sanction", "disgorgement",
                     "reciprocal order")),
    ("fraud_disarm", ("disarming", "shut down", "took down", "removed from",
                      "fraudulent investment sites", "disrupted")),
    ("rulemaking", ("announce adoption", "final amendments",
                    "adoption of", "adopt amendments", "final rule",
                    "comes into force", "publishes final")),
    ("consultation", ("publishes proposed", "proposed amendment",
                      "invites stakeholders", "invites comment",
                      "request for comment", "consultation paper",
                      "invite comments")),
    ("tokenization", ("tokenization", "tokenized", "digital asset",
                      "distributed ledger", "crypto asset")),
    ("prediction_market", ("prediction market", "event contract",
                           "event-based contract")),
    ("reporting_change", ("semi-annual", "reporting pilot",
                          "continuous disclosure",
                          "insider reporting", "interim reporting",
                          "financial reporting")),
    ("review", ("oversight", "key oversight activities",
                "annual report on", "report on activities")),
]


def _classify(title: str, desc: str) -> str:
    blob = (title + " " + desc).lower()
    for kind, keys in KIND_RULES:
        for k in keys:
            if k in blob:
                return kind
    return "press"


def _fetch() -> bytes:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _parse_pubdate(raw: str) -> str:
    s = raw.strip()
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S"):
        try:
            return dt.datetime.strptime(s[:31], fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    try:
        body = _fetch().decode("utf-8", "ignore")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"csa_canada: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"csa_canada: keeping prior {OUT_CSV.name}")
        return

    items = re.findall(r"<item>(.*?)</item>", body, re.DOTALL)
    rows: list[dict] = []
    for it in items:
        t = re.search(r"<title>(.*?)</title>", it, re.DOTALL)
        d = re.search(r"<pubDate>(.*?)</pubDate>", it, re.DOTALL)
        link = re.search(r"<link>(.*?)</link>", it, re.DOTALL)
        desc = re.search(r"<description>(.*?)</description>", it, re.DOTALL)

        title_raw = (t.group(1) if t else "").strip()
        title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", title_raw))[:240]
        iso_date = _parse_pubdate(d.group(1) if d else "")
        desc_raw = desc.group(1) if desc else ""
        desc_clean = re.sub(r"<!\[CDATA\[|\]\]>", "", desc_raw)
        desc_txt = re.sub(r"<[^>]+>", " ", html.unescape(desc_clean))
        desc_txt = re.sub(r"\s+", " ", desc_txt).strip()[:500]
        link_url = (link.group(1) if link else "").strip()[:240]

        kind = _classify(title, desc_txt)

        if not title:
            continue
        rows.append({
            "filed": iso_date,
            "kind": kind,
            "title": title,
            "url": link_url,
            "captured_at": now_iso,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"csa_canada: 0 items, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["filed"], reverse=True)
    fieldnames = ["filed", "kind", "title", "url", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_kind: dict[str, int] = {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    kb = " ".join(f"{k}={v}" for k, v in
                  sorted(by_kind.items(), key=lambda kv: -kv[1]))
    top = rows[:3]
    tb = " | ".join(f"{r['title'][:38]}:{r['kind']}" for r in top)
    print(f"csa_canada: {len(rows)} items | {kb} | {tb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
