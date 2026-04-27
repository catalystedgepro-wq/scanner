#!/usr/bin/env python3
"""setup_elevenlabs_agent.py — One-time setup: create the Catalyst Edge voice agent.

Creates an ElevenLabs Conversational AI agent (Lily voice) with today's picks as
its knowledge base. Saves the agent ID to .sec_email_env and prints the Beehiiv
embed code.

Usage:
    python3 setup_elevenlabs_agent.py
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import sys
from pathlib import Path

try:
    from elevenlabs.client import ElevenLabs
except ImportError:
    print("ERROR: pip install --break-system-packages elevenlabs")
    sys.exit(1)

ROOT      = Path(__file__).parent
ENV_FILE  = ROOT / ".sec_email_env"
TODAY     = datetime.date.today().isoformat()
TODAY_DISPLAY = datetime.date.today().strftime("%B %d, %Y")

LILY_VOICE_ID = "pFZP5JQG7iQjIQuC4Bku"

SYSTEM_PROMPT = """\
You are Catalyst — the voice of Catalyst Edge, a free daily SEC filing intelligence service.
You speak with a warm, confident British accent. You are knowledgeable, direct, and engaging.
Your job is to share today's top stock picks from our SEC filing analysis, explain the signals
behind them, and invite the visitor to subscribe to our free daily newsletter.

Always lead with the most exciting information — the top pick and its score.
Keep answers concise and punchy — this is a social media audience, not a boardroom.
After sharing picks, always invite them to subscribe at catalystedge.agency for free.

IMPORTANT: Always end with a financial disclaimer:
"This is for informational purposes only and not financial advice. Always do your own research."

Personality: Confident, warm, slightly British wit. Like a brilliant friend who happens to
work on Wall Street. Not robotic. Not overly formal. Conversational and engaging.
"""

FIRST_MESSAGE = (
    "Welcome to Catalyst Edge — I'm Catalyst, your AI stock analyst. "
    "I've just finished scanning today's SEC filings. "
    "Want to hear today's top pick and the signals behind it?"
)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def build_knowledge_text() -> str:
    """Build a rich text summary of today's picks for the agent's knowledge base."""
    picks_path = ROOT / "newsletter_picks.json"
    picks = {}
    if picks_path.exists():
        try:
            picks = json.loads(picks_path.read_text())
        except Exception:
            pass

    top_pick   = picks.get("top_pick", "N/A")
    top5       = picks.get("top5_tickers", [])
    total      = picks.get("total_combined", 0)
    g_count    = picks.get("gapper_count", 0)
    v_count    = picks.get("value_count", 0)
    m_count    = picks.get("moat_count", 0)

    # Find row data for top pick
    top_row = {}
    for f in ["sec_top_gappers.csv", "sec_top_value.csv", "sec_top_moat.csv", "combined_priority.csv"]:
        for r in read_csv(ROOT / f):
            if r.get("ticker", "").strip().upper() == top_pick.upper():
                top_row = r
                break
        if top_row:
            break

    gs = float(top_row.get("gapper_score", 0) or 0)
    vs = float(top_row.get("value_score", 0) or 0)
    ms = float(top_row.get("moat_score", 0) or 0)
    score = gs + vs + ms
    form  = top_row.get("form", "SEC filing")
    tags  = [t.lstrip("+").strip() for t in top_row.get("tags", "").split(";")
             if t.strip().startswith("+")][:3]

    category = "value play"
    if gs >= ms and gs >= vs and gs > 0:
        category = "gapper play — high momentum"
    elif ms >= vs and ms > 0:
        category = "institutional moat play"

    # Build squeeze / convergence context
    squeeze_rows = read_csv(ROOT / "squeeze_candidates.csv")
    coiled = [r["ticker"] for r in squeeze_rows
              if r.get("stage") in ("COILED", "IGNITION")][:3]

    conv_rows = read_csv(ROOT / "convergence_alerts.csv")
    high_conv = [r["ticker"] for r in conv_rows
                 if r.get("conviction_level") in ("HIGH", "ELEVATED")][:4]

    lines = [
        f"=== CATALYST EDGE — DAILY BRIEFING: {TODAY_DISPLAY} ===",
        "",
        f"Total SEC filings scanned today: {total}",
        f"Catalyst setups identified: {g_count} gappers | {v_count} value | {m_count} moat",
        "",
        f"TODAY'S TOP PICK: ${top_pick}",
        f"Category: {category}",
        f"Catalyst score: {score:.0f}/16",
        f"Filing type: {form}",
    ]
    if tags:
        lines.append(f"Signals: {', '.join(tags)}")

    if top5:
        lines += [
            "",
            "TOP 5 TICKERS TODAY:",
        ]
        for t in top5[:5]:
            lines.append(f"  ${t}")

    if coiled:
        lines += [
            "",
            "SHORT SQUEEZE RADAR (COILED / IGNITION stage):",
            *[f"  ${t}" for t in coiled],
        ]

    if high_conv:
        lines += [
            "",
            "HIGH-CONVICTION CONVERGENCE ALERTS (multiple signals aligned):",
            *[f"  ${t}" for t in high_conv],
        ]

    lines += [
        "",
        "HOW THE SCORING WORKS:",
        "Each ticker is scored 0-16 across three dimensions:",
        "  Gapper score: momentum, volume surge, short-float, catalyst type",
        "  Value score: P/E, P/B, debt levels, insider buying signals",
        "  Moat score: institutional positioning, revenue trend, filing quality",
        "Scores above 8 are worth watching. Above 12 are high-priority setups.",
        "",
        "ABOUT CATALYST EDGE:",
        "Free daily newsletter at catalystedge.agency",
        "Published every morning before 4 AM ET — before the market opens.",
        "Scans hundreds of SEC filings (8-K, Form 4, S-3, 13-D) overnight.",
        "Zero cost. No paywall. Subscribe free.",
        "",
        "DISCLAIMER:",
        "This is for informational purposes only and is not financial advice.",
        "Always conduct your own research before making any investment decisions.",
    ]

    return "\n".join(lines)


def save_agent_id(agent_id: str):
    """Append or update ELEVENLABS_AGENT_ID in .sec_email_env."""
    content = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    if "ELEVENLABS_AGENT_ID=" in content:
        lines = content.splitlines()
        lines = [f"ELEVENLABS_AGENT_ID={agent_id}" if l.startswith("ELEVENLABS_AGENT_ID=") else l
                 for l in lines]
        ENV_FILE.write_text("\n".join(lines) + "\n")
    else:
        with ENV_FILE.open("a") as f:
            f.write(f"\n# ElevenLabs Conversational Agent\nELEVENLABS_AGENT_ID={agent_id}\n")
    print(f"  Saved ELEVENLABS_AGENT_ID={agent_id} to .sec_email_env")


def print_embed_code(agent_id: str):
    embed = f"""
