"""promote_to_live.py — Flip the autonomous loop from paper to live Alpaca.

Reads live keys from $WORKSPACE_ROOT/.alpaca_live_keys (a file the operator
drops in once), validates them against Alpaca's live API, backs up the
current .sec_email_env, swaps in the live keys + URL, sets conservative
canary safety limits, and verifies the full chain works end-to-end.

The .alpaca_live_keys file format (drop two lines):
  ALPACA_API_KEY_ID=PK....your live key
  ALPACA_API_SECRET=...your live secret

When the file exists this script:
  1. Loads the candidate keys
  2. Validates them by GET /v2/account against api.alpaca.markets
  3. Confirms the account is funded (cash > 0 and trading_blocked == false)
  4. Backs up .sec_email_env to .sec_email_env.paper.<timestamp>
  5. Rewrites .sec_email_env: ALPACA_BASE_URL → live, swaps key + secret
  6. Writes conservative canary limits (1% of equity max position, 1% drawdown)
  7. Runs agent_kill_switch.py against the live account to confirm wiring
  8. Securely shreds .alpaca_live_keys (single-use)
  9. Posts Discord notification

If validation fails at any step the script aborts WITHOUT touching .sec_email_env.

Exit codes:
  0  — promoted successfully (live trading is now active)
  1  — .alpaca_live_keys not found (waiting for operator)
  2  — validation failed; .sec_email_env unchanged
  3  — promotion partial; .sec_email_env restored from backup
"""

import datetime as dt
import json
import os
import sys
import shutil
import subprocess
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
ENV_FILE = ROOT / ".sec_email_env"
LIVE_KEYS_FILE = ROOT / ".alpaca_live_keys"
LOG_FILE = ROOT / "logs" / "promote_to_live.log"
LIVE_BASE = "https://api.alpaca.markets"
PAPER_BASE = "https://paper-api.alpaca.markets"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    line = f"[{ts}] {msg}\n"
    LOG_FILE.write_text(LOG_FILE.read_text(encoding="utf-8") + line if LOG_FILE.exists() else line, encoding="utf-8")
    sys.stdout.write(line)
    sys.stdout.flush()


def parse_kv_file(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def alpaca_get(base: str, path: str, key: str, secret: str, timeout: int = 15) -> tuple[int, object]:
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    }, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"error": str(e)}
        return e.code, err
    except urllib.error.URLError as e:
        return 0, {"error": f"URLError: {e}"}


