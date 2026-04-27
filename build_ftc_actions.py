#!/usr/bin/env python3
"""build_ftc_actions.py - FTC press-release tape.

The Federal Trade Commission issues press releases for:
- Merger challenges / consent decrees (M&A risk tape)
- Enforcement actions (data privacy, deceptive advertising)
- Rulemaking and policy statements
- Testimony, workshops, reports

For a catalyst scanner, merger challenges and enforcement
actions are the actionable rows. An FTC complaint against
a pending merger can move the target 10-40% in a day.
Consent decrees (settle-and-close) typically resolve the
overhang.

Output: ftc_actions.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import html
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "ftc_actions.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

FEED = "https://www.ftc.gov/feeds/press-release.xml"

KIND_RULES = [
    ("merger_challenge", ("sue to block", "sues to block", "block merger",
                          "block acquisition", "challenge merger",
                          "challenges merger", "challenges acquisition",
                          "move to block", "administrative complaint")),
    ("consent_order", ("consent order", "consent decree", "proposed consent",
                       "final order settling", "agrees to settle",
                       "settles charges")),
    ("enforcement", ("stops operation", "takes action against",
                     "halts", "refund", "ban from",
                     "permanent injunction", "complaint against",
                     "charges ", "orders ", "warning letter")),
    ("rulemaking", ("final rule", "proposed rule", "notice of proposed",
                    "rulemaking", "new rule")),
    ("testimony", ("testifies", "testimony")),
    ("workshop", ("workshop", "hosts event", "public meeting")),
    ("report", ("report finds", "releases report", "annual report",
                "staff report", "research paper")),
]


def _classify(title: str, desc: str) -> str:
    blob = (title + " " + desc).lower()
    for kind, keys in KIND_RULES:
        for k in keys:
            if k in blob:
                return kind
    return "other"


BLACKLIST = (
    "federal trade com", "federal trade co", "justice department",
    "antitrust division", "commission", "federal reserve",
    "securities and exchange", "department of justice",
    "consumer financial", "ftc staff",
)


def _extract_company(title: str, desc: str) -> str:
    """Pull the first Inc./LLC/Corp./Co. phrase, skipping agency self-refs."""
    blob = title + " " + desc
    blob = re.sub(r"<[^>]+>", " ", blob)
    blob = html.unescape(blob)
    # Require proper-noun phrase: each word starts capitalized,
    # then a corp-suffix, then word boundary (space/punct/eol).
    pat = re.compile(
        r"((?:[A-Z][A-Za-z0-9&.\-']*\.?,?\s+){0,5}"
        r"[A-Z][A-Za-z0-9&.\-']*,?\s+"
        r"(?:Inc\.?|LLC|Corp\.?|Company|Co\.|"
        r"Holdings|Pharmaceuticals|Laboratories|Limited|Ltd\.?|PLC)"
        r")\b"
    )
    for m in pat.finditer(blob):
        cand = m.group(1).strip().rstrip(",.")
        low = cand.lower()
        if any(b in low for b in BLACKLIST):
            continue
        return cand[:80]
    return ""


def _fetch() -> bytes:
    req = urllib.request.Request(FEED, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main() -> None:
    now_iso = (dt.datetime.now(dt.timezone.utc)
               .isoformat(timespec="seconds").replace("+00:00", "Z"))
    try:
        body = _fetch().decode("utf-8", "ignore")
    except Exception as e:
        print(f"ftc_actions: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"ftc_actions: keeping prior {OUT_CSV.name}")
        return

    items = re.findall(r"<item>(.*?)</item>", body, re.DOTALL)
    rows: list[dict] = []
    for it in items:
        t = re.search(r"<title>(.*?)</title>", it, re.DOTALL)
        d = re.search(r"<pubDate>(.*?)</pubDate>", it, re.DOTALL)
        link = re.search(r"<link>(.*?)</link>", it, re.DOTALL)
        desc = re.search(r"<description>(.*?)</description>", it, re.DOTALL)
        title = html.unescape((t.group(1) if t else "").strip())[:240]
        date_str = (d.group(1) if d else "").strip()
        # Parse RFC-822 date to ISO
        iso_date = ""
        try:
            parsed = dt.datetime.strptime(date_str[:25],
                                          "%a, %d %b %Y %H:%M:%S")
            iso_date = parsed.date().isoformat()
        except Exception:
            iso_date = ""
        desc_raw = desc.group(1) if desc else ""
        desc_txt = re.sub(r"<[^>]+>", " ", html.unescape(desc_raw))
        desc_txt = re.sub(r"\s+", " ", desc_txt).strip()[:300]
        kind = _classify(title, desc_txt)
        company = _extract_company(title, desc_txt)
        link_url = (link.group(1) if link else "").strip()[:200]
        if not title:
            continue
        rows.append({
            "filed": iso_date,
            "kind": kind,
            "title": title,
            "company_raw": company,
            "url": link_url,
            "captured_at": now_iso,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"ftc_actions: 0 items, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["filed"], reverse=True)
    fieldnames = ["filed", "kind", "title", "company_raw",
                  "url", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    by_kind: dict[str, int] = {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    kb = " ".join(f"{k}={v}" for k, v in
                  sorted(by_kind.items(), key=lambda kv: -kv[1]))
    tagged = sum(1 for r in rows if r["company_raw"])
    top = [r for r in rows if r["company_raw"]][:4]
    tb = " | ".join(f"{r['company_raw'][:30]}:{r['kind']}" for r in top)
    print(f"ftc_actions: {len(rows)} items ({tagged} tagged) | "
          f"{kb} | {tb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
