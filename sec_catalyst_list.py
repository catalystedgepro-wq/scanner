#!/usr/bin/env python3
"""Fetch recent SEC catalyst filings and print a ranked ticker list.

No third-party dependencies.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import random
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

CATALYST_FORMS = [
    "8-K",
    "6-K",
    "4",
    "S-3",
    "424B1",
    "424B2",
    "424B3",
    "424B4",
    "424B5",
    "SC 13D",
    "SC 13G",
    "RW",
    "NT 10-Q",
    "NT 10-K",
    # 2026-04-17 expansion: proxy, tender offers, IPOs, M&A registrations.
    "DEF 14A",
    "PRE 14A",
    "SC TO-T",
    "SC 14D9",
    "S-1",
    "S-1/A",
    "S-4",
    # 2026-04-17 late-add: periodic reports. These carry going-concern /
    # material-weakness disclosures that move small caps. Score weighted
    # lower than 8-K in rank_sec_catalysts.py because volume is high.
    "10-Q",
    "10-K",
    # 2026-04-24 expansion — high-signal events missing from original whitelist.
    "SC TO-I",    # issuer self-tender / buyback (bullish pop)
    "SC 13E3",    # going-private transaction (+50% pops historically)
    "DEFA14A",    # definitive additional proxy materials (activist campaigns)
    "DFAN14A",    # non-management soliciting (activist)
    "PREC14A",    # preliminary contested proxy (activist)
    "25",         # delisting notification from exchange
    "25-NSE",     # delisting notification (non-SRO exchange)
    "15-12G",     # deregistration
    "15-12B",     # deregistration (§12(b))
    "8-K/A",      # 8-K amendment (restatements, new material info)
    "F-1",        # foreign issuer IPO
    "F-3",        # foreign issuer shelf
    "F-4",        # foreign issuer M&A registration
    "SC 13G/A",   # passive holder amendment
    "SC 13D/A",   # activist holder amendment
]

ROOT = Path(__file__).resolve().parent
TICKER_CACHE_PATH = ROOT / ".sec_company_tickers_cache.json"
RETRYABLE_HTTP_CODES = {403, 429, 500, 502, 503, 504}


def _retry_delay(exc: Exception, attempt: int, base: float, cap: float) -> float:
    retry_after = None
    if isinstance(exc, urllib.error.HTTPError):
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
    if retry_after:
        try:
            return min(cap, max(base, float(retry_after)))
        except ValueError:
            pass
    return min(cap, base * (2 ** attempt)) + random.uniform(0.0, min(0.75, base))


def http_get(url: str, user_agent: str, retries: int, backoff_base: float, backoff_cap: float) -> bytes:
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in RETRYABLE_HTTP_CODES or attempt >= retries:
                raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt >= retries:
                raise
        delay = _retry_delay(last_exc, attempt, backoff_base, backoff_cap)
        print(
            f"SEC retry {attempt + 1}/{retries} for {url} after {last_exc!r}; sleeping {delay:.1f}s",
            file=sys.stderr,
        )
        time.sleep(delay)
    if last_exc is None:
        raise RuntimeError(f"Failed to fetch {url}")
    raise last_exc


def load_cik_to_ticker(
    user_agent: str,
    retries: int,
    backoff_base: float,
    backoff_cap: float,
    cache_path: Path,
) -> dict[str, str]:
    try:
        data = http_get(
            "https://www.sec.gov/files/company_tickers.json",
            user_agent,
            retries=retries,
            backoff_base=backoff_base,
            backoff_cap=backoff_cap,
        )
        cache_path.write_bytes(data)
    except Exception as exc:
        if not cache_path.exists():
            raise RuntimeError(f"Unable to refresh SEC ticker map and no cache exists: {exc}") from exc
        print(
            f"Using cached SEC ticker map from {cache_path.name} because live fetch failed: {exc}",
            file=sys.stderr,
        )
        data = cache_path.read_bytes()
    payload = json.loads(data.decode("utf-8"))
    mapping: dict[str, str] = {}
    for row in payload.values():
        cik = str(row["cik_str"]).zfill(10)
        ticker = str(row["ticker"]).upper()
        mapping[cik] = ticker
    return mapping


def parse_feed_entries(xml_bytes: bytes) -> list[dict[str, str]]:
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml_bytes)
    out: list[dict[str, str]] = []
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        updated = (entry.findtext("a:updated", default="", namespaces=ns) or "").strip()
        link_el = entry.find("a:link", ns)
        link = link_el.attrib.get("href", "") if link_el is not None else ""
        summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
        out.append({"title": title, "updated": updated, "link": link, "summary": summary})
    return out


def extract_cik(text: str) -> str | None:
    m = re.search(r"CIK(?:=|:)\s*0*([0-9]{1,10})", text, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"/data/0*([0-9]{1,10})/", text)
    if not m:
        return None
    return m.group(1).zfill(10)


def parse_updated(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def fetch_recent_forms(
    user_agent: str,
    forms: list[str],
    max_per_form: int,
    retries: int,
    backoff_base: float,
    backoff_cap: float,
) -> list[dict[str, str]]:
    all_rows: list[dict[str, str]] = []
    failures: list[str] = []
    for form in forms:
        q = urllib.parse.urlencode(
            {
                "action": "getcurrent",
                "type": form,
                "owner": "include",
                "count": str(max_per_form),
                "output": "atom",
            }
        )
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?{q}"
        try:
            xml_bytes = http_get(
                url,
                user_agent,
                retries=retries,
                backoff_base=backoff_base,
                backoff_cap=backoff_cap,
            )
        except Exception as exc:
            failures.append(f"{form}: {exc}")
            print(f"Skipping SEC form feed {form} after retries: {exc}", file=sys.stderr)
            continue
        for row in parse_feed_entries(xml_bytes):
            row["form"] = form
            all_rows.append(row)
    if not all_rows:
        detail = "; ".join(failures) if failures else "no rows returned"
        raise RuntimeError(f"All SEC form feeds failed: {detail}")
    return all_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Recent SEC catalyst filings.")
    parser.add_argument("--max-per-form", type=int, default=100)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--backoff-base", type=float, default=1.5)
    parser.add_argument("--backoff-cap", type=float, default=20.0)
    parser.add_argument("--ticker-cache", default=str(TICKER_CACHE_PATH))
    args = parser.parse_args()

    user_agent = os.getenv(
        "SEC_USER_AGENT",
        "LocalScanner/1.0 (Catalyst Edge Maintainers Catalyst@gmail.com)",
    )

    cik_to_ticker = load_cik_to_ticker(
        user_agent,
        retries=max(0, args.retries),
        backoff_base=max(0.25, args.backoff_base),
        backoff_cap=max(args.backoff_base, args.backoff_cap),
        cache_path=Path(args.ticker_cache),
    )
    rows = fetch_recent_forms(
        user_agent,
        CATALYST_FORMS,
        args.max_per_form,
        retries=max(0, args.retries),
        backoff_base=max(0.25, args.backoff_base),
        backoff_cap=max(args.backoff_base, args.backoff_cap),
    )

    now = dt.datetime.now(dt.timezone.utc)
    seen: set[tuple[str, str, str]] = set()
    ranked: list[dict[str, str]] = []

    for row in rows:
        cik = extract_cik(f"{row.get('title','')} {row.get('summary','')} {row.get('link','')}")
        if not cik:
            continue
        ticker = cik_to_ticker.get(cik, "")
        if not ticker:
            continue
        # Map warrants/rights/units to underlying common stock
        # e.g. ABVEW → ABVE, IPAXW → IPAX, HCAIU → HCAI
        if len(ticker) == 5 and ticker[-1] in ("W", "R", "U") and ticker[:-1].isalpha():
            ticker = ticker[:-1]
        updated = parse_updated(row.get("updated", ""))
        recency_min = ""
        if updated is not None:
            recency_min = str(int((now - updated).total_seconds() // 60))
        key = (ticker, row["form"], row.get("updated", ""))
        if key in seen:
            continue
        seen.add(key)
        ranked.append(
            {
                "ticker": ticker,
                "form": row["form"],
                "updated_utc": row.get("updated", ""),
                "recency_min": recency_min,
                "title": row.get("title", ""),
                "link": row.get("link", ""),
            }
        )

    ranked.sort(key=lambda r: int(r["recency_min"]) if r["recency_min"].isdigit() else 10**9)
    ranked = ranked[: args.limit]

    print("ticker,form,updated_utc,recency_min,link")
    for r in ranked:
        print(f"{r['ticker']},{r['form']},{r['updated_utc']},{r['recency_min']},{r['link']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)
