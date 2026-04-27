#!/usr/bin/env python3
"""
build_ftc.py — Federal Trade Commission (FTC) press-release tape.

Source: https://www.ftc.gov/feeds/press-release.xml  (Drupal RSS 2.0)

FTC is the **antitrust + consumer-protection quasi-judicial agency** that
sues to block mergers, orders divestitures, settles HSR violations, and
files Section 5 unfair-practices cases. Where USTR negotiates trade
policy and USITC adjudicates trade-injury cases, FTC adjudicates
**domestic competition** — the third regulatory leg alongside DOJ
Antitrust Division and the SEC.

Direct equity catalysts:
- Merger challenge / Part-3 administrative complaint → announced deal
  becomes binary: acquirer drops 5-15%, target drops 20-40% if deal
  likely fails. Historically: MSFT-ATVI, KR-ACI, AMGN-HZNP, META-WITH,
  MMYT-US, LIN-PX, T-DTV, ILMN-GRAL, UNH-AMED, etc.
- Consent order / divestiture → partial deal failure, forced asset sale
  (typically at 40-70% of prior negotiation value).
- Consumer-protection enforcement → individual-firm reputational + fines
  (HSBC, TD, VZ/T/CHTR/TMUS robocall, META $5B 2019, AMZN ROSCA, GOOG
  children's privacy).
- Rulemaking (e.g., non-compete ban, click-to-cancel, negative-option,
  junk-fees, "Made in USA", funeral rule) → cross-industry cost shock.
- HSR filing transparency → early-signal M&A volume gauge.
- Fraud / deceptive-practice litigation → recurring small-cap landmines
  (timeshare-exit, telemarketing, weight-loss, crypto MLM).

Output: ftc.csv — filed_utc, kind, title, link, summary.

Stdlib only.
"""
from __future__ import annotations

import csv
import html
import pathlib
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

URL = "https://www.ftc.gov/feeds/press-release.xml"
TIMEOUT = 20
USER_AGENT = "CerebroCatalystEdge/1.0 (admin@catalystedgescanner.com)"

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "ftc.csv"


def _classify(title: str, summary: str) -> str:
    """Priority-ordered 21-kind classifier for FTC press releases."""
    t = (title + " " + summary).lower()

    # Merger challenges — highest narrow-signal priority
    if any(k in t for k in ("sue to block", "sues to block", "challenge merger",
                             "block merger", "block acquisition", "file complaint to stop",
                             "temporarily halt", "preliminary injunction")):
        return "merger_challenge"
    if any(k in t for k in ("consent order", "divestiture", "divest")) and \
       any(k in t for k in ("merger", "acquisition", "combine")):
        return "merger_consent"
    if "abandon" in t and any(k in t for k in ("merger", "acquisition", "deal")):
        return "merger_abandoned"
    if "hart-scott" in t or "hsr" in t or "premerger" in t:
        return "hsr_filings"

    # Rule-making
    if "final rule" in t or "rulemaking" in t:
        return "final_rule"
    if "proposed rule" in t or "notice of proposed" in t:
        return "proposed_rule"
    if "non-compete" in t or "noncompete" in t:
        return "noncompete_rule"
    if "click-to-cancel" in t or "negative option" in t or "rosca" in t:
        return "subscription_rule"
    if "junk fee" in t or "hidden fee" in t:
        return "junk_fee_rule"
    if "made in usa" in t or "made in america" in t:
        return "madeinusa_rule"

    # Antitrust enforcement actions
    if "section 5" in t or "unfair method" in t:
        return "section_5_unfair"
    if "monopoly" in t or "monopolization" in t or "maintain dominance" in t:
        return "monopoly_case"
    if "price fix" in t or "bid rig" in t or "collusion" in t:
        return "price_fixing"

    # Consumer protection bread-and-butter
    if any(k in t for k in ("deceptive", "false claim", "misleading")):
        return "deceptive_practices"
    if any(k in t for k in ("robocall", "telemarketing", "do not call")):
        return "telemarketing_enforcement"
    if any(k in t for k in ("privacy", "coppa", "child online", "children's data")):
        return "privacy_enforcement"
    if any(k in t for k in ("data breach", "data security", "reasonable security")):
        return "data_security"
    if any(k in t for k in ("weight loss", "supplement", "health claim")):
        return "health_claims"
    if any(k in t for k in ("crypto", "cryptocurrency", "token")):
        return "crypto_enforcement"
    if any(k in t for k in ("timeshare", "debt relief", "credit repair")):
        return "consumer_scam"

    # Refunds / redress
    if "refund" in t or "restitution" in t or "redress" in t:
        return "refund_order"

    # Leadership / Commissioner speeches, confirmations
    if any(k in t for k in ("commissioner", "chairman", "chairwoman", "nominat",
                             "sworn in", "retire", "step down")):
        return "leadership_ftc"

    return "ftc_general"


def _strip(text: str, cap: int = 400) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > cap:
        text = text[:cap].rsplit(" ", 1)[0] + "..."
    return text


def _to_utc(pub_date: str) -> str:
    if not pub_date:
        return ""
    try:
        dt_obj = parsedate_to_datetime(pub_date).astimezone(timezone.utc)
        return dt_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return pub_date


def _fetch() -> bytes:
    req = urllib.request.Request(URL, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def main() -> int:
    try:
        raw = _fetch()
    except Exception as exc:
        print(f"[WARN] FTC fetch failed: {exc}", file=sys.stderr)
        return 0

    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        print(f"[WARN] FTC parse failed: {exc}", file=sys.stderr)
        return 0

    items = root.findall(".//item")

    rows = []
    kinds: dict[str, int] = {}
    for it in items:
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        link = (it.findtext("link") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        summary = _strip(it.findtext("description") or "")

        kind = _classify(title, summary)
        rows.append({
            "filed_utc": _to_utc(pub),
            "kind": kind,
            "title": _strip(title, cap=300),
            "link": link,
            "summary": summary,
        })
        kinds[kind] = kinds.get(kind, 0) + 1

    rows.sort(key=lambda x: x["filed_utc"], reverse=True)

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["filed_utc", "kind", "title", "link", "summary"])
        w.writeheader()
        w.writerows(rows)

    dist = ", ".join(f"{k}={v}" for k, v in sorted(kinds.items(), key=lambda x: -x[1])[:8])
    print(f"ftc: {len(rows)} rows | {dist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
