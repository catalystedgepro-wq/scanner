#!/usr/bin/env bash
# autonomous_loop.sh — continuous scanner improvement loop.
#
# Runs every 2 hours during market hours. Jobs:
#   1. Refresh new-catalyst spokes (bankruptcy, 13D, delisting, cfpb)
#   2. Re-rank convergence with fresh data
#   3. Re-build gap∩convergence JACKPOT list
#   4. Evaluate outcomes (updates hit rate from yesterday's picks)
#   5. Auto-tune scoring_config based on fresh metrics
#   6. Bloomberg benchmark check — if hit_rate >= BENCHMARK_TARGET, idle
#
# Logs to /var/log/catalyst_loop.log
set -euo pipefail

ROOT="/opt/catalyst"
LOG="/var/log/catalyst_loop.log"
BENCHMARK_TARGET="${BENCHMARK_TARGET:-75}"  # stop condition: 75% hit_rate on +2% intraday
# Loop status written to internal path — NOT under docs/ so it is not
# served publicly. Operator-only telemetry.
STATUS_FILE="$ROOT/loop_status.json"
LOCK="/tmp/autonomous_loop.lock"

# Prevent overlapping cron runs — if a cycle is still running when the next one fires, skip it.
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] autonomous_loop SKIP: previous run still active" >> "$LOG"
  exit 0
fi

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

log() { echo "[$(ts)] $*" >> "$LOG"; }

cd "$ROOT"

log "=== autonomous_loop START ==="

# 1. Refresh catalyst spokes (parallel — they're independent)
run_spoke() {
  local name="$1"
  if [[ -f "$ROOT/$name" ]]; then
    if timeout 120 /usr/bin/python3 "$ROOT/$name" >> "$LOG" 2>&1; then
      log "  spoke_ok=$name"
    else
      log "  spoke_fail=$name"
    fi
  fi
}
run_spoke build_sec_bankruptcy.py &
run_spoke build_sec_13d.py &
run_spoke build_sec_delisting.py &
run_spoke build_cfpb.py &
run_spoke build_gap_scanner.py &
wait
# DCF runs serially after (SEC rate limits across spokes; don't pound the host)
# Timeout increased to 600s since DCF pulls 200 tickers at 10 req/s.
if [[ -f "$ROOT/build_sec_xbrl_dcf.py" ]]; then
  if timeout 600 /usr/bin/python3 "$ROOT/build_sec_xbrl_dcf.py" >> "$LOG" 2>&1; then
    log "  spoke_ok=build_sec_xbrl_dcf"
  else
    log "  spoke_fail=build_sec_xbrl_dcf (timeout or error)"
  fi
fi

# Numerai Signals — regenerate after convergence + DCF so signal reflects
# current rank. Submission happens weekly (Friday); we keep the file fresh.
if [[ -f "$ROOT/build_numerai_signals.py" ]]; then
  if /usr/bin/python3 "$ROOT/build_numerai_signals.py" >> "$LOG" 2>&1; then
    log "  spoke_ok=build_numerai_signals"
  fi
fi

# Composer.trade strategy export — JACKPOT picks as importable symphony.
# Distribution channel; refreshed every cycle so daily basket is current.
if [[ -f "$ROOT/build_composer_symphony.py" ]]; then
  if /usr/bin/python3 "$ROOT/build_composer_symphony.py" >> "$LOG" 2>&1; then
    log "  spoke_ok=build_composer_symphony"
  fi
fi

# Numerai auto-submit — only attempt if Signals model exists on user's account.
# Failure is logged + status JSON written, no break.
if [[ -f "$ROOT/submit_numerai.py" ]]; then
  /usr/bin/python3 "$ROOT/submit_numerai.py" >> "$LOG" 2>&1 || true
fi


# International + decentralized — append-mode spokes
if [[ -f "$ROOT/build_bse_india.py" ]]; then
  /usr/bin/python3 "$ROOT/build_bse_india.py" >> "$LOG" 2>&1 || true
fi
if [[ -f "$ROOT/build_eth_gas.py" ]]; then
  /usr/bin/python3 "$ROOT/build_eth_gas.py" >> "$LOG" 2>&1 || true
fi
# International equity overnight gappers (10 markets, 60+ tickers)
if [[ -f "$ROOT/build_intl_equity_gappers.py" ]]; then
  /usr/bin/python3 "$ROOT/build_intl_equity_gappers.py" >> "$LOG" 2>&1 || true
