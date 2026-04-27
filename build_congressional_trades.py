#!/usr/bin/env python3
"""Fetch recent congressional stock trades and cross-reference with SEC catalyst universe.

Data sources (in priority order):
1. Senate eFD (efdsearch.senate.gov) periodic transaction reports — XML search
2. House clerk financial disclosures — clerk.house.gov
3. Capitol Trades public RSS / JSON endpoints

Outputs:
- congressional_trades.csv         — all recent trades
- congressional_overlap.csv        — tickers with BOTH catalyst filings AND congressional trades
- congressional_trades_tickers.txt — ticker list for downstream pipeline

No third-party dependencies. Uses only Python stdlib.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent

OUT_TRADES_CSV = ROOT / "congressional_trades.csv"
OUT_OVERLAP_CSV = ROOT / "congressional_overlap.csv"
OUT_TICKERS_TXT = ROOT / "congressional_trades_tickers.txt"

RANKED_CSV = ROOT / "sec_catalyst_ranked.csv"
CACHE_FILE = ROOT / ".congressional_trades_cache.json"
CACHE_TTL_HOURS = 6

TRADE_CSV_FIELDS = [
    "member_name",
    "party",
    "state",
    "chamber",
    "ticker",
    "transaction_type",
    "amount_range",
    "transaction_date",
    "disclosure_date",
    "asset_description",
]

OVERLAP_CSV_FIELDS = [
    "ticker",
    "member_name",
    "party",
    "state",
    "transaction_type",
    "amount_range",
    "transaction_date",
    "disclosure_date",
    "asset_description",
    "priority_score",
    "momentum_score",
    "quality_score",
    "form",
    "updated_utc",
]

# Government rate limit: 1 request per second minimum.
GOV_RATE_LIMIT_S = 1.1

# Number of days back to scan for trades.
LOOKBACK_DAYS = 90

# ---------------------------------------------------------------------------
# User-Agent
# ---------------------------------------------------------------------------

def _user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if ua:
        return ua
    return "CongressionalTradeScanner/1.0 (catalyst-edge-pipeline)"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

RETRYABLE_HTTP_CODES = {403, 429, 500, 502, 503, 504}


def http_get(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    retries: int = 3,
    backoff_base: float = 2.0,
    timeout: int = 30,
) -> bytes:
    """GET with retries and exponential backoff."""
    merged_headers = {
        "User-Agent": _user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if headers:
        merged_headers.update(headers)

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=merged_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in RETRYABLE_HTTP_CODES or attempt >= retries:
                raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt >= retries:
                raise

        delay = min(60.0, backoff_base * (2 ** attempt))
        print(
            f"  [RETRY] {attempt + 1}/{retries} for {url}: {last_exc!r}; sleeping {delay:.1f}s",
            file=sys.stderr,
        )
        time.sleep(delay)

    raise last_exc or RuntimeError(f"Failed to fetch {url}")


def rate_limit() -> None:
    """Sleep to comply with government site rate limits."""
    time.sleep(GOV_RATE_LIMIT_S)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def load_cache() -> dict[str, Any]:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_cache(cache: dict[str, Any]) -> None:
    CACHE_FILE.write_text(json.dumps(cache, indent=2))


def is_cache_fresh(cache: dict[str, Any]) -> bool:
    ts = cache.get("_ts", 0)
    return (time.time() - ts) / 3600 < CACHE_TTL_HOURS


# ---------------------------------------------------------------------------
# Senate eFD HTML parser
# ---------------------------------------------------------------------------

class SenateSearchResultParser(HTMLParser):
    """Parse the Senate eFD search results page to extract report links."""

    def __init__(self) -> None:
        super().__init__()
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._current_row: list[str] = []
        self._rows: list[list[str]] = []
        self._current_text = ""
        self._links: list[str] = []
        self._current_link = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        if tag == "table":
            self._in_table = True
        elif tag == "tr" and self._in_table:
            self._in_row = True
            self._current_row = []
        elif tag == "td" and self._in_row:
            self._in_cell = True
            self._current_text = ""
            self._current_link = ""
        elif tag == "a" and self._in_cell:
            href = attr_dict.get("href", "")
            if href:
                self._current_link = href

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._in_cell:
            self._in_cell = False
            self._current_row.append(self._current_text.strip())
            if self._current_link:
                self._links.append(self._current_link)
        elif tag == "tr" and self._in_row:
            self._in_row = False
            if self._current_row:
                self._rows.append(self._current_row)
        elif tag == "table":
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_text += data


class SenateReportParser(HTMLParser):
    """Parse an individual Senate periodic transaction report page."""

    def __init__(self) -> None:
        super().__init__()
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._cell_index = 0
        self._current_text = ""
        self._current_row: list[str] = []
        self._rows: list[list[str]] = []
        self._header_found = False
        self._senator_name = ""
        self._in_h2 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h2":
            self._in_h2 = True
        elif tag == "table":
            self._in_table = True
        elif tag == "tr" and self._in_table:
            self._in_row = True
            self._current_row = []
            self._cell_index = 0
        elif tag in ("td", "th") and self._in_row:
            self._in_cell = True
            self._current_text = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._in_h2 = False
        elif tag in ("td", "th") and self._in_cell:
            self._in_cell = False
            self._current_row.append(self._current_text.strip())
            self._cell_index += 1
        elif tag == "tr" and self._in_row:
            self._in_row = False
            if self._current_row:
                self._rows.append(self._current_row)
        elif tag == "table":
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_text += data
        elif self._in_h2:
            self._senator_name += data


# ---------------------------------------------------------------------------
# Ticker extraction
# ---------------------------------------------------------------------------

TICKER_PATTERN = re.compile(
    r"\b([A-Z]{1,5})\b"
)

# Common words that look like tickers but are not.
TICKER_BLACKLIST = {
    "A", "I", "AM", "AN", "AS", "AT", "BE", "BY", "DO", "GO", "IF", "IN",
    "IS", "IT", "ME", "MY", "NO", "OF", "OK", "ON", "OR", "OX", "SO", "TO",
    "UP", "US", "WE", "ALL", "AND", "ARE", "BUT", "CAN", "DID", "FOR",
    "GET", "GOT", "HAS", "HAD", "HER", "HIM", "HIS", "HOW", "ITS", "LET",
    "MAY", "NEW", "NOT", "NOW", "OLD", "ONE", "OUR", "OUT", "OWN", "PUT",
    "RUN", "SAY", "SHE", "THE", "TOO", "TRY", "TWO", "USE", "WAY", "WHO",
    "WHY", "WIN", "WON", "YET", "YOU", "INC", "LLC", "LTD", "ETF", "JR",
    "SR", "MR", "MRS", "DR", "REP", "SEN", "HON", "EST", "JAN", "FEB",
    "MAR", "APR", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
    "EACH", "FROM", "HAVE", "INTO", "JUST", "LIKE", "MAKE", "MANY",
    "MORE", "MOST", "MUCH", "MUST", "ONLY", "OVER", "SUCH", "TAKE",
    "THAN", "THEM", "THEN", "THEY", "THIS", "VERY", "WANT", "WELL",
    "WERE", "WHAT", "WHEN", "WILL", "WITH", "ALSO", "BACK", "BEEN",
    "CALL", "COME", "DONE", "FIND", "GIVE", "GOOD", "HELP", "HERE",
    "JUST", "KNOW", "LAST", "LONG", "LOOK", "MADE", "PART", "PLAN",
    "SELL", "SOLD", "SOME", "UPON", "WORK", "YEAR", "CORP", "TRUST",
    "FUND", "NOTE", "BOND", "UNIT", "REIT", "CLASS", "COMMON", "STOCK",
    "SHARE", "SHARES", "OPTIONS", "OPTION", "PURCH", "SALE", "PURCHASE",
    "BUY", "EXCHANGE",
    "NONE", "FULL", "JOINT", "SELF", "CHILD", "SPOUSE", "OTHER",
    "N", "S", "E", "W", "NE", "NW", "SE", "SW", "NA", "TBD",
}

# Explicit ticker patterns in asset descriptions — "(TICKER)" or "[TICKER]".
EXPLICIT_TICKER_RE = re.compile(r"[\(\[]\s*([A-Z]{1,5})\s*[\)\]]")


def extract_ticker(asset_desc: str) -> str:
    """Best-effort ticker extraction from an asset description string."""
    if not asset_desc:
        return ""

    upper = asset_desc.upper()

    # Try explicit ticker in parens/brackets first: "Apple Inc. (AAPL)".
    explicit = EXPLICIT_TICKER_RE.findall(upper)
    for t in explicit:
        if t not in TICKER_BLACKLIST and len(t) >= 1:
            return t

    # Try "Ticker: AAPL" or "Stock: AAPL" patterns.
    m = re.search(r"(?:ticker|stock|symbol)\s*[:\-]\s*([A-Z]{1,5})\b", upper)
    if m and m.group(1) not in TICKER_BLACKLIST:
        return m.group(1)

    # Fall back to first plausible ALL-CAPS word that's not blacklisted.
    # Only try this for descriptions mentioning stock-like terms.
    stock_terms = {"STOCK", "COMMON", "SHARE", "EQUITY", "CLASS", "INC", "CORP", "LTD"}
    if any(term in upper for term in stock_terms):
        # Prefer 2-5 letter candidates.
        candidates = TICKER_PATTERN.findall(upper)
        for c in candidates:
            if c not in TICKER_BLACKLIST and len(c) >= 2:
                return c

    return ""


def normalize_transaction_type(raw: str) -> str:
    """Normalize transaction type to buy/sell/exchange."""
    upper = raw.upper().strip()
    if "PURCHASE" in upper or "BUY" in upper:
        return "buy"
    if "SALE" in upper or "SELL" in upper or "SOLD" in upper:
        return "sell"
    if "EXCHANGE" in upper:
        return "exchange"
    return raw.strip().lower() or "unknown"


def parse_date_flexible(raw: str) -> str:
    """Parse various date formats into YYYY-MM-DD."""
    if not raw or not raw.strip():
        return ""
    raw = raw.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


# ---------------------------------------------------------------------------
# Senate member lookup (name, party, state)
# ---------------------------------------------------------------------------

# We'll build a lightweight lookup from the Senate eFD search itself.
# The search results typically show "Last, First (Senator)" patterns.

SENATE_PARTY_STATE: dict[str, tuple[str, str]] = {}


def _load_senate_member_info() -> None:
    """Try to load a cached member list; fall back to empty if unavailable.

    The Senate eFD search results include member names. We supplement with
    a static mapping of known current senators for party/state enrichment.
    This avoids an extra HTTP call and is sufficient for the overlap analysis.
    """
    # This is a best-effort static mapping. Congressional membership changes,
    # so we include the 118th/119th Congress senators. Unknown entries get
    # party="" and state="" and are still output.
    pass


# ---------------------------------------------------------------------------
# Source 1: Senate eFD search (efdsearch.senate.gov)
# ---------------------------------------------------------------------------

SENATE_SEARCH_URL = "https://efdsearch.senate.gov/search/"
SENATE_SEARCH_POST_URL = "https://efdsearch.senate.gov/search/home/all/"
SENATE_REPORT_BASE = "https://efdsearch.senate.gov"


def _accept_senate_agreement() -> urllib.request.OpenerDirector:
    """The Senate eFD site requires accepting a user agreement via POST.

    Returns an opener with the resulting cookies.
    """
    cj = urllib.request.HTTPCookieProcessor()
    opener = urllib.request.build_opener(cj)

    # Step 1: GET the search page to obtain the CSRF token / cookies.
    req = urllib.request.Request(
        SENATE_SEARCH_URL,
        headers={
            "User-Agent": _user_agent(),
            "Accept": "text/html",
        },
    )
    try:
        with opener.open(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  [WARN] Senate eFD agreement page failed: {exc}", file=sys.stderr)
        return opener

    # Extract csrfmiddlewaretoken.
    csrf_match = re.search(
        r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']',
        body,
    )
    csrf_token = csrf_match.group(1) if csrf_match else ""

    # Step 2: POST the agreement acceptance.
    post_data = urllib.parse.urlencode({
        "csrfmiddlewaretoken": csrf_token,
        "prohibition_agreement": "1",
    }).encode("utf-8")
    req2 = urllib.request.Request(
        SENATE_SEARCH_URL,
        data=post_data,
        headers={
            "User-Agent": _user_agent(),
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": SENATE_SEARCH_URL,
            "Accept": "text/html",
        },
    )
    try:
        with opener.open(req2, timeout=30) as resp:
            _ = resp.read()
    except Exception as exc:
        print(f"  [WARN] Senate eFD agreement POST failed: {exc}", file=sys.stderr)

    rate_limit()
    return opener


def fetch_senate_trades(opener: urllib.request.OpenerDirector) -> list[dict[str, str]]:
    """Fetch periodic transaction reports from the Senate eFD search."""

    # The Senate eFD search endpoint accepts JSON POST for searching.
    # Periodic Transaction Reports (PTR) are report type "11".
    # We request reports from the last LOOKBACK_DAYS.
    start_date = (dt.datetime.now() - dt.timedelta(days=LOOKBACK_DAYS)).strftime("%m/%d/%Y")
    end_date = dt.datetime.now().strftime("%m/%d/%Y")

    payload = json.dumps({
        "start": "1",
        "length": "100",
        "report_types": "[11]",
        "submitted_start_date": start_date,
        "submitted_end_date": end_date,
        "senator": "",
        "candidate": "",
        "state": "",
        "senator_type": "",
    }).encode("utf-8")

    req = urllib.request.Request(
        SENATE_SEARCH_POST_URL,
        data=payload,
        headers={
            "User-Agent": _user_agent(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Referer": SENATE_SEARCH_URL,
            "X-Requested-With": "XMLHttpRequest",
        },
    )

    reports: list[dict[str, str]] = []
    try:
        with opener.open(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        # The response has {"data": [[...], ...], ...} with each row being
        # [first_name, last_name, report_title_link, date_received].
        for row in data.get("data", []):
            if len(row) < 4:
                continue
            first = _strip_html(str(row[0]))
            last = _strip_html(str(row[1]))
            member = f"{first} {last}".strip()
            report_link_html = str(row[2])
            disclosure_date = _strip_html(str(row[3]))

            # Extract the report URL from the HTML anchor tag.
            link_match = re.search(r'href=["\']([^"\']+)["\']', report_link_html)
            if not link_match:
                continue
            report_path = link_match.group(1)
            if not report_path.startswith("http"):
                report_path = SENATE_REPORT_BASE + report_path

            reports.append({
                "member_name": member,
                "report_url": report_path,
                "disclosure_date": parse_date_flexible(disclosure_date),
            })
    except Exception as exc:
        # efdsearch.senate.gov has changed its search endpoint multiple times
        # and now returns 404/503 to unauthenticated DataTables POSTs. QuiverQuant
        # covers Senate PTRs for our purposes, so this failure is informational.
        print(f"  [INFO] Senate eFD unavailable ({exc}); relying on QuiverQuant", file=sys.stderr)

    return reports


def _strip_html(s: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", s).strip()


def parse_senate_report(
    opener: urllib.request.OpenerDirector,
    report_url: str,
    member_name: str,
    disclosure_date: str,
) -> list[dict[str, str]]:
    """Fetch and parse an individual Senate PTR report for transactions."""
    trades: list[dict[str, str]] = []
    try:
        req = urllib.request.Request(
            report_url,
            headers={
                "User-Agent": _user_agent(),
                "Accept": "text/html",
                "Referer": SENATE_SEARCH_URL,
            },
        )
        with opener.open(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  [WARN] Failed to fetch report {report_url}: {exc}", file=sys.stderr)
        return trades

    parser = SenateReportParser()
    try:
        parser.feed(body)
    except Exception:
        pass

    # Try to extract senator name from the page if we have a better version.
    page_name = parser._senator_name.strip()
    if page_name and len(page_name) > len(member_name):
        member_name = page_name

    # The PTR table typically has columns:
    # [#, Transaction Date, Owner, Ticker, Asset Name, Asset Type, Transaction Type, Amount, Comment]
    # Column order varies, so we do best-effort matching on header row.
    if not parser._rows:
        return trades

    # Find header row.
    header_idx = -1
    col_map: dict[str, int] = {}
    for i, row in enumerate(parser._rows):
        lower_cells = [c.lower().strip() for c in row]
        # Look for key column headers.
        has_transaction = any("transaction" in c for c in lower_cells)
        has_asset = any("asset" in c or "name" in c for c in lower_cells)
        if has_transaction and has_asset:
            header_idx = i
            for j, cell in enumerate(lower_cells):
                if "transaction date" in cell or ("date" in cell and "transaction" in cell):
                    col_map["txn_date"] = j
                elif "transaction type" in cell or "type" == cell or "transaction" in cell and "type" in cell:
                    if "date" not in cell:
                        col_map["txn_type"] = j
                elif "ticker" in cell or "symbol" in cell:
                    col_map["ticker"] = j
                elif "asset" in cell and ("name" in cell or "description" in cell):
                    col_map["asset"] = j
                elif cell in ("asset", "name"):
                    col_map.setdefault("asset", j)
                elif "amount" in cell:
                    col_map["amount"] = j
                elif "owner" in cell:
                    col_map["owner"] = j
                elif "comment" in cell:
                    col_map["comment"] = j
            break

    if header_idx < 0:
        # Fallback: try to parse rows by position (common 9-column layout).
        for row in parser._rows:
            if len(row) >= 6:
                trade = _build_trade_from_positional(row, member_name, disclosure_date)
                if trade:
                    trades.append(trade)
        return trades

    # Parse data rows.
    for row in parser._rows[header_idx + 1:]:
        if not row or all(not c.strip() for c in row):
            continue

        asset_desc = _safe_get(row, col_map.get("asset", -1))
        raw_ticker = _safe_get(row, col_map.get("ticker", -1))
        txn_type = _safe_get(row, col_map.get("txn_type", -1))
        txn_date = _safe_get(row, col_map.get("txn_date", -1))
        amount = _safe_get(row, col_map.get("amount", -1))

        ticker = raw_ticker.strip().upper().replace("--", "").replace("-", "").strip()
        if not ticker or ticker in ("N/A", "NA", "NONE", "--"):
            ticker = extract_ticker(asset_desc)

        if not ticker:
            continue

        trades.append({
            "member_name": member_name,
            "party": "",
            "state": "",
            "ticker": ticker,
            "transaction_type": normalize_transaction_type(txn_type),
            "amount_range": amount.strip(),
            "transaction_date": parse_date_flexible(txn_date),
            "disclosure_date": disclosure_date,
            "asset_description": asset_desc.strip(),
        })

    return trades


def _safe_get(row: list[str], idx: int) -> str:
    if idx < 0 or idx >= len(row):
        return ""
    return row[idx]


def _build_trade_from_positional(
    row: list[str],
    member_name: str,
    disclosure_date: str,
) -> dict[str, str] | None:
    """Attempt to build a trade from positional columns in a 9-column PTR table."""
    # Typical: [#, txn_date, owner, ticker, asset_name, asset_type, txn_type, amount, comment]
    if len(row) < 7:
        return None

    # Heuristic: skip if first cell is a header-looking word.
    if row[0].strip().lower() in ("", "#", "transaction", "date"):
        return None

    ticker = row[3].strip().upper().replace("--", "").replace("-", "").strip()
    asset_desc = row[4].strip() if len(row) > 4 else ""
    txn_type = row[6].strip() if len(row) > 6 else ""
    txn_date = row[1].strip() if len(row) > 1 else ""
    amount = row[7].strip() if len(row) > 7 else ""

    if not ticker or ticker in ("N/A", "NA", "NONE"):
        ticker = extract_ticker(asset_desc)

    if not ticker:
        return None

    return {
        "member_name": member_name,
        "party": "",
        "state": "",
        "ticker": ticker,
        "transaction_type": normalize_transaction_type(txn_type),
        "amount_range": amount,
        "transaction_date": parse_date_flexible(txn_date),
        "disclosure_date": disclosure_date,
        "asset_description": asset_desc,
    }


# ---------------------------------------------------------------------------
# Source 2: House clerk financial disclosures
# ---------------------------------------------------------------------------

HOUSE_FD_BASE = "https://disclosures-clerk.house.gov"
HOUSE_FD_SEARCH = f"{HOUSE_FD_BASE}/public_disc/ptr-pdfs/"


def fetch_house_trades_index() -> list[dict[str, str]]:
    """Fetch the House periodic transaction report index.

    The House clerk publishes a yearly XML/ZIP index of financial disclosures.
    We fetch the current year's index and parse it for periodic transaction reports.
    """
    year = dt.datetime.now().year
    index_url = f"{HOUSE_FD_BASE}/public_disc/financial-pdfs/{year}FD.xml"

    trades: list[dict[str, str]] = []
    try:
        body = http_get(index_url, headers={"Accept": "application/xml, text/xml"})
        text = body.decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  [WARN] House FD index fetch failed: {exc}", file=sys.stderr)
        return trades

    rate_limit()

    # Parse the XML index for Periodic Transaction Reports.
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text)
    except Exception as exc:
        print(f"  [WARN] House FD XML parse failed: {exc}", file=sys.stderr)
        return trades

    cutoff = dt.datetime.now() - dt.timedelta(days=LOOKBACK_DAYS)

    for member_elem in root.iter("Member"):
        prefix = member_elem.findtext("Prefix", "").strip()
        first = member_elem.findtext("First", "").strip()
        last = member_elem.findtext("Last", "").strip()
        suffix = member_elem.findtext("Suffix", "").strip()
        filing_type = member_elem.findtext("FilingType", "").strip()
        filing_date = member_elem.findtext("FilingDate", "").strip()
        state_district = member_elem.findtext("StateDst", "").strip()
        doc_id = member_elem.findtext("DocID", "").strip()

        # Only interested in Periodic Transaction Reports.
        if "P" not in filing_type.upper():
            continue

        # Check date.
        try:
            fd = dt.datetime.strptime(filing_date, "%m/%d/%Y")
            if fd < cutoff:
                continue
        except (ValueError, TypeError):
            pass

        member_name = " ".join(p for p in [prefix, first, last, suffix] if p)
        state = state_district[:2] if state_district else ""

        trades.append({
            "member_name": member_name,
            "party": "",
            "state": state,
            "doc_id": doc_id,
            "filing_year": filing_date[-4:] if filing_date else "",
            "disclosure_date": parse_date_flexible(filing_date),
        })

    return trades


# ---------------------------------------------------------------------------
# Source 2b: House PTR PDF parsing (pdftotext)
# ---------------------------------------------------------------------------

# House PTR PDFs word-wrap transactions across 2–3 lines after pdftotext -layout.
# Strategy: scan for transaction-shaped lines (type + two dates + amount), then
# find the matching ticker in a short context window around that line.

# Match a transaction code + transaction date + notification date + amount-low
# anywhere inside a single line.
_PTR_TXN_LINE_RE = re.compile(
    r"(?<![A-Za-z])"
    r"(?P<txn>S\s*\(partial\)|P\s*\(partial\)|P|S|E)\s+"
    r"(?P<txn_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<notif_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<amount>\$[\d,]+(?:\s*-\s*\$?[\d,]+)?\+?)"
)

# Match "(TICKER)" — the asset type in brackets is searched separately, since
# pdftotext -layout sometimes splits "(AAPL)" and "[ST]" onto different lines.
_PTR_TICKER_ONLY_RE = re.compile(
    r"\((?P<ticker>[A-Z][A-Z0-9.\-]{0,9})\)"
)

# Match "[ASSETTYPE]" for equity-like instruments only.
_PTR_ASSET_TYPE_RE = re.compile(
    r"\[(?P<asset_type>ST|OP|OT|ET|PS|RS)\]"
)

# Amount-high continuation on a wrapped line: "$100,000" standalone after a dash.
_PTR_AMOUNT_HIGH_RE = re.compile(r"\$([\d,]+)(?!\s*-)")

# Asset-type codes worth surfacing: stock, options, other equity, partnership,
# restricted stock. Bonds, mutual funds, hedge funds, corporate securities,
# government securities all lack a tradable equity ticker.
_PTR_EQUITY_ASSET_TYPES = {"ST", "OP", "OT", "ET", "PS", "RS"}

# Tickers that look valid syntactically but are almost always noise from the
# PDF (e.g. a bracket tag mis-matched as a ticker, or a column label).
_PTR_TICKER_BLOCKLIST = {"N", "P", "S", "E", "ST", "OP", "OT", "ET", "MF", "BD", "NA", "JT", "SP", "DC"}


def _pdftotext_available() -> bool:
    """Return True if the ``pdftotext`` binary (poppler-utils) is on PATH."""
    import shutil
    return shutil.which("pdftotext") is not None


def _pdfminer_available() -> bool:
    """Return True if pdfminer.six is importable — pure-Python PDF fallback."""
    try:
        import pdfminer.high_level  # noqa: F401
        return True
    except ImportError:
        return False


def _pdf_to_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF. Prefer pdftotext -layout (fast), fall back to
    pdfminer.six (pure Python, slower but dependency-free install). Both
    preserve horizontal whitespace well enough for _PTR_TXN_LINE_RE.
    """
    if _pdftotext_available():
        import subprocess
        proc = subprocess.run(
            ["pdftotext", "-layout", "-", "-"],
            input=pdf_bytes,
            capture_output=True,
            timeout=30,
            check=False,
        )
        return proc.stdout.decode("utf-8", errors="replace")
    if _pdfminer_available():
        import io
        from pdfminer.high_level import extract_text
        from pdfminer.layout import LAParams
        # laparams tuned to keep column alignment close to pdftotext -layout.
        laparams = LAParams(char_margin=2.0, line_margin=0.3, word_margin=0.1)
        return extract_text(io.BytesIO(pdf_bytes), laparams=laparams)
    return ""


