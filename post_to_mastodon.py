#!/usr/bin/env python3
"""post_to_mastodon.py — Webhook poster (tier-1 reliability).

Mastodon instances accept a single POST to /api/v1/statuses with a Bearer
access token. No cookies, no anti-bot, no captchas. Once the access token
is in .sec_email_env it works forever (or until the user revokes it).

Get a token:
  1. Sign in to your Mastodon instance (e.g., mastodon.social)
  2. Settings → Development → New application
  3. Scopes: write:statuses
  4. Copy the access token

Add to .sec_email_env:
  MASTODON_INSTANCE=https://mastodon.social
  MASTODON_TOKEN=<token>

Usage:
    INBOX_TEXT_FILE=/path/to/post.txt python3 post_to_mastodon.py
    python3 post_to_mastodon.py --text "Hello fediverse"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent


def _load_env() -> dict:
    env_path = WORKSPACE / ".sec_email_env"
    env: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def post(text: str, instance: str, token: str) -> bool:
    if len(text) > 500:
        text = text[:497] + "..."
    url = instance.rstrip("/") + "/api/v1/statuses"
    body = json.dumps({"status": text, "visibility": "public"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Idempotency-Key": str(hash(text))[:32],
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            code = resp.getcode()
            print(f"mastodon: HTTP {code}")
            return 200 <= code < 300
    except Exception as e:
        print(f"mastodon ERROR: {e}")
        return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", help="explicit text (overrides INBOX_TEXT_FILE)")
    args = parser.parse_args(argv)

    env = _load_env()
    instance = env.get("MASTODON_INSTANCE") or os.environ.get("MASTODON_INSTANCE")
    token = env.get("MASTODON_TOKEN") or os.environ.get("MASTODON_TOKEN")
    if not (instance and token):
        print("mastodon: skipped (MASTODON_INSTANCE / MASTODON_TOKEN not set)")
        return 0  # not fatal — feature gated on creds

    text = args.text
    if not text:
        inbox = os.environ.get("INBOX_TEXT_FILE")
        if inbox and Path(inbox).exists():
            text = Path(inbox).read_text(encoding="utf-8").strip()
    if not text:
        print("mastodon: no text to post")
        return 1

    return 0 if post(text, instance, token) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
