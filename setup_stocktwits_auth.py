#!/usr/bin/env python3
"""StockTwits OAuth 2.0 token setup for Catalyst Edge.

Checks .sec_email_env for existing credentials, walks the user through
app registration if needed, and exchanges an authorization code for an
access token — writing it back to .sec_email_env automatically.

Usage:
    python3 setup_stocktwits_auth.py
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".sec_email_env"

# ── Helpers ─────────────────────────────────────────────────────────────────


def _load_env_file() -> dict[str, str]:
    """Parse KEY=VALUE pairs from .sec_email_env (best-effort, no shell logic)."""
    result: dict[str, str] = {}
    if not ENV_FILE.exists():
        return result
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        result[key.strip()] = val.strip()
    return result


def _append_env_file(key: str, value: str) -> None:
    """Append or replace a KEY=VALUE line in .sec_email_env."""
    existing_lines: list[str] = []
    if ENV_FILE.exists():
        existing_lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    # Replace existing key if present
    new_lines: list[str] = []
    replaced = False
    for line in existing_lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped == key:
            new_lines.append(f"{key}={value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"  -> Written to {ENV_FILE}")


def _exchange_code(client_id: str, client_secret: str, code: str) -> str:
    """POST authorization code to StockTwits token endpoint; return access_token."""
    params = urllib.parse.urlencode({
        "client_id":     client_id,
        "client_secret": client_secret,
        "code":          code,
        "grant_type":    "authorization_code",
        "redirect_uri":  "urn:ietf:wg:oauth:2.0:oob",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.stocktwits.com/api/2/oauth/token",
        data=params,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    token = body.get("access_token") or body.get("token", {}).get("access_token")
    if not token:
        raise RuntimeError(f"Unexpected response: {body}")
    return token


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    env = _load_env_file()
    # Also honour vars already in the process environment (e.g. from sourcing .sec_email_env)
    for key in ("STOCKTWITS_ACCESS_TOKEN", "STOCKTWITS_CLIENT_ID", "STOCKTWITS_CLIENT_SECRET"):
        if key not in env and os.environ.get(key):
            env[key] = os.environ[key]

    # ── Step 0: already have a token? ────────────────────────────────────────
    existing_token = env.get("STOCKTWITS_ACCESS_TOKEN", "").strip()
    if existing_token:
        print("=== STOCKTWITS TOKEN SETUP ===")
        print()
        print(f"STOCKTWITS_ACCESS_TOKEN is already set in {ENV_FILE}")
        print("  Token (first 8 chars):", existing_token[:8] + "...")
        print()
        print("Nothing to do. If you need to rotate the token, remove the")
        print("STOCKTWITS_ACCESS_TOKEN line from .sec_email_env and re-run.")
        return 0

    client_id     = env.get("STOCKTWITS_CLIENT_ID",     "").strip()
    client_secret = env.get("STOCKTWITS_CLIENT_SECRET", "").strip()

    # ── Step 1: no credentials at all → print registration instructions ──────
    if not client_id or not client_secret:
        print("=== STOCKTWITS TOKEN SETUP ===")
        print()
        print("Step 1: Register your app (one-time):")
        print("  https://api.stocktwits.com/developers/apps/new")
        print("  - App name: Catalyst Edge")
        print("  - Website: https://catalystedge.agency")
        print("  - Callback URL: urn:ietf:wg:oauth:2.0:oob")
        print()
        print("Step 2: Add CLIENT_ID and CLIENT_SECRET to .sec_email_env:")
        print("  STOCKTWITS_CLIENT_ID=your_client_id")
        print("  STOCKTWITS_CLIENT_SECRET=your_client_secret")
        print()
        print("Step 3: Run this script again with those vars set.")
        return 0

    # ── Step 2: have client creds → build authorize URL and get code ─────────
    authorize_url = (
        "https://api.stocktwits.com/api/2/oauth/authorize"
        f"?client_id={urllib.parse.quote(client_id)}"
        "&response_type=code"
        "&redirect_uri=urn:ietf:wg:oauth:2.0:oob"
        "&scope=publish_messages"
    )

    print("=== STOCKTWITS TOKEN SETUP ===")
    print()
    print("Visit this URL in your browser to authorize the app:")
    print()
    print(f"  {authorize_url}")
    print()
    print("After approving, StockTwits will show you an authorization code.")
    print("Paste it below and press Enter.")
    print()

    code = input("Authorization code: ").strip()
    if not code:
        print("ERROR: No authorization code provided.")
        return 1

    # ── Step 3: exchange code for access token ────────────────────────────────
    print()
    print("Exchanging authorization code for access token...")
    try:
        token = _exchange_code(client_id, client_secret, code)
    except Exception as exc:
        print(f"ERROR: Token exchange failed — {exc}")
        return 1

    print()
    print("SUCCESS! Your StockTwits access token:")
    print(f"  {token}")
    print()
    print("Add this line to .sec_email_env (done automatically below):")
    print(f"  STOCKTWITS_ACCESS_TOKEN={token}")
    print()

    _append_env_file("STOCKTWITS_ACCESS_TOKEN", token)
    print("Done. post_to_stocktwits.py will use this token automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
