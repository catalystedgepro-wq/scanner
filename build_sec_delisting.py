#!/usr/bin/env python3
"""build_sec_delisting.py — SEC Form 25 / Form 15 delisting & deregistration.

Catalysts for the tape of companies exiting public markets:
- Form 25 / 25-NSE: exchange-initiated voluntary delisting (merger close,
  bankruptcy, or failure to maintain listing standards). Almost always
  paired with a Form 15 within 10 days.
- Form 15-12B / 15-12G: deregistration of registered class (1934 Act).
  Indicates company is going dark / suspending reporting.
- Form 15-15D: deregistration after Form 15's 90-day grace period.
- Form 15F-12B / 15F-12G / 15F-15D: foreign private issuer variants.

Signal:
- Form 25 (Filer=issuer) → voluntary exit (merger/go-private). Often +
- Form 25 (Filer=exchange) → forced delist. Historically -20% to -50%
- Form 15 → remaining float illiquid, going-dark risk for holders
- FPI 15F → ADR delisting, potential sympathy to peer ADRs

Source: SEC EDGAR atom feeds (getcurrent, per form type)
Output: sec_delisting.csv
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "sec_delisting.csv"

UA = "CatalystEdge/1.0 (opensource@example.com)"
BASE = "https://www.sec.gov/cgi-bin/browse-edgar"

FORMS = [
    ("25", "delisting"),
    ("25-NSE", "exchange_notice"),
    ("15-12B", "deregister_class_B"),
    ("15-12G", "deregister_class_G"),
    ("15-15D", "deregister_post_15d"),
    ("15F-12B", "deregister_fpi_class_B"),
    ("15F-12G", "deregister_fpi_class_G"),
    ("15F-15D", "deregister_fpi_post_15d"),
]


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"sec_delisting: {url[:90]}: {e}")
        return ""


def _parse_entries(atom: str, form: str, category: str) -> list[dict]:
    entries = re.findall(r"<entry>(.*?)</entry>", atom, re.S)
    rows: list[dict] = []
    for e in entries:
        title_m = re.search(r"<title>([^<]+)</title>", e)
        link_m = re.search(r'<link rel="alternate"[^>]*href="([^"]+)"', e)
        upd_m = re.search(r"<updated>([^<]+)</updated>", e)
        sum_m = re.search(r"<summary[^>]*>(.*?)</summary>", e, re.S)
        if not title_m:
            continue
        title = title_m.group(1).strip()
        # Only keep items whose form matches exactly (the feed also
        # surfaces adjacent forms like 253G2 for 25 queries).
        tm = re.match(r"^(\S+)\s+-\s+(.+?)\s+\((\d+)\)\s+\(([^)]+)\)$", title)
        if not tm:
            continue
        feed_form = tm.group(1)
        if feed_form != form:
            continue
        company = tm.group(2).strip()
        cik = tm.group(3).strip()
        role = tm.group(4).strip()
        filed = ""
        if sum_m:
            fm = re.search(r"Filed:</b>\s*([0-9\-]+)", sum_m.group(1))
            if fm:
                filed = fm.group(1)
        link = link_m.group(1) if link_m else ""
        updated = upd_m.group(1) if upd_m else ""
        rows.append({
            "form": feed_form,
            "category": category,
            "company": company[:160],
            "cik": cik,
            "role": role,
            "filed_date": filed,
            "updated_at": updated,
            "link": link,
        })
    return rows


def main() -> None:
    all_rows: list[dict] = []
    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")

    for form, category in FORMS:
        url = (f"{BASE}?action=getcurrent&type="
               f"{urllib.request.quote(form)}"
               "&company=&dateb=&owner=include&count=40&output=atom")
        atom = _get(url)
        if not atom:
            continue
        rows = _parse_entries(atom, form, category)
        for r in rows:
            r["captured_at"] = now_iso
        all_rows.extend(rows)

    if not all_rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"sec_delisting: empty, keeping {OUT_CSV.name}")
        return

    # Newest first by filed_date then updated_at.
    all_rows.sort(key=lambda r: (r["filed_date"], r["updated_at"]),
                  reverse=True)

    fieldnames = ["form", "category", "company", "cik", "role",
                  "filed_date", "updated_at", "link", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    by_form: dict[str, int] = {}
    for r in all_rows:
        by_form[r["form"]] = by_form.get(r["form"], 0) + 1
    bits = " ".join(f"{k}={v}" for k, v in
                    sorted(by_form.items(), key=lambda x: -x[1]))
    print(f"sec_delisting: {len(all_rows)} filings | {bits} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
