# Contributing

Thanks for considering a contribution. The project values:

* **Stdlib-only Python** in core spokes (no `numpy`, `pandas`, `requests` —
  use `urllib`, `csv`, `json`). Keeps deploy footprint small. Exceptions:
  `cryptography` for Tradier JWT, optional ML deps clearly opt-in.
* **Wilson-bounded conviction** — every quantitative claim should ship with
  a confidence interval, not a raw point estimate.
* **Publish-first compliance** — anything that triggers a trade must publish
  a citation page first.

## Workflow

1. Fork → clone
2. `cp .env.example .env` and fill in the keys you actually need
3. Run `python3 build_news_momentum.py` to validate your local pipeline
4. Open a PR with a description of what your change does and why
5. Tests live in `tests/` — `python3 -m pytest tests/`

## What we'll accept

* New free-tier data spokes (follow `build_polymarket.py` shape)
* Bug fixes with reproducer
* Documentation improvements
* Wilson lower-bound improvements + walk-forward methodology

## What we won't merge

* Hardcoded API keys
* Code that scrapes paywalled sources
* Spokes requiring proprietary licenses (Bloomberg Terminal, Refinitiv, etc.)
* Trading strategies without statistical validation
