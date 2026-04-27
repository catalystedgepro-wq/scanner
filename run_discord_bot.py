#!/usr/bin/env python3
"""run_discord_bot.py — Catalyst Edge Discord bot.

Responds to slash commands and $TICKER mentions in any server it's added to.
Uses rich embeds for professional formatting. Every response includes a CTA.

Slash commands:
  /picks      — today's top 5 picks (rich embed)
  /top        — #1 pick with full detail
  /squeeze    — squeeze radar (COILED/IGNITION tickers)
  /polymarket — prediction market signals
  /help       — command list + invite link

Also watches messages for $TICKER mentions and responds with pick data.

Setup:
  1. Go to discord.com/developers/applications → New Application
  2. Bot tab → Add Bot → copy token → set DISCORD_BOT_TOKEN in .sec_email_env
  3. Bot tab → enable "Message Content Intent"
  4. OAuth2 → URL Generator → scopes: bot, applications.commands
     permissions: Send Messages, Embed Links, Read Message History
  5. Use the generated URL to add the bot to servers
  6. python3 run_discord_bot.py

Required env vars:
    DISCORD_BOT_TOKEN
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import re
from pathlib import Path

import discord
from discord import app_commands

ROOT           = Path(__file__).parent
NEWSLETTER_URL = "https://catalystedge.agency"
AGENCY_URL     = "https://www.catalystedge.agency"
ELEVENLABS_REF = "https://try.elevenlabs.io/i8s2iekmmq5m"
DISCORD_INVITE = "https://discord.gg/8aJEHghHVy"
TELEGRAM_URL   = "https://t.me/CatalystEdgeDaily"
BOT_TOKEN      = os.environ.get("DISCORD_BOT_TOKEN", "")

# Brand colors
COLOR_GOLD    = 0xFFD700
COLOR_GREEN   = 0x00C853
COLOR_BLUE    = 0x1565C0
COLOR_RED     = 0xE53935
COLOR_PURPLE  = 0x7B1FA2
COLOR_GREY    = 0x546E7A


# ── Data loaders (identical to Telegram bot) ──────────────────────────────────

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
        ("definitive_agreement", "Merger agreement 🤝"),
        ("contract_award",       "Contract award 📋"),
        ("raises_guidance",      "Raised guidance 📈"),
        ("record_revenue",       "Record revenue 💰"),
        ("earnings_beat",        "Earnings beat 💪"),
        ("share_repurchase",     "Buyback authorized 🔄"),
        ("insider_buy",          "Insider buying 👤"),
        ("special_dividend",     "Special dividend 💵"),
        ("patent",               "Patent filing 📜"),
    ]
    for key, label in tag_map:
        if key in tags:
            return label
    form_map = {
        "8-K":    "8-K event filing 📄",
        "4":      "Form 4 insider buy 👤",
        "SC 13D": "Activist 13D 🎯",
        "6-K":    "6-K foreign filing 🌐",
    }
    return form_map.get(row.get("form", ""), "SEC catalyst filing 📄")


def get_score(row: dict) -> float | None:
    for col in ["total_score", "gapper_score", "value_score", "moat_score"]:
        try:
            return min(float(row.get(col, "")), 10.0)
        except (ValueError, TypeError):
            pass
    return None


# ── Embed builders ────────────────────────────────────────────────────────────

def embed_no_picks() -> discord.Embed:
    e = discord.Embed(
        title="⚠️ Picks not ready yet",
        description="The pipeline runs at **4am ET** every weekday.\nSubscribe to get them delivered to your inbox.",
        color=COLOR_GREY,
    )
    e.add_field(name="📬 Free newsletter", value=NEWSLETTER_URL, inline=False)
    return e


def embed_picks() -> discord.Embed:
    picks = load_picks()
    if not picks:
        return embed_no_picks()

    top5     = picks.get("top5_tickers", [])
    top_pick = picks.get("top_pick", "")
    total    = picks.get("total_combined", 0)
    date     = picks.get("date", datetime.date.today().isoformat())

    if top_pick and top_pick not in top5:
        top5 = [top_pick] + top5[:4]

    e = discord.Embed(
        title=f"⚡ TOP 5 PICKS — {date}",
        description=f"_{total}+ SEC filings scanned this morning_",
        color=COLOR_GREEN,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )

    emojis = ["🥇", "🥈", "🥉", "📌", "📌"]
    for i, t in enumerate(top5[:5]):
        row   = get_ticker_detail(t)
        sig   = signal_label(row) if row else "SEC catalyst filing 📄"
        score = get_score(row)
        em    = emojis[i] if i < len(emojis) else "📌"
        score_str = f" | Score {score:.1f}/10" if score is not None else ""
        e.add_field(
            name=f"{em} ${t}{score_str}",
            value=sig,
            inline=False,
        )

    e.add_field(
        name="📬 Full breakdown + free newsletter",
        value=f"[catalystedge.agency]({NEWSLETTER_URL})",
        inline=True,
    )
    e.add_field(
        name="🎙️ Talk to Catalyst AI",
        value=f"[catalystedge.agency]({AGENCY_URL})",
        inline=True,
    )
    e.set_footer(text="Sourced from live SEC EDGAR filings • Free every morning")
    return e


def embed_top() -> discord.Embed:
    picks = load_picks()
    if not picks:
        return embed_no_picks()

    top_pick = picks.get("top_pick", "")
    top5     = picks.get("top5_tickers", [])
    if not top_pick and top5:
        top_pick = top5[0]
    if not top_pick:
        return embed_no_picks()

    row   = get_ticker_detail(top_pick)
    sig   = signal_label(row) if row else "SEC catalyst filing 📄"
    score = get_score(row)
    form  = row.get("form", "SEC filing") if row else "SEC filing"
    price = row.get("price", "") if row else ""

    others = [f"${t}" for t in top5 if t != top_pick][:4]

    e = discord.Embed(
        title=f"🥇 TOP PICK: ${top_pick}",
        description="Highest-conviction catalyst from today's scan",
        color=COLOR_GOLD,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    e.add_field(name="Signal",  value=sig,   inline=True)
    e.add_field(name="Filing",  value=form,  inline=True)
    if score is not None:
        e.add_field(name="Score", value=f"{score:.1f}/10", inline=True)
    if price:
        e.add_field(name="Entry ref", value=f"${price}", inline=True)
    if others:
        e.add_field(name="Also watching", value=" · ".join(others), inline=False)

    e.add_field(
        name="📬 Full breakdown",
        value=f"[Free newsletter]({NEWSLETTER_URL})",
        inline=True,
    )
    e.add_field(
        name="🎙️ Ask Catalyst AI",
        value=f"[catalystedge.agency]({AGENCY_URL})",
        inline=True,
    )
    e.set_footer(text="Sourced from live SEC EDGAR filings — public data most traders never read")
    return e


def embed_squeeze() -> discord.Embed:
    rows   = read_csv(ROOT / "squeeze_candidates.csv")
    coiled = [(r.get("ticker", "").upper(), r.get("stage", ""),
               r.get("short_interest", ""), r.get("dtc", ""))
              for r in rows if r.get("stage") in ("COILED", "IGNITION")][:6]

    e = discord.Embed(
        title="🔥 SQUEEZE RADAR",
        description="_Elevated short interest + SEC catalyst — these could force short covering_",
        color=COLOR_RED,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )

    if not coiled:
        e.description = "No tickers in COILED or IGNITION stage today."
        e.add_field(name="📬 Check tomorrow", value=NEWSLETTER_URL, inline=False)
        return e

    for t, stage, si, dtc in coiled:
        emoji = "🔥" if stage == "IGNITION" else "🌀"
        details = []
        if si:
            details.append(f"SI: {si}%")
        if dtc:
            details.append(f"DTC: {dtc}")
        detail_str = " | ".join(details) if details else "SEC catalyst present"
        e.add_field(
            name=f"{emoji} ${t} — {stage}",
            value=detail_str,
            inline=True,
        )

    e.add_field(
        name="📬 Full analysis",
        value=f"[Free newsletter]({NEWSLETTER_URL})",
        inline=False,
    )
    e.set_footer(text="A catalyst can trigger rapid short covering — watch these closely")
    return e


def embed_polymarket() -> discord.Embed:
    signals = load_polymarket()

    e = discord.Embed(
        title="🎲 POLYMARKET SIGNALS",
        description="_Live prediction market odds — how the crowd is betting_",
        color=COLOR_PURPLE,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )

    if not signals:
        e.description = "No fresh Polymarket signals right now. Data refreshes daily at 4am ET."
        e.add_field(name="📬 Subscribe", value=NEWSLETTER_URL, inline=False)
        return e

    for s in signals[:5]:
        prob   = s.get("probability", 50)
        title  = s.get("title", "")[:60]
        impact = s.get("impact", "")
        if prob >= 60:
            label = "🟢 LIKELY"
        elif prob <= 40:
            label = "🔴 UNLIKELY"
        else:
            label = "🟡 CONTESTED"
        e.add_field(
            name=f"{label} {prob:.0f}% — {title}",
            value=impact or "Market impact TBD",
            inline=False,
        )

    e.add_field(
        name="📬 We combine this with SEC data daily",
        value=f"[Free newsletter]({NEWSLETTER_URL})",
        inline=False,
    )
    e.set_footer(text="Polymarket odds + SEC filings = edge most traders don't have")
    return e


def embed_ticker(ticker: str) -> discord.Embed | None:
    picks    = load_picks()
    top5     = picks.get("top5_tickers", [])
    top_pick = picks.get("top_pick", "")
    all_picks = list({top_pick} | set(top5)) if top_pick else list(top5)

    if ticker.upper() not in [t.upper() for t in all_picks]:
        return None

    row   = get_ticker_detail(ticker)
    sig   = signal_label(row) if row else "SEC catalyst filing 📄"
    score = get_score(row)
    is_top = ticker.upper() == top_pick.upper()

    e = discord.Embed(
        title=("🥇 TOP PICK" if is_top else "📌 In today's picks") + f": ${ticker.upper()}",
        color=COLOR_GOLD if is_top else COLOR_GREEN,
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )
    e.add_field(name="Signal", value=sig, inline=True)
    if score is not None:
        e.add_field(name="Score", value=f"{score:.1f}/10", inline=True)
    e.add_field(
        name="📬 Full breakdown",
        value=f"[Free newsletter]({NEWSLETTER_URL})",
        inline=False,
    )
    e.set_footer(text="Sourced from SEC EDGAR this morning")
    return e


def embed_help(invite_url: str = "") -> discord.Embed:
    e = discord.Embed(
        title="⚡ Catalyst Edge Bot — Commands",
        description=(
            "I scan 300+ SEC EDGAR filings every morning and surface "
            "the highest-conviction catalyst plays — free."
        ),
        color=COLOR_BLUE,
    )
    e.add_field(
        name="Slash Commands",
        value=(
            "`/picks` — today's top 5 SEC catalyst picks\n"
            "`/top` — #1 pick with signal, score & filing detail\n"
            "`/squeeze` — tickers in COILED or IGNITION squeeze stage\n"
            "`/polymarket` — live Polymarket prediction market signals\n"
            "`/help` — this menu"
        ),
        inline=False,
    )
    e.add_field(
        name="💡 Tip",
        value="Mention any `$TICKER` in chat — I'll check if it's in today's picks.",
        inline=False,
    )
    e.add_field(
        name="📬 Free daily newsletter",
        value=f"[catalystedge.agency]({NEWSLETTER_URL})",
        inline=True,
    )
    e.add_field(
        name="📲 Telegram channel",
        value=f"[t.me/CatalystEdgeDaily]({TELEGRAM_URL})",
        inline=True,
    )
    e.add_field(
        name="🎙️ AI voice agent",
        value=f"[catalystedge.agency]({AGENCY_URL})",
        inline=True,
    )
    if invite_url:
        e.add_field(
            name="➕ Add to your server",
            value=f"[Invite link]({invite_url})",
            inline=False,
        )
    e.set_footer(text="Free • No ads • Sourced from public SEC EDGAR data")
    return e


# ── Bot setup ─────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True   # required to read message text for $TICKER

class CatalystBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("  Slash commands synced globally")


bot = CatalystBot()


# ── Slash commands ────────────────────────────────────────────────────────────

@bot.tree.command(name="picks", description="Today's top 5 SEC catalyst picks")
async def cmd_picks(interaction: discord.Interaction):
    await interaction.response.send_message(embed=embed_picks())
    print(f"  [/picks] {interaction.user} in {getattr(interaction.guild, 'name', 'DM')}")


@bot.tree.command(name="top", description="#1 pick with full signal, score & filing detail")
async def cmd_top(interaction: discord.Interaction):
    await interaction.response.send_message(embed=embed_top())
    print(f"  [/top] {interaction.user} in {getattr(interaction.guild, 'name', 'DM')}")


@bot.tree.command(name="squeeze", description="Squeeze radar — tickers in COILED or IGNITION stage")
async def cmd_squeeze(interaction: discord.Interaction):
    await interaction.response.send_message(embed=embed_squeeze())
    print(f"  [/squeeze] {interaction.user} in {getattr(interaction.guild, 'name', 'DM')}")


@bot.tree.command(name="polymarket", description="Live Polymarket prediction market signals")
async def cmd_polymarket(interaction: discord.Interaction):
    await interaction.response.send_message(embed=embed_polymarket())
    print(f"  [/polymarket] {interaction.user} in {getattr(interaction.guild, 'name', 'DM')}")


@bot.tree.command(name="help", description="Command list and newsletter links")
async def cmd_help(interaction: discord.Interaction):
    invite = os.environ.get("DISCORD_INVITE_URL", "")
    await interaction.response.send_message(embed=embed_help(invite))
    print(f"  [/help] {interaction.user} in {getattr(interaction.guild, 'name', 'DM')}")


# ── Events ────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"run_discord_bot: logged in as {bot.user} (id={bot.user.id})")
    print(f"  Servers: {len(bot.guilds)}")
    print(f"  Commands: /picks /top /squeeze /polymarket /help")
    print(f"  $TICKER detection: ON")
    print(f"  Invite URL: https://discord.com/api/oauth2/authorize"
          f"?client_id={bot.user.id}"
          f"&permissions=274877908992"
          f"&scope=bot%20applications.commands")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="300+ SEC filings daily | /picks"
        )
    )


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Post a welcome message when added to a new server."""
    print(f"  Joined server: {guild.name} ({guild.member_count} members)")
    # Find the first channel we can send to
    target = None
    for ch in guild.text_channels:
        if ch.permissions_for(guild.me).send_messages:
            if ch.name in ("general", "stocks", "trading", "finance", "bot-commands", "bots"):
                target = ch
                break
    if target is None:
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                target = ch
                break
    if target:
        invite = (f"https://discord.com/api/oauth2/authorize"
                  f"?client_id={bot.user.id}"
                  f"&permissions=274877908992"
                  f"&scope=bot%20applications.commands")
        community = DISCORD_INVITE
        e = discord.Embed(
            title="⚡ Catalyst Edge Bot is here",
            description=(
                "I scan **300+ SEC EDGAR filings** every morning and surface "
                "the highest-conviction catalyst plays — completely free.\n\n"
                "Use `/picks` to see today's top 5 right now."
            ),
            color=COLOR_GREEN,
        )
        e.add_field(name="Commands", value="`/picks` `/top` `/squeeze` `/polymarket` `/help`", inline=False)
        e.add_field(name="📬 Free newsletter", value=f"[catalystedge.agency]({NEWSLETTER_URL})", inline=True)
        e.add_field(name="📲 Telegram", value=f"[t.me/CatalystEdgeDaily]({TELEGRAM_URL})", inline=True)
        e.add_field(name="🎙️ AI voice agent", value=f"[catalystedge.agency]({AGENCY_URL})", inline=True)
        e.add_field(name="➕ Share with other servers", value=f"[Invite link]({invite})", inline=False)
        e.set_footer(text="Free • No ads • Powered by live SEC EDGAR data")
        await target.send(embed=e)


@bot.event
async def on_message(message: discord.Message):
    # Ignore own messages
    if message.author == bot.user:
        return

    text = message.content or ""
    tickers = re.findall(r'\$([A-Z]{1,5})\b', text.upper())

    for ticker in tickers[:2]:
        embed = embed_ticker(ticker)
        if embed:
            await message.reply(embed=embed, mention_author=False)
            print(f"  [$TICKER] ${ticker} by {message.author} in "
                  f"{getattr(message.guild, 'name', 'DM')}")
            break  # one reply per message


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        print("run_discord_bot: DISCORD_BOT_TOKEN not set — exiting")
        print("  Set it in .sec_email_env: DISCORD_BOT_TOKEN=your_token_here")
        return
    print("run_discord_bot: connecting to Discord...")
    bot.run(BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