fi
# BTC spot ETF dollar-flow proxy (11 funds, IBIT/FBTC/etc)
if [[ -f "$ROOT/build_btc_etf_flows.py" ]]; then
  /usr/bin/python3 "$ROOT/build_btc_etf_flows.py" >> "$LOG" 2>&1 || true
fi
# DeFi protocol stress map via DefiLlama TVL deltas
if [[ -f "$ROOT/build_defi_liquidations.py" ]]; then
  /usr/bin/python3 "$ROOT/build_defi_liquidations.py" >> "$LOG" 2>&1 || true
fi
# Cross-border convergence: ADR↔home-listing pair scanner (50 pairs)
if [[ -f "$ROOT/build_crossborder_convergence.py" ]]; then
  timeout 300 /usr/bin/python3 "$ROOT/build_crossborder_convergence.py" >> "$LOG" 2>&1 || true
fi
# Intl derived panels: sympathy chains + sector heatmap + country leaderboard
if [[ -f "$ROOT/build_intl_derived.py" ]]; then
  /usr/bin/python3 "$ROOT/build_intl_derived.py" >> "$LOG" 2>&1 || true
fi
# International DCF: two-stage Damodaran via yfinance, 38 markets / 370+ names
if [[ -f "$ROOT/build_intl_dcf.py" ]]; then
  timeout 600 /usr/bin/python3 "$ROOT/build_intl_dcf.py" >> "$LOG" 2>&1 || true
fi
# Asymmetric Edge Insights: multi-scanner overlap + sector rotation + cross-asset
if [[ -f "$ROOT/build_intl_edge.py" ]]; then
  /usr/bin/python3 "$ROOT/build_intl_edge.py" >> "$LOG" 2>&1 || true
fi
# ASX announcements — Australian "8-K equivalent" feed (Markit Digital)
if [[ -f "$ROOT/build_asx_announcements.py" ]]; then
  /usr/bin/python3 "$ROOT/build_asx_announcements.py" >> "$LOG" 2>&1 || true
fi
# RNS UK — London Stock Exchange announcement feed (yfinance news)
if [[ -f "$ROOT/build_rns_uk.py" ]]; then
  timeout 240 /usr/bin/python3 "$ROOT/build_rns_uk.py" >> "$LOG" 2>&1 || true
fi
# HKEX — Hong Kong news feed (yfinance news)
if [[ -f "$ROOT/build_hkex_news.py" ]]; then
  timeout 240 /usr/bin/python3 "$ROOT/build_hkex_news.py" >> "$LOG" 2>&1 || true
fi
# TDnet — Japan TSE news feed (yfinance .T)
if [[ -f "$ROOT/build_tdnet_jp.py" ]]; then
  timeout 240 /usr/bin/python3 "$ROOT/build_tdnet_jp.py" >> "$LOG" 2>&1 || true
fi
# CVM — Brazil B3 news feed (yfinance .SA)
if [[ -f "$ROOT/build_cvm_br.py" ]]; then
  timeout 240 /usr/bin/python3 "$ROOT/build_cvm_br.py" >> "$LOG" 2>&1 || true
fi
# KIND — Korea KRX news feed (yfinance .KS)
if [[ -f "$ROOT/build_kind_kr.py" ]]; then
  timeout 240 /usr/bin/python3 "$ROOT/build_kind_kr.py" >> "$LOG" 2>&1 || true
fi
# BaFin — Germany XETRA news feed (yfinance .DE)
if [[ -f "$ROOT/build_bafin_de.py" ]]; then
  timeout 240 /usr/bin/python3 "$ROOT/build_bafin_de.py" >> "$LOG" 2>&1 || true
fi
# Cross-Asset Macro — yield curve, DXY, oil/gold, VIX, crude/natgas regimes
if [[ -f "$ROOT/build_xasset_macro.py" ]]; then
  timeout 120 /usr/bin/python3 "$ROOT/build_xasset_macro.py" >> "$LOG" 2>&1 || true
fi
# NSE — India catalyst news feed (yfinance .NS)
if [[ -f "$ROOT/build_nse_in.py" ]]; then
  timeout 240 /usr/bin/python3 "$ROOT/build_nse_in.py" >> "$LOG" 2>&1 || true
fi
# BMV — Mexico catalyst news feed (yfinance .MX)
if [[ -f "$ROOT/build_bmv_mx.py" ]]; then
  timeout 240 /usr/bin/python3 "$ROOT/build_bmv_mx.py" >> "$LOG" 2>&1 || true
