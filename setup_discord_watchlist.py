#!/usr/bin/env python3
"""setup_discord_watchlist.py — One-time setup: creates the live watchlist
category and voice channels in your Discord server.

Run once:
  python3 setup_discord_watchlist.py

Outputs channel IDs to discord_watchlist_config.json for the update script.
"""

from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

ROOT        = Path(__file__).parent
CONFIG_FILE = ROOT / "discord_watchlist_config.json"
TOKEN       = os.environ.get("DISCORD_BOT_TOKEN", "")
BASE        = "https://discord.com/api/v10"

HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type":  "application/json",
    "User-Agent":    "CatalystEdge/1.0",
}

# Initial ticker slots — bot will fill these with real gap plays
INITIAL_TICKERS = [
    "LOADING...", "LOADING...", "LOADING...",
    "LOADING...", "LOADING...", "LOADING...",
    "LOADING...", "LOADING...", "LOADING...",
    "LOADING...",
]


def api(method: str, endpoint: str, data: dict | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    req  = urllib.request.Request(
        f"{BASE}{endpoint}", data=body, method=method, headers=HEADERS
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {endpoint} → {e.code}: {e.read().decode()[:300]}")


def main() -> int:
    if not TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN not set")
        return 1

    # Get list of guilds (servers) the bot is in
    guilds = api("GET", "/users/@me/guilds")
    if not guilds:
        print("Bot is not in any server yet — add it first via OAuth2 URL")
        return 1

    print("Bot is in these servers:")
    for i, g in enumerate(guilds):
        print(f"  [{i}] {g['name']} (id={g['id']})")

    guild = guilds[0]
    guild_id = guild["id"]
    print(f"\nUsing: {guild['name']} (id={guild_id})")

    # Create watchlist category
    print("\nCreating 📊 LIVE WATCHLIST category...")
    category = api("POST", f"/guilds/{guild_id}/channels", {
        "name": "📊 LIVE WATCHLIST",
        "type": 4,  # category
    })
    category_id = category["id"]
    print(f"  Category created: {category_id}")

    # Create 10 voice channel slots under the category
    channel_ids = []
    for i in range(10):
        ch = api("POST", f"/guilds/{guild_id}/channels", {
            "name":      f"loading-{i+1}",
            "type":      2,          # voice channel
            "parent_id": category_id,
            "user_limit": 0,         # no join limit
        })
        channel_ids.append(ch["id"])
        print(f"  Channel {i+1}: {ch['id']}")

    # Save config
    config = {
        "guild_id":    guild_id,
        "category_id": category_id,
        "channel_ids": channel_ids,
    }
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"\nConfig saved → {CONFIG_FILE.name}")
    print("\n✅ Setup complete! Run post_discord_watchlist.py to populate with live prices.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
