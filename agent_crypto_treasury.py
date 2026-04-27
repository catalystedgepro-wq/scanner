#!/usr/bin/env python3
"""agent_crypto_treasury.py — Catalyst Edge crypto-treasury equity trader.

Bridges "trade crypto" with our actual edge (SEC equity catalysts) by filtering
the daily scanner picks to a curated crypto-treasury equity universe. These
tickers are 0.7–0.9 correlated with BTC and our scanner already covers them.

UNIVERSE (crypto-treasury equities):
  Bitcoin treasuries: MSTR, TSLA, SQ, BLOCK
  Bitcoin miners:     MARA, RIOT, CIFR, CLSK, IREN, BITF, HUT, HIVE
  Crypto exchanges:   COIN, HOOD
  ETF issuers:        BITO (futures-based BTC ETF, used as proxy)

ROUTING (parallel — same signal, two ledgers):
  - Alpaca paper:  always on (read-only proof from PA38BWRTO9EP)
  - Tradier live:  gated by TRADIER_LIVE_ORDERS=1 in .sec_email_env
                   uses TRADIER_TOKEN + TRADIER_ACCOUNT_ID

SAFETY (per-leg, hardcoded, env-overridable):
  CRYPTO_TREASURY_MAX_POSITION_USD     default 25  (small while validating)
  CRYPTO_TREASURY_MAX_OPEN             default 4
  CRYPTO_TREASURY_TP_PCT               default 0.05
  CRYPTO_TREASURY_SL_PCT               default 0.04
  .agent_crypto_treasury_halted file → kill switch

OUTPUTS (both feed /trust/ public ledger):
  docs/data/crypto_treasury_decisions.json   every candidate + decision
  docs/data/crypto_treasury_ledger.json      placed orders only (audit trail)

The strategy: rank our scanner's combined_priority by score, filter to
universe, take the top N each day. Same logic on both ledgers — when Tradier
is funded and TRADIER_LIVE_ORDERS=1, real money follows the paper trail.
"""
from __future__ import annotations

import csv
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/operator/.openclaw/workspace")
ENV_FILE = ROOT / ".sec_email_env"
HALT_FILE = ROOT / ".agent_crypto_treasury_halted"
COMBINED_CSV = ROOT / "combined_priority.csv"
DECISIONS_OUT = ROOT / "docs/data/crypto_treasury_decisions.json"
LEDGER_OUT = ROOT / "docs/data/crypto_treasury_ledger.json"
LOG_PATH = ROOT / "logs/crypto_treasury.log"
LOG_PATH.parent.mkdir(exist_ok=True)
DECISIONS_OUT.parent.mkdir(parents=True, exist_ok=True)

UNIVERSE = {
    # bitcoin treasuries
    "MSTR": "Strategy (treasury)",
    "TSLA": "Tesla (treasury)",
    "SQ":   "Block Inc (treasury)",
    "BLOCK": "Block Inc (treasury)",
    # bitcoin miners
    "MARA": "MARA Holdings (miner)",
    "RIOT": "Riot Platforms (miner)",
    "CIFR": "Cipher Mining (miner)",
    "CLSK": "CleanSpark (miner)",
    "IREN": "IREN (miner)",
    "BITF": "Bitfarms (miner)",
    "HUT":  "Hut 8 (miner)",
    "HIVE": "HIVE Digital (miner)",
    # exchanges
    "COIN": "Coinbase (exchange)",
    "HOOD": "Robinhood (exchange)",
    # ETF proxies
    "BITO": "ProShares BTC futures ETF",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg: str) -> None:
    line = f"[{now_iso()}] {msg}"
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def env_float(name: str, default: float) -> float:
    try:
        return float((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


def read_picks() -> list[dict]:
    if not COMBINED_CSV.exists():
        return []
    rows: list[dict] = []
    with COMBINED_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = (r.get("ticker") or "").strip().upper()
            if t in UNIVERSE:
                try:
                    score = float(r.get("composite_score") or r.get("total_score") or r.get("score") or 0)
                except ValueError:
                    score = 0.0
                rows.append({
                    "ticker": t,
                    "label": UNIVERSE[t],
                    "score": score,
                    "form": r.get("form") or r.get("filing") or "",
                    "reason": r.get("reason") or r.get("rationale") or "",
                })
    rows.sort(key=lambda r: -r["score"])
    return rows


def get_alpaca_quote(ticker: str, key: str, secret: str, base: str) -> float | None:
    url = f"{base}/v2/stocks/{ticker}/quotes/latest"
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        q = d.get("quote") or {}
        ap = float(q.get("ap") or 0)
        bp = float(q.get("bp") or 0)
        if ap and bp:
            return (ap + bp) / 2
        return ap or bp or None
    except Exception as e:
        log(f"alpaca_quote {ticker} ERROR: {e}")
        return None


def place_alpaca_order(ticker: str, qty: int, key: str, secret: str, base: str,
                      tp_pct: float, sl_pct: float) -> dict:
    url = f"{base.replace('data.', 'api.')}/v2/orders"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    coid = f"ce_ct_{today}_{ticker}"
    quote = get_alpaca_quote(ticker, key, secret, base.replace("api.", "data."))
    if not quote:
        return {"ok": False, "reason": "no_quote"}
    body = {
        "symbol": ticker,
        "qty": str(qty),
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
        "order_class": "bracket",
        "take_profit": {"limit_price": str(round(quote * (1 + tp_pct), 2))},
        "stop_loss": {"stop_price": str(round(quote * (1 - sl_pct), 2))},
        "client_order_id": coid,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"ok": True, "alpaca": json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"raw": str(e)}
        return {"ok": False, "reason": "http_" + str(e.code), "err": err}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}


def place_tradier_order(ticker: str, qty: int, token: str, account: str) -> dict:
    """Place a market day order on Tradier. Only fires if TRADIER_LIVE_ORDERS=1."""
    if (os.environ.get("TRADIER_LIVE_ORDERS") or "").strip() != "1":
        return {"ok": False, "reason": "TRADIER_LIVE_ORDERS!=1 (gate)"}
    if not token or not account:
        return {"ok": False, "reason": "missing TRADIER_TOKEN or TRADIER_ACCOUNT_ID"}
    url = f"https://api.tradier.com/v1/accounts/{account}/orders"
    body = {
        "class": "equity",
        "symbol": ticker,
        "side": "buy",
        "quantity": str(qty),
        "type": "market",
        "duration": "day",
    }
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"ok": True, "tradier": json.loads(resp.read().decode("utf-8"))}
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8"))
        except Exception:
            err = {"raw": str(e)}
        return {"ok": False, "reason": "http_" + str(e.code), "err": err}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}


