#!/usr/bin/env python3
"""post_discord_daily_picks.py — Post daily picks briefing to a Discord text channel.

Uses the Discord Bot API (not a webhook) to post a rich embed to a dedicated
#daily-picks channel, creating it under the LIVE WATCHLIST category if needed.

Creates the channel if it doesn't exist and saves the channel ID to
discord_watchlist_config.json under key 'daily_picks_channel_id'.

Required env var:
  DISCORD_BOT_TOKEN

Optional (loaded from .sec_email_env as fallback for local testing):
  NEWSLETTER_URL
"""
from __future__ import annotations

import csv
import datetime
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT           = Path(__file__).parent
CONFIG_FILE    = ROOT / "discord_watchlist_config.json"
SCANNER_URL    = "https://catalystedgescanner.com"
NEWSLETTER_URL = os.environ.get("NEWSLETTER_URL", "https://catalystedge.agency")
DISCORD_API    = "https://discord.com/api/v10"
CHANNEL_NAME   = "daily-picks"

# Brand colors
GREEN = 0x00FF88


# ── Env loader ───────────────────────────────────────────────────────────────

def _load_env() -> None:
    env_file = ROOT / ".sec_email_env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k not in os.environ:
            os.environ[k] = v.strip()


# ── Flag gating ──────────────────────────────────────────────────────────────

def already_posted(date_str: str) -> bool:
    return (ROOT / f".discord_picks_{date_str}").exists()


def mark_posted(date_str: str) -> None:
    (ROOT / f".discord_picks_{date_str}").touch()


# ── Config helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_config(config: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


# ── Data loaders ─────────────────────────────────────────────────────────────

def load_picks() -> dict:
    p = ROOT / "newsletter_picks.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def load_csv(name: str) -> list[dict]:
    p = ROOT / name
    if not p.exists():
        return []
    try:
        with p.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def load_gap_top() -> list[dict]:
    return load_csv("gap_scanner_top.csv")


def load_squeeze() -> list[dict]:
    return load_csv("squeeze_candidates.csv")


# ── Discord API helpers ───────────────────────────────────────────────────────

