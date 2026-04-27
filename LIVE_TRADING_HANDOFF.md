# Live Trading — Operator Handoff

Status: **PAPER** (Alpaca paper account, $100,000 simulated equity).
Goal: Migrate to a $50–$100 funded live account with zero engineering involvement from you.

## What's already in place (no action needed)

| Component | File | Status |
|---|---|---|
| Equity order agent | `agent_alpaca_orders.py` | ✅ live-ready, lockfile-aware |
| Crypto order agent | `agent_alpaca_crypto.py` | ✅ live-ready, lockfile-aware |
| Options order agent | `agent_alpaca_options.py` | ✅ Tradier-backed, lockfile-aware |
| Portfolio circuit breaker | `agent_kill_switch.py` | ✅ cron `*/5 14-21 * * 1-5` |
| Streaming market data | `stream_market_data.py` | ✅ Finnhub/Alpaca WS, auto-reconnect |
| Live canary monitor | `live_canary_monitor.py` | ✅ cron `*/15 13-22 * * 1-5` |
| Live dashboard | `docs/canary/index.html` | ✅ public at `/canary/` |
| Auto-promotion script | `promote_to_live.py` | ✅ waits for `.alpaca_live_keys` |
| Auto-promotion watcher | cron every 30 min | ✅ runs `promote_to_live.py` if file appears |
| Discord + Telegram alerts | hard-wired to existing webhooks | ✅ every fill, drawdown, kill-switch event |

## Your three steps (literally everything you do)

### Step 1 — Fund your live Alpaca account
1. Log into <https://app.alpaca.markets>
2. **Banking → Deposit** → wire $50–$100 (whatever you're comfortable risking)
3. Wait for the deposit to clear (1–3 business days for ACH)

### Step 2 — Generate live API keys
1. <https://app.alpaca.markets> → **Manage Account** → **API Keys**
2. Click **Generate** in the LIVE TRADING section (NOT paper)
3. Copy the Key ID + Secret immediately (Alpaca shows the secret only once)

### Step 3 — Drop the keys into the workspace
Save a file at `/home/operator/.openclaw/workspace/.alpaca_live_keys` with exactly this content:

```
ALPACA_API_KEY_ID=PK....your_live_key_id
ALPACA_API_SECRET=....your_live_secret
```

The auto-promotion watcher fires every 30 minutes during market hours. The next cycle after you drop the file will:

1. Validate the keys against `https://api.alpaca.markets/v2/account`
2. Confirm the account is funded and not trading-blocked
3. Backup the current `.sec_email_env` to `.sec_email_env.paper.<timestamp>`
4. Write the live keys + URLs into `.sec_email_env`
5. Set conservative canary safety limits:
   - `ALPACA_MAX_POSITION_USD` = 1% of your equity (so $1 if you fund $100)
   - `ALPACA_MAX_DAILY_LOSS_USD` = 1% of equity
   - `KILL_SWITCH_DRAWDOWN_PCT` = 1.0%
   - `ALPACA_MAX_OPEN_POSITIONS` = 3
   - `ALPACA_MAX_SIGNALS_PER_RUN` = 2
6. Run the kill switch against live to confirm wiring
7. Securely shred `.alpaca_live_keys` (single-use file)
8. Post a Discord notification: `🟢 LIVE TRADING ENABLED`

If anything fails, the script aborts WITHOUT modifying `.sec_email_env`.

## What you'll see during live operation

- **Discord** + **Telegram** notifications on every:
  - Position opened (`🟢 OPEN {ticker}`)
  - Position closed (`🔴 CLOSE {ticker}` with P/L)
  - Drawdown threshold crossed (-0.5%, -1%, -2%)
  - Kill switch trip (`🛑` with full reason)
  - Daily summary at 21:00 UTC

- **Live dashboard** at `https://catalystedgescanner.com/canary/`
  - Equity, P/L today, cash, open positions, unrealized P/L, orders
  - Kill switch state (armed / tripped)
  - Last 20 events
  - Auto-refreshes every 30 seconds

## Manual overrides

| Action | Command |
|---|---|
| Pause all trading immediately | `touch /home/operator/.openclaw/workspace/.kill_switch_tripped` |
| Resume after pause | `rm /home/operator/.openclaw/workspace/.kill_switch_tripped` |
| Roll back to paper | `cp /home/operator/.openclaw/workspace/.sec_email_env.paper.<ts> /home/operator/.openclaw/workspace/.sec_email_env` |
| Increase position size after canary | edit `ALPACA_MAX_POSITION_USD` in `.sec_email_env` |

## Recommended canary protocol

Week 1: fund $50, watch the dashboard, expect 1-3 paper-equivalent positions per day at $1 each.
Week 2: if Week 1 P/L is positive, increase `ALPACA_MAX_POSITION_USD` to 2% of equity.
Week 4: if Week 1-3 P/L is positive, increase to 5% and bump `ALPACA_MAX_OPEN_POSITIONS` to 5.

The kill switch will protect against catastrophic loss at any size — but your eyes on the Discord alerts are still the best safety layer.