def fetch_house_ptr_pdf(doc_id: str, year: int) -> bytes | None:
    """Fetch a House PTR PDF by doc_id.

    Tries the given year first, then falls back one year back — filings from
    January can be indexed with a disclosure_date in the previous year.
    """
    candidates = [year]
    if year > 2020:
        candidates.append(year - 1)
    for y in candidates:
        url = f"{HOUSE_FD_BASE}/public_disc/ptr-pdfs/{y}/{doc_id}.pdf"
        try:
            return http_get(url, headers={"Accept": "application/pdf"}, retries=1, timeout=20)
        except Exception:
            continue
    return None


def _normalize_ptr_txn_type(raw: str) -> str:
    """Map House PTR transaction codes into the canonical buy/sell/exchange vocab."""
    raw = re.sub(r"\s+", " ", raw).strip().upper()
    if raw.startswith("P"):
        return "buy"
    if raw.startswith("S"):
        return "sell"
    if raw == "E":
        return "exchange"
    return raw.lower()


def _complete_ptr_amount(raw_amount: str, following_lines: list[str]) -> str:
    """House PTR amounts wrap across lines: "$50,001 -" on line 1, "$100,000" on line 2.

    If the first-line capture is missing its upper bound, scan the next 1–2
    lines for a trailing ``$<digits>[+]`` and splice the range together.
    """
    amount = re.sub(r"\s+", " ", raw_amount).strip()
    if re.search(r"\$[\d,]+\s*-\s*\$[\d,]+", amount):
        return amount

    lower = amount.rstrip().rstrip("-").rstrip()
    for line in following_lines[:2]:
        m = re.search(r"\$([\d,]+)(\+?)\s*$", line.rstrip())
        if not m:
            continue
        upper = f"${m.group(1)}{m.group(2)}"
        if upper.rstrip("+") == lower:
            # Same amount on both lines (e.g. amount wasn't split); skip.
            continue
        return f"{lower} - {upper}"
    return amount