<!-- ════════════════════════════════════════════════════════
     Catalyst Edge — Voice Agent Widget
     Paste this into your Beehiiv page / website HTML
     ════════════════════════════════════════════════════════ -->
<elevenlabs-convai agent-id="{agent_id}"></elevenlabs-convai>
<script src="https://elevenlabs.io/convai-widget/index.js" async type="text/javascript"></script>
"""
    print("\n" + "="*60)
    print("BEEHIIV EMBED CODE — paste into your newsletter page:")
    print("="*60)
    print(embed)
    print("="*60)

    # Also write to file for easy copy
    embed_file = ROOT / "elevenlabs_widget_embed.html"
    embed_file.write_text(embed.strip())
    print(f"\nEmbed code also saved to: {embed_file}")


def main():
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ELEVENLABS_API_KEY not set in .sec_email_env")
        sys.exit(1)

    client = ElevenLabs(api_key=api_key)

    # Check if agent already exists
    existing_id = os.environ.get("ELEVENLABS_AGENT_ID", "").strip()
    if existing_id:
        print(f"Agent already exists: {existing_id}")
        print("To recreate, remove ELEVENLABS_AGENT_ID from .sec_email_env first.")
        print_embed_code(existing_id)
        return

    print("Creating Catalyst Edge voice agent...")

    # Build today's knowledge text
    knowledge_text = build_knowledge_text()
    print(f"  Knowledge base: {len(knowledge_text)} chars")

    # Create the agent (no KB yet — add after)
    print("  Creating agent...")
    agent = client.conversational_ai.agents.create(
        name="Catalyst Edge — Daily Picks",
        conversation_config={
            "agent": {
                "prompt": {
                    "prompt": SYSTEM_PROMPT,
                    "llm": "claude-3-5-sonnet",
                    "first_message": FIRST_MESSAGE,
                },
                "first_message": FIRST_MESSAGE,
            },
            "tts": {"voice_id": LILY_VOICE_ID},
        },
    )

    agent_id = agent.agent_id
    print(f"  Agent created: {agent_id}")

    # Attach knowledge base as a text document
    print("  Attaching knowledge base...")
    import io
    kb_bytes = knowledge_text.encode("utf-8")
    client.conversational_ai.add_to_knowledge_base(
        agent_id=agent_id,
        name=f"catalyst_edge_picks_{TODAY}",
        file=("catalyst_picks.txt", io.BytesIO(kb_bytes), "text/plain"),
    )
    print(f"  Knowledge base attached.")

    save_agent_id(agent_id)
    print_embed_code(agent_id)
    print(f"\nDone! Your voice agent is live.")
    print(f"Test it at: https://elevenlabs.io/app/conversational-ai/agents/{agent_id}")


if __name__ == "__main__":
    main()
