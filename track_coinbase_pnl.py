#!/usr/bin/env python3
"""track_coinbase_pnl.py — Cumulative P/L tracker for the Coinbase live bot.

Runs every cron tick. Pulls all fills + current MTM, computes:
  - realized P/L (closed positions only)
  - unrealized P/L (open positions, MTM)
  - total fees paid
  - daily/weekly equity curve
  - drawdown from peak

Writes to docs/data/coinbase_pnl.json for /trust/ to render.
Fires a Discord webhook + Telegram on any new fill (entry or exit).

NOT a backtester. This is forward-only — what actually happened on Coinbase.
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".sec_email_env"
# Try multiple key file locations; env vars are the canonical path on the
# droplet (Windows path is for local WSL dev only).
KEY_FILE_CANDIDATES = [
    Path("/opt/catalyst/cdp_api_key.json"),
    ROOT / "cdp_api_key.json",
    Path("/path/to/local/Desktop/catalyst-edge/cdp_api_key.json"),
]
KEY_FILE = next((p for p in KEY_FILE_CANDIDATES if p.exists()), KEY_FILE_CANDIDATES[0])
PNL_OUT = ROOT / "docs/data/coinbase_pnl.json"
SEEN_FILLS = ROOT / "docs/data/coinbase_fills_seen.json"
LOG = ROOT / "logs/coinbase_pnl.log"
LOG.parent.mkdir(exist_ok=True)
PNL_OUT.parent.mkdir(parents=True, exist_ok=True)

PRODUCTS = ["BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "LINK-USD",
            "DOGE-USD", "POL-USD", "DOT-USD", "ATOM-USD", "ARB-USD"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(m: str) -> None:
    line = f"[{now_iso()}] {m}"
    LOG.open("a").write(line + "\n")
    print(line)


def load_env() -> None:
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def get_key() -> tuple[str, bytes] | None:
    """CDP key resolution: try keyfile first, fall back to env vars.

    Env-var path: COINBASE_API_KEY is the key id (UUID-form), and
    COINBASE_API_SECRET is the base64-encoded privateKey (same format as
    the JSON keyfile's privateKey field). This lets the droplet run from
    .sec_email_env without a separate JSON dropped on disk.
    """
    if KEY_FILE.exists():
        d = json.loads(KEY_FILE.read_text())
        raw = base64.b64decode(d["privateKey"])
        return d["id"], raw[:32]
    key_id = os.environ.get("COINBASE_API_KEY", "").strip()
    secret = os.environ.get("COINBASE_API_SECRET", "").strip()
    if not (key_id and secret):
        return None
    try:
        raw = base64.b64decode(secret)
    except Exception:
        return None
    if len(raw) < 32:
        return None
    return key_id, raw[:32]


def jwt_for(method: str, path_no_query: str, key_id: str, priv32: bytes) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import jwt as pyjwt
    pk = Ed25519PrivateKey.from_private_bytes(priv32)
    n = int(time.time())
    return pyjwt.encode(
        {"sub": key_id, "iss": "cdp", "nbf": n, "exp": n + 120,
         "uri": f"{method} api.coinbase.com{path_no_query}"},
        pk, algorithm="EdDSA", headers={"kid": key_id, "nonce": str(n)},
    )


def cb_get(path_with_query: str, key_id: str, priv32: bytes) -> dict | None:
    path_no_q = path_with_query.split("?", 1)[0]
    token = jwt_for("GET", path_no_q, key_id, priv32)
    req = urllib.request.Request(
        "https://api.coinbase.com" + path_with_query,
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        log(f"cb_get {path_with_query} ERR: {e}")
        return None


def fetch_all_fills(key_id: str, priv32: bytes) -> list[dict]:
    """Pull recent fills across all products."""
    out: list[dict] = []
    for p in PRODUCTS:
        d = cb_get(
            f"/api/v3/brokerage/orders/historical/fills?product_id={p}&limit=100",
            key_id, priv32,
        )
        if d and "fills" in d:
            out.extend(d["fills"])
    out.sort(key=lambda f: f.get("trade_time") or "", reverse=False)
    return out


def fetch_balances(key_id: str, priv32: bytes) -> dict:
    d = cb_get("/api/v3/brokerage/accounts?limit=250", key_id, priv32) or {}
    holdings: dict[str, float] = {}
    usd = 0.0
    for a in d.get("accounts", []):
        cur = a.get("currency", "")
        bal = float((a.get("available_balance") or {}).get("value") or 0)
        if cur == "USD":
            usd = bal
        elif bal > 0:
            holdings[cur] = bal
    return {"usd": usd, "holdings": holdings}


def fetch_prices() -> dict[str, float]:
    out: dict[str, float] = {}
    for p in PRODUCTS:
        sym = p.split("-")[0]
        try:
            with urllib.request.urlopen(
                f"https://api.coinbase.com/api/v3/brokerage/market/products/{p}",
                timeout=8,
            ) as r:
                d = json.loads(r.read())
            out[sym] = float(d.get("price") or 0)
        except Exception:
            pass
    return out


def _fill_base_size(f: dict) -> float:
    """Coinbase fill 'size' is in BASE currency when size_in_quote=False, in
    QUOTE currency (USD) when size_in_quote=True. We always normalize to base
    units (ETH, BTC, etc) so cost-basis math is consistent."""
    raw = float(f.get("size") or 0)
    px = float(f.get("price") or 0)
    in_quote = bool(f.get("size_in_quote"))
    if in_quote and px > 0:
        return raw / px
    return raw


def compute_pnl(fills: list[dict], holdings: dict, prices: dict) -> dict:
    """FIFO match BUYs and SELLs per product. Sizes normalized to base units."""
    by_product: dict[str, list[dict]] = {}
    for f in fills:
        pid = f.get("product_id")
        if pid:
            by_product.setdefault(pid, []).append(f)

    realized = 0.0
    fees_paid = 0.0
    closed_trades: list[dict] = []
    open_lots: dict[str, list[tuple[float, float, str]]] = {}

    for pid, flist in by_product.items():
        lots: list[tuple[float, float, str]] = []
        for f in flist:
            side = f.get("side")
            base_sz = _fill_base_size(f)  # always BASE units
            px = float(f.get("price") or 0)
            fee = float(f.get("commission") or 0)
            ts = f.get("trade_time") or ""
            fees_paid += fee
            if base_sz <= 0 or px <= 0:
                continue
            if side == "BUY":
                lots.append((base_sz, px, ts))
            elif side == "SELL":
                remaining = base_sz
                cost_basis = 0.0
                while remaining > 0 and lots:
                    lot_sz, lot_px, lot_ts = lots[0]
                    take = min(lot_sz, remaining)
                    cost_basis += take * lot_px
                    if take >= lot_sz - 1e-12:
                        lots.pop(0)
                    else:
                        lots[0] = (lot_sz - take, lot_px, lot_ts)
                    remaining -= take
                gross = base_sz * px
                pnl = gross - cost_basis
                realized += pnl
                closed_trades.append({
                    "product": pid, "base_size": base_sz, "exit_price": px,
                    "exit_ts": ts, "pnl": pnl,
                })
        open_lots[pid] = lots

    unrealized = 0.0
    open_positions: list[dict] = []
    for pid, lots in open_lots.items():
        if not lots:
            continue
        sym = pid.split("-")[0]
        price = prices.get(sym, 0)
        for sz, px, ts in lots:
            u = (price - px) * sz
            unrealized += u
            open_positions.append({
                "product": pid, "base_size": sz, "entry_price": px,
                "entry_ts": ts, "mark_price": price,
                "unrealized_pnl": round(u, 4),
                "unrealized_pct": round((price/px - 1) if px else 0, 6),
            })

    return {
        "realized_pnl": round(realized, 4),
        "unrealized_pnl": round(unrealized, 4),
        "total_pnl": round(realized + unrealized, 4),
        "fees_paid": round(fees_paid, 4),
        "fills_count": len(fills),
        "closed_trades": closed_trades[-25:],
        "open_positions": open_positions,
    }


def post_webhooks(message: str) -> None:
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chan = os.environ.get("TELEGRAM_CHANNEL", "")
    dc_url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if tg_token and tg_chan:
        try:
            urllib.request.urlopen(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                data=json.dumps({
                    "chat_id": tg_chan, "text": message, "parse_mode": "Markdown",
                }).encode(),
                timeout=10,
            )
        except Exception:
            pass
    if dc_url:
        try:
            urllib.request.urlopen(
                dc_url,
                data=json.dumps({"content": message}).encode(),
                timeout=10,
            )
        except Exception:
            pass


def main() -> int:
    load_env()
    k = get_key()
    if not k:
        log("no Coinbase key file — exit")
        return 1
    key_id, priv32 = k
    fills = fetch_all_fills(key_id, priv32)
    bal = fetch_balances(key_id, priv32)
    prices = fetch_prices()
    pnl = compute_pnl(fills, bal["holdings"], prices)

    equity = bal["usd"] + sum(
        float(q) * (prices.get(s, 0) or 0)
        for s, q in (bal["holdings"] or {}).items()
    )

    PNL_OUT.write_text(json.dumps({
        "as_of": now_iso(),
        "usd_balance": round(bal["usd"], 2),
        "equity": round(equity, 2),
        "holdings_value": round(equity - bal["usd"], 2),
        "starting_capital": float(os.environ.get("COINBASE_STARTING_CAPITAL", "97.50")),
        "total_pnl": pnl["total_pnl"],
        "realized_pnl": pnl["realized_pnl"],
        "unrealized_pnl": pnl["unrealized_pnl"],
        "fees_paid": pnl["fees_paid"],
        "fills_count": pnl["fills_count"],
        "open_positions": pnl["open_positions"],
        "recent_closed": pnl["closed_trades"],
    }, indent=2))

    # Webhook on any new fill since last run
    seen: dict[str, bool] = {}
    if SEEN_FILLS.exists():
        try:
            seen = json.loads(SEEN_FILLS.read_text())
        except Exception:
            seen = {}
    new_fills = [f for f in fills if f.get("trade_id") and not seen.get(f["trade_id"])]
    referral_url = os.environ.get("COINBASE_REFERRAL_URL", "")
    for f in new_fills:
        side = f.get("side")
        pid = f.get("product_id")
        sz = f.get("size")
        px = f.get("price")
        ts = f.get("trade_time", "")[:19]
        msg = (f"⚡ Catalyst Edge bot — *{side} {pid}*  {sz} @ ${px}  ({ts}Z)\n"
               f"Live ledger: https://catalystedgescanner.com/trust/")
        if referral_url:
            msg += f"\nMirror via Coinbase: {referral_url}"
        post_webhooks(msg)
        seen[f["trade_id"]] = True
    SEEN_FILLS.write_text(json.dumps(seen, indent=2))

    log(f"equity=${equity:.2f} total_pnl=${pnl['total_pnl']:+.4f} "
        f"realized=${pnl['realized_pnl']:+.4f} unrealized=${pnl['unrealized_pnl']:+.4f} "
        f"fees=${pnl['fees_paid']:.4f} fills={pnl['fills_count']} "
        f"open={len(pnl['open_positions'])} new_alerts={len(new_fills)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