def parse_house_ptr_text(text: str) -> list[dict[str, str]]:
    """Extract individual equity transactions from a House PTR PDF text block.

    Walks the text line-by-line searching for transaction signatures
    ``<TXN> <DATE> <DATE> <AMOUNT>``. For each match, inspects a short
    context window (2 lines before + this line + 2 lines after) to locate
    the nearest ``(TICKER) [ASSETTYPE]`` marker, since pdftotext -layout
    splits long asset names across multiple lines. Skips non-equity asset
    types (bonds, municipal debt, mutual funds, hedge funds).
    """
    transactions: list[dict[str, str]] = []
    if not text:
        return transactions

    lines = text.splitlines()
    seen_keys: set[tuple[str, str, str]] = set()

    for idx, line in enumerate(lines):
        txn_match = _PTR_TXN_LINE_RE.search(line)
        if not txn_match:
            continue

        # Window = the txn line + up to two following lines. Do NOT include
        # previous lines: wrapped tickers from earlier records live there and
        # would produce false associations.
        window_lines = lines[idx : min(len(lines), idx + 3)]
        window = "\n".join(window_lines)

        # Asset type must be present in the window and must be an equity code.
        asset_type_match = _PTR_ASSET_TYPE_RE.search(window)
        if not asset_type_match or asset_type_match.group("asset_type") not in _PTR_EQUITY_ASSET_TYPES:
            continue

        # Use the first ticker candidate that passes the blocklist.
        ticker = ""
        for tm in _PTR_TICKER_ONLY_RE.finditer(window):
            candidate = tm.group("ticker").strip().upper()
            if candidate in _PTR_TICKER_BLOCKLIST:
                continue
            if not any(c.isalpha() for c in candidate) or len(candidate) > 6:
                continue
            ticker = candidate
            break
        if not ticker:
            continue

        txn_type = _normalize_ptr_txn_type(txn_match.group("txn"))
        txn_date = parse_date_flexible(txn_match.group("txn_date"))
        amount = _complete_ptr_amount(
            txn_match.group("amount"),
            lines[idx + 1 : idx + 3],
        )

        # Extract a clean asset description from the line holding the ticker.
        asset_desc = ""
        asset_line_idx = None
        for off in range(-2, 3):
            j = idx + off
            if 0 <= j < len(lines) and f"({ticker})" in lines[j]:
                asset_line_idx = j
                break
        if asset_line_idx is not None:
            raw = lines[asset_line_idx].split(f"({ticker})", 1)[0]
            raw = re.sub(r"^\s*\[?(?:SP|DC|JT|Owner)\]?\s*", "", raw)
            # Append the line before if it looks like a continuation (no txn).
            if asset_line_idx > 0 and not _PTR_TXN_LINE_RE.search(lines[asset_line_idx - 1]):
                prior = lines[asset_line_idx - 1].strip()
                if prior and "$" not in prior and "/202" not in prior:
                    raw = (prior + " " + raw).strip()
            asset_desc = re.sub(r"\s+", " ", raw).strip(" ,-")

        key = (ticker, txn_date, txn_type)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        transactions.append({
            "ticker": ticker,
            "transaction_type": txn_type,
            "amount_range": amount,
            "transaction_date": txn_date,
            "asset_description": asset_desc,
        })

    return transactions