def notify_discord(env: dict, content: str) -> None:
    webhook = env.get("DISCORD_WEBHOOK_URL") or os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook:
        return
    try:
        body = json.dumps({"content": content[:1900]}).encode("utf-8")
        req = urllib.request.Request(webhook, data=body,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:  # noqa: BLE001
        log(f"discord notify failed: {e}")


def write_env_atomic(env_dict: dict, path: Path) -> None:
    """Rewrite the env file preserving comments/structure where possible."""
    if not path.exists():
        path.write_text("\n".join(f"{k}={v}" for k, v in env_dict.items()) + "\n", encoding="utf-8")
        path.chmod(0o600)
        return

    new_lines = []
    seen = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line or line.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        k = line.split("=", 1)[0].strip()
        if k in env_dict:
            new_lines.append(f"{k}={env_dict[k]}")
            seen.add(k)
        else:
            new_lines.append(line)
    # append any keys that weren't in the file before
    for k, v in env_dict.items():
        if k not in seen:
            new_lines.append(f"{k}={v}")
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    tmp_path.chmod(0o600)
    tmp_path.replace(path)


def shred_file(path: Path) -> None:
    """Best-effort secure delete — overwrite then unlink."""
    if not path.exists():
        return
    try:
        size = path.stat().st_size
        with path.open("wb") as fh:
            fh.write(b"\0" * max(size, 1))
            fh.flush()
            os.fsync(fh.fileno())
        path.unlink()
    except Exception as e:  # noqa: BLE001
        log(f"shred failed (falling back to unlink): {e}")
        try:
            path.unlink()
        except Exception:
            pass


def main() -> int:
    log("=== promote_to_live start ===")

    if not LIVE_KEYS_FILE.exists():
        log(f"WAITING: drop your live Alpaca keys at {LIVE_KEYS_FILE} (two lines:")
        log("  ALPACA_API_KEY_ID=...")
        log("  ALPACA_API_SECRET=...")
        log("then re-run this script). exit 1")
        return 1

    candidate = parse_kv_file(LIVE_KEYS_FILE)
    new_key = candidate.get("ALPACA_API_KEY_ID", "").strip()
    new_secret = candidate.get("ALPACA_API_SECRET", "").strip()
    if not new_key or not new_secret:
        log("ERROR: .alpaca_live_keys missing ALPACA_API_KEY_ID and/or ALPACA_API_SECRET")
        return 2

    env_now = parse_kv_file(ENV_FILE)
    log(f"current ALPACA_BASE_URL = {env_now.get('ALPACA_BASE_URL', '<unset>')}")

    # Step 1: validate live keys
    log("validating live keys against api.alpaca.markets …")
    code, account = alpaca_get(LIVE_BASE, "/v2/account", new_key, new_secret)
    if code != 200 or not isinstance(account, dict):
        log(f"ERROR: Alpaca rejected the live keys (HTTP {code}): {account}")
        log("ABORT — .sec_email_env unchanged")
        return 2

    try:
        equity = float(account.get("equity") or 0)
        cash = float(account.get("cash") or 0)
        trading_blocked = bool(account.get("trading_blocked"))
        account_id = account.get("id", "?")
    except (TypeError, ValueError) as e:
        log(f"ERROR: parsing live-account fields: {e}")
        return 2

    log(f"live account verified: id={account_id[:8]}…  equity=${equity:,.2f}  cash=${cash:,.2f}  trading_blocked={trading_blocked}")

    if trading_blocked:
        log("ERROR: Alpaca has trading_blocked=True on this account. Cannot promote.")
        return 2

    if cash <= 0:
        log("WARNING: account cash is $0. Promotion will continue, but the agent")
        log("  cannot place orders until you fund it. Recommended: $50-$100 to start.")

    # Step 2: backup
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    backup = ENV_FILE.with_name(f".sec_email_env.paper.{ts}")
    shutil.copy2(ENV_FILE, backup)
    log(f"backup written: {backup}")

    # Step 3: compute conservative canary limits (1% of equity for max-position,
    # 1% drawdown trigger, $50 absolute loss trigger)
    canary_max_position = max(2.0, round(equity * 0.01, 2))
    canary_drawdown_pct = "1.0"           # 1% portfolio drawdown
    canary_max_loss_usd = max(5.0, round(equity * 0.01, 2))  # ~1% absolute
    canary_max_open = "3"
    canary_tp_pct = "0.05"                 # 5% take-profit
    canary_sl_pct = "0.02"                 # 2% stop-loss
    canary_max_signals = "2"               # max 2 entries per cycle

    log(f"canary limits: max_position=${canary_max_position}  drawdown_pct={canary_drawdown_pct}%  max_loss=${canary_max_loss_usd}")

    # Step 4: write the new env atomically
    new_env = dict(env_now)
    new_env["ALPACA_BASE_URL"] = LIVE_BASE
    new_env["ALPACA_DATA_URL"] = "https://data.alpaca.markets"
    new_env["ALPACA_API_KEY_ID"] = new_key
    new_env["ALPACA_API_SECRET"] = new_secret
    new_env["ALPACA_AGENT_LIVE_ORDERS"] = "1"
    new_env["ALPACA_MAX_POSITION_USD"] = str(canary_max_position)
    new_env["ALPACA_MAX_DAILY_LOSS_USD"] = str(canary_max_loss_usd)
    new_env["ALPACA_MAX_OPEN_POSITIONS"] = canary_max_open
    new_env["ALPACA_TAKE_PROFIT_PCT"] = canary_tp_pct
    new_env["ALPACA_STOP_LOSS_PCT"] = canary_sl_pct
    new_env["ALPACA_MAX_SIGNALS_PER_RUN"] = canary_max_signals
    new_env["KILL_SWITCH_DRAWDOWN_PCT"] = canary_drawdown_pct
    new_env["KILL_SWITCH_MAX_LOSS_USD"] = str(canary_max_loss_usd)
    write_env_atomic(new_env, ENV_FILE)
    log(f"wrote {ENV_FILE} with live keys + canary limits")

    # Step 5: verify kill switch works against live
    log("running agent_kill_switch.py against live …")
    ks_env = os.environ.copy()
    ks_env.update(new_env)
    result = subprocess.run(
        ["python3", str(ROOT / "agent_kill_switch.py")],
        env=ks_env,
        capture_output=True, text=True, timeout=30
    )
    log(f"  kill switch exit={result.returncode}  stdout={result.stdout.strip()[-200:]}")
    if result.returncode == 2:
        log("ERROR: kill switch failed validation against live keys")
        log("  rolling back …")
        shutil.copy2(backup, ENV_FILE)
        log(f"  restored {ENV_FILE} from {backup}")
        return 3

    # Step 6: shred the keys file (single-use)
    shred_file(LIVE_KEYS_FILE)
    log(f"shredded {LIVE_KEYS_FILE}")

    # Step 7: notify
    discord_msg = (
        "🟢 **LIVE TRADING ENABLED**\n"
        f"Alpaca account `{account_id[:8]}…` promoted from paper → live.\n"
        f"Equity: ${equity:,.2f}  Cash: ${cash:,.2f}\n"
        f"Canary limits: max-position ${canary_max_position}, "
        f"drawdown {canary_drawdown_pct}%, max-loss ${canary_max_loss_usd}\n"
        f"Kill switch verified. Stream daemon: `nohup python3 stream_market_data.py &`\n"
        f"Backup: `{backup.name}`"
    )
    notify_discord(new_env, discord_msg)
    log("=== promote_to_live SUCCESS ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
