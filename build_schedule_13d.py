#!/usr/bin/env python3
"""build_schedule_13d.py — SEC SC 13D/13G activist filings.

SC 13D: >5% stake + active intent (proxy fight, board seat, M&A push).
SC 13G: >5% stake + passive (index fund / quiet accumulator).

The 13D flow is the single loudest activist signal in US markets —
Icahn, Elliott, Pershing, Starboard all file here before launching
campaigns. 13G shows quiet mega-caps crossing the 5% line.

Signal: 13D on small/mid-cap = 2-5× upside setup (buyouts, spinoffs,
forced strategic review). 13G on mega-cap = index rebalance / sovereign
wealth flow.

Source: sec.gov/cgi-bin/browse-edgar getcurrent atom (free).
Output: schedule_13d.csv
Columns: form, filed_at, issuer, cik, filer, url, captured_at
"""
from __future__ import annotations
import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
OUT_CSV = ROOT / "schedule_13d.csv"

UA = "CatalystEdge/1.0 opensource@example.com"
BASE = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
        "&type={form}&company=&dateb=&owner=include&count=40&output=atom")

FORMS = ["SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"]

ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.DOTALL | re.IGNORECASE)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL | re.IGNORECASE)
UPDATED_RE = re.compile(r"<updated>(.*?)</updated>",
                        re.DOTALL | re.IGNORECASE)
LINK_RE = re.compile(r'<link[^>]+href="([^"]+)"', re.IGNORECASE)
SUMMARY_RE = re.compile(r"<summary[^>]*>(.*?)</summary>",
                        re.DOTALL | re.IGNORECASE)


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&lt;", "<", s)
    s = re.sub(r"&gt;", ">", s)
    s = re.sub(r"&#39;", "'", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _fetch_form(form: str) -> list[dict]:
    url = BASE.format(form=urllib.request.quote(form))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read().decode("utf-8", errors="ignore")

    rows: list[dict] = []
    for block in ENTRY_RE.findall(body):
        title_m = TITLE_RE.search(block)
        if not title_m:
            continue
        title = _strip_html(title_m.group(1))
        updated_m = UPDATED_RE.search(block)
        updated = updated_m.group(1).strip() if updated_m else ""
        link_m = LINK_RE.search(block)
        link = link_m.group(1) if link_m else ""
        summary_m = SUMMARY_RE.search(block)
        summary = _strip_html(summary_m.group(1)) if summary_m else ""

        # Title format: "SC 13D - IssuerName (0001234567) (filer name)"
        issuer = ""
        cik = ""
        filer = ""
        m = re.search(r"-\s*(.*?)\s*\((\d{7,10})\)\s*\((.*?)\)", title)
        if m:
            issuer = m.group(1).strip()[:60]
            cik = m.group(2)
            filer = m.group(3).strip()[:60]
        else:
            issuer = title[:60]

        rows.append({
            "form": form,
            "filed_at": updated[:19],
            "issuer": issuer,
            "cik": cik,
            "filer": filer,
            "url": link[:160],
            "summary": summary[:160],
        })
    return rows


def main() -> None:
    all_rows: list[dict] = []
    errs: list[str] = []
    for form in FORMS:
        try:
            all_rows.extend(_fetch_form(form))
        except Exception as e:
            errs.append(f"{form}:{e}")

    if not all_rows:
        if OUT_CSV.exists() and OUT_CSV.stat().st_size > 200:
            print(f"schedule_13d: {';'.join(errs) or 'empty'}; "
                  f"keeping existing {OUT_CSV.name}")
        else:
            print(f"schedule_13d: no data ({';'.join(errs) or 'empty'})")
        return

    all_rows.sort(key=lambda r: r["filed_at"], reverse=True)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    now = now.replace("+00:00", "Z")
    for r in all_rows:
        r["captured_at"] = now

    fieldnames = ["form", "filed_at", "issuer", "cik", "filer", "url",
                  "summary", "captured_at"]
    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    by_form: dict[str, int] = {}
    for r in all_rows:
        by_form[r["form"]] = by_form.get(r["form"], 0) + 1
    bits = " ".join(f"{k}={v}" for k, v in sorted(by_form.items()))
    print(f"schedule_13d: {len(all_rows)} filings | {bits} -> "
          f"{OUT_CSV.name}")


if __name__ == "__main__":
    main()