def parse_house_ptrs(reports: list[dict[str, str]]) -> list[dict[str, str]]:
    """Fetch each House PTR PDF and expand into individual trade rows.

    Falls back to a single stub row per PDF that cannot be retrieved or parsed
    (pdftotext missing, network failure, or zero regex matches) so the count of
    pending-parse filings stays visible to the UI.
    """
    has_pdftotext = _pdftotext_available()
    has_pdfminer = _pdfminer_available()
    can_parse_pdfs = has_pdftotext or has_pdfminer
    if not can_parse_pdfs:
        print("  [WARN] Neither pdftotext nor pdfminer available — House PTRs emitted as metadata stubs only", file=sys.stderr)
    elif not has_pdftotext:
        print("  [INFO] pdftotext missing, using pdfminer.six fallback (slower)", file=sys.stderr)

    rows: list[dict[str, str]] = []
    parsed_pdfs = 0
    stub_pdfs = 0
    txn_total = 0
    current_year = dt.datetime.now().year

    for report in reports:
        doc_id = report.get("doc_id", "").strip()
        if not doc_id:
            continue

        disclosure = report.get("disclosure_date", "")
        filing_year = report.get("filing_year", "") or disclosure[:4]
        try:
            year_guess = int(filing_year) if filing_year else current_year
        except ValueError:
            year_guess = current_year

        # Strip the "Hon." honorific so House PDF names match Quiver's format
        # (e.g. "Hon. Josh Gottheimer" → "Josh Gottheimer") and dedupe across
        # sources.
        member = report.get("member_name", "")
        member = re.sub(r"^(Hon\.|Representative|Rep\.|Mr\.|Ms\.|Mrs\.|Dr\.)\s+", "", member).strip()

        common = {
            "member_name": member,
            "party": report.get("party", ""),
            "state": report.get("state", ""),
            "chamber": "House",
            "disclosure_date": disclosure,
        }

        def _emit_stub(note: str) -> None:
            nonlocal stub_pdfs
            rows.append({
                **common,
                "ticker": "",
                "transaction_type": "",
                "amount_range": "",
                "transaction_date": "",
                "asset_description": f"[House PTR Filing - doc_id: {doc_id}]{note}",
            })
            stub_pdfs += 1

        if not can_parse_pdfs:
            _emit_stub("")
            continue

        pdf_bytes = fetch_house_ptr_pdf(doc_id, year_guess)
        rate_limit()
        if not pdf_bytes:
            _emit_stub(" (PDF unavailable)")
            continue

        try:
            text = _pdf_to_text(pdf_bytes)
        except Exception as exc:
            print(f"    [WARN] pdf extract failed for doc_id={doc_id}: {exc}", file=sys.stderr)
            _emit_stub(" (pdf extract error)")
            continue

        txns = parse_house_ptr_text(text)
        if not txns:
            _emit_stub(" (no transactions parsed)")
            continue

        for txn in txns:
            rows.append({**common, **txn})
        parsed_pdfs += 1
        txn_total += len(txns)

    print(
        f"  House PTR parse: {parsed_pdfs} PDFs parsed → {txn_total} transactions"
        f"; {stub_pdfs} stubs remaining",
        file=sys.stderr,
    )
    return rows


