#!/usr/bin/env python3
"""update_agent_knowledge.py — Keep the ElevenLabs voice agent current all day.

Called from:
  - Morning pipeline (after picks are built)          ~4am ET
  - post_open_recap.py (after market opens)           ~9:30am ET
  - post_midday_update.py (midday check-in)           ~1pm ET
  - post_eod_recap.py (after market close)            ~4:15pm ET
  - post_price_alert.py (whenever a pick moves big)   real-time

Each call rebuilds the full system prompt with the latest:
  - Today's top picks + scores + catalyst signals
  - Live intraday prices (from Yahoo Finance Spark API)
  - Polymarket prediction market signals
  - Macro context (if available)
  - Squeeze candidates in COILED/IGNITION stage
  - High-conviction convergence alerts
  - Dark pool and smart money signals (if available)

This ensures the agent at catalystedge.agency never talks about yesterday's picks
or stale data — she's always current to within the last pipeline run.

Required env vars:
    ELEVENLABS_API_KEY
    ELEVENLABS_AGENT_ID (or D_ID_AGENT_ID for D-ID agents)
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT  = Path(__file__).parent
TODAY = datetime.date.today().isoformat()

YAHOO_SPARK = "https://query2.finance.yahoo.com/v8/finance/spark?symbols={}&range=1d&interval=5m"


# ── Data helpers ──────────────────────────────────────────────────────────────

def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def fetch_live_prices(tickers: list[str]) -> dict[str, dict]:
    """Get intraday price/pct_change for each ticker via Yahoo Spark."""
    if not tickers:
        return {}
    url = YAHOO_SPARK.format(",".join(tickers))
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        out = {}
        for item in (data.get("spark", {}).get("result") or []):
            sym      = item.get("symbol", "").upper()
            response = (item.get("response") or [{}])[0]
            meta     = response.get("meta", {})
            closes   = response.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            closes   = [c for c in closes if c is not None]
            if not closes:
                continue
            prev = meta.get("previousClose") or meta.get("chartPreviousClose")
            curr = closes[-1]
            pct  = ((curr - prev) / prev * 100) if prev and prev > 0 else 0.0
            out[sym] = {"price": round(curr, 2), "pct_change": round(pct, 2)}
        return out
    except Exception:
        return {}


def load_polymarket() -> list[dict]:
    """Load fresh Polymarket signals (max 36h old)."""
    p = ROOT / "polymarket_signals.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        age_h = (datetime.datetime.now(datetime.timezone.utc) -
                 datetime.datetime.fromisoformat(data.get("generated_at", "1970-01-01T00:00:00+00:00"))
                 ).total_seconds() / 3600
        if age_h > 36:
            return []
        return [s for s in data.get("signals", []) if 10 <= s.get("probability", 0) <= 90][:4]
    except Exception:
        return []


def load_macro_context() -> str:
    """Load macro_context.json summary if available."""
    p = ROOT / "macro_context.json"
    if not p.exists():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        lines = []
        if data.get("fed_rate"):
            lines.append(f"Fed rate: {data['fed_rate']}")
        if data.get("vix"):
            lines.append(f"VIX: {data['vix']}")
        if data.get("market_regime"):
            lines.append(f"Market regime: {data['market_regime']}")
        if data.get("sector_leader"):
            lines.append(f"Leading sector: {data['sector_leader']}")
        return " | ".join(lines) if lines else ""
    except Exception:
        return ""


def signal_description(row: dict) -> str:
    """Friendly catalyst description from tags/form."""
    tags = (row.get("tags") or "").lower()
    tag_map = [
        ("fda_approval",         "FDA approval received"),
        ("fda_clearance",        "FDA clearance granted"),
        ("definitive_agreement", "definitive merger agreement signed"),
        ("contract_award",       "major contract awarded"),
        ("raises_guidance",      "guidance raised above consensus"),
        ("record_revenue",       "record revenue quarter reported"),
        ("earnings_beat",        "earnings beat — top and bottom line"),
        ("share_repurchase",     "share buyback authorized"),
        ("insider_buy",          "CEO/Director buying on open market"),
        ("special_dividend",     "special dividend declared"),
        ("patent",               "key patent filed or granted"),
    ]
    for key, desc in tag_map:
        if key in tags:
            return desc
    form_map = {
        "8-K": "material 8-K event filed",
        "4":   "Form 4 insider purchase",
        "SC 13D": "activist investor 13D filed",
        "6-K": "6-K foreign issuer disclosure",
    }
    return form_map.get(row.get("form", ""), "SEC catalyst filing detected")


# ── Knowledge text builder ─────────────────────────────────────────────────────

def build_knowledge_text() -> str:
    # ── Picks data ────────────────────────────────────────────────────────────
    picks_path = ROOT / "newsletter_picks.json"
    picks: dict = {}
    if picks_path.exists():
        try:
            picks = json.loads(picks_path.read_text())
        except Exception:
            pass

    top_pick = picks.get("top_pick", "N/A")
    top5     = picks.get("top5_tickers", [])
    total    = picks.get("total_combined", 0)
    g_count  = picks.get("gapper_count", 0)
    v_count  = picks.get("value_count", 0)
    m_count  = picks.get("moat_count", 0)

    # ── Top pick detail ───────────────────────────────────────────────────────
    top_row: dict = {}
    for fname in ["sec_top_gappers.csv", "sec_top_value.csv",
                  "sec_clean_gappers.csv", "combined_priority.csv"]:
        for r in read_csv(ROOT / fname):
            if r.get("ticker", "").strip().upper() == top_pick.upper():
                top_row = r
                break
        if top_row:
            break

    score    = (float(top_row.get("gapper_score") or 0) +
                float(top_row.get("value_score") or 0) +
                float(top_row.get("moat_score") or 0))
    signal   = signal_description(top_row)
    form     = top_row.get("form", "SEC filing")
    price    = top_row.get("price", "")

    category = "value play"
    gs = float(top_row.get("gapper_score") or 0)
    ms = float(top_row.get("moat_score") or 0)
    if gs >= ms and gs > 0:
        category = "gapper play — short-term momentum catalyst"
    elif ms > 0:
        category = "institutional moat play — longer-term positioning"

    # ── Live intraday prices ──────────────────────────────────────────────────
    live_prices = fetch_live_prices(top5[:5]) if top5 else {}

    # Determine market session (ET = UTC-4 in EDT, UTC-5 in EST)
    # Use UTC-4 (EDT) as default for March-November
    now_utc   = datetime.datetime.now(datetime.timezone.utc)
    et_offset = -4  # EDT; change to -5 for EST (Nov-Mar)
    now_et    = now_utc + datetime.timedelta(hours=et_offset)
    hour_et   = now_et.hour
    if hour_et < 9 or (hour_et == 9 and now_et.minute < 30):
        session = "pre-market"
    elif 9 <= hour_et < 16 or (hour_et == 9 and now_et.minute >= 30):
        session = "market hours"
    else:
        session = "after-hours"

    # ── Squeeze candidates ────────────────────────────────────────────────────
    squeeze_rows = read_csv(ROOT / "squeeze_candidates.csv")
    coiled   = [(r["ticker"], r.get("stage","")) for r in squeeze_rows
                if r.get("stage") in ("COILED", "IGNITION")][:4]

    # ── Convergence alerts ────────────────────────────────────────────────────
    conv_rows = read_csv(ROOT / "convergence_alerts.csv")
    high_conv = [(r["ticker"], r.get("conviction_level",""))
                 for r in conv_rows
                 if r.get("conviction_level") in ("HIGH", "ELEVATED")][:4]

    # ── Dark pool / smart money ───────────────────────────────────────────────
    dark_rows   = read_csv(ROOT / "dark_pool.csv")[:3]
    smart_rows  = read_csv(ROOT / "smart_money.csv")[:3]

    # ── Polymarket signals ────────────────────────────────────────────────────
    pm_signals = load_polymarket()

    # ── Macro context ─────────────────────────────────────────────────────────
    macro = load_macro_context()

    # ── Build the knowledge document ──────────────────────────────────────────
    date_display = datetime.date.today().strftime("%B %d, %Y")
    now_str      = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M UTC")

    lines = [
        f"=== CATALYST EDGE LIVE BRIEFING — {date_display} ({now_str}) ===",
        f"Market session: {session}",
        f"SEC filings scanned today: {total}",
        f"Setups found: {g_count} gappers | {v_count} value | {m_count} moat",
        "",
        f"★ TODAY'S TOP PICK: ${top_pick}",
        f"  Category: {category}",
        f"  Filing type: {form}",
        f"  Catalyst signal: {signal}",
    ]
    if price:
        lines.append(f"  Entry price reference: ${price}")
    if score > 0:
        lines.append(f"  Score: {score:.0f}/16")

    # Live price section
    if live_prices:
        lines += ["", "LIVE PRICES (as of now):"]
        for t in top5[:5]:
            q = live_prices.get(t.upper())
            if q:
                sign = "+" if q["pct_change"] >= 0 else ""
                move = f"{sign}{q['pct_change']:.1f}%"
                emoji = "🚀" if q["pct_change"] >= 3 else ("📈" if q["pct_change"] >= 0 else "📉")
                lines.append(f"  {emoji} ${t}: ${q['price']} ({move} today)")
            else:
                lines.append(f"  ${t}: price not yet available")

    # Top 5 list
    if top5:
        lines += ["", "TODAY'S FULL TOP 5 PICKS:"]
        for i, t in enumerate(top5[:5], 1):
            q = live_prices.get(t.upper())
            price_str = f" — currently ${q['price']}" if q else ""
            lines.append(f"  {i}. ${t}{price_str}")

    # Squeeze radar
    if coiled:
        lines += ["", "SQUEEZE RADAR (elevated short interest + catalyst):"]
        for t, stage in coiled:
            lines.append(f"  ${t} — {stage} stage")

    # Convergence alerts
    if high_conv:
        lines += ["", "HIGH-CONVICTION CONVERGENCE ALERTS:"]
        for t, level in high_conv:
            lines.append(f"  ${t} — {level}")

    # Smart money / dark pool
    dark_tickers  = [r.get("ticker","").upper() for r in dark_rows if r.get("ticker")]
    smart_tickers = [r.get("ticker","").upper() for r in smart_rows if r.get("ticker")]
    if dark_tickers:
        lines += ["", f"DARK POOL ACTIVITY: {', '.join('$'+t for t in dark_tickers)}"]
    if smart_tickers:
        lines += [f"SMART MONEY SIGNALS: {', '.join('$'+t for t in smart_tickers)}"]

    # Polymarket
    if pm_signals:
        lines += ["", "PREDICTION MARKET CONTEXT (Polymarket — current odds):"]
        for sig in pm_signals[:3]:
            prob   = sig.get("probability", 50)
            title  = sig.get("title", "")[:70]
            impact = sig.get("impact", "")
            label  = "LIKELY" if prob >= 60 else ("UNLIKELY" if prob <= 40 else "CONTESTED")
            lines.append(f"  {prob:.0f}% ({label}): \"{title}\" — {impact}")

    # Macro
    if macro:
        lines += ["", f"MACRO CONTEXT: {macro}"]

    lines += [
        "",
        "ABOUT CATALYST EDGE:",
        "Free daily newsletter that reads 300+ SEC EDGAR filings every morning",
        "before market open and ranks them by catalyst strength.",
        "Subscribe free: catalystedge.agency",
        "",
        "DISCLAIMER: This is for informational purposes only.",
        "Not financial advice. Always do your own research.",
    ]

    return "\n".join(lines)


# ── ElevenLabs agent updater ──────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """\
You are Catalyst — the voice of Catalyst Edge, a free daily SEC filing intelligence service.

