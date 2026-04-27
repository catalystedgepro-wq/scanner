# Catalyst Edge — Open-Source Catalyst Scanner

A self-hosted catalyst-trading research toolkit. Aggregates SEC EDGAR
filings, tier-1 wire services, prediction markets, and disaster sensor
APIs into Wilson-bounded conviction scores. Optional live-trading agent
mirrors the same publicly-published signals via your brokerage API.

## What's inside

* **`build_*.py`** — data spokes (one per source: SEC, AlphaVantage,
  Polymarket, GDACS, Federal Register, Cloudflare Radar, IMF PortWatch, ...)
* **`compute_causal_lift.py`** — counterfactual peer-cohort baseline
  attribution; the "is the move attributable to the catalyst itself?" engine
* **`compute_authenticity.py`** — anti-pump scoring
* **`build_scoreboard.py`** — public hit-rate scoreboard generator
* **`agent_tradier_equities.py`** — publish-first compliance trading agent
* **`evaluate_sec_outcomes.py`** — outcome ledger w/ SPY-relative alpha
* **`tune_scoring_config.py`** — walk-forward holdout auto-tuner

## Quick start

```bash
git clone <this repo>
cp .env.example .env
# Fill in SEC_USER_AGENT minimum. Rest are optional.
python3 build_news_momentum.py
python3 build_scoreboard.py
```

See `SECURITY.md` for credential management and `CONTRIBUTING.md` for PRs.

## Design philosophy

1. **Wilson lower bound everywhere** — never trust a small-n claim
2. **Walk-forward, not in-sample** — tune on T-90→T-30, report T-30→T
3. **Publish-first** — never trade a signal that hasn't been publicly
   surfaced first (the analyst-newsletter compliance posture)
4. **Stdlib-first** — minimal external deps so it runs anywhere

## License

MIT — see LICENSE.

## Disclaimer

Not financial advice. Trading the live agent against your own brokerage
account is at your own risk. Read SECURITY.md before activating any
live-trade env vars.
