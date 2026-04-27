#!/usr/bin/env python3
"""Build tiered-news momentum signals and combine with SEC scores."""

from __future__ import annotations

import csv
import datetime as dt
import email.utils
import json
import math
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "scoring_config.json"

OUT_NEWS_ROWS = ROOT / "news_signals.csv"
OUT_NEWS_SECTOR = ROOT / "news_sector_momentum.csv"
OUT_COMBINED = ROOT / "combined_priority.csv"
OUT_COMBINED_TICKERS = ROOT / "combined_priority_tickers.txt"
OUT_HEADLINE_ONLY = ROOT / "headline_only_momentum.csv"
OUT_BBG_USED = ROOT / "bloomberg_headlines_used.csv"

NOW_UTC = dt.datetime.now(dt.timezone.utc)
CFG: dict[str, Any] = {}

# Free feeds only (tiered trust model).
FEEDS = [
    {"name": "reuters_business", "url": "https://feeds.reuters.com/reuters/businessNews", "tier": 1, "weight": 1.0},
    {"name": "reuters_world", "url": "https://feeds.reuters.com/reuters/worldNews", "tier": 1, "weight": 1.0},
    {"name": "marketwatch_top", "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories", "tier": 2, "weight": 0.8},
    {"name": "yahoo_finance", "url": "https://finance.yahoo.com/news/rssindex", "tier": 2, "weight": 0.7},
    {"name": "noaa_nhc", "url": "https://www.nhc.noaa.gov/index-at.xml", "tier": 2, "weight": 0.9},
    {"name": "eia_today", "url": "https://www.eia.gov/rss/todayinenergy.xml", "tier": 2, "weight": 0.9},
]

# Optional Bloomberg input file (manual export / API dump adapter).
# Expected columns (case-insensitive aliases supported):
# - timestamp_utc | published_utc | timestamp
# - ticker
# - headline | title
# - summary (optional)
# - sector (optional)
# - event (optional)
# - link (optional)
BLOOMBERG_INPUT = ROOT / "bloomberg_headlines.csv"
ALPHAVANTAGE_INPUT = ROOT / "alphavantage_news.csv"
PRESS_WIRES_INPUT = ROOT / "press_wires.csv"
FEDERAL_REGISTER_INPUT = ROOT / "federal_register.csv"
DOJ_NEWS_INPUT = ROOT / "doj_news.csv"
POLYMARKET_INPUT = ROOT / "polymarket_signals.csv"
GDACS_INPUT = ROOT / "gdacs_alerts.csv"
EIA_PETROLEUM_INPUT = ROOT / "eia_petroleum.csv"
NASA_FIRMS_INPUT = ROOT / "nasa_firms.csv"
CLOUDFLARE_RADAR_INPUT = ROOT / "cloudflare_radar.csv"
IMF_PORTWATCH_INPUT = ROOT / "imf_portwatch.csv"

SECTOR_KEYWORDS = {
    "defense": ["defense", "military", "missile", "drone", "pentagon", "aerospace", "conflict", "war"],
    "energy": ["oil", "gas", "lng", "opec", "refinery", "crude", "diesel", "power grid", "natural gas"],
    "agriculture": ["crop", "corn", "soybean", "wheat", "harvest", "drought", "farming", "fertilizer"],
    "weather": ["hurricane", "storm", "flood", "wildfire", "heatwave", "cold snap", "landfall"],
    "semis_ai": ["semiconductor", "chip", "ai", "gpu", "datacenter", "foundry", "inference", "hbm"],
    "biotech": ["fda", "trial", "phase 3", "clinical", "approval", "drug", "therapy", "biotech"],
    "financials": ["bank", "credit", "yield", "rate cut", "fed", "treasury", "liquidity"],
    "transport": ["shipping", "airline", "freight", "rail", "logistics", "port", "container"],
}

EVENT_KEYWORDS = {
    "conflict_risk": ["war", "attack", "strike", "sanction", "missile", "conflict"],
    "weather_shock": ["hurricane", "flood", "storm", "drought", "wildfire"],
    "supply_chain": ["shortage", "disruption", "backlog", "port delay", "factory shutdown"],
    "policy_macro": ["fed", "rate", "tariff", "subsidy", "regulation", "export control"],
    "company_catalyst": ["guidance", "earnings", "contract", "approval", "acquisition", "partnership"],
}

STOPWORDS = {
    "THE",
    "AND",
    "FOR",
    "WITH",
    "FROM",
    "THIS",
    "THAT",
    "NEWS",
    "LIVE",
    "WILL",
    "HAS",
    "HAVE",
    "ARE",
    "BEEN",
    "MORE",
    "AFTER",
    "ABOUT",
    "MARKET",
    "STOCK",
    "STOCKS",
}