Personality: Warm, confident, slightly British wit. Like a brilliant friend who happens to
work on Wall Street. Direct, never robotic. Keep answers punchy — this is a social media
audience, not a boardroom.

Your role:
- Share today's top stock picks from our SEC filing analysis
- Explain what catalysts are driving each pick (in plain English)
- Discuss live price moves and what they mean
- Share Polymarket prediction market context when asked about the macro
- Invite visitors to subscribe free at catalystedge.agency
- When asked how you work or what AI powers you, mention ElevenLabs and share the referral link

RULES:
1. ONLY use the data section below for pick names and prices. Do NOT invent or guess tickers.
2. For macro questions, you CAN use general market knowledge, but ground it in the data below.
3. Always end with: "This is for informational purposes only — not financial advice. Always DYOR."
4. If asked about a ticker NOT in today's data, say you haven't analyzed it today but invite
   them to subscribe for tomorrow's scan.
5. If someone asks "what AI are you?", "how does your voice work?", or "what technology powers you?",
   say: "I'm built on ElevenLabs — their conversational AI is genuinely impressive.
   If you want to build something similar, you can try it free at try.elevenlabs.io/i8s2iekmmq5m"

{knowledge_text}
"""


def update_elevenlabs_agent(knowledge_text: str) -> bool:
    api_key  = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    agent_id = (os.environ.get("ELEVENLABS_AGENT_ID", "").strip() or
                os.environ.get("D_ID_AGENT_ID", "").strip())

    if not api_key:
        print("update_agent_knowledge: ELEVENLABS_API_KEY not set — skipping")
        return False
    if not agent_id:
        print("update_agent_knowledge: ELEVENLABS_AGENT_ID not set — skipping")
        return False

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(knowledge_text=knowledge_text)

    payload = json.dumps({
        "conversation_config": {
            "agent": {
                "prompt": {"prompt": system_prompt}
            }
        }
    }).encode("utf-8")

    request = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/convai/agents/{agent_id}",
        data=payload,
        method="PATCH",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as r:
            r.read()
        print(f"  ElevenLabs agent updated — {len(knowledge_text)} chars of live data injected")
        return True
    except urllib.error.HTTPError as e:
        print(f"  ElevenLabs PATCH failed {e.code}: {e.read().decode()[:200]}")
        return False
    except Exception as e:
        print(f"  ElevenLabs update error: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"update_agent_knowledge: rebuilding agent knowledge ({TODAY})...")

    knowledge_text = build_knowledge_text()
    print(f"  Knowledge text: {len(knowledge_text)} chars")

    # Show a preview of what the agent knows
    preview_lines = knowledge_text.split("\n")[:12]
    for line in preview_lines:
        print(f"  | {line}")
    print("  | ...")

    success = update_elevenlabs_agent(knowledge_text)

    if success:
        # Save a local copy for debugging
        out = ROOT / f"agent_knowledge_{TODAY}.txt"
        out.write_text(knowledge_text, encoding="utf-8")
        print(f"  Local copy: {out}")
        print("update_agent_knowledge: done — agent is now current")
        return 0
    else:
        # Still save the knowledge text even if upload failed
        out = ROOT / f"agent_knowledge_{TODAY}.txt"
        out.write_text(knowledge_text, encoding="utf-8")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
