#!/usr/bin/env python3
"""post_to_bluesky.py — Webhook poster (tier-1 reliability).

Bluesky AT Protocol API uses a session token from createSession. No
captcha, no anti-bot, no headless detection. App passwords are easy to
revoke, so this is safe long-term.

Get an app password:
  1. bsky.app → Settings → Privacy and security → App passwords
  2. Create new password (can scope to "no DMs")
  3. Copy

Add to .sec_email_env:
  BLUESKY_HANDLE=catalystedge.bsky.social
  BLUESKY_APP_PASSWORD=<password>

Usage:
    INBOX_TEXT_FILE=/path/to/post.txt python3 post_to_bluesky.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
PDS = "https://bsky.social"


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


def _post_json(url: str, headers: dict, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def create_session(handle: str, app_pwd: str) -> dict:
    return _post_json(
        f"{PDS}/xrpc/com.atproto.server.createSession",
        {},
        {"identifier": handle, "password": app_pwd},
    )


def post(text: str, session: dict) -> bool:
    if len(text) > 300:
        text = text[:297] + "..."
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    }
    try:
        result = _post_json(
            f"{PDS}/xrpc/com.atproto.repo.createRecord",
            {"Authorization": f"Bearer {session['accessJwt']}"},
            {"repo": session["did"], "collection": "app.bsky.feed.post", "record": record},
        )
        print(f"bluesky: posted uri={result.get('uri', '?')}")
        return True
    except Exception as e:
        print(f"bluesky ERROR: {e}")
        return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", help="explicit text (overrides INBOX_TEXT_FILE)")
    args = parser.parse_args(argv)

    env = _load_env()
    handle = env.get("BLUESKY_HANDLE") or os.environ.get("BLUESKY_HANDLE")
    app_pwd = env.get("BLUESKY_APP_PASSWORD") or os.environ.get("BLUESKY_APP_PASSWORD")
    if not (handle and app_pwd):
        print("bluesky: skipped (BLUESKY_HANDLE / BLUESKY_APP_PASSWORD not set)")
        return 0

    text = args.text
    if not text:
        inbox = os.environ.get("INBOX_TEXT_FILE")
        if inbox and Path(inbox).exists():
            text = Path(inbox).read_text(encoding="utf-8").strip()
    if not text:
        print("bluesky: no text to post")
        return 1

    try:
        session = create_session(handle, app_pwd)
    except Exception as e:
        print(f"bluesky session ERROR: {e}")
        return 2

    return 0 if post(text, session) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
