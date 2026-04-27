#!/usr/bin/env python3
"""run_telegram_bot.py — Interactive Catalyst Edge Telegram bot.

Runs as a persistent polling bot. Responds to commands in DMs and in any
group it's added to. Every response ends with a newsletter CTA.

Commands:
  /start    — welcome message + what the bot does
  /picks    — today's full top 5 picks
  /top      — #1 pick with full catalyst detail
  /squeeze  — squeeze radar (COILED/IGNITION tickers)
  /polymarket — current prediction market signals
  /help     — command list + newsletter link

Also responds when anyone mentions $TICKER in a group — looks it up
in today's picks and replies with signal data if found.

Run persistently:
    python3 run_telegram_bot.py

Or as a background service (see install_telegram_bot_service.sh)

Required env vars:
    TELEGRAM_BOT_TOKEN
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT           = Path(__file__).parent
NEWSLETTER_URL = "https://catalystedge.agency"
AGENCY_URL     = "https://www.catalystedge.agency"
ELEVENLABS_REF = "https://try.elevenlabs.io/i8s2iekmmq5m"
DISCORD_URL    = "https://discord.gg/8aJEHghHVy"
BOT_TOKEN      = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API_BASE       = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Seen update IDs to avoid re-processing
_seen: set[int] = set()


# ── Telegram API helpers ──────────────────────────────────────────────────────

def tg_get(method: str, params: dict | None = None) -> dict:
    url = f"{API_BASE}/{method}"
    if params:
        url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def tg_post(method: str, payload: dict) -> dict:
    import urllib.parse
    url  = f"{API_BASE}/{method}"
    body = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(url, data=body,
                                   headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  tg_post error: {e}")
        return {}


def send(chat_id: int | str, text: str, reply_to: int | None = None) -> None:
    payload: dict = {
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    tg_post("sendMessage", payload)


import urllib.parse  # noqa: E402 (needed above)


# ── Data loaders ──────────────────────────────────────────────────────────────

def load_picks() -> dict:
    p = ROOT / "newsletter_picks.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def load_polymarket() -> list[dict]:
    p = ROOT / "polymarket_signals.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        age_h = (datetime.datetime.now(datetime.timezone.utc) -
                 datetime.datetime.fromisoformat(
                     data.get("generated_at", "1970-01-01T00:00:00+00:00"))
                 ).total_seconds() / 3600
        if age_h > 36:
            return []
        return [s for s in data.get("signals", [])
                if 10 <= s.get("probability", 0) <= 90][:5]
    except Exception:
        return []


def get_ticker_detail(ticker: str) -> dict:
    """Full row for a ticker from any clean CSV."""
    for fname in ["sec_clean_gappers.csv", "sec_clean_value.csv",
                  "sec_top_gappers.csv", "sec_top_value.csv",
                  "combined_priority.csv"]:
        for row in read_csv(ROOT / fname):
            if row.get("ticker", "").upper() == ticker.upper():
                return row
    return {}


def signal_label(row: dict) -> str:
    tags = (row.get("tags") or "").lower()
    tag_map = [
        ("fda_approval",         "FDA approval ✅"),
        ("fda_clearance",        "FDA clearance ✅"),
        ("definitive_agreement", "merger agreement 🤝"),
        ("contract_award",       "contract award 📋"),
        ("raises_guidance",      "raised guidance 📈"),
        ("record_revenue",       "record revenue 💰"),
        ("earnings_beat",        "earnings beat 💪"),
        ("share_repurchase",     "buyback authorized 🔄"),
        ("insider_buy",          "insider buying 👤"),
        ("special_dividend",     "special dividend 💵"),
        ("patent",               "patent filing 📜"),
    ]
    for key, label in tag_map:
        if key in tags:
            return label
    form_map = {
        "8-K":    "8-K event filing 📄",
        "4":      "Form 4 insider buy 👤",
        "SC 13D": "activist 13D 🎯",
        "6-K":    "6-K foreign filing 🌐",
    }
    return form_map.get(row.get("form", ""), "SEC catalyst filing 📄")


def get_score(row: dict) -> str:
    for col in ["total_score", "gapper_score", "value_score", "moat_score"]:
        try:
            v = float(row.get(col, ""))
            return f"{v:.1f}"
        except (ValueError, TypeError):
            pass
    return ""


# ── Response builders ─────────────────────────────────────────────────────────

def resp_start() -> str:
    return (
        "⚡ *Welcome to Catalyst Edge Bot*\n\n"
        "I scan 300+ SEC EDGAR filings every morning before the market opens "
        "and deliver the highest-conviction catalyst plays — free.\n\n"
        "*Commands:*\n"
        "/picks — today's top 5 picks\n"
        "/top — #1 pick with full detail\n"
        "/squeeze — squeeze radar\n"
        "/polymarket — prediction market signals\n"
        "/help — full command list\n\n"
        f"📬 *Free daily newsletter:* {NEWSLETTER_URL}\n"
        f"💬 *Discord community:* {DISCORD_URL}\n"
        f"🎙️ *Talk to Catalyst AI:* {AGENCY_URL}"
    )


def resp_help() -> str:
    return (
        "⚡ *Catalyst Edge Bot — Commands*\n\n"
        "/picks — today's full top 5 SEC catalyst picks\n"
        "/top — #1 pick with signal, score, and filing detail\n"
        "/squeeze — tickers in COILED or IGNITION squeeze stage\n"
        "/polymarket — live Polymarket prediction market signals\n"
        "/start — about this bot\n\n"
        "💡 *Tip:* Mention any `$TICKER` in the chat and I'll check "
        "if it's in today's picks.\n\n"
        f"📬 Free daily picks: {NEWSLETTER_URL}\n"
        f"💬 Discord community: {DISCORD_URL}\n"
        f"🎙️ AI voice agent: {AGENCY_URL}"
    )


def resp_picks() -> str:
    picks = load_picks()
    if not picks:
        return (
            "⚠️ Today's picks aren't ready yet — pipeline runs at 4am ET.\n\n"
            f"Subscribe to get them by email: {NEWSLETTER_URL}"
        )

    top5     = picks.get("top5_tickers", [])
    top_pick = picks.get("top_pick", "")
    total    = picks.get("total_combined", 0)
    date     = picks.get("date", datetime.date.today().isoformat())

    if top_pick and top_pick not in top5:
        top5 = [top_pick] + top5[:4]

    emojis = ["🥇", "🥈", "🥉", "📌", "📌"]
    lines  = []
    for i, t in enumerate(top5[:5]):
        row    = get_ticker_detail(t)
        sig    = signal_label(row) if row else "SEC catalyst"
        score  = get_score(row)
        score_str = f" | Score {score}" if score else ""
        em = emojis[i] if i < len(emojis) else "📌"
        lines.append(f"{em} *${t}*{score_str}\n    ↳ {sig}")

    picks_text = "\n\n".join(lines)

    return (
        f"⚡ *TOP 5 PICKS — {date}*\n"
        f"_{total}+ SEC filings scanned_\n\n"
        f"{picks_text}\n\n"
        f"📬 Full breakdown + free newsletter:\n{NEWSLETTER_URL}"
    )


def resp_top() -> str:
    picks = load_picks()
    if not picks:
        return f"⚠️ No picks yet today. Subscribe for 4am delivery: {NEWSLETTER_URL}"

    top_pick = picks.get("top_pick", "")
    top5     = picks.get("top5_tickers", [])
    if not top_pick and top5:
        top_pick = top5[0]
    if not top_pick:
        return f"⚠️ No picks found. Check back after 4am ET: {NEWSLETTER_URL}"

    row   = get_ticker_detail(top_pick)
    sig   = signal_label(row) if row else "SEC catalyst"
    score = get_score(row)
    form  = row.get("form", "SEC filing") if row else "SEC filing"
    price = row.get("price", "") if row else ""

    others = [f"${t}" for t in top5 if t != top_pick][:4]
    others_str = " · ".join(others) if others else ""

    score_display = f"{min(float(score), 10.0):.1f}" if score else ""
    score_line = f"*Score:* {score_display}/10\n" if score_display else ""
    price_line = f"*Entry ref:* ${price}\n" if price else ""
    others_line = f"*Also watching:* {others_str}\n" if others_str else ""

    return (
        f"🥇 *TOP PICK: ${top_pick}*\n\n"
        f"*Signal:* {sig}\n"
        f"*Filing:* {form}\n"
        f"{score_line}"
        f"{price_line}"
        f"{others_line}\n"
        f"This is sourced from live SEC EDGAR filings — public data "
        f"that most traders never read.\n\n"
        f"📬 Full breakdown: {NEWSLETTER_URL}\n"
        f"🎙️ Ask Catalyst AI: {AGENCY_URL}"
    )


def resp_squeeze() -> str:
    rows   = read_csv(ROOT / "squeeze_candidates.csv")
    coiled = [(r.get("ticker","").upper(), r.get("stage",""),
               r.get("short_interest",""), r.get("dtc",""))
              for r in rows if r.get("stage") in ("COILED","IGNITION")][:6]

    if not coiled:
        return (
            "📊 No squeeze setups in COILED or IGNITION stage today.\n\n"
            f"Check tomorrow's scan: {NEWSLETTER_URL}"
        )

    lines = []
    for t, stage, si, dtc in coiled:
        si_str  = f" | SI: {si}%" if si else ""
        dtc_str = f" | DTC: {dtc}" if dtc else ""
        emoji   = "🔥" if stage == "IGNITION" else "🌀"
        lines.append(f"{emoji} *${t}* — {stage}{si_str}{dtc_str}")

    return (
        "🔥 *SQUEEZE RADAR*\n"
        "_Elevated short interest + SEC catalyst_\n\n"
        + "\n".join(lines) + "\n\n"
        "These are tickers where a catalyst could force short covering.\n\n"
        f"📬 Full analysis: {NEWSLETTER_URL}"
    )


def resp_polymarket() -> str:
    signals = load_polymarket()
    if not signals:
        return (
            "📊 No fresh Polymarket signals available right now.\n"
            "Data refreshes daily at 4am ET.\n\n"
            f"Subscribe: {NEWSLETTER_URL}"
        )

    lines = []
    for s in signals[:5]:
        prob   = s.get("probability", 50)
        title  = s.get("title", "")[:60]
        impact = s.get("impact", "")
        label  = "🟢 LIKELY" if prob >= 60 else ("🔴 UNLIKELY" if prob <= 40 else "🟡 CONTESTED")
        lines.append(f"{label} *{prob:.0f}%*\n_{title}_\n→ {impact}")

    return (
        "🎲 *POLYMARKET SIGNALS*\n"
        "_Live prediction market odds_\n\n"
        + "\n\n".join(lines) + "\n\n"
        f"📬 We combine this with SEC data daily: {NEWSLETTER_URL}"
    )


def resp_ticker(ticker: str) -> str | None:
    """Check if ticker is in today's picks and respond with detail."""
    picks = load_picks()
    top5  = picks.get("top5_tickers", [])
    top_pick = picks.get("top_pick", "")
    all_picks = list({top_pick} | set(top5)) if top_pick else top5

    if ticker.upper() not in [t.upper() for t in all_picks]:
        return None  # Not in picks — don't respond to avoid noise

    row   = get_ticker_detail(ticker)
    sig   = signal_label(row) if row else "SEC catalyst"
    score = get_score(row)
    rank  = "🥇 TOP PICK" if ticker.upper() == top_pick.upper() else "📌 In today's picks"

    score_display = f"{min(float(score), 10.0):.1f}" if score else ""
    score_str = f" | Score {score_display}/10" if score_display else ""
    return (
        f"{rank}: *${ticker.upper()}*{score_str}\n"
        f"Signal: {sig}\n\n"
        f"Sourced from SEC EDGAR this morning.\n"
        f"Full breakdown: {NEWSLETTER_URL}"
    )


