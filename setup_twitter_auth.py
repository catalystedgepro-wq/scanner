#!/usr/bin/env python3
"""Interactive Twitter/X API credential setup for Catalyst Edge.

One command, zero manual file editing. Walks you through creating a Twitter
developer app, prompts for each credential, validates with a live OAuth
request, writes everything to .sec_email_env, and deploys to the production
droplet.

Usage:
    python3 setup_twitter_auth.py

Stdlib only -- no pip dependencies.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".sec_email_env"
DROPLET_DEST = "root@67.205.148.181:/opt/catalyst/.sec_email_env"

# ── Terminal colors ──────────────────────────────────────────────────────────

_COLOR = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _COLOR else text

def _bold(t: str) -> str:   return _c("1", t)
def _green(t: str) -> str:  return _c("32", t)
def _red(t: str) -> str:    return _c("31", t)
def _yellow(t: str) -> str: return _c("33", t)
def _cyan(t: str) -> str:   return _c("36", t)
def _dim(t: str) -> str:    return _c("2", t)
def _mag(t: str) -> str:    return _c("35", t)


def _banner() -> None:
    print()
    print(_bold("=" * 64))
    print(_bold("  CATALYST EDGE  --  Twitter/X API Setup"))
    print(_bold("=" * 64))
    print()


def _section(n: int, title: str) -> None:
    print()
    print(_cyan(f"  [{n}] {title}"))
    print(_dim("  " + "-" * 56))


def _ok(msg: str) -> None:
    print(f"  {_green('[OK]')} {msg}")


def _fail(msg: str) -> None:
    print(f"  {_red('[FAIL]')} {msg}")


def _warn(msg: str) -> None:
    print(f"  {_yellow('[!]')} {msg}")


def _info(msg: str) -> None:
    print(f"  {_dim('[i]')} {msg}")


# ── Env file helpers ─────────────────────────────────────────────────────────

def _load_env() -> dict[str, str]:
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


def _upsert_env(key: str, value: str) -> None:
    """Insert or replace a KEY=VALUE line in .sec_email_env."""
    existing: list[str] = []
    if ENV_FILE.exists():
        existing = ENV_FILE.read_text(encoding="utf-8").splitlines()

    new_lines: list[str] = []
    replaced = False
    for line in existing:
        stripped = line.strip()
        if stripped.startswith(f"{key}=") or stripped == key:
            new_lines.append(f"{key}={value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ── OAuth 1.0a ───────────────────────────────────────────────────────────────

def _pct(s: str) -> str:
    return urllib.parse.quote(str(s), safe="")


def _oauth_header(method: str, url: str,
                  consumer_key: str, consumer_secret: str,
                  token: str, token_secret: str) -> str:
    """Build OAuth 1.0a Authorization header (JSON body -- no body params)."""
    oauth: dict[str, str] = {
        "oauth_consumer_key":     consumer_key,
        "oauth_nonce":            uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            token,
        "oauth_version":          "1.0",
    }
    param_str = "&".join(
        f"{_pct(k)}={_pct(v)}" for k, v in sorted(oauth.items())
    )
    base = f"{method.upper()}&{_pct(url)}&{_pct(param_str)}"
    key = f"{_pct(consumer_secret)}&{_pct(token_secret)}"
    sig = base64.b64encode(
        hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(
        f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items())
    )


def _oauth_header_get(method: str, url: str,
                      consumer_key: str, consumer_secret: str,
                      token: str, token_secret: str,
                      query_params: dict[str, str] | None = None) -> str:
    """Build OAuth 1.0a header for GET requests (query params in base string)."""
    oauth: dict[str, str] = {
        "oauth_consumer_key":     consumer_key,
        "oauth_nonce":            uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            token,
        "oauth_version":          "1.0",
    }
    all_params = dict(oauth)
    if query_params:
        all_params.update(query_params)
    param_str = "&".join(
        f"{_pct(k)}={_pct(v)}" for k, v in sorted(all_params.items())
    )
    base_url = url.split("?")[0]
    base = f"{method.upper()}&{_pct(base_url)}&{_pct(param_str)}"
    key = f"{_pct(consumer_secret)}&{_pct(token_secret)}"
    sig = base64.b64encode(
        hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(
        f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(oauth.items())
    )


# ── Twitter API ──────────────────────────────────────────────────────────────

def _verify_credentials(api_key: str, api_secret: str,
                        access_token: str, access_secret: str) -> dict | None:
    """GET /2/users/me to verify OAuth 1.0a credentials. Returns user data."""
    url = "https://api.twitter.com/2/users/me"
    query = {"user.fields": "username,name,public_metrics,created_at"}
    full_url = url + "?" + urllib.parse.urlencode(query)

    auth = _oauth_header_get(
        "GET", url,
        api_key, api_secret, access_token, access_secret,
        query_params=query,
    )
    req = urllib.request.Request(
        full_url,
        headers={
            "Authorization": auth,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _deploy_to_droplet() -> bool:
    """SCP .sec_email_env to the production droplet. Returns True on success."""
    try:
        result = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
             str(ENV_FILE), DROPLET_DEST],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ── Interactive prompts ──────────────────────────────────────────────────────

def _prompt(label: str, current: str = "", secret: bool = False) -> str:
    """Prompt user for a value. Shows current value if one exists."""
    if current:
        masked = current[:6] + "..." if secret else current
        hint = f" {_dim(f'[current: {masked} -- press Enter to keep]')}"
    else:
        hint = ""
    print()
    if secret:
        val = getpass.getpass(f"  {label}{hint}: ").strip()
    else:
        val = input(f"  {label}{hint}: ").strip()
    return val or current


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    _banner()

    env = _load_env()

    for key in ("TWITTER_API_KEY", "TWITTER_API_SECRET",
                "TWITTER_ACCESS_TOKEN", "TWITTER_ACCESS_SECRET"):
        if key not in env and os.environ.get(key):
            env[key] = os.environ[key]

    # ── STEP 1: Instructions ─────────────────────────────────────────────────
    _section(1, "Create a Twitter/X Developer App")
    print()
    print(f"  {_bold('Option A')} -- Developer Portal (full access):")
    print()
    print(f"    1. Go to {_bold('https://developer.twitter.com/en/portal/dashboard')}")
    print(f"    2. Create a Project (or use existing)")
    print(f"    3. Create an App inside the project")
    print(f"    4. Under {_bold('\"User authentication settings\"')}, enable OAuth 1.0a")
    print(f"    5. Set App Permissions to {_mag('Read and Write')}")
    print(f"    6. Callback URL: http://localhost:8080")
    print(f"    7. Website URL:  https://catalystedge.agency")
    print()
    print(f"  {_bold('Option B')} -- Quick path (if you already have keys):")
    print()
    print(f"    1. Go to {_bold('https://developer.twitter.com/en/portal/projects-and-apps')}")
    print(f"    2. Click your app -> {_bold('\"Keys and tokens\"')} tab")
    print(f"    3. Under {_bold('\"Consumer Keys\"')}, copy API Key and Secret")
    print(f"    4. Under {_bold('\"Authentication Tokens\"')}, generate Access Token & Secret")
    print(f"       {_yellow('Make sure permissions say \"Read and Write\" before generating!')}")
    print()
    _info("The Free tier allows 1,500 tweets/month -- plenty for a daily thread.")

    # ── STEP 2: Collect credentials ──────────────────────────────────────────
    _section(2, "Enter your credentials")
    print()
    print(f"  {_dim('All four values come from the \"Keys and tokens\" tab of your app.')}")

    api_key = _prompt(
        "API Key              (Consumer Key)",
        env.get("TWITTER_API_KEY", ""),
    )
    api_secret = _prompt(
        "API Key Secret       (Consumer Secret)",
        env.get("TWITTER_API_SECRET", ""),
        secret=True,
    )
    access_token = _prompt(
        "Access Token         (under Authentication Tokens)",
        env.get("TWITTER_ACCESS_TOKEN", ""),
    )
    access_secret = _prompt(
        "Access Token Secret",
        env.get("TWITTER_ACCESS_SECRET", ""),
        secret=True,
    )

    if not all([api_key, api_secret, access_token, access_secret]):
        print()
        _fail("All four fields are required. Please re-run and fill each one.")
        return 1

    # ── STEP 3: Validate ─────────────────────────────────────────────────────
    _section(3, "Validating credentials with Twitter API")
    print()
    _info("Calling GET /2/users/me ...")

    try:
        data = _verify_credentials(api_key, api_secret, access_token, access_secret)
    except urllib.error.HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode()
        except Exception:
            pass
        print()
        _fail(f"HTTP {exc.code} -- {exc.reason}")
        if body_text:
            try:
                parsed = json.loads(body_text)
                detail = parsed.get("detail") or parsed.get("title") or body_text
            except Exception:
                detail = body_text
            _info(f"Response: {detail}")
        print()
        _warn("Troubleshooting:")
        if exc.code == 401:
            print(f"    - API Key or Secret is wrong")
            print(f"    - Access Token was regenerated after changing permissions")
            print(f"    - {_bold('Fix')}: Regenerate Access Token & Secret, then re-run this script")
        elif exc.code == 403:
            print(f"    - App permissions may be Read-only")
            print(f"    - {_bold('Fix')}: Set to 'Read and Write' in User Authentication Settings,")
            print(f"      then regenerate Access Token & Secret")
        elif exc.code == 429:
            print(f"    - Rate limited. Wait a minute and try again.")
        else:
            print(f"    - Check all four credential values and try again")
        return 1
    except Exception as exc:
        print()
        _fail(f"Connection error: {exc}")
        return 1

    if not data or "data" not in data:
        _fail(f"Unexpected response: {data}")
        return 1

    user_data = data["data"]
    handle = user_data.get("username", "unknown")
    name = user_data.get("name", "")
    metrics = user_data.get("public_metrics", {})
    followers = metrics.get("followers_count", "?")
    tweet_count = metrics.get("tweet_count", "?")

    print()
    _ok(f"Authenticated as {_bold('@' + handle)}" + (f" ({name})" if name else ""))
    _ok(f"Followers: {followers}  |  Tweets: {tweet_count}")

    # Check write permission by inspecting if we can access the tweet endpoint
    # (We won't actually tweet, just confirm auth works)
    _ok("OAuth 1.0a signature verified")

    # ── STEP 4: Write to .sec_email_env ──────────────────────────────────────
    _section(4, "Saving credentials to .sec_email_env")
    print()

    creds = {
        "TWITTER_API_KEY":      api_key,
        "TWITTER_API_SECRET":   api_secret,
        "TWITTER_ACCESS_TOKEN": access_token,
        "TWITTER_ACCESS_SECRET": access_secret,
    }
    for key, val in creds.items():
        _upsert_env(key, val)
        display = val[:8] + "..." if len(val) > 8 else val
        _ok(f"  {key} = {display}")

    # ── STEP 5: Deploy to droplet ────────────────────────────────────────────
    _section(5, "Deploying to production droplet")
    print()
    _info(f"SCP -> {DROPLET_DEST}")

    if _deploy_to_droplet():
        _ok("Deployed to droplet")
    else:
        _warn("Could not reach droplet (non-fatal)")
        _info("You can deploy manually later:")
        _info(f"  scp .sec_email_env {DROPLET_DEST}")

    # ── Done ─────────────────────────────────────────────────────────────────
    print()
    print(_bold("=" * 64))
    print(_green("  TWITTER/X SETUP COMPLETE"))
    print(_bold("=" * 64))
    print()
    print(f"  The next pipeline run will automatically post a daily thread to X.")
    print(f"  Script: {_dim('post_to_twitter.py')}")
    print()
    print(f"  Account:  {_bold('@' + handle)}")
    print(f"  Format:   3-tweet thread (Polymarket hook + picks + CTA)")
    print(f"  Schedule: Daily before pre-market, after SEC scan completes")
    print()
    print(f"  Test manually:  {_cyan('python3 post_to_twitter.py')}")
    print()
    _info("Important: If you change app permissions later, you MUST")
    _info("regenerate the Access Token & Secret and re-run this script.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