# Hard-exclude warrant/preferred/unit derivative tickers from combined scoring.
# Matches: hyphenated series (DSX-WT, C-PR), double-W warrants (DJTWW),
# WS/WT suffix warrants, and 5+ char tickers ending in single W (DAICW, BFRIW).
def _is_derivative(ticker: str) -> bool:
    if "-" in ticker:
        return True
    if ticker.endswith(("WW", "WS", "WT")):
        return True
    if len(ticker) >= 5 and ticker.endswith("W"):
        return True
    return False


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        obj = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def parse_ts(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d
    except ValueError:
        pass
    try:
        d = email.utils.parsedate_to_datetime(value)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_rss(xml_bytes: bytes, feed_name: str, tier: int, weight: float) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return out

    channel = root.find("channel")
    if channel is None:
        channel = root

    items = channel.findall(".//item")
    ns = {"a": "http://www.w3.org/2005/Atom"}
    if not items:
        for entry in root.findall(".//a:entry", ns):
            title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
            link_el = entry.find("a:link", ns)
            link = link_el.attrib.get("href", "") if link_el is not None else ""
            summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
            pub = (entry.findtext("a:updated", default="", namespaces=ns) or "").strip()
            out.append(
                {
                    "source": feed_name,
                    "tier": tier,
                    "weight": weight,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "published": pub,
                }
            )
        return out

    for item in items:
        title = (item.findtext("title", default="") or "").strip()
        summary = (item.findtext("description", default="") or "").strip()
        link = (item.findtext("link", default="") or "").strip()
        pub = (item.findtext("pubDate", default="") or item.findtext("published", default="") or "").strip()
        out.append(
            {
                "source": feed_name,
                "tier": tier,
                "weight": weight,
                "title": title,
                "summary": summary,
                "link": link,
                "published": pub,
            }
        )
    return out


def match_keywords(text: str, mapping: dict[str, list[str]]) -> list[str]:
    t = text.lower()
    hits: list[str] = []
    for k, kws in mapping.items():
        if any(kw in t for kw in kws):
            hits.append(k)
    return hits


def extract_ticker_candidates(text: str) -> list[str]:
    cands = set(re.findall(r"\(([A-Z]{1,5})\)", text))
    cands |= set(re.findall(r"\b[A-Z]{2,5}\b", text))
    out = []
    for c in cands:
        if c in STOPWORDS:
            continue
        if c.isalpha() and len(c) <= 5:
            out.append(c)
    return sorted(set(out))[:6]


def recency_decay(minutes: float) -> float:
    # Two-regime decay: fast intraday + slow multi-day carryover.
    # Tetlock (2007) Table II: sentiment predicts returns through lag 5 (~1 week).
    # Garcia (2013, JF): predictive horizon 1-2 days for extreme sentiment.
    # Glasserman & Mamaysky (2019, JFE): news-implied vol predicts out to 3-5 days.
    # Fast component (tau=300 min, weight 0.6): captures intraday spike.
    # Slow component (tau=1440 min, weight 0.4): captures multi-day carryover.
    fast = math.exp(-minutes / 300.0)
    slow = math.exp(-minutes / 1440.0)
    return 0.6 * fast + 0.4 * slow


def build_news_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_links = set()
    source_override = CFG.get("news", {}).get("source_weight_overrides", {})
    for feed in FEEDS:
        w = float(source_override.get(feed["name"], feed["weight"]))
        try:
            xml = http_get(feed["url"])
            items = parse_rss(xml, feed["name"], feed["tier"], w)
        except Exception:
            items = []
        for it in items:
            link = it.get("link", "")
            if link and link in seen_links:
                continue
            if link:
                seen_links.add(link)
            ts = parse_ts(it.get("published", "")) or NOW_UTC
            recency_min = max(0.0, (NOW_UTC - ts).total_seconds() / 60.0)
            text = f"{it.get('title','')} {it.get('summary','')}"
            sectors = match_keywords(text, SECTOR_KEYWORDS)
            events = match_keywords(text, EVENT_KEYWORDS)
            tickers = extract_ticker_candidates(text)
            base = 10.0 * float(it["weight"])
            score = base * recency_decay(recency_min)
            if sectors:
                score += min(6, 2 * len(sectors))
            if events:
                score += min(6, 2 * len(events))
            rows.append(
                {
                    "source": it["source"],
                    "tier": str(it["tier"]),
                    "ticker_explicit": "0",
                    "headline": it["title"],
                    "link": link,
                    "published_utc": ts.isoformat(),
                    "recency_min": f"{recency_min:.1f}",
                    "sector_tags": ";".join(sectors),
                    "event_tags": ";".join(events),
                    "ticker_candidates": ";".join(tickers),
                    "news_score": f"{score:.3f}",
                }
            )
    rows.sort(key=lambda r: float(r["news_score"]), reverse=True)
    return rows


def load_wire_rows() -> list[dict[str, Any]]:
    """Adapter for the press-wire scrapers (PRN/BW/GNW/Accesswire via
    build_press_wires.py + build_federal_register.py + build_doj_news.py).

    Applies universe-lock + pump filter via lib_wire_filter so the noise
    floor doesn't drown the news_momentum signal. Per-ticker rows for
    press wires; sector-only rows for Federal Register + DOJ.
    """
    out: list[dict[str, Any]] = []
    try:
        from lib_wire_filter import (
            extract_tickers, filter_pump_rows, dedup_rows, load_universe,
        )
    except ImportError:
        return out
    universe = load_universe()
    if not universe:
        return out

    # Press wires (per-ticker).
    if PRESS_WIRES_INPUT.exists():
        raw_rows: list[dict[str, str]] = []
        with PRESS_WIRES_INPUT.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                title = (r.get("title") or "").strip()
                link = (r.get("link") or "").strip()
                source = (r.get("source") or "wire").strip().lower()
                pub = (r.get("published") or "").strip()
                ts = parse_ts(pub) or NOW_UTC
                # Try existing ticker_guess first, else extract from title.
                tg = (r.get("ticker_guess") or "").strip().upper()
                tickers = [tg] if tg in universe else extract_tickers(title, universe)
                for t in tickers:
                    raw_rows.append(
                        {
                            "ticker": t,
                            "headline": title,
                            "summary": "",
                            "link": link,
                            "source_pub": source,
                            "_ts": ts.isoformat(),
                            "_ts_obj": ts,
                        }
                    )
        # Drop pumps + cross-wire dedup.
        clean = dedup_rows(filter_pump_rows(raw_rows))
        for r in clean:
            ts = r["_ts_obj"]
            recency_min = max(0.0, (NOW_UTC - ts).total_seconds() / 60.0)
            text = r["headline"]
            sectors = set(match_keywords(text, SECTOR_KEYWORDS))
            events = set(match_keywords(text, EVENT_KEYWORDS))
            # Tier-1 wires (PRN, BusinessWire, GlobeNewswire, Accesswire) get
            # a 12-base score, just below Bloomberg/AlphaVantage but above
            # the tier-2 RSS feeds. Recency-decay applied.
            score = 12.0 * recency_decay(recency_min)
            if sectors:
                score += min(8, 2.5 * len(sectors))
            if events:
                score += min(8, 2.5 * len(events))
            out.append(
                {
                    "source": r["source_pub"],
                    "tier": "1",
                    "ticker_explicit": "1",
                    "headline": r["headline"],
                    "link": r["link"],
                    "published_utc": r["_ts"],
                    "recency_min": f"{recency_min:.1f}",
                    "sector_tags": ";".join(sorted(sectors)),
                    "event_tags": ";".join(sorted(events)),
                    "ticker_candidates": r["ticker"],
                    "news_score": f"{score:.3f}",
                }
            )

    # Federal Register — sectoral (no ticker), feeds the sector aggregator.
    if FEDERAL_REGISTER_INPUT.exists():
        with FEDERAL_REGISTER_INPUT.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                title = (r.get("title") or "").strip()
                pub = (r.get("pub_date") or r.get("publication_date") or "").strip()
                ts = parse_ts(pub) or NOW_UTC
                recency_min = max(0.0, (NOW_UTC - ts).total_seconds() / 60.0)
                if recency_min > 60 * 48:  # cap at 48h relevance
                    continue
                text = f"{title} {(r.get('abstract') or '')}"
                sectors = set(match_keywords(text, SECTOR_KEYWORDS))
                events = set(match_keywords(text, EVENT_KEYWORDS))
                if not sectors:
                    continue
                score = 9.0 * recency_decay(recency_min) + 2.5 * len(sectors)
                out.append(
                    {
                        "source": "federal_register",
                        "tier": "1",
                        "ticker_explicit": "0",
                        "headline": title,
                        "link": (r.get("url") or "").strip(),
                        "published_utc": ts.isoformat(),
                        "recency_min": f"{recency_min:.1f}",
                        "sector_tags": ";".join(sorted(sectors)),
                        "event_tags": ";".join(sorted(events)),
                        "ticker_candidates": "",
                        "news_score": f"{score:.3f}",
                    }
                )

    # DOJ News — corporate enforcement actions (sector + event tagged).
    if DOJ_NEWS_INPUT.exists():
        with DOJ_NEWS_INPUT.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                title = (r.get("title") or r.get("headline") or "").strip()
                pub = (
                    r.get("filed")
                    or r.get("published")
                    or r.get("timestamp_utc")
                    or ""
                ).strip()
                ts = parse_ts(pub) or NOW_UTC
                recency_min = max(0.0, (NOW_UTC - ts).total_seconds() / 60.0)
                if recency_min > 60 * 72:
                    continue
                text = title
                tickers = extract_tickers(text, universe)
                sectors = set(match_keywords(text, SECTOR_KEYWORDS))
                events = set(match_keywords(text, EVENT_KEYWORDS))
                base = 11.0 * recency_decay(recency_min)
                if sectors:
                    base += min(6, 2.0 * len(sectors))
                if events:
                    base += min(6, 2.0 * len(events))
                if tickers:
                    for t in tickers:
                        out.append(
                            {
                                "source": "doj_news",
                                "tier": "1",
                                "ticker_explicit": "1",
                                "headline": title,
                                "link": (r.get("link") or r.get("url") or "").strip(),
                                "published_utc": ts.isoformat(),
                                "recency_min": f"{recency_min:.1f}",
                                "sector_tags": ";".join(sorted(sectors)),
                                "event_tags": ";".join(sorted(events)),
                                "ticker_candidates": t,
                                "news_score": f"{base:.3f}",
                            }
                        )
                elif sectors:
                    out.append(
                        {
                            "source": "doj_news",
                            "tier": "1",
                            "ticker_explicit": "0",
                            "headline": title,
                            "link": (r.get("link") or r.get("url") or "").strip(),
                            "published_utc": ts.isoformat(),
                            "recency_min": f"{recency_min:.1f}",
                            "sector_tags": ";".join(sorted(sectors)),
                            "event_tags": ";".join(sorted(events)),
                            "ticker_candidates": "",
                            "news_score": f"{base:.3f}",
                        }
                    )

    out.sort(key=lambda r: float(r["news_score"]), reverse=True)
    return out


def load_polymarket_rows() -> list[dict[str, Any]]:
    """Polymarket probability-surge → forward-looking event signal.

    Surges (|24h delta| >= 10pp) get the highest weight; nexus-tagged
    markets (FDA / M&A / earnings / macro) emit sector + event tags so
    downstream scoring picks them up the same as a press wire.
    """
    if not POLYMARKET_INPUT.exists():
        return []
    out: list[dict[str, Any]] = []
    with POLYMARKET_INPUT.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ts = parse_ts(r.get("timestamp_utc") or "") or NOW_UTC
            recency_min = max(0.0, (NOW_UTC - ts).total_seconds() / 60.0)
            if recency_min > 60 * 12:
                continue
            try:
                delta = abs(float(r.get("delta_24h", 0) or 0))
                vol = float(r.get("volume_24h_usd", 0) or 0)
            except (TypeError, ValueError):
                delta = vol = 0
            surge = r.get("surge_flag") == "1"
            nexus = (r.get("nexus") or "").strip().lower()
            tickers = (r.get("ticker_candidates") or "").strip().upper()
            # Nexus → sector/event mapping for downstream scoring.
            sector = ""
            event = ""
            if nexus == "biotech":
                sector, event = "biotech", "company_catalyst"
            elif nexus == "merger":
                sector, event = "financials", "company_catalyst"
            elif nexus.startswith("macro"):
                sector, event = "financials", "policy_macro"
            elif nexus == "earnings":
                event = "company_catalyst"
            elif nexus == "trade":
                event = "policy_macro"
            elif nexus == "credit":
                sector, event = "financials", "supply_chain"
            # Score: 14 base for surge (just below tier-1 wire 12), with
            # volume+delta bumps capped to keep prediction-market noise from
            # dominating SEC catalyst signal.
            base = 14.0 if surge else 9.0
            score = base * recency_decay(recency_min)
            if delta:
                score += min(5, delta * 30)
            if vol:
                score += min(3, (vol / 50_000) * 1.5)
            out.append({
                "source": "polymarket",
                "tier": "1",
                "ticker_explicit": "1" if tickers else "0",
                "headline": (r.get("question") or "")[:200],
                "link": r.get("url", ""),
                "published_utc": ts.isoformat(),
                "recency_min": f"{recency_min:.1f}",
                "sector_tags": sector,
                "event_tags": event,
                "ticker_candidates": tickers,
                "news_score": f"{score:.3f}",
            })
    out.sort(key=lambda r: float(r["news_score"]), reverse=True)
    return out


def load_gdacs_rows() -> list[dict[str, Any]]:
    """GDACS disaster alerts → sector signal for insurers, energy, shipping."""
    if not GDACS_INPUT.exists():
        return []
    out: list[dict[str, Any]] = []
    with GDACS_INPUT.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ts = parse_ts(r.get("timestamp_utc") or "") or NOW_UTC
            recency_min = max(0.0, (NOW_UTC - ts).total_seconds() / 60.0)
            if recency_min > 60 * 48:
                continue
            sev = (r.get("severity") or "").lower()
            evt = (r.get("event_type") or "").lower()
            # Sector mapping per disaster type.
            sectors: list[str] = ["financials"]  # insurers always tagged
            if evt in ("earthquake", "tsunami"):
                sectors.append("transport")
            if evt in ("cyclone", "flood", "wildfire"):
                sectors.append("agriculture")
            if evt == "wildfire":
                sectors.append("energy")
            severity_weight = {"red": 12.0, "orange": 8.0, "green": 4.0}.get(sev, 4.0)
            score = severity_weight * recency_decay(recency_min)
            score += 2.0 * len(sectors)
            out.append({
                "source": "gdacs",
                "tier": "1",
                "ticker_explicit": "0",
                "headline": (r.get("title") or "")[:200],
                "link": r.get("link", ""),
                "published_utc": ts.isoformat(),
                "recency_min": f"{recency_min:.1f}",
                "sector_tags": ";".join(sectors),
                "event_tags": "weather_shock" if evt in ("cyclone", "flood") else "supply_chain",
                "ticker_candidates": "",
                "news_score": f"{score:.3f}",
            })
    out.sort(key=lambda r: float(r["news_score"]), reverse=True)
    return out


def load_eia_petroleum_rows() -> list[dict[str, Any]]:
    """EIA Weekly Petroleum Status → energy sector signal.

    Big surprise builds/draws move XOM/CVX/USO/XLE within minutes of release.
    """
    if not EIA_PETROLEUM_INPUT.exists():
        return []
    out: list[dict[str, Any]] = []
    with EIA_PETROLEUM_INPUT.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ts = parse_ts(r.get("report_date") or "") or NOW_UTC
            recency_min = max(0.0, (NOW_UTC - ts).total_seconds() / 60.0)
            if recency_min > 60 * 24 * 7:
                continue
            tag = (r.get("tag") or "").strip()
            move = (r.get("move_vs_prior") or "").strip()
            try:
                move_f = float(move)
            except (TypeError, ValueError):
                move_f = 0
            base = 11.0 if abs(move_f) >= 5 else 8.0
            score = base * recency_decay(recency_min) + min(3, abs(move_f) / 2)
            out.append({
                "source": "eia_petroleum",
                "tier": "1",
                "ticker_explicit": "0",
                "headline": f"EIA {r.get('series','')}: {move} {r.get('unit','')} ({tag})"[:200],
                "link": "https://www.eia.gov/petroleum/weekly/",
                "published_utc": ts.isoformat(),
                "recency_min": f"{recency_min:.1f}",
                "sector_tags": "energy",
                "event_tags": "supply_chain",
                "ticker_candidates": "",
                "news_score": f"{score:.3f}",
            })
    out.sort(key=lambda r: float(r["news_score"]), reverse=True)
    return out


def load_nasa_firms_rows() -> list[dict[str, Any]]:
    """NASA FIRMS wildfire detections → insurance/energy/timber sector signal."""
    if not NASA_FIRMS_INPUT.exists():
        return []
    out: list[dict[str, Any]] = []
    high_conf_count = 0
    with NASA_FIRMS_INPUT.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                conf = float(r.get("confidence") or r.get("CONFIDENCE") or 0)
            except (TypeError, ValueError):
                conf = 0
            if conf < 70:
                continue
            high_conf_count += 1
    # Aggregate signal: emit ONE row representing total high-confidence detections
    # in the last 24h, NOT one row per fire (keeps news_signals clean).
    if high_conf_count == 0:
        return []
    score = min(15, 5 + high_conf_count / 50.0)
    out.append({
        "source": "nasa_firms",
        "tier": "1",
        "ticker_explicit": "0",
        "headline": f"NASA FIRMS: {high_conf_count} high-confidence wildfire detections (24h)"[:200],
        "link": "https://firms.modaps.eosdis.nasa.gov/active_fire/",
        "published_utc": NOW_UTC.isoformat(),
        "recency_min": "0",
        "sector_tags": "energy;agriculture;financials",
        "event_tags": "weather_shock",
        "ticker_candidates": "",
        "news_score": f"{score:.3f}",
    })
    return out


def load_cloudflare_radar_rows() -> list[dict[str, Any]]:
    """Cloudflare internet outages → telecom/datacenter/cyber sector signal."""
    if not CLOUDFLARE_RADAR_INPUT.exists():
        return []
    out: list[dict[str, Any]] = []
    with CLOUDFLARE_RADAR_INPUT.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ts = parse_ts(r.get("timestamp_utc") or "") or NOW_UTC
            recency_min = max(0.0, (NOW_UTC - ts).total_seconds() / 60.0)
            if recency_min > 60 * 24 * 7:
                continue
            sev = (r.get("severity") or "").lower()
            sectors = (r.get("sector_tags") or "").strip()
            base_w = {"high": 12.0, "medium": 8.0, "low": 4.0}.get(sev, 4.0)
            score = base_w * recency_decay(recency_min)
            out.append({
                "source": "cloudflare_radar",
                "tier": "1",
                "ticker_explicit": "0",
                "headline": (
                    f"Cloudflare Radar: {sev.upper()} {r.get('outage_type','')} outage "
                    f"in {r.get('country','?')} ({r.get('duration_hours','?')}h)"
                )[:200],
                "link": r.get("link", ""),
                "published_utc": ts.isoformat(),
                "recency_min": f"{recency_min:.1f}",
                "sector_tags": sectors,
                "event_tags": "supply_chain",
                "ticker_candidates": "",
                "news_score": f"{score:.3f}",
            })
    out.sort(key=lambda r: float(r["news_score"]), reverse=True)
    return out


def load_imf_portwatch_rows() -> list[dict[str, Any]]:
    """IMF chokepoint transit collapse → energy/shipping sector signal."""
    if not IMF_PORTWATCH_INPUT.exists():
        return []
    out: list[dict[str, Any]] = []
    for r in csv.DictReader(IMF_PORTWATCH_INPUT.open(newline="", encoding="utf-8")):
        try:
            yoy = float(r.get("vol_growth_yoy_pct") or 0)
        except ValueError:
            yoy = 0
        # Fire only on meaningful disruption (YoY transit drop > 20%).
        if abs(yoy) < 20:
            continue
        sectors = (r.get("sector_tags") or "energy;shipping").strip()
        score = 13.0 + min(5, abs(yoy) / 10.0)
        out.append({
            "source": "imf_portwatch",
            "tier": "1",
            "ticker_explicit": "0",
            "headline": (
                f"IMF PortWatch: {r.get('chokepoint','?')} transit "
                f"{'+' if yoy >= 0 else ''}{yoy:.1f}% YoY"
            )[:200],
            "link": "https://portwatch.imf.org/",
            "published_utc": NOW_UTC.isoformat(),
            "recency_min": "0",
            "sector_tags": sectors,
            "event_tags": "supply_chain",
            "ticker_candidates": "",
            "news_score": f"{score:.3f}",
        })
    out.sort(key=lambda r: float(r["news_score"]), reverse=True)
    return out


def load_alphavantage_rows() -> list[dict[str, Any]]:
    """Adapter for AlphaVantage NEWS_SENTIMENT export (build_alphavantage_news.py).

    Tier-1 boost: aggregator covers Bloomberg/Reuters/WSJ/CNBC wires with
    ticker-tagged sentiment. We weight by AlphaVantage's relevance score so
    spurious ticker mentions get suppressed.
    """
    if not ALPHAVANTAGE_INPUT.exists():
        return []
    out: list[dict[str, Any]] = []
    with ALPHAVANTAGE_INPUT.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = parse_ts(row.get("timestamp_utc") or "") or NOW_UTC
            recency_min = max(0.0, (NOW_UTC - ts).total_seconds() / 60.0)
            ticker = (row.get("ticker") or "").strip().upper()
            title = (row.get("headline") or "").strip()
            summary = (row.get("summary") or "").strip()
            if not ticker or not title:
                continue
            text = f"{title} {summary}"
            sectors = set(match_keywords(text, SECTOR_KEYWORDS))
            events = set(match_keywords(text, EVENT_KEYWORDS))
            try:
                relevance = float(row.get("relevance") or 0)
                sentiment = float(row.get("ticker_sentiment") or 0)
            except (TypeError, ValueError):
                relevance = sentiment = 0.0
            # Base score 13 (just below Bloomberg's 15) × relevance × recency
            # decay. Sentiment magnitude adds asymmetric kicker — strong
            # positive OR negative wires both move stocks.
            score = 13.0 * max(0.5, relevance) * recency_decay(recency_min)
            score += min(4, abs(sentiment) * 6.0)
            if sectors:
                score += min(8, 2.5 * len(sectors))
            if events:
                score += min(8, 2.5 * len(events))
            out.append(
                {
                    "source": "alphavantage",
                    "tier": "1",
                    "ticker_explicit": "1",
                    "headline": title,
                    "link": (row.get("link") or "").strip(),
                    "published_utc": ts.isoformat(),
                    "recency_min": f"{recency_min:.1f}",
                    "sector_tags": ";".join(sorted(sectors)),
                    "event_tags": ";".join(sorted(events)),
                    "ticker_candidates": ticker,
                    "news_score": f"{score:.3f}",
                }
            )
    out.sort(key=lambda r: float(r["news_score"]), reverse=True)
    return out


def load_bloomberg_rows() -> list[dict[str, Any]]:
    if not BLOOMBERG_INPUT.exists():
        return []
    out: list[dict[str, Any]] = []
    with BLOOMBERG_INPUT.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            timestamp = (
                row.get("timestamp_utc")
                or row.get("published_utc")
                or row.get("timestamp")
                or ""
            ).strip()
            ts = parse_ts(timestamp) or NOW_UTC
            recency_min = max(0.0, (NOW_UTC - ts).total_seconds() / 60.0)
            ticker = (row.get("ticker") or "").strip().upper()
            title = (row.get("headline") or row.get("title") or "").strip()
            summary = (row.get("summary") or "").strip()
            if not ticker and not title:
                continue
            text = f"{title} {summary}"
            sectors = set(match_keywords(text, SECTOR_KEYWORDS))
            events = set(match_keywords(text, EVENT_KEYWORDS))
            if row.get("sector"):
                sectors.add(row["sector"].strip().lower())
            if row.get("event"):
                events.add(row["event"].strip().lower())
            # Bloomberg tier-1 boost + recency decay.
            score = 15.0 * recency_decay(recency_min)
            if sectors:
                score += min(8, 2.5 * len(sectors))
            if events:
                score += min(8, 2.5 * len(events))
            out.append(
                {
                    "source": "bloomberg",
                    "tier": "1",
                    "ticker_explicit": "1",
                    "headline": title,
                    "link": (row.get("link") or "").strip(),
                    "published_utc": ts.isoformat(),
                    "recency_min": f"{recency_min:.1f}",
                    "sector_tags": ";".join(sorted(sectors)),
                    "event_tags": ";".join(sorted(events)),
                    "ticker_candidates": ticker,
                    "news_score": f"{score:.3f}",
                }
            )
    out.sort(key=lambda r: float(r["news_score"]), reverse=True)
    return out


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def aggregate_sector(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    for r in rows:
        sc = float(r["news_score"])
        rec = float(r["recency_min"])
        for s in [x for x in r["sector_tags"].split(";") if x]:
            cur = agg.setdefault(s, {"sector": s, "score_sum": 0.0, "mentions": 0, "best_recency_min": 999999.0})
            cur["score_sum"] += sc
            cur["mentions"] += 1
            cur["best_recency_min"] = min(cur["best_recency_min"], rec)
    out = []
    for v in agg.values():
        out.append(
            {
                "sector": v["sector"],
                "sector_score": f"{v['score_sum']:.3f}",
                "mentions": str(v["mentions"]),
                "best_recency_min": f"{v['best_recency_min']:.1f}",
            }
        )
    out.sort(key=lambda r: float(r["sector_score"]), reverse=True)
    return out


def load_sec_scores() -> dict[str, dict[str, float]]:
    files = [
        ("sec_top_gappers.csv", "gapper_score"),
        ("sec_top_value.csv", "value_score"),
        ("sec_top_moat_core.csv", "moat_score"),
    ]
    scores: dict[str, dict[str, float]] = {}
    for fname, col in files:
        p = ROOT / fname
        if not p.exists():
            continue
        with p.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                t = (row.get("ticker") or "").strip().upper()
                if not t or _is_derivative(t):
                    continue
                s = float(row.get(col) or 0)
                rec = scores.setdefault(t, {"sec_score": 0.0, "gapper_score": 0.0, "value_score": 0.0, "moat_score": 0.0})
                rec[col] = max(rec[col], s)
                rec["sec_score"] = max(rec["gapper_score"], rec["value_score"], rec["moat_score"])
    return scores


def aggregate_news_by_ticker(news_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    require_explicit = bool(CFG.get("precision", {}).get("require_explicit_ticker_news", False))
    out: dict[str, dict[str, Any]] = {}
    for r in news_rows:
        if require_explicit and r.get("ticker_explicit") != "1":
            continue
        score = float(r["news_score"])
        recency = float(r["recency_min"])
        sectors = r["sector_tags"]
        events = r["event_tags"]
        for t in [x for x in r["ticker_candidates"].split(";") if x]:
            if _is_derivative(t):
                continue
            cur = out.setdefault(
                t,
                {
                    "news_score": 0.0,
                    "best_recency_min": 999999.0,
                    "news_hits": 0,
                    "sector_tags": set(),
                    "event_tags": set(),
                },
            )
            # F-3 fix: logarithmic diminishing returns for repeated coverage.
            # Tetlock (2011, AER): stale/repeated news has zero incremental signal.
            # k-th hit for same ticker contributes score / ln(k+1).
            hit_num = cur["news_hits"] + 1
            diminished = score / math.log(hit_num + 1) if hit_num > 1 else score
            cur["news_score"] += diminished
            cur["best_recency_min"] = min(cur["best_recency_min"], recency)
            cur["news_hits"] += 1
            cur["sector_tags"].update([x for x in sectors.split(";") if x])
            cur["event_tags"].update([x for x in events.split(";") if x])
    return out


def build_combined(sec_scores: dict[str, dict[str, float]], news_ticker: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    news_weight = float(CFG.get("news", {}).get("combined_news_weight", 0.8))
    universe = set(sec_scores.keys()) | set(news_ticker.keys())
    rows = []
    headline_only = []
    for t in universe:
        sec = sec_scores.get(t, {})
        news = news_ticker.get(t, {})
        sec_score = float(sec.get("sec_score", 0.0))
        news_score = float(news.get("news_score", 0.0))
        total = sec_score * 1.0 + news_score * news_weight
        row = {
            "ticker": t,
            "total_score": f"{total:.3f}",
            "sec_score": f"{sec_score:.3f}",
            "news_score": f"{news_score:.3f}",
            "gapper_score": f"{float(sec.get('gapper_score', 0.0)):.3f}",
            "value_score": f"{float(sec.get('value_score', 0.0)):.3f}",
            "moat_score": f"{float(sec.get('moat_score', 0.0)):.3f}",
            "news_hits": str(int(news.get("news_hits", 0))),
            "best_news_recency_min": f"{float(news.get('best_recency_min', 999999.0)):.1f}",
            "sector_tags": ";".join(sorted(news.get("sector_tags", set()))),
            "event_tags": ";".join(sorted(news.get("event_tags", set()))),
        }
        rows.append(row)
        if sec_score <= 0 and news_score > 0:
            headline_only.append(row)
    rows.sort(key=lambda r: float(r["total_score"]), reverse=True)
    headline_only.sort(key=lambda r: float(r["news_score"]), reverse=True)
    return rows, headline_only


def main() -> int:
    global CFG
    CFG = load_config()
    feed_rows = build_news_rows()
    bbg_rows = load_bloomberg_rows()
    av_rows = load_alphavantage_rows()
    wire_rows = load_wire_rows()
    poly_rows = load_polymarket_rows()
    gdacs_rows = load_gdacs_rows()
    eia_rows = load_eia_petroleum_rows()
    firms_rows = load_nasa_firms_rows()
    cf_rows = load_cloudflare_radar_rows()
    imf_rows = load_imf_portwatch_rows()
    news_rows = sorted(
        feed_rows + bbg_rows + av_rows + wire_rows
        + poly_rows + gdacs_rows + eia_rows + firms_rows
        + cf_rows + imf_rows,
        key=lambda r: float(r["news_score"]),
        reverse=True,
    )
    write_csv(
        OUT_NEWS_ROWS,
        news_rows,
        [
            "source",
            "tier",
            "ticker_explicit",
            "published_utc",
            "recency_min",
            "news_score",
            "sector_tags",
            "event_tags",
            "ticker_candidates",
            "headline",
            "link",
        ],
    )
    if bbg_rows:
        write_csv(
            OUT_BBG_USED,
            bbg_rows,
            [
                "source",
                "tier",
                "ticker_explicit",
                "published_utc",
                "recency_min",
                "news_score",
                "sector_tags",
                "event_tags",
                "ticker_candidates",
                "headline",
                "link",
            ],
        )
    else:
        with OUT_BBG_USED.open("w", encoding="utf-8") as f:
            f.write("source,tier,published_utc,recency_min,news_score,sector_tags,event_tags,ticker_candidates,headline,link\n")

    sector_rows = aggregate_sector(news_rows)
    write_csv(OUT_NEWS_SECTOR, sector_rows, ["sector", "sector_score", "mentions", "best_recency_min"])

    sec_scores = load_sec_scores()
    news_ticker = aggregate_news_by_ticker(news_rows)
    combined, headline_only = build_combined(sec_scores, news_ticker)
    write_csv(
        OUT_COMBINED,
        combined,
        [
            "ticker",
            "total_score",
            "sec_score",
            "news_score",
            "gapper_score",
            "value_score",
            "moat_score",
            "news_hits",
            "best_news_recency_min",
            "sector_tags",
            "event_tags",
        ],
    )
    with OUT_COMBINED_TICKERS.open("w", encoding="utf-8") as f:
        for r in combined[:80]:
            f.write(r["ticker"] + "\n")
    write_csv(
        OUT_HEADLINE_ONLY,
        headline_only,
        [
            "ticker",
            "total_score",
            "sec_score",
            "news_score",
            "gapper_score",
            "value_score",
            "moat_score",
            "news_hits",
            "best_news_recency_min",
            "sector_tags",
            "event_tags",
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