def _discord_request(method: str, path: str, token: str,
                     payload: dict | None = None) -> dict | None:
    url  = f"{DISCORD_API}{path}"
    body = json.dumps(payload).encode("utf-8") if payload else None
    req  = urllib.request.Request(
        url, data=body,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type":  "application/json",
            "User-Agent":    "CatalystEdge/1.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read()
        print(f"  Discord API error {e.code} on {method} {path}: {err_body[:200]}")
        return None
    except Exception as e:
        print(f"  Discord request error: {e}")
        return None


def get_guild_channels(guild_id: str, token: str) -> list[dict]:
    result = _discord_request("GET", f"/guilds/{guild_id}/channels", token)
    return result if isinstance(result, list) else []


def create_channel(guild_id: str, token: str, name: str,
                   category_id: str | None = None) -> dict | None:
    payload: dict = {"name": name, "type": 0}  # type 0 = text channel
    if category_id:
        payload["parent_id"] = category_id
    return _discord_request("POST", f"/guilds/{guild_id}/channels", token, payload)


def post_message(channel_id: str, token: str, embeds: list[dict]) -> dict | None:
    return _discord_request(
        "POST", f"/channels/{channel_id}/messages", token,
        {"embeds": embeds},
    )


# ── Channel resolver ──────────────────────────────────────────────────────────

def resolve_channel_id(guild_id: str, category_id: str | None,
                       token: str, config: dict) -> str | None:
    """Return existing or newly-created daily-picks channel ID."""
    # Check saved config first
    saved = config.get("daily_picks_channel_id")
    if saved:
        return saved

    # Search existing channels
    channels = get_guild_channels(guild_id, token)
    for ch in channels:
        if (ch.get("name", "").lower() == CHANNEL_NAME
                and ch.get("type") == 0):
            return str(ch["id"])

    # Create new channel
    print(f"  Creating #{CHANNEL_NAME} channel...")
    ch = create_channel(guild_id, token, CHANNEL_NAME, category_id)
    if ch:
        return str(ch.get("id", ""))
    return None


# ── Embed builder ─────────────────────────────────────────────────────────────

def build_embed(picks: dict, gap_rows: list[dict], squeeze_rows: list[dict]) -> dict:
    today    = datetime.date.today().strftime("%B %-d, %Y")
    top_pick = picks.get("top_pick", "—")
    top5     = picks.get("top5_tickers", [])
    gappers  = int(picks.get("gapper_count", 0) or 0)
    total    = picks.get("total_combined", 0)

    fields: list[dict] = []

    # Top pick field
    fields.append({
        "name":   "Top Pick",
        "value":  f"**${top_pick}**",
        "inline": True,
    })

    # Gap plays
    if gap_rows:
        gap_lines = []
        for row in gap_rows[:5]:
            t   = row.get("ticker", "").upper()
            g   = row.get("gap_pct", row.get("gap", ""))
            v   = row.get("vol_ratio", "")
            try:
                gap_str = f"+{float(g):.1f}%"
            except (ValueError, TypeError):
                gap_str = ""
            try:
                vol_str = f"{float(v):.1f}x vol"
            except (ValueError, TypeError):
                vol_str = ""
            stat = " | ".join(s for s in [gap_str, vol_str] if s)
            gap_lines.append(f"**${t}** {stat}" if stat else f"**${t}**")
        fields.append({
            "name":   "Gap Plays",
            "value":  "\n".join(gap_lines) or "—",
            "inline": True,
        })
    elif top5:
        pick_lines = [f"**${t}**" for t in top5[:5]]
        fields.append({
            "name":   "Today's Picks",
            "value":  "\n".join(pick_lines),
            "inline": True,
        })

    # Squeeze radar
    coiled   = [r for r in squeeze_rows if r.get("stage") == "COILED"]
    ignition = [r for r in squeeze_rows if r.get("stage") == "IGNITION"]
    sq_top   = (coiled + ignition)[:4]
    if sq_top:
        sq_lines = [
            f"**${r['ticker']}** `{r.get('stage','')}` SI {r.get('short_pct_float','')}%"
            for r in sq_top
        ]
        fields.append({
            "name":   "Squeeze Radar",
            "value":  "\n".join(sq_lines),
            "inline": False,
        })

    # Today's edge
    edge_parts = []
    if gappers:
        edge_parts.append(f"{gappers} gap plays flagged")
    if total:
        edge_parts.append(f"{total} tickers scanned")
    edge_str = " | ".join(edge_parts) if edge_parts else "SEC catalyst intelligence — daily"
    fields.append({
        "name":   "Today's Edge",
        "value":  edge_str,
        "inline": False,
    })

    return {
        "title":     f"\u26a1 CATALYST EDGE -- {today} | Top Picks",
        "color":     GREEN,
        "fields":    fields,
        "footer":    {
            "text": (
                f"Live scanner -> {SCANNER_URL} | "
                f"Newsletter -> {NEWSLETTER_URL} | "
                f"Alerts -> t.me/CatalystEdgePro"
            )
        },
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    _load_env()

    today_str = datetime.date.today().isoformat()

    if already_posted(today_str):
        print(f"post_discord_daily_picks: already posted today ({today_str}) — skipping")
        return 0

    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        print("post_discord_daily_picks: DISCORD_BOT_TOKEN not set — skipping")
        return 0

    config      = load_config()
    guild_id    = config.get("guild_id", "")
    category_id = config.get("category_id")

    if not guild_id:
        print("post_discord_daily_picks: guild_id not in discord_watchlist_config.json — skipping")
        return 0

    channel_id = resolve_channel_id(guild_id, category_id, token, config)
    if not channel_id:
        print("post_discord_daily_picks: could not resolve or create channel — skipping")
        return 1

    # Save channel ID for future runs
    if config.get("daily_picks_channel_id") != channel_id:
        config["daily_picks_channel_id"] = channel_id
        save_config(config)
        print(f"  Saved daily_picks_channel_id={channel_id} to config")

    picks      = load_picks()
    gap_rows   = load_gap_top()
    sq_rows    = load_squeeze()
    embed      = build_embed(picks, gap_rows, sq_rows)

    print(f"post_discord_daily_picks: posting embed to channel {channel_id}")
    result = post_message(channel_id, token, [embed])

    if result and result.get("id"):
        mark_posted(today_str)
        print(f"  Posted message id={result['id']}")
        return 0
    else:
        print("  Failed to post Discord embed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
