"""Shared wire-feed filter — universe-locked tickers + pump regex + dedup.

Used by build_prnewswire.py / build_businesswire.py / build_globenewswire.py /
build_doj_press.py / any RSS-style wire ingestion. Centralizes the noise
filtering so we don't duplicate logic across 5 files.

Public API:
    extract_tickers(text, universe) -> list[str]
    is_pump_release(headline, summary, mcap_lookup, ticker) -> bool
    canonical_dedup_key(headline, link) -> str
    load_universe() -> set[str]
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).parent
ENTITY_MASTER = ROOT / "entity_master.json"
SEC_LATEST = ROOT / "sec_catalyst_latest.csv"

# Common-word tickers that produce huge false-positive rates if matched naively.
# When these appear in text, require a $TICKER prefix or stricter context.
COMMON_WORD_TICKERS = {
    "A", "ALL", "AT", "BE", "BY", "FOR", "GO", "HAS", "HE", "I", "IS", "IT",
    "ON", "OR", "OUT", "REAL", "SO", "T", "TO", "TWO", "UP", "US", "WE", "Y",
    "FUN", "NEW", "ONE", "PLAY", "GOOD", "BAD", "CASH", "EAT", "OPEN", "OUT",
    "SEE", "SAVE", "GAIN", "BIG", "TOP", "PRO", "JOB", "AI",
}

# Pump-and-dump patterns. Hits trigger drop unless mcap > smallcap_ceiling.
PUMP_REGEXES = [
    re.compile(r"\b(?:massive|breakout|skyrocket|explod\w+|moon|once.in.a.lifetime)\b", re.I),
    re.compile(r"\b(?:dont miss|don.t miss|act now|buy now|ground floor)\b", re.I),
    re.compile(r"\b(?:hot stock|next bitcoin|next tesla|10x potential|100x)\b", re.I),
    re.compile(r"\b(?:revolutionary|game.changer|disrupt\w+|paradigm.shift)\b", re.I),
    re.compile(r"\b(?:undiscovered|under.the.radar|hidden gem)\b", re.I),
]
PUMP_MCAP_FLOOR = 100_000_000  # below $100M, pump regex wins

TICKER_RE = re.compile(r"(?:^|[^A-Z0-9.])(?:\$([A-Z]{1,5}(?:\.[A-Z])?)|([A-Z]{2,5}))(?=[^A-Z0-9.]|$)")


def load_universe() -> set[str]:
    """Build the set of valid public-equity tickers we know about.

    Pulls from entity_master.json (broad universe) + sec_catalyst_latest.csv
    (recent active filers). Falls back to empty if neither exists.
    """
    out: set[str] = set()
    if ENTITY_MASTER.exists():
        try:
            data = json.loads(ENTITY_MASTER.read_text(encoding="utf-8"))
            # entity_master.json: list of {ticker:..., ...} or dict keyed by ticker.
            if isinstance(data, dict):
                for k in data.keys():
                    if isinstance(k, str) and 1 <= len(k) <= 5:
                        out.add(k.upper())
            elif isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict):
                        t = entry.get("ticker") or entry.get("symbol") or ""
                        if isinstance(t, str) and 1 <= len(t) <= 5:
                            out.add(t.upper())
        except (json.JSONDecodeError, OSError):
            pass
    if SEC_LATEST.exists():
        try:
            with SEC_LATEST.open(newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    t = (r.get("ticker") or "").strip().upper()
                    if 1 <= len(t) <= 5 and t.isalpha():
                        out.add(t)
        except OSError:
            pass
    return out


def extract_tickers(text: str, universe: set[str]) -> list[str]:
    """Pull tickers from a press-release headline+summary.

    Strategy: prefer $TICKER explicit cashtag, fall back to any all-caps
    2-5 char token that's IN the universe AND not in COMMON_WORD_TICKERS.
    """
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for m in TICKER_RE.finditer(text):
        cashtag = m.group(1)
        bare = m.group(2)
        if cashtag:
            t = cashtag.upper()
            if 1 <= len(t) <= 5 and t in universe and t not in seen:
                found.append(t)
                seen.add(t)
        elif bare:
            t = bare.upper()
            if t in COMMON_WORD_TICKERS:
                continue
            if t not in universe:
                continue
            if t in seen:
                continue
            found.append(t)
            seen.add(t)
    return found


def is_pump_release(
    headline: str,
    summary: str,
    mcap_lookup: dict[str, float] | None = None,
    ticker: str | None = None,
) -> bool:
    """Heuristic pump detector.

    True if any pump regex matches AND either:
      - no mcap context provided, OR
      - the named ticker is below the smallcap pump floor.
    """
    text = f"{headline or ''} {summary or ''}"
    if not any(rx.search(text) for rx in PUMP_REGEXES):
        return False
    if not (mcap_lookup and ticker):
        return True  # no context → assume pump if pattern hits
    mcap = mcap_lookup.get(ticker.upper(), 0.0)
    return mcap > 0 and mcap < PUMP_MCAP_FLOOR


def canonical_dedup_key(headline: str, link: str) -> str:
    """Stable key for cross-wire deduplication.

    PR distributors syndicate the same release through multiple wires; we want
    one row per release per ticker. Hash a normalized (headline + link host).
    """
    h = (headline or "").strip().lower()
    h = re.sub(r"\s+", " ", h)
    h = re.sub(r"[^a-z0-9 ]+", "", h)
    # Collapse to first 20 words for fuzzy match across wire variants.
    h = " ".join(h.split()[:20])
    # Strip query string from link.
    link_norm = (link or "").split("?")[0].rstrip("/").lower()
    return hashlib.sha1(f"{h}|{link_norm}".encode("utf-8")).hexdigest()[:16]


def filter_pump_rows(
    rows: Iterable[dict[str, str]],
    mcap_lookup: dict[str, float] | None = None,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for r in rows:
        if is_pump_release(
            r.get("headline", ""),
            r.get("summary", ""),
            mcap_lookup,
            r.get("ticker"),
        ):
            continue
        out.append(r)
    return out


def dedup_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for r in rows:
        key = canonical_dedup_key(r.get("headline", ""), r.get("link", ""))
        ticker = (r.get("ticker") or "").upper()
        # Dedup at (canonical_key, ticker) level so a multi-ticker release
        # still emits one row per ticker.
        full = f"{key}|{ticker}"
        if full in seen:
            continue
        seen.add(full)
        out.append(r)
    return out