# ── Inline query handler ──────────────────────────────────────────────────────

def answer_inline(query_id: str, results: list[dict]) -> None:
    tg_post("answerInlineQuery", {
        "inline_query_id":    query_id,
        "results":            results,
        "cache_time":         60,    # 1 min — picks update daily, stay fresh
        "is_personal":        False, # same picks for everyone, allow caching
    })


def inline_article(uid: str, title: str, description: str, text: str) -> dict:
    return {
        "type":  "article",
        "id":    uid,
        "title": title,
        "description": description,
        "input_message_content": {
            "message_text":             text,
            "parse_mode":               "Markdown",
            "disable_web_page_preview": True,
        },
    }


def process_inline(update: dict) -> None:
    q = update.get("inline_query", {})
    query_id = q.get("id", "")
    raw      = (q.get("query") or "").strip().lower()
    username = q.get("from", {}).get("username", "unknown")

    print(f"  [inline] @{username}: '{raw}'")

    import re
    results = []

    # Known command keywords — skip ticker lookup for these to avoid false matches
    # ('top', 'picks', 'help' are valid 1-5 letter strings but not tickers)
    _CMD_KEYWORDS = {"picks", "top", "help", "start", "squeeze", "polymarket",
                     "play", "today", "best", "sec", "all", "what", "how"}

    # ── Ticker lookup ──────────────────────────────────────────────────────────
    ticker_match = re.match(r'^\$?([A-Za-z]{1,5})$', raw)
    if ticker_match and raw.lstrip("$").lower() not in _CMD_KEYWORDS:
        ticker = ticker_match.group(1).upper()
        resp = resp_ticker(ticker)
        if resp:
            results.append(inline_article(
                f"ticker_{ticker}",
                f"${ticker} — in today's picks ✅",
                "Tap to share this signal in chat",
                resp,
            ))
        else:
            # Ticker not in today's picks — offer the full picks list instead
            results.append(inline_article(
                f"ticker_miss_{ticker}",
                f"${ticker} not in today's picks",
                "Tap to share today's top 5 picks instead",
                resp_picks(),
            ))

    # ── Keyword routing ────────────────────────────────────────────────────────
    # If query is empty, show all cards (default menu)
    if not raw:
        show_picks = show_top = show_squeeze = show_polymarket = True
        show_help  = False  # Don't waste a slot on help when everything else shows
    else:
        show_picks      = any(k in raw for k in ("pick", "top", "today", "play", "sec", "best", "all"))
        show_top        = any(k in raw for k in ("top", "pick", "#1", "best", "number one"))
        show_squeeze    = any(k in raw for k in ("squeeze", "short", "coil", "ignit"))
        show_polymarket = any(k in raw for k in ("poly", "market", "odds", "predict", "bet"))
        show_help       = any(k in raw for k in ("help", "command", "how", "what", "use"))

    # Only add picks if no ticker card already covers today's picks
    ticker_card_present = any(r["id"].startswith("ticker_") for r in results)

    if show_picks and not ticker_card_present:
        results.append(inline_article(
            "picks",
            "⚡ Today's Top 5 SEC Catalyst Picks",
            "Share today's full pick list in this chat",
            resp_picks(),
        ))

    if show_top and not any(r["id"] == "top" for r in results):
        results.append(inline_article(
            "top",
            "🥇 #1 Pick — Full Detail",
            "Share the top pick with signal, score & filing",
            resp_top(),
        ))

    if show_squeeze:
        results.append(inline_article(
            "squeeze",
            "🔥 Squeeze Radar — COILED & IGNITION",
            "Share tickers with elevated short interest + catalyst",
            resp_squeeze(),
        ))

    if show_polymarket:
        results.append(inline_article(
            "polymarket",
            "🎲 Polymarket Prediction Market Signals",
            "Share live Polymarket odds relevant to the market",
            resp_polymarket(),
        ))

    # Help: only add if nothing else matched (fallback) or explicitly requested
    if show_help or not results:
        results.append(inline_article(
            "help",
            "📋 How to Use Catalyst Edge Bot",
            "Try: picks · top · squeeze · $TICKER",
            resp_help(),
        ))

    # Telegram allows up to 50 results; we cap at 5 for clean UX
    # Help is already only added when needed so the cap won't drop it
    answer_inline(query_id, results[:5])