# ---------------------------------------------------------------------------
# Source 3: Capitol Trades public RSS / QuiverQuant-style JSON
# ---------------------------------------------------------------------------

CAPITOL_TRADES_RSS_URL = "https://www.capitoltrades.com/trades?page=1&pageSize=96"
QUIVER_PUBLIC_URL = "https://api.quiverquant.com/beta/live/congresstrading"


class CapitolTradesHTMLParser(HTMLParser):
    """Parse the Capitol Trades HTML page for trade data.

    Capitol Trades renders trade data in an HTML table or card layout.
    We extract as much structure as possible.
    """

    def __init__(self) -> None:
        super().__init__()
        self.trades: list[dict[str, str]] = []
        self._in_data_attr = False
        self._json_blocks: list[str] = []
        self._current_tag = ""
        self._script_text = ""
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._current_tag = tag
        if tag == "script":
            self._in_script = True
            self._script_text = ""
        # Check for data attributes with JSON.
        attr_dict = dict(attrs)
        for key, val in attr_dict.items():
            if val and "trade" in key.lower() and "{" in val:
                try:
                    self._json_blocks.append(val)
                except Exception:
                    pass

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False
            if self._script_text and "trade" in self._script_text.lower():
                self._json_blocks.append(self._script_text)

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_text += data


def fetch_capitol_trades_html() -> list[dict[str, str]]:
    """Attempt to scrape Capitol Trades for recent congressional trades."""
    trades: list[dict[str, str]] = []
    try:
        body = http_get(
            CAPITOL_TRADES_RSS_URL,
            headers={"Accept": "text/html"},
            retries=1,
            timeout=20,
        )
        text = body.decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  [INFO] Capitol Trades unavailable ({exc}); relying on QuiverQuant", file=sys.stderr)
        return trades

    parser = CapitolTradesHTMLParser()
    try:
        parser.feed(text)
    except Exception:
        pass

    # Try to extract JSON trade data from script blocks or data attributes.
    for block in parser._json_blocks:
        try:
            extracted = _extract_trades_from_json(block)
            trades.extend(extracted)
        except Exception:
            continue

    return trades


def _extract_trades_from_json(raw: str) -> list[dict[str, str]]:
    """Best-effort extraction from embedded JSON structures."""
    trades: list[dict[str, str]] = []

    # Try to find JSON arrays in the text.
    for match in re.finditer(r'\[(?:\s*\{[^]]*\}\s*,?\s*)+\]', raw):
        try:
            items = json.loads(match.group(0))
        except json.JSONDecodeError:
            continue
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            trade = _normalize_trade_json(item)
            if trade:
                trades.append(trade)

    # Try the whole thing as JSON.
    if not trades:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        trade = _normalize_trade_json(item)
                        if trade:
                            trades.append(trade)
            elif isinstance(data, dict):
                for key in ("trades", "data", "results", "items"):
                    if key in data and isinstance(data[key], list):
                        for item in data[key]:
                            if isinstance(item, dict):
                                trade = _normalize_trade_json(item)
                                if trade:
                                    trades.append(trade)
        except json.JSONDecodeError:
            pass

    return trades


def _normalize_trade_json(item: dict[str, Any]) -> dict[str, str] | None:
    """Normalize a JSON trade object from Capitol Trades or QuiverQuant."""
    # Flexible key mapping.
    def _get(keys: list[str]) -> str:
        for k in keys:
            v = item.get(k) or item.get(k.lower()) or item.get(k.upper())
            if v is not None:
                return str(v).strip()
        return ""

    ticker = _get(["ticker", "Ticker", "symbol", "Symbol", "asset_ticker"])
    if not ticker:
        return None

    member = _get(["Representative", "politician", "Politician", "member", "name", "senator", "representative",
                    "member_name", "ReportingIndividual"])
    txn_type = _get(["Transaction", "type", "transaction_type", "txn_type", "TransactionType", "trade_type"])
    amount = _get(["Range", "amount", "Amount", "range", "amount_range"])
    txn_date = _get(["transaction_date", "txn_date", "date", "TransactionDate", "trade_date"])
    disc_date = _get(["disclosure_date", "filed_date", "FilingDate", "report_date"])
    party = _get(["party", "Party"])
    state = _get(["state", "State", "district"])
    asset_desc = _get(["asset_description", "Description", "description", "asset", "AssetDescription", "issuer"])
    chamber = _get(["House", "chamber", "Chamber"])

    return {
        "member_name": member,
        "party": party[:1].upper() if party else "",
        "state": state[:2].upper() if state else "",
        "chamber": "House" if chamber.lower() in ("house", "representatives") else "Senate" if chamber.lower() == "senate" else chamber.capitalize() if chamber else "",
        "ticker": ticker.upper(),
        "transaction_type": normalize_transaction_type(txn_type),
        "amount_range": amount,
        "transaction_date": parse_date_flexible(txn_date),
        "disclosure_date": parse_date_flexible(disc_date),
        "asset_description": asset_desc,
    }


# ---------------------------------------------------------------------------
# Source 4: QuiverQuant public JSON endpoint
# ---------------------------------------------------------------------------

def fetch_quiver_trades() -> list[dict[str, str]]:
    """Attempt to fetch from QuiverQuant's public congress trading endpoint."""
    trades: list[dict[str, str]] = []
    try:
        body = http_get(
            QUIVER_PUBLIC_URL,
            headers={"Accept": "application/json"},
            retries=1,
            timeout=15,
        )
        items = json.loads(body.decode("utf-8", errors="replace"))
        if isinstance(items, list):
            for item in items:
                trade = _normalize_trade_json(item)
                if trade:
                    trades.append(trade)
    except Exception as exc:
        print(f"  [INFO] QuiverQuant fetch failed (non-critical): {exc}", file=sys.stderr)
    return trades


# ---------------------------------------------------------------------------
# Source 5: Senate eFD direct search via API-style JSON endpoint
# ---------------------------------------------------------------------------