fi
# Africa — JSE + ADRs + Nigeria/Kenya/Morocco/Egypt catalyst feed
if [[ -f "$ROOT/build_jse_africa.py" ]]; then
  timeout 240 /usr/bin/python3 "$ROOT/build_jse_africa.py" >> "$LOG" 2>&1 || true
fi
# SGX — Singapore catalyst news feed (yfinance .SI)
if [[ -f "$ROOT/build_sgx_sg.py" ]]; then
  timeout 240 /usr/bin/python3 "$ROOT/build_sgx_sg.py" >> "$LOG" 2>&1 || true
fi
# TWSE — Taiwan catalyst news feed (yfinance .TW)
if [[ -f "$ROOT/build_twse_tw.py" ]]; then
  timeout 240 /usr/bin/python3 "$ROOT/build_twse_tw.py" >> "$LOG" 2>&1 || true
fi
# Global Catalyst Tape — merge ALL per-country panels into unified feed
# Run AFTER all per-country spokes so it has fresh data.
if [[ -f "$ROOT/build_global_tape.py" ]]; then
  /usr/bin/python3 "$ROOT/build_global_tape.py" >> "$LOG" 2>&1 || true
fi
# Global Heatmap — continent → country → sector drill-down
if [[ -f "$ROOT/build_global_heatmap.py" ]]; then
  /usr/bin/python3 "$ROOT/build_global_heatmap.py" >> "$LOG" 2>&1 || true
fi


# Stripe live revenue snapshot — read-only via STRIPE_RESTRICTED_KEY
if [[ -f "$ROOT/build_stripe_revenue.py" ]]; then
  /usr/bin/python3 "$ROOT/build_stripe_revenue.py" >> "$LOG" 2>&1 || true
fi

# Alpaca paper-account snapshot — read-only, equity/positions/orders
if [[ -f "$ROOT/build_alpaca_account.py" ]]; then
  /usr/bin/python3 "$ROOT/build_alpaca_account.py" >> "$LOG" 2>&1 || true
fi

# Alpaca options chain — top 20 tickers by combined_priority score, unusual-flow flagging
if [[ -f "$ROOT/build_alpaca_options_chain.py" ]]; then
  /usr/bin/python3 "$ROOT/build_alpaca_options_chain.py" >> "$LOG" 2>&1 || true
fi

# Catalyst Edge → Alpaca paper trader.
# Default = DRY-RUN (logs decisions, does not place orders).
# To enable real paper-trade execution, add ALPACA_AGENT_LIVE_ORDERS=1 to .sec_email_env.
# Hard guardrails (env-overridable): max $50/trade, $200 daily loss kill switch, 5 open positions.
if [[ -f "$ROOT/agent_alpaca_orders.py" ]]; then
  /usr/bin/python3 "$ROOT/agent_alpaca_orders.py" >> "$LOG" 2>&1 || true
fi

# Catalyst Edge → Alpaca crypto paper trader.
# Default = DRY-RUN. To enable, add ALPACA_AGENT_CRYPTO_LIVE=1 to .sec_email_env.
# Universe: BTC/ETH/SOL/LTC/AVAX. Signals: BTC ETF flows + DeFi calm + ETH gas. Threshold score >= 2.
if [[ -f "$ROOT/agent_alpaca_crypto.py" ]]; then
  /usr/bin/python3 "$ROOT/agent_alpaca_crypto.py" >> "$LOG" 2>&1 || true
fi

# Catalyst Edge → crypto-treasury equity trader (the bridge between SEC scanner + crypto exposure).
# Routes the same signal to Alpaca paper (always) AND Tradier live (gated by TRADIER_LIVE_ORDERS=1).
# Universe: MSTR, MARA, RIOT, COIN, CIFR, CLSK, IREN, BITF, HUT, HIVE, TSLA, SQ, HOOD, BITO.
# Default $25/position cap, 4 concurrent max.
if [[ -f "$ROOT/agent_crypto_treasury.py" ]]; then
  /usr/bin/python3 "$ROOT/agent_crypto_treasury.py" >> "$LOG" 2>&1 || true
fi

# Catalyst Edge → Hyperliquid 24/7 perp trader (NON-US-jurisdiction venue).
# Hyperliquid blocks US/sanctioned IPs; for US operators use agent_coinbase.py instead.
# Default = DRY-RUN. Live: HYPERLIQUID_LIVE_ORDERS=1 + HYPERLIQUID_PRIVATE_KEY.
if [[ -f "$ROOT/agent_hyperliquid.py" ]]; then
  /usr/bin/python3 "$ROOT/agent_hyperliquid.py" >> "$LOG" 2>&1 || true
