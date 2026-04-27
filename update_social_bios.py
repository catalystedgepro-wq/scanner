#!/usr/bin/env python3
"""update_social_bios.py — Update social media bios with current community links.

- X/Twitter: updates bio via API v2 (automated)
- Instagram, TikTok, YouTube, LinkedIn: writes copy-paste bio text to file

Run once after setting up new community links, then as needed.

Required env vars:
    TWITTER_API_KEY, TWITTER_API_SECRET
    TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT    = Path(__file__).parent
TODAY   = datetime.date.today().isoformat()

# ── Community links ────────────────────────────────────────────────────────────
NEWSLETTER_URL = "https://catalystedge.agency"
AGENCY_URL     = "https://www.catalystedge.agency"
DISCORD_URL    = "https://discord.gg/8aJEHghHVy"
TELEGRAM_URL   = "https://t.me/CatalystEdgeDaily"
TELEGRAM_BOT   = "https://t.me/CatalystEdgeBot"
YOUTUBE_URL    = "https://www.youtube.com/@CatalystEdgePro"

# ── Bio text per platform (keep within char limits) ───────────────────────────
BIOS = {
    "twitter_x": (
        "⚡ Free daily SEC catalyst stock picks — 300+ filings scanned every morning.\n"
        "📬 Newsletter: catalystedge.agency\n"
        "💬 Discord: discord.gg/8aJEHghHVy\n"
        "📲 Telegram: t.me/CatalystEdgeDaily"
    ),
    "instagram": (
        "⚡ Free daily SEC catalyst stock picks\n"
        "300+ filings scanned every morning 📊\n"
        "📬 Newsletter 👇\n"
        "💬 Discord: discord.gg/8aJEHghHVy\n"
        "📲 Telegram: @CatalystEdgeDaily\n"
        "🎙️ AI agent: catalystedge.agency"
    ),
    "tiktok": (
        "⚡ Free daily stock picks from SEC filings\n"
        "📬 catalystedge.agency\n"
        "💬 Discord: discord.gg/8aJEHghHVy\n"
        "📲 Telegram: @CatalystEdgeDaily"
    ),
    "youtube": (
        "Free daily stock picks from SEC EDGAR filings — 300+ filings scanned every morning "
        "before the market opens.\n\n"
        "📬 Free newsletter: https://catalystedge.agency\n"
        "💬 Discord community: https://discord.gg/8aJEHghHVy\n"
        "📲 Telegram channel: https://t.me/CatalystEdgeDaily\n"
        "🤖 Telegram bot: https://t.me/CatalystEdgeBot\n"
        "🎙️ Talk to our AI: https://www.catalystedge.agency"
    ),
    "linkedin": (
        "Catalyst Edge delivers free daily stock picks sourced from live SEC EDGAR filings. "
        "We scan 300+ catalyst filings every morning before the market opens and surface "
        "the highest-conviction plays — gappers, value plays, and institutional moat stocks.\n\n"
        "📬 Free newsletter: https://catalystedge.agency\n"
        "💬 Discord: https://discord.gg/8aJEHghHVy\n"
        "📲 Telegram: https://t.me/CatalystEdgeDaily\n"
        "🎙️ AI agent: https://www.catalystedge.agency"
    ),
}


# ── X/Twitter API v2 bio update ───────────────────────────────────────────────

def _oauth1_header(method: str, url: str, params: dict, creds: dict) -> str:
    oauth = {
        "oauth_consumer_key":     creds["api_key"],
        "oauth_nonce":            hashlib.md5(str(time.time()).encode()).hexdigest(),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            creds["access_token"],
        "oauth_version":          "1.0",
    }
    all_params = {**params, **oauth}
    sorted_params = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(all_params.items())
    )
    base = "&".join([
        method.upper(),
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote(sorted_params, safe=""),
    ])
    signing_key = (
        urllib.parse.quote(creds["api_secret"], safe="") + "&" +
        urllib.parse.quote(creds["access_secret"], safe="")
    )
    sig = hmac.new(signing_key.encode(), base.encode(), "sha1")
    import base64
    oauth["oauth_signature"] = base64.b64encode(sig.digest()).decode()
    return "OAuth " + ", ".join(
        f'{k}="{urllib.parse.quote(str(v), safe="")}"'
        for k, v in sorted(oauth.items())
    )


def update_twitter_bio(bio: str, creds: dict) -> bool:
    """Update X/Twitter profile description via API v2."""
    url  = "https://api.twitter.com/2/users/me"
    body = json.dumps({"description": bio}).encode("utf-8")
    auth = _oauth1_header("POST", url, {}, creds)
    req  = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Authorization": auth},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
        if resp.get("data", {}).get("id"):
            print("  X/Twitter: bio updated ✓")
            return True
        print(f"  X/Twitter: unexpected response — {resp}")
        return False
    except Exception as e:
        print(f"  X/Twitter: bio update failed — {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"update_social_bios: {TODAY}")

    # ── X/Twitter: automated ──────────────────────────────────────────────────
    creds = {
        "api_key":      os.environ.get("TWITTER_API_KEY", ""),
        "api_secret":   os.environ.get("TWITTER_API_SECRET", ""),
        "access_token": os.environ.get("TWITTER_ACCESS_TOKEN", ""),
        "access_secret":os.environ.get("TWITTER_ACCESS_SECRET", ""),
    }
    if all(creds.values()):
        print("  Updating X/Twitter bio...")
        update_twitter_bio(BIOS["twitter_x"], creds)
    else:
        print("  X/Twitter: creds not set — skipping automated update")

    # ── All platforms: write copy-paste file to Windows Desktop ───────────────
    WIN_DESKTOP = Path("/path/to/local/Desktop/catalyst-edge/social")
    out_path    = WIN_DESKTOP / "SOCIAL_BIOS_UPDATE.txt" if WIN_DESKTOP.exists() \
                  else ROOT / "social" / "SOCIAL_BIOS_UPDATE.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"CATALYST EDGE — SOCIAL MEDIA BIOS ({TODAY})",
        "=" * 60,
        "Copy-paste these into each platform's bio/about section.",
        "",
    ]
    for platform, bio in BIOS.items():
        char_count = len(bio)
        lines += [
            f"── {platform.upper()} ({char_count} chars) ──────────────",
            bio,
            "",
        ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Bio copy-paste file: {out_path}")
    print()
    print("  Platforms needing manual update:")
    print("  • Instagram  → Edit Profile → Bio")
    print("  • TikTok     → Edit Profile → Bio")
    print("  • YouTube    → YouTube Studio → Customization → Basic info → Description")
    print("  • LinkedIn   → Edit page → About")


if __name__ == "__main__":
    main()