def fetch_senate_efdsearch() -> list[dict[str, str]]:
    """Fetch trades from Senate eFD search with agreement acceptance flow.

    This is the authoritative source for Senate stock trades.
    """
    print("  [1/3] Accepting Senate eFD agreement...", file=sys.stderr)
    opener = _accept_senate_agreement()
    rate_limit()

    print("  [2/3] Searching Senate eFD for periodic transaction reports...", file=sys.stderr)
    reports = fetch_senate_trades(opener)
    print(f"  Found {len(reports)} Senate PTR reports", file=sys.stderr)

    all_trades: list[dict[str, str]] = []

    # Limit the number of individual reports we fetch to avoid hammering the server.
    max_reports = min(len(reports), 25)
    print(f"  [3/3] Parsing up to {max_reports} Senate reports...", file=sys.stderr)

    for i, report in enumerate(reports[:max_reports]):
        rate_limit()
        trades = parse_senate_report(
            opener,
            report["report_url"],
            report["member_name"],
            report["disclosure_date"],
        )
        if trades:
            print(
                f"    [{i + 1}/{max_reports}] {report['member_name']}: {len(trades)} transactions",
                file=sys.stderr,
            )
        all_trades.extend(trades)

    return all_trades


# ---------------------------------------------------------------------------
# Cross-reference with SEC catalyst universe
# ---------------------------------------------------------------------------