fi

# Catalyst Edge → Coinbase Advanced 24/7 spot trader (US-legal).
# Same signal stack as Hyperliquid bot: crypto-treasury equity flags (×3) +
# BTC ETF flow + DeFi calm + ETH gas relief.
# Default = DRY-RUN. To go live: COINBASE_LIVE_ORDERS=1 + COINBASE_API_KEY +
# COINBASE_API_SECRET in .sec_email_env.
if [[ -f "$ROOT/agent_coinbase.py" ]]; then
  /usr/bin/python3 "$ROOT/agent_coinbase.py" >> "$LOG" 2>&1 || true
fi

# Cumulative P/L tracker for the Coinbase bot — runs every loop tick.
# Computes realized + unrealized P/L from actual fills, fires Telegram +
# Discord webhooks on any new fill (entry or exit).
if [[ -f "$ROOT/track_coinbase_pnl.py" ]]; then
  /usr/bin/python3 "$ROOT/track_coinbase_pnl.py" >> "$LOG" 2>&1 || true
fi

# DeFi shadow trader — no venue, signal validation only.
# Universe: top 10 DeFi protocols by TVL. 5-day horizon, ±5%/-3% theoretical TP/SL.
if [[ -f "$ROOT/agent_defi_shadow.py" ]]; then
  /usr/bin/python3 "$ROOT/agent_defi_shadow.py" >> "$LOG" 2>&1 || true
fi

# Catalyst Edge → Alpaca options paper trader (long-call first cut).
# Default = DRY-RUN. To enable, add ALPACA_AGENT_OPTIONS_LIVE=1 to .sec_email_env.
# Universe: top-5 unusual-flow calls from /data/options_flow.json. $200/contract cap, 3 max open.
if [[ -f "$ROOT/agent_alpaca_options.py" ]]; then
  /usr/bin/python3 "$ROOT/agent_alpaca_options.py" >> "$LOG" 2>&1 || true
fi

# Catalyst Edge → Tradier equity agent ($100 funded, $25/position cap).
# Publish-first compliance: only trades tickers that have a validated scoop
# published in /scoops/ within the last 36h. Default DRY-RUN; flips to live
# when both TRADIER_LIVE=1 and TRADIER_AGENT_ENABLED=1 are set in .sec_email_env.
if [[ -f "$ROOT/agent_tradier_equities.py" ]]; then
  /usr/bin/python3 "$ROOT/agent_tradier_equities.py" >> "$LOG" 2>&1 || true
fi

# Agent outcomes tracker — read-only ledger of fills, exits, +1d/+5d/+30d outcomes vs SPY.
# Feeds tune_scoring_config.py via agent_outcomes_summary.csv (mirrors sec_outcome_summary.csv shape).
if [[ -f "$ROOT/track_agent_outcomes.py" ]]; then
  /usr/bin/python3 "$ROOT/track_agent_outcomes.py" >> "$LOG" 2>&1 || true
fi

# LinkedIn posts — generate fresh copy-paste posts from live data each cycle
if [[ -f "$ROOT/build_linkedin_posts.py" ]]; then
  /usr/bin/python3 "$ROOT/build_linkedin_posts.py" >> "$LOG" 2>&1 || true
fi

# Sitemap — regenerate on every loop so new pages get indexed
if [[ -f "$ROOT/build_sitemap.py" ]]; then
  /usr/bin/python3 "$ROOT/build_sitemap.py" >> "$LOG" 2>&1 || true
fi

