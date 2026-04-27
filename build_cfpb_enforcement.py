#!/usr/bin/env python3
"""build_cfpb_enforcement.py - CFPB enforcement-actions tape.

The Consumer Financial Protection Bureau posts enforcement
actions at consumerfinance.gov/enforcement/actions/feed/.
Each RSS item IS a defendant company (title is literally the
entity name - e.g. "Equifax, Inc. and Equifax Information
Services LLC").

Universe of typical defendants:
- Big banks (JPM/BAC/WFC/C/USB): UDAAP + servicing failures
- Regional banks + credit unions (KRE components)
- Card issuers (SYF/COF/AXP/DFS)
- Fintech lenders (UPST/LC/SQ/PYPL/AFRM/SOFI)
- BNPL/neobanks/payments
- Consumer reporting (EFX/TRU/FICO)
- Debt collectors/mortgage servicers (PFSI/COOP)
- Credit-repair + payday + auto-title operations

Action kind detected from description text:
- complaint: Bureau filed complaint (litigation opened)
- consent_order: Bureau issued order (settlement)
- stipulated_judgment: final judgment and order (closed)
- civil_penalty: monetary penalty quantified
- ban: individual/entity permanent ban
- dismissed: case dismissed

Output: cfpb_enforcement.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import html
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "cfpb_enforcement.csv"
UA = "CatalystEdge/1.0 (opensource@example.com)"

FEED = "https://www.consumerfinance.gov/enforcement/actions/feed/"

KIND_RULES = [
    ("stipulated_judgment", ("stipulated final judgment",
                             "proposed stipulated final")),
    ("consent_order", ("proposed consent order", "consent order",
                       "consent decree", "settles charges",
                       "agrees to settle")),
    ("complaint", ("filed a complaint", "commenced an adversary",
                   "initiated a lawsuit", "filed suit")),
    ("civil_penalty", ("civil money penalty", "civil penalty",
                       "pay penalty of", "million penalty",
                       "billion penalty")),
    ("ban", ("permanently ban", "banned from", "ban from")),
    ("dismissed", ("dismissed the case", "case was dismissed")),
    ("order", ("issued an order", "issued a consent",
               "ordered ", "final order")),
]


def _classify(title: str, desc: str) -> str:
    blob = (title + " " + desc).lower()
    for kind, keys in KIND_RULES:
        for k in keys:
            if k in blob:
                return kind
    return "other"


def _extract_amount(desc: str) -> str:
    """Pull first $-denominated penalty amount from description."""
    # Match $NNN million/billion or $N,NNN,NNN
    m = re.search(
        r"\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|thousand)?",
        desc, re.IGNORECASE)
    if not m:
        return ""
    num = m.group(1).replace(",", "")
    scale = (m.group(2) or "").lower()
    try:
        v = float(num)
    except ValueError:
        return ""
    if scale == "billion":
        v *= 1_000_000_000
    elif scale == "million":
        v *= 1_000_000
    elif scale == "thousand":
        v *= 1_000
    return f"{int(v)}"


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
        print(f"cfpb_enforcement: fetch failed: {e}")
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"cfpb_enforcement: keeping prior {OUT_CSV.name}")
        return

    items = re.findall(r"<item>(.*?)</item>", body, re.DOTALL)
    rows: list[dict] = []
    for it in items:
        t = re.search(r"<title>(.*?)</title>", it, re.DOTALL)
        d = re.search(r"<pubDate>(.*?)</pubDate>", it, re.DOTALL)
        link = re.search(r"<link>(.*?)</link>", it, re.DOTALL)
        desc = re.search(r"<description>(.*?)</description>", it, re.DOTALL)
        title = html.unescape((t.group(1) if t else "").strip())[:160]
        date_str = (d.group(1) if d else "").strip()
        iso_date = ""
        try:
            iso_date = dt.datetime.strptime(
                date_str[:25], "%a, %d %b %Y %H:%M:%S").date().isoformat()
        except Exception:
            pass
        desc_raw = desc.group(1) if desc else ""
        desc_txt = re.sub(r"<[^>]+>", " ", html.unescape(desc_raw))
        desc_txt = re.sub(r"\s+", " ", desc_txt).strip()[:400]
        kind = _classify(title, desc_txt)
        penalty_usd = _extract_amount(desc_txt)
        link_url = (link.group(1) if link else "").strip()[:200]
        if not title:
            continue
        rows.append({
            "filed": iso_date,
            "kind": kind,
            "defendant": title,
            "penalty_usd": penalty_usd,
            "url": link_url,
            "captured_at": now_iso,
        })

    if not rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"cfpb_enforcement: 0 items, keeping {OUT_CSV.name}")
        return

    rows.sort(key=lambda r: r["filed"], reverse=True)
    fieldnames = ["filed", "kind", "defendant", "penalty_usd",
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
    priced = sum(1 for r in rows if r["penalty_usd"])
    top = rows[:4]
    tb = " | ".join(
        f"{r['defendant'][:32]}:{r['kind']}"
        for r in top)
    print(f"cfpb_enforcement: {len(rows)} items ({priced} with $) | "
          f"{kb} | {tb} -> {OUT_CSV.name}")


if __name__ == "__main__":
    main()