# ── Update processor ──────────────────────────────────────────────────────────

def process_update(update: dict) -> None:
    uid = update.get("update_id", 0)
    if uid in _seen:
        return
    _seen.add(uid)

    # Handle inline queries (works in any group without being added)
    if "inline_query" in update:
        process_inline(update)
        return

    msg = update.get("message") or update.get("channel_post")
    if not msg:
        return

    chat_id = msg.get("chat", {}).get("id")
    msg_id  = msg.get("message_id")
    text    = (msg.get("text") or "").strip()

    if not text or not chat_id:
        return

    chat_type = msg.get("chat", {}).get("type", "")
    is_group  = chat_type in ("group", "supergroup")

    # In groups, only respond to commands or $TICKER mentions
    # (avoid responding to every message)
    cmd = text.split()[0].lower().split("@")[0] if text.startswith("/") else ""

    reply_to = msg_id if is_group else None

    if cmd == "/start":
        send(chat_id, resp_start(), reply_to)
    elif cmd == "/picks":
        send(chat_id, resp_picks(), reply_to)
    elif cmd == "/top":
        send(chat_id, resp_top(), reply_to)
    elif cmd == "/squeeze":
        send(chat_id, resp_squeeze(), reply_to)
    elif cmd == "/polymarket":
        send(chat_id, resp_polymarket(), reply_to)
    elif cmd == "/help":
        send(chat_id, resp_help(), reply_to)
    elif not cmd:
        # Look for $TICKER mentions in any message
        import re
        tickers = re.findall(r'\$([A-Z]{1,5})\b', text.upper())
        for ticker in tickers[:2]:  # Max 2 tickers per message
            response = resp_ticker(ticker)
            if response:
                send(chat_id, response, reply_to)
                break  # Only respond once per message

    # Log
    username = msg.get("from", {}).get("username", "unknown")
    print(f"  [{datetime.datetime.now().strftime('%H:%M:%S')}] "
          f"{chat_type} @{username}: {text[:60]}")


# ── Polling loop ──────────────────────────────────────────────────────────────

def run_bot() -> None:
    if not BOT_TOKEN:
        print("run_telegram_bot: TELEGRAM_BOT_TOKEN not set — exiting")
        return

    print(f"run_telegram_bot: starting polling loop")
    print(f"  Bot: t.me/CatalystEdgeBot")
    print(f"  Channel: @CatalystEdgeDaily")
    print(f"  Commands: /start /picks /top /squeeze /polymarket /help")
    print(f"  Inline: @CatalystEdgeBot picks  (works in ANY group)")
    print(f"  Press Ctrl+C to stop\n")

    offset = 0
    while True:
        try:
            result = tg_get("getUpdates", {
                "offset":          offset,
                "timeout":         25,
                "allowed_updates": '["message","channel_post","inline_query"]',
            })
            updates = result.get("result", [])
            for update in updates:
                process_update(update)
                offset = max(offset, update.get("update_id", 0) + 1)
        except KeyboardInterrupt:
            print("\nrun_telegram_bot: stopped")
            break
        except Exception as e:
            print(f"  polling error: {e} — retrying in 5s")
            time.sleep(5)


if __name__ == "__main__":
    run_bot()