# Daily digest email — once per day at 07:00 UTC, idempotent via status JSON
if [[ -f "$ROOT/send_daily_digest.py" ]]; then
  HOUR_UTC=$(date -u +%H)
  TODAY_UTC=$(date -u +%Y-%m-%d)
  LAST_SENT=$(/usr/bin/python3 -c "
import json, sys
try:
    d = json.load(open('$ROOT/docs/data/daily_digest_status.json'))
    print((d.get('last_attempt_utc') or '')[:10])
except Exception:
    print('')
" 2>/dev/null)
  if [[ "$HOUR_UTC" == "07" && "$LAST_SENT" != "$TODAY_UTC" ]]; then
    /usr/bin/python3 "$ROOT/send_daily_digest.py" >> "$LOG" 2>&1 || true
  fi
fi

# 1c. AlphaVantage NEWS_SENTIMENT — tier-1 news enrichment for top tickers.
# Free tier 25 req/day; we use 1-2/cycle. Skips silently if API key missing.
if [[ -f "$ROOT/build_alphavantage_news.py" ]]; then
  if /usr/bin/python3 "$ROOT/build_alphavantage_news.py" >> "$LOG" 2>&1; then
    log "  alphavantage_ok"
  else
    log "  alphavantage_fail"
  fi
fi

# 1c-bis. Short scanner data refresh — produces short_scanner.json +
# short_heatmap.json consumed by /short-scanner/ page. Without this cron
# wiring the data goes stale within hours of the morning run.
if [[ -f "$ROOT/build_short_scanner.py" ]]; then
  if /usr/bin/python3 "$ROOT/build_short_scanner.py" >> "$LOG" 2>&1; then
    log "  short_scanner_ok"
  else
    log "  short_scanner_fail"
  fi
fi

# 1c-tris. New cross-domain primary sources (Polymarket, GDACS, IMF PortWatch,
# NASA FIRMS, EIA petroleum). Each is feature-flag-gated by file existence;
# autonomous_loop is robust to any individual spoke failing.
for spoke in build_polymarket.py build_gdacs.py build_imf_portwatch.py build_nasa_firms.py build_cloudflare_radar.py compute_causal_lift.py compute_authenticity.py build_scoreboard.py compute_beat_rate.py; do
  if [[ -f "$ROOT/$spoke" ]]; then
    /usr/bin/python3 "$ROOT/$spoke" >> "$LOG" 2>&1 && log "  ${spoke%.py}_ok" || log "  ${spoke%.py}_fail"
  fi
done

# 1d. News momentum recompute — picks up the fresh AlphaVantage feed +
# all new tier-1 cross-domain sources (Polymarket/GDACS/EIA/FIRMS).
if [[ -f "$ROOT/build_news_momentum.py" ]]; then
  if /usr/bin/python3 "$ROOT/build_news_momentum.py" >> "$LOG" 2>&1; then
    log "  news_momentum_ok"
  fi
fi

# 1e. Auto-scoop summaries — citation-only narrative for top convergence
# alerts. Strict validator + Groq with no-individuals + cite-every-claim
# system prompt. Page renders even when LLM fails (citation-only fallback).
if [[ -f "$ROOT/build_scoop_summary.py" ]]; then
  if /usr/bin/python3 "$ROOT/build_scoop_summary.py" >> "$LOG" 2>&1; then
    log "  scoops_ok"
  else
    log "  scoops_fail"
  fi
fi

# 2. Re-rank
if /usr/bin/python3 "$ROOT/build_convergence_score.py" >> "$LOG" 2>&1; then
  log "  convergence_ok"
else
  log "  convergence_fail"
fi

# 3. JACKPOT list: gap ∩ convergence
/usr/bin/python3 - <<'PY' >> "$LOG" 2>&1
import csv, json
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path("/opt/catalyst")
gap = {}
gp = ROOT/"gap_scanner.csv"
if gp.exists():
    with gp.open() as f:
        for r in csv.DictReader(f): gap[r["ticker"]] = r
picks = []
cp = ROOT/"convergence_alerts.csv"
if cp.exists():
    with cp.open() as f:
        for r in csv.DictReader(f):
            t = r["ticker"]
            if t not in gap: continue
            g = gap[t]
            gs = float(g.get("gap_score") or 0)
            ong = float(g.get("overnight_gap_pct") or 0)
            cs = int(r.get("convergence_score") or 0)
            if gs < 60 or cs < 12: continue
            picks.append({
                "ticker": t, "score": cs, "conviction": r.get("conviction_level"),
                "gap_score": gs, "overnight_gap_pct": ong,
                "price": g.get("price",""),
                "signals": r.get("signals_fired",""),
                "tradable_today": ong >= 2,
            })
picks.sort(key=lambda x: (not x["tradable_today"], -x["score"]))
payload = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "count": len(picks), "tradable_today": sum(1 for p in picks if p["tradable_today"]),
    "picks": picks,
}
(ROOT/"docs/data").mkdir(parents=True, exist_ok=True)
(ROOT/"docs/data/gap_convergence.json").write_text(json.dumps(payload, indent=2))
print(f"jackpot: {len(picks)} picks, {payload['tradable_today']} tradable")
PY
log "  jackpot_ok"

# 4. Outcome evaluation (refresh hit rate metrics)
if /usr/bin/python3 "$ROOT/evaluate_sec_outcomes.py" --days 60 >> "$LOG" 2>&1; then
  log "  outcomes_ok"