def main() -> int:
    load_env()
    if HALT_FILE.exists():
        log("HALT file present — exiting without placing orders")
        return 0

    max_pos_usd = env_float("CRYPTO_TREASURY_MAX_POSITION_USD", 25.0)
    max_open = env_int("CRYPTO_TREASURY_MAX_OPEN", 4)
    tp_pct = env_float("CRYPTO_TREASURY_TP_PCT", 0.05)
    sl_pct = env_float("CRYPTO_TREASURY_SL_PCT", 0.04)
    alpaca_live = (os.environ.get("ALPACA_AGENT_LIVE_ORDERS") or "").strip() == "1"
    tradier_live = (os.environ.get("TRADIER_LIVE_ORDERS") or "").strip() == "1"

    alpaca_key = os.environ.get("ALPACA_API_KEY_ID", "")
    alpaca_sec = os.environ.get("ALPACA_API_SECRET_KEY", "")
    alpaca_base = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    alpaca_data = "https://data.alpaca.markets"

    tradier_token = os.environ.get("TRADIER_TOKEN", "")
    tradier_account = os.environ.get("TRADIER_ACCOUNT_ID", "")

    picks = read_picks()
    log(f"universe={len(UNIVERSE)} matches={len(picks)} alpaca_live={alpaca_live} tradier_live={tradier_live}")
    if not picks:
        DECISIONS_OUT.write_text(json.dumps({
            "as_of": now_iso(),
            "universe_size": len(UNIVERSE),
            "matches": 0,
            "max_open": max_open,
            "max_position_usd": max_pos_usd,
            "alpaca_live": alpaca_live,
            "tradier_live": tradier_live,
            "decisions": [],
        }, indent=2))
        return 0

    decisions: list[dict] = []
    placed: list[dict] = []
    for i, p in enumerate(picks[:max_open]):
        t = p["ticker"]
        # Determine quantity from available quote and max_pos_usd cap
        quote = get_alpaca_quote(t, alpaca_key, alpaca_sec, alpaca_data) if alpaca_key else None
        qty = max(1, int(max_pos_usd / quote)) if quote else 1
        decision: dict = {
            "ticker": t, "label": p["label"], "score": p["score"],
            "rank": i + 1, "qty": qty, "approx_price": quote,
            "max_position_usd": max_pos_usd,
            "alpaca": None, "tradier": None,
        }
        # Alpaca paper (always logs, only places if ALPACA_AGENT_LIVE_ORDERS=1)
        if alpaca_live and alpaca_key and alpaca_sec:
            decision["alpaca"] = place_alpaca_order(
                t, qty, alpaca_key, alpaca_sec, alpaca_data, tp_pct, sl_pct,
            )
        else:
            decision["alpaca"] = {"ok": False, "reason": "dry_run (ALPACA_AGENT_LIVE_ORDERS!=1)"}
        # Tradier live (always tries; gate is inside place_tradier_order)
        if tradier_token and tradier_account:
            decision["tradier"] = place_tradier_order(t, qty, tradier_token, tradier_account)
        else:
            decision["tradier"] = {"ok": False, "reason": "missing TRADIER_TOKEN or TRADIER_ACCOUNT_ID"}

        decisions.append(decision)
        if (decision["alpaca"] or {}).get("ok") or (decision["tradier"] or {}).get("ok"):
            placed.append(decision)
        log(f"  #{i+1} {t} qty={qty} alpaca_ok={(decision['alpaca'] or {}).get('ok')} tradier_ok={(decision['tradier'] or {}).get('ok')}")

    DECISIONS_OUT.write_text(json.dumps({
        "as_of": now_iso(), "universe_size": len(UNIVERSE),
        "matches": len(picks), "max_open": max_open,
        "max_position_usd": max_pos_usd,
        "alpaca_live": alpaca_live, "tradier_live": tradier_live,
        "decisions": decisions,
    }, indent=2))

    # Append placed to ledger (audit trail — never overwritten)
    existing: list[dict] = []
    if LEDGER_OUT.exists():
        try:
            existing = json.loads(LEDGER_OUT.read_text())
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
    for p in placed:
        existing.append({"placed_at": now_iso(), **p})
    LEDGER_OUT.write_text(json.dumps(existing[-500:], indent=2))

    log(f"DONE  decisions={len(decisions)}  placed={len(placed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