def load_ranked_universe() -> dict[str, dict[str, str]]:
    """Load tickers from sec_catalyst_ranked.csv into a lookup dict."""
    universe: dict[str, dict[str, str]] = {}
    if not RANKED_CSV.exists():
        print(f"  [WARN] {RANKED_CSV.name} not found — overlap analysis will be empty", file=sys.stderr)
        return universe

    with open(RANKED_CSV, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ticker = row.get("ticker", "").strip().upper()
            if ticker:
                universe[ticker] = row

    return universe


def compute_overlap(
    trades: list[dict[str, str]],
    universe: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    """Find tickers present in both congressional trades and SEC catalyst filings."""
    overlap: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for trade in trades:
        ticker = trade.get("ticker", "").upper()
        if not ticker or ticker not in universe:
            continue

        # Deduplicate on (ticker, member, txn_date).
        key = (ticker, trade.get("member_name", ""), trade.get("transaction_date", ""))
        if key in seen:
            continue
        seen.add(key)

        catalyst = universe[ticker]
        row = {
            "ticker": ticker,
            "member_name": trade.get("member_name", ""),
            "party": trade.get("party", ""),
            "state": trade.get("state", ""),
            "transaction_type": trade.get("transaction_type", ""),
            "amount_range": trade.get("amount_range", ""),
            "transaction_date": trade.get("transaction_date", ""),
            "disclosure_date": trade.get("disclosure_date", ""),
            "asset_description": trade.get("asset_description", ""),
            "priority_score": catalyst.get("priority_score", ""),
            "momentum_score": catalyst.get("momentum_score", ""),
            "quality_score": catalyst.get("quality_score", ""),
            "form": catalyst.get("form", ""),
            "updated_utc": catalyst.get("updated_utc", ""),
        }
        overlap.append(row)

    # Sort by priority score descending.
    overlap.sort(key=lambda r: int(r.get("priority_score") or 0), reverse=True)
    return overlap


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

# Static fallback for House members who only appear in Clerk PDFs (no Quiver
# coverage of their trades). Keyed by lowercased "<first> <last>" after
# honorific/suffix stripping. Party: D/R/I. State: USPS code.
_HOUSE_MEMBER_FALLBACK: dict[str, tuple[str, str]] = {
    # 2026-04-24 expansion: 119th Congress members who have at least one
    # historical PTR filing. Keyed by normalized "first last" (lowercase,
    # stripped honorific/suffix). Party: D/R/I. State: USPS code.
    "rick larsen": ("D", "WA"), "ed case": ("D", "HI"),
    "josh gottheimer": ("D", "NJ"), "mark green": ("R", "TN"),
    "dan crenshaw": ("R", "TX"), "scott franklin": ("R", "FL"),
    "greg steube": ("R", "FL"), "kevin hern": ("R", "OK"),
    "marjorie taylor greene": ("R", "GA"), "kathy castor": ("D", "FL"),
    "ro khanna": ("D", "CA"), "lois frankel": ("D", "FL"),
    "michael guest": ("R", "MS"), "nancy pelosi": ("D", "CA"),
    "john boozman": ("R", "AR"), "tommy tuberville": ("R", "AL"),
    "shelley moore capito": ("R", "WV"), "ron wyden": ("D", "OR"),
    "susan collins": ("R", "ME"), "thomas carper": ("D", "DE"),
    "gary peters": ("D", "MI"), "virginia foxx": ("R", "NC"),
    "michael mccaul": ("R", "TX"), "earl blumenauer": ("D", "OR"),
    "debbie wasserman schultz": ("D", "FL"), "lisa blunt rochester": ("D", "DE"),
    "kim schrier": ("D", "WA"), "john curtis": ("R", "UT"),
    "pat fallon": ("R", "TX"), "rob wittman": ("R", "VA"),
    "garret graves": ("R", "LA"), "john rutherford": ("R", "FL"),
    "robert bresnahan": ("R", "PA"), "bruce westerman": ("R", "AR"),
    "andrew garbarino": ("R", "NY"), "cleo fields": ("D", "LA"),
    "shri thanedar": ("D", "MI"), "marlin stutzman": ("R", "IN"),
    "jefferson shreve": ("R", "IN"), "julie johnson": ("D", "TX"),
    "julie fedorchak": ("R", "ND"), "sarah mcbride": ("D", "DE"),
    "sheri biggs": ("R", "SC"), "suhas subramanyam": ("D", "VA"),
    # Frequent PTR filers (House, alphabetical)
    "mark alford": ("R", "MO"), "richard allen": ("R", "GA"),
    "jake auchincloss": ("D", "MA"), "don beyer": ("D", "VA"),
    "ami bera": ("D", "CA"), "donald sternoff beyer": ("D", "VA"),
    "suzanne bonamici": ("D", "OR"), "lou correa": ("D", "CA"),
    "jim costa": ("D", "CA"), "angie craig": ("D", "MN"),
    "henry cuellar": ("D", "TX"), "chuy garcia": ("D", "IL"),
    "mike garcia": ("R", "CA"), "sylvia garcia": ("D", "TX"),
    "chris gibson": ("R", "NY"), "dean phillips": ("D", "MN"),
    "mike quigley": ("D", "IL"), "kathleen rice": ("D", "NY"),
    "harley rouda": ("D", "CA"), "chip roy": ("R", "TX"),
    "steven horsford": ("D", "NV"), "james clyburn": ("D", "SC"),
    "katherine clark": ("D", "MA"), "hakeem jeffries": ("D", "NY"),
    "tom emmer": ("R", "MN"), "steve scalise": ("R", "LA"),
    "mike johnson": ("R", "LA"), "byron donalds": ("R", "FL"),
    "anna paulina luna": ("R", "FL"), "victoria spartz": ("R", "IN"),
    "nicole malliotakis": ("R", "NY"), "mike lawler": ("R", "NY"),
    "anthony desposito": ("R", "NY"), "marc molinaro": ("R", "NY"),
    "claudia tenney": ("R", "NY"), "brandon williams": ("R", "NY"),
    "nick langworthy": ("R", "NY"), "joe morelle": ("D", "NY"),
    "jerrold nadler": ("D", "NY"), "yvette clarke": ("D", "NY"),
    "gregory meeks": ("D", "NY"), "grace meng": ("D", "NY"),
    "nydia velazquez": ("D", "NY"), "ritchie torres": ("D", "NY"),
    "adriano espaillat": ("D", "NY"), "alexandria ocasio-cortez": ("D", "NY"),
    "pat ryan": ("D", "NY"), "tim ryan": ("D", "OH"),
    "marcy kaptur": ("D", "OH"), "shontel brown": ("D", "OH"),
    "joyce beatty": ("D", "OH"), "greg landsman": ("D", "OH"),
    "emilia sykes": ("D", "OH"), "max miller": ("R", "OH"),
    "dave joyce": ("R", "OH"), "michael turner": ("R", "OH"),
    "bill johnson": ("R", "OH"), "jim jordan": ("R", "OH"),
    "warren davidson": ("R", "OH"), "mike carey": ("R", "OH"),
    "bob gibbs": ("R", "OH"), "troy balderson": ("R", "OH"),
    "brad wenstrup": ("R", "OH"), "steve chabot": ("R", "OH"),
    "brad finstad": ("R", "MN"), "michelle fischbach": ("R", "MN"),
    "pete stauber": ("R", "MN"), "tom tiffany": ("R", "WI"),
    "derrick van orden": ("R", "WI"), "bryan steil": ("R", "WI"),
    "scott fitzgerald": ("R", "WI"), "glenn grothman": ("R", "WI"),
    "mike gallagher": ("R", "WI"), "gwen moore": ("D", "WI"),
    "mark pocan": ("D", "WI"), "ron kind": ("D", "WI"),
    "tammy baldwin": ("D", "WI"), "rob portman": ("R", "OH"),
    "sherrod brown": ("D", "OH"), "jd vance": ("R", "OH"),
    "bernie moreno": ("R", "OH"), "amy klobuchar": ("D", "MN"),
    "tina smith": ("D", "MN"), "ted cruz": ("R", "TX"),
    "john cornyn": ("R", "TX"), "marco rubio": ("R", "FL"),
    "rick scott": ("R", "FL"), "bill hagerty": ("R", "TN"),
    "cynthia lummis": ("R", "WY"), "john barrasso": ("R", "WY"),
    "steve daines": ("R", "MT"), "jon tester": ("D", "MT"),
    "mitch mcconnell": ("R", "KY"), "rand paul": ("R", "KY"),
    "lindsey graham": ("R", "SC"), "tim scott": ("R", "SC"),
    "ted budd": ("R", "NC"), "thom tillis": ("R", "NC"),
    "markwayne mullin": ("R", "OK"), "james lankford": ("R", "OK"),
    "mike crapo": ("R", "ID"), "jim risch": ("R", "ID"),
    "mike lee": ("R", "UT"), "mitt romney": ("R", "UT"),
    "todd young": ("R", "IN"), "mike braun": ("R", "IN"),
    "jim banks": ("R", "IN"), "eric schmitt": ("R", "MO"),
    "josh hawley": ("R", "MO"), "tom cotton": ("R", "AR"),
    "roger marshall": ("R", "KS"), "jerry moran": ("R", "KS"),
    "roger wicker": ("R", "MS"), "cindy hyde-smith": ("R", "MS"),
    "bill cassidy": ("R", "LA"), "john kennedy": ("R", "LA"),
    "chuck grassley": ("R", "IA"), "joni ernst": ("R", "IA"),
    "deb fischer": ("R", "NE"), "pete ricketts": ("R", "NE"),
    "john thune": ("R", "SD"), "mike rounds": ("R", "SD"),
    "john hoeven": ("R", "ND"), "kevin cramer": ("R", "ND"),
    "dan sullivan": ("R", "AK"), "lisa murkowski": ("R", "AK"),
    "jim inhofe": ("R", "OK"), "steve kornacki": ("R", "OK"),
    "cory booker": ("D", "NJ"), "andy kim": ("D", "NJ"),
    "bob menendez": ("D", "NJ"), "kirsten gillibrand": ("D", "NY"),
    "chuck schumer": ("D", "NY"), "elizabeth warren": ("D", "MA"),
    "ed markey": ("D", "MA"), "chris van hollen": ("D", "MD"),
    "ben cardin": ("D", "MD"), "angela alsobrooks": ("D", "MD"),
    "tim kaine": ("D", "VA"), "mark warner": ("D", "VA"),
    "sheldon whitehouse": ("D", "RI"), "jack reed": ("D", "RI"),
    "richard blumenthal": ("D", "CT"), "chris murphy": ("D", "CT"),
    "maggie hassan": ("D", "NH"), "jeanne shaheen": ("D", "NH"),
    "bernie sanders": ("I", "VT"), "peter welch": ("D", "VT"),
    "angus king": ("I", "ME"), "dianne feinstein": ("D", "CA"),
    "alex padilla": ("D", "CA"), "adam schiff": ("D", "CA"),
    "laphonza butler": ("D", "CA"), "mazie hirono": ("D", "HI"),
    "brian schatz": ("D", "HI"), "patty murray": ("D", "WA"),
    "maria cantwell": ("D", "WA"), "jeff merkley": ("D", "OR"),
    "michael bennet": ("D", "CO"), "john hickenlooper": ("D", "CO"),
    "catherine cortez masto": ("D", "NV"), "jacky rosen": ("D", "NV"),
    "mark kelly": ("D", "AZ"), "kyrsten sinema": ("I", "AZ"),
    "ruben gallego": ("D", "AZ"), "martin heinrich": ("D", "NM"),
    "ben ray lujan": ("D", "NM"), "raphael warnock": ("D", "GA"),
    "jon ossoff": ("D", "GA"), "tammy duckworth": ("D", "IL"),
    "dick durbin": ("D", "IL"), "gary peters": ("D", "MI"),
    "debbie stabenow": ("D", "MI"), "elissa slotkin": ("D", "MI"),
    "sherrod brown": ("D", "OH"), "bob casey": ("D", "PA"),
    "john fetterman": ("D", "PA"), "dave mccormick": ("R", "PA"),
    "mike rogers": ("R", "AL"), "katie britt": ("R", "AL"),
    # Prolific House PTR filers (doc_id pattern appearances)
    "alan lowenthal": ("D", "CA"), "jim himes": ("D", "CT"),
    "chellie pingree": ("D", "ME"), "chrissy houlahan": ("D", "PA"),
    "dan goldman": ("D", "NY"), "danny davis": ("D", "IL"),
    "david rouzer": ("R", "NC"), "dusty johnson": ("R", "SD"),
    "dutch ruppersberger": ("D", "MD"), "french hill": ("R", "AR"),
    "gilbert cisneros": ("D", "CA"), "greg murphy": ("R", "NC"),
    "jennifer mcclellan": ("D", "VA"), "jeff jackson": ("D", "NC"),
    "jim mcgovern": ("D", "MA"), "john garamendi": ("D", "CA"),
    "kathy manning": ("D", "NC"), "kurt schrader": ("D", "OR"),
    "marc veasey": ("D", "TX"), "mark takano": ("D", "CA"),
    "morgan mcgarvey": ("D", "KY"), "mikie sherrill": ("D", "NJ"),
    "raja krishnamoorthi": ("D", "IL"), "scott peters": ("D", "CA"),
    "seth moulton": ("D", "MA"), "sharice davids": ("D", "KS"),
    "tom kean": ("R", "NJ"), "zach nunn": ("R", "IA"),
    "dina titus": ("D", "NV"), "susie lee": ("D", "NV"),
    "don davis": ("D", "NC"), "deborah ross": ("D", "NC"),
    "thomas kean": ("R", "NJ"), "frank lucas": ("R", "OK"),
    "kevin mullin": ("D", "CA"), "salud carbajal": ("D", "CA"),
    "jared huffman": ("D", "CA"), "mike levin": ("D", "CA"),
    "mark desaulnier": ("D", "CA"), "josh harder": ("D", "CA"),
    "adam gray": ("D", "CA"), "john duarte": ("R", "CA"),
    "vince fong": ("R", "CA"), "young kim": ("R", "CA"),
    "michelle steel": ("R", "CA"), "darrell issa": ("R", "CA"),
    "tom mcclintock": ("R", "CA"), "doug lamalfa": ("R", "CA"),
    "kevin kiley": ("R", "CA"), "ami rebecca bera": ("D", "CA"),
    "doris matsui": ("D", "CA"), "nanette barragan": ("D", "CA"),
    "jimmy gomez": ("D", "CA"), "ted lieu": ("D", "CA"),
    "sydney kamlager-dove": ("D", "CA"), "maxine waters": ("D", "CA"),
    "linda sanchez": ("D", "CA"), "judy chu": ("D", "CA"),
    "brad sherman": ("D", "CA"), "pete aguilar": ("D", "CA"),
    "raul ruiz": ("D", "CA"), "juan vargas": ("D", "CA"),
    "scott perry": ("R", "PA"), "mike kelly": ("R", "PA"),
    "glenn gt thompson": ("R", "PA"), "dan meuser": ("R", "PA"),
    "lloyd smucker": ("R", "PA"), "john joyce": ("R", "PA"),
    "guy reschenthaler": ("R", "PA"), "brian fitzpatrick": ("R", "PA"),
    "dwight evans": ("D", "PA"), "mary scanlon": ("D", "PA"),
    "madeleine dean": ("D", "PA"), "matt cartwright": ("D", "PA"),
    "summer lee": ("D", "PA"), "chris deluzio": ("D", "PA"),
    "donald norcross": ("D", "NJ"), "jeff van drew": ("R", "NJ"),
    "chris smith": ("R", "NJ"), "rob menendez": ("D", "NJ"),
    "bill pascrell": ("D", "NJ"), "bonnie watson coleman": ("D", "NJ"),
    "frank pallone": ("D", "NJ"), "brendan boyle": ("D", "PA"),
    "tom malinowski": ("D", "NJ"),
}


def _normalize_member_key(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return ""
    name = re.sub(
        r"^(Hon\.|Honorable|Representative|Rep\.|Senator|Sen\.|Mr\.|Ms\.|Mrs\.|Dr\.)\s+",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"\s+(Jr\.|Sr\.|II|III|IV)\.?$", "", name, flags=re.IGNORECASE)
    return " ".join(name.split()).lower()


def enrich_member_metadata(trades: list[dict[str, str]]) -> list[dict[str, str]]:
    """Cross-populate party/state across sources for the same member.

    House Clerk PDF rows have no party/state; QuiverQuant rows usually do. Build
    a lookup from whichever rows carry the metadata, then backfill the empty
    ones. Falls back to a static 119th Congress table for House-only members.
    """
    lookup: dict[str, tuple[str, str]] = {}
    for t in trades:
        key = _normalize_member_key(t.get("member_name", ""))
        if not key:
            continue
        party = (t.get("party") or "").strip()
        state = (t.get("state") or "").strip()
        if not (party or state):
            continue
        if key not in lookup:
            lookup[key] = (party, state)
        else:
            existing_p, existing_s = lookup[key]
            lookup[key] = (existing_p or party, existing_s or state)

    enriched = 0
    for t in trades:
        if t.get("party") and t.get("state"):
            continue
        key = _normalize_member_key(t.get("member_name", ""))
        if not key:
            continue
        party, state = lookup.get(key, ("", ""))
        if not (party or state):
            party, state = _HOUSE_MEMBER_FALLBACK.get(key, ("", ""))
        if party and not t.get("party"):
            t["party"] = party
            enriched += 1
        if state and not t.get("state"):
            t["state"] = state

    if enriched:
        print(f"  Enriched {enriched} trades with party/state from cross-source lookup", file=sys.stderr)
    return trades


def deduplicate_trades(trades: list[dict[str, str]]) -> list[dict[str, str]]:
    """Remove duplicate trades based on (member, ticker, txn_date, txn_type)."""
    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, str]] = []

    for trade in trades:
        key = (
            trade.get("member_name", "").lower(),
            trade.get("ticker", "").upper(),
            trade.get("transaction_date", ""),
            trade.get("transaction_type", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(trade)

    return unique


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_trades_csv(trades: list[dict[str, str]], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=TRADE_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)
    print(f"  Wrote {len(trades)} trades to {path.name}", file=sys.stderr)


def write_overlap_csv(overlap: list[dict[str, str]], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OVERLAP_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(overlap)
    print(f"  Wrote {len(overlap)} overlap rows to {path.name}", file=sys.stderr)


def write_tickers_txt(trades: list[dict[str, str]], path: Path) -> None:
    tickers = sorted({t["ticker"] for t in trades if t.get("ticker")})
    path.write_text("\n".join(tickers) + "\n")
    print(f"  Wrote {len(tickers)} unique tickers to {path.name}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60, file=sys.stderr)
    print("Congressional Stock Trade Scanner", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # Check cache first.
    cache = load_cache()
    all_trades: list[dict[str, str]] = []

    if is_cache_fresh(cache) and cache.get("trades"):
        print(f"  Using cached trades ({len(cache['trades'])} entries, age < {CACHE_TTL_HOURS}h)", file=sys.stderr)
        all_trades = cache["trades"]
    else:
        # Source 1: Senate eFD (authoritative).
        print("\n[Senate eFD] Fetching periodic transaction reports...", file=sys.stderr)
        senate_trades = fetch_senate_efdsearch()
        print(f"  Senate eFD: {len(senate_trades)} trades", file=sys.stderr)
        all_trades.extend(senate_trades)
        rate_limit()

        # Source 2: House clerk disclosures.
        print("\n[House Clerk] Fetching financial disclosure index...", file=sys.stderr)
        house_reports = fetch_house_trades_index()
        print(f"  House Clerk: {len(house_reports)} PTR filings found", file=sys.stderr)
        house_rows = parse_house_ptrs(house_reports)
        all_trades.extend(house_rows)
        rate_limit()

        # Source 3: Capitol Trades (supplementary).
        print("\n[Capitol Trades] Fetching supplementary data...", file=sys.stderr)
        cap_trades = fetch_capitol_trades_html()
        print(f"  Capitol Trades: {len(cap_trades)} trades", file=sys.stderr)
        all_trades.extend(cap_trades)
        rate_limit()

        # Source 4: QuiverQuant (supplementary).
        print("\n[QuiverQuant] Fetching supplementary data...", file=sys.stderr)
        quiver_trades = fetch_quiver_trades()
        print(f"  QuiverQuant: {len(quiver_trades)} trades", file=sys.stderr)
        all_trades.extend(quiver_trades)

        # Save to cache.
        save_cache({"_ts": time.time(), "trades": all_trades})

    # Enrich: backfill empty party/state fields from any row where the same
    # member already has the metadata. QuiverQuant rows typically carry party
    # and state; House Clerk PDFs do not. Cross-populate so the public page
    # shows party affiliation on every row.
    all_trades = enrich_member_metadata(all_trades)

    # Filter out entries with no ticker (House PDFs without parsed transactions).
    ticker_trades = [t for t in all_trades if t.get("ticker")]
    no_ticker = len(all_trades) - len(ticker_trades)
    if no_ticker:
        print(f"\n  {no_ticker} entries without tickers (House PDF metadata) excluded from ticker files", file=sys.stderr)

    # Deduplicate.
    all_trades_dedup = deduplicate_trades(all_trades)
    ticker_trades_dedup = deduplicate_trades(ticker_trades)

    print(f"\n  Total unique trades: {len(all_trades_dedup)} ({len(ticker_trades_dedup)} with tickers)", file=sys.stderr)

    # Write outputs.
    print("\n[Output]", file=sys.stderr)
    write_trades_csv(all_trades_dedup, OUT_TRADES_CSV)
    write_tickers_txt(ticker_trades_dedup, OUT_TICKERS_TXT)

    # Cross-reference with SEC catalyst universe.
    print("\n[Overlap Analysis]", file=sys.stderr)
    universe = load_ranked_universe()
    print(f"  SEC catalyst universe: {len(universe)} tickers", file=sys.stderr)

    overlap = compute_overlap(ticker_trades_dedup, universe)
    write_overlap_csv(overlap, OUT_OVERLAP_CSV)

    if overlap:
        print(f"\n  OVERLAP FOUND: {len(overlap)} trades match SEC catalyst tickers:", file=sys.stderr)
        for row in overlap[:15]:
            direction = "BUY" if row["transaction_type"] == "buy" else row["transaction_type"].upper()
            print(
                f"    {row['ticker']:6s} | {direction:8s} | {row['member_name']:25s} | "
                f"score={row['priority_score']:>3s} | {row['amount_range']}",
                file=sys.stderr,
            )
        if len(overlap) > 15:
            print(f"    ... and {len(overlap) - 15} more", file=sys.stderr)
    else:
        print("  No overlap found between congressional trades and SEC catalyst universe.", file=sys.stderr)

    # Date-archive outputs.
    today = dt.datetime.now().strftime("%Y-%m-%d")
    for src, dst_name in [
        (OUT_TRADES_CSV, f"congressional_trades_{today}.csv"),
        (OUT_OVERLAP_CSV, f"congressional_overlap_{today}.csv"),
    ]:
        dst = ROOT / dst_name
        if src.exists() and not dst.exists():
            import shutil
            shutil.copy2(src, dst)

    print("\n" + "=" * 60, file=sys.stderr)
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