else
  log "  outcomes_fail"
fi

# 5. Auto-tune (walk-forward eval + step adjustments, floor-guarded)
if /usr/bin/python3 "$ROOT/tune_scoring_config.py" >> "$LOG" 2>&1; then
  log "  tune_ok"
fi

# 5a. Loser-cluster rediscovery — refreshes sec_loser_clusters.json each cycle
# so new bad buckets get identified as outcome history grows.
if [[ -f "$ROOT/analyze_loser_clusters.py" ]]; then
  if /usr/bin/python3 "$ROOT/analyze_loser_clusters.py" >> "$LOG" 2>&1; then
    log "  cluster_ok"
  else
    log "  cluster_fail"
  fi
fi

# 5b. Interaction lookup table — cross-feature conditional hit rates.
# Used for borderline pick scoring; refreshed alongside cluster output.
if [[ -f "$ROOT/build_interaction_score.py" ]]; then
  if /usr/bin/python3 "$ROOT/build_interaction_score.py" >> "$LOG" 2>&1; then
    log "  interaction_ok"
  else
    log "  interaction_fail"
  fi
fi

# 5c. Auto-promote kill-list rules when a stable bucket falls below Wilson 25%.
# This is the closed-loop magic: cluster discovers losers, promoter blocks them.
if [[ -f "$ROOT/auto_promote_kill_list.py" ]]; then
  if /usr/bin/python3 "$ROOT/auto_promote_kill_list.py" >> "$LOG" 2>&1; then
    log "  promote_ok"
  else
    log "  promote_fail"
  fi
fi

# 5d. Walk-forward decay alarm — if holdout regressed, surface to /trust/.
DECAY=$(/usr/bin/python3 -c "
import json
try:
    d = json.load(open('$ROOT/sec_walk_forward_summary.json'))
    print('1' if d.get('decay_flag') else '0')
except: print('0')
" 2>/dev/null || echo "0")
if [[ "$DECAY" == "1" ]]; then
  log "  decay_alarm: holdout < train by 5pp+"
fi

# 6. Honest benchmark: published score>=15 hit rate (NOT raw in-sample noise floor)
CURRENT_HIT=$(/usr/bin/python3 -c "
import csv
try:
    with open('$ROOT/sec_outcome_summary.csv') as f:
        for r in csv.DictReader(f):
            if r.get('list_name') == 'sec_clean_gappers':
                # Prefer published_hit_rate_2pct (score>=15 only); fall back to raw.
                print(r.get('published_hit_rate_2pct') or r.get('hit_rate_2pct','0'))
                break
except: print('0')
" 2>/dev/null || echo "0")

# Holdout (out-of-sample) hit rate from walk-forward split.
HOLDOUT_HIT=$(/usr/bin/python3 -c "
import json
try:
    d = json.load(open('$ROOT/sec_walk_forward_summary.json'))
    print(d.get('holdout_hit_rate_2pct', 0))
except: print('0')
" 2>/dev/null || echo "0")

BEATS_BENCHMARK="false"
if /usr/bin/python3 -c "import sys; sys.exit(0 if float('$CURRENT_HIT' or 0) >= float('$BENCHMARK_TARGET') else 1)" 2>/dev/null; then
  BEATS_BENCHMARK="true"
fi

# Publish loop status for /trust/ — now includes published + holdout + decay flag.
/usr/bin/python3 - <<PY >> "$LOG" 2>&1
import json
from datetime import datetime, timezone
payload = {
    "last_run": datetime.now(timezone.utc).isoformat(),
    "published_hit_rate_2pct": float("$CURRENT_HIT" or 0),
    "holdout_hit_rate_2pct": float("$HOLDOUT_HIT" or 0),
    "benchmark_target": float("$BENCHMARK_TARGET"),
    "beats_benchmark": $([ "$BEATS_BENCHMARK" = "true" ] && echo "True" || echo "False"),
    "decay_flag": $([ "$DECAY" = "1" ] && echo "True" || echo "False"),
    "status": "IDLE_AT_TARGET" if $([ "$BEATS_BENCHMARK" = "true" ] && echo "True" || echo "False") else "LOOPING",
}
open("$STATUS_FILE","w").write(json.dumps(payload, indent=2))
PY

log "  published_hit=$CURRENT_HIT  holdout_hit=$HOLDOUT_HIT  target=$BENCHMARK_TARGET  beats=$BEATS_BENCHMARK  decay=$DECAY"
log "=== autonomous_loop END ==="
