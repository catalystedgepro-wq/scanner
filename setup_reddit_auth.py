#!/usr/bin/env python3
"""Interactive Reddit API credential setup for Catalyst Edge.

One command, zero manual file editing. Walks you through creating a Reddit
"script" app, prompts for each credential, validates with a live OAuth request,
writes everything to .sec_email_env, and deploys to the production droplet.

Usage:
    python3 setup_reddit_auth.py

Stdlib only -- no pip dependencies.
"""
from __future__ import annotations

import base64
import getpass
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
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
    print(_bold("  CATALYST EDGE  --  Reddit API Setup"))
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


# ── Reddit API ───────────────────────────────────────────────────────────────

def _test_auth(client_id: str, client_secret: str,
               username: str, password: str) -> dict:
    """Hit Reddit's OAuth2 password endpoint. Returns the parsed JSON."""
    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()
    body = urllib.parse.urlencode({
        "grant_type": "password",
        "username":   username,
        "password":   password,
    }).encode()
    req = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token",
        data=body,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type":  "application/x-www-form-urlencoded",
            "User-Agent":    f"CatalystEdge/1.0 by u/{username}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())


def _fetch_identity(token: str, username: str) -> dict | None:
    """GET /api/v1/me to confirm the token works and return account info."""
    req = urllib.request.Request(
        "https://oauth.reddit.com/api/v1/me",
        headers={
            "Authorization": f"bearer {token}",
            "User-Agent":    f"CatalystEdge/1.0 by u/{username}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


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
        masked = current[:4] + "..." if secret else current
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

    # Pull from process env as fallback
    for key in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET",
                "REDDIT_USERNAME", "REDDIT_PASSWORD"):
        if key not in env and os.environ.get(key):
            env[key] = os.environ[key]

    # ── STEP 1: Instructions ─────────────────────────────────────────────────
    _section(1, "Create a Reddit 'script' app")
    print()
    print(f"  Open this URL in your browser:")
    print()
    print(f"    {_bold('https://www.reddit.com/prefs/apps')}")
    print()
    print(f"  Then follow these steps:")
    print()
    print(f"    1. Scroll to the bottom, click {_bold('\"create another app...\"')}")
    print(f"    2. {_bold('Name')}:         Catalyst Edge Bot")
    print(f"    3. Select type:    {_mag('script')}  {_dim('(the third radio button)')}")
    print(f"    4. {_bold('Description')}:  Daily SEC catalyst scanner")
    print(f"    5. {_bold('About URL')}:    https://catalystedge.agency")
    print(f"    6. {_bold('Redirect URI')}: http://localhost:8080")
    print(f"    7. Click {_bold('\"create app\"')}")
    print()
    print(f"  After creating:")
    print(f"    - The {_bold('Client ID')} is the ~14 character string under the app name")
    print(f"    - The {_bold('Client Secret')} is labeled \"secret\"")
    print()
    _info("If you already created the app, just enter the existing credentials.")

    # ── STEP 2: Collect credentials ──────────────────────────────────────────
    _section(2, "Enter your credentials")

    client_id = _prompt(
        "Reddit Client ID     (14 chars under app name)",
        env.get("REDDIT_CLIENT_ID", ""),
    )
    client_secret = _prompt(
        "Reddit Client Secret (labeled 'secret')",
        env.get("REDDIT_CLIENT_SECRET", ""),
        secret=True,
    )
    username = _prompt(
        "Reddit Username      (without u/)",
        env.get("REDDIT_USERNAME", ""),
    )
    password = _prompt(
        "Reddit Password",
        env.get("REDDIT_PASSWORD", ""),
        secret=True,
    )

    if not all([client_id, client_secret, username, password]):
        print()
        _fail("All four fields are required. Please re-run and fill each one.")
        return 1

    # ── STEP 3: Validate ─────────────────────────────────────────────────────
    _section(3, "Validating credentials with Reddit API")
    print()
    _info(f"Authenticating as u/{username}...")

    try:
        data = _test_auth(client_id, client_secret, username, password)
    except urllib.error.HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode()
        except Exception:
            pass
        print()
        _fail(f"HTTP {exc.code} -- {exc.reason}")
        if body_text:
            _info(f"Response: {body_text}")
        print()
        _warn("Troubleshooting:")
        print(f"    - Verify the Client ID and Secret match your app page")
        print(f"    - Make sure the app type is {_bold('script')} (not 'web' or 'installed')")
        print(f"    - If Reddit returns 401, the credentials are wrong")
        return 1
    except Exception as exc:
        print()
        _fail(f"Connection error: {exc}")
        return 1

    if "error" in data:
        err = data["error"]
        print()
        _fail(f"Reddit returned error: {_bold(str(err))}")
        print()
        if err == "invalid_grant":
            _warn("Username or password is wrong, OR 2FA is enabled on the account.")
            _info("Reddit script apps cannot use 2FA. Disable it or use a bot account.")
        elif err == "unauthorized_client":
            _warn("App type must be 'script'. Web/installed app types cannot use password flow.")
        elif err == "invalid_client":
            _warn("Client ID or Client Secret is incorrect.")
        else:
            _warn("Check all four credential values and try again.")
        return 1

    token = data.get("access_token", "")
    if not token:
        _fail(f"No access_token in response: {data}")
        return 1

    # Verify token works by pulling identity
    identity = _fetch_identity(token, username)
    if identity and identity.get("name"):
        acct_name = identity["name"]
        karma = identity.get("total_karma", "?")
        created = identity.get("created_utc")
        age_str = ""
        if created:
            import datetime
            age_days = (datetime.datetime.now(datetime.timezone.utc).timestamp() - created) / 86400
            if age_days >= 365:
                age_str = f" ({age_days / 365:.1f} years old)"
            else:
                age_str = f" ({int(age_days)} days old)"
        print()
        _ok(f"Authenticated as {_bold('u/' + acct_name)}{age_str}")
        _ok(f"Karma: {karma}")
    else:
        print()
        _ok("Token obtained successfully")
        _warn("Could not verify identity (non-critical)")

    print()
    _ok(f"Access token: {_dim(token[:12] + '...')}")

    # ── STEP 4: Write to .sec_email_env ──────────────────────────────────────
    _section(4, "Saving credentials to .sec_email_env")
    print()

    creds = {
        "REDDIT_CLIENT_ID":     client_id,
        "REDDIT_CLIENT_SECRET": client_secret,
        "REDDIT_USERNAME":      username,
        "REDDIT_PASSWORD":      password,
    }
    for key, val in creds.items():
        _upsert_env(key, val)
        _ok(f"  {key} = {val[:6]}..." if len(val) > 6 else f"  {key} = {val}")

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
    print(_green("  REDDIT SETUP COMPLETE"))
    print(_bold("=" * 64))
    print()
    print(f"  The next pipeline run will automatically post to Reddit.")
    print(f"  Script: {_dim('post_to_reddit.py')}")
    print()
    print(f"  Posts go to: {_bold('r/CatalystEdgePro')} (home base)")
    print(f"  Cross-posts: r/pennystocks, r/Daytrading, r/RobinhoodPennyStocks")
    print()
    print(f"  Test manually:  {_cyan('python3 post_to_reddit.py')}")
    print()
    _info("Tip: Create r/CatalystEdgePro if it doesn't exist yet:")
    _info("  https://www.reddit.com/subreddits/create")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
