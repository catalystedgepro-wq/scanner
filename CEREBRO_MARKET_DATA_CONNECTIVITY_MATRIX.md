# Cerebro Market Data Connectivity Matrix

## New Agent Lane

- `Minsky`
  - Role: Senior Fintech Integration Engineer
  - Mission: reduce market-data bottlenecks, rationalize provider sprawl, and open the next expansion lanes for crypto, prediction markets, and macro without turning Cerebro into a patchwork of one-off adapters

## Pairings

- `Minsky` + `Einstein`
  - scoring and signal inputs
- `Minsky` + `Avicenna`
  - symbol normalization, rescue overlays, and Scanner/HUD parity
- `Minsky` + `Chandrasekhar`
  - scanner ingestion cadence, freshness, and degraded-mode policy
- `Minsky` + `Dirac`
  - secrets, deploy guards, connector health checks, and runtime failover
- `Minsky` + `Mnemosyne`
  - provider memory, quotas, failure patterns, and connector recall
- `Minsky` + `Graphify`
  - connectivity map across repos, providers, auth surfaces, and downstream feature lanes
- `Minsky` + `Peirce` / `Hume`
  - crypto, macro, and prediction-market surfaces once the data lanes are stable enough to visualize

## Scope Boundary

This matrix is intentionally curated for Cerebro's real build path.

- It focuses on providers that are directly useful for:
  - equities
  - options
  - macro
  - crypto
  - prediction markets
  - ETF and sector taxonomy
- It does not attempt to enumerate every API inside the large aggregator lists.

## Current Cerebro Baseline

Already present in the repo today:

- `FMP_API_KEY`
- `FINNHUB_API_KEY`
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `TRADIER_TOKEN`
- public FRED CSV pulls

This means the best next architecture is not "add 40 keys".
It is:

1. keep keyless lanes where possible
2. consolidate high-value paid feeds
3. use OpenBB as the unification layer where it reduces bespoke integrations

## Connectivity Matrix

| Repository Name | Data Provider | Key Registration Link | Auth Method (Env Var Name) |
| --- | --- | --- | --- |
| `OpenBB` | Alpha Vantage | https://www.alphavantage.co/support/#api-key | API key (`ALPHA_VANTAGE_API_KEY`) |
| `OpenBB` | Polygon.io / Massive | https://polygon.io/dashboard/signup | API key (`POLYGON_API_KEY`) |
| `OpenBB` | FRED | https://fred.stlouisfed.org/docs/api/api_key.html | Query/header key (`FRED_API_KEY`) |
| `OpenBB` | Financial Modeling Prep | https://site.financialmodelingprep.com/developer/docs | API key (`FMP_API_KEY`) |
| `OpenBB` | Finnhub | https://finnhub.io/register | API key (`FINNHUB_API_KEY`) |
| `OpenBB` | Nasdaq Data Link / Quandl | https://data.nasdaq.com/sign-up | API key (`NASDAQ_DATA_LINK_API_KEY`) |
| `OpenBB` | Tradier | https://developer.tradier.com/user/sign_up | Bearer token / OAuth (`TRADIER_TOKEN`) |
| `OpenBB` | Alpaca | https://app.alpaca.markets/signup | Key + secret (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`) |
| `FRED API (Federal Reserve)` | FRED | https://fred.stlouisfed.org/docs/api/api_key.html | Query/header key (`FRED_API_KEY`) |
| `Trading Economics` | Trading Economics API | https://docs.tradingeconomics.com/get_started/ | API key in query/header (`TRADINGECONOMICS_API_KEY`) |
| `yfinance` | Yahoo Finance public endpoints | - | No key required (`none`) |
| `FinanceDatabase` | FinanceDatabase curated symbol taxonomy | - | No key required (`none`) |
| `economic-indicators` | FRED | https://fred.stlouisfed.org/docs/api/api_key.html | Optional API key (`FRED_API_KEY`) |
| `economic-indicators` | U.S. Treasury yield data | - | No key required (`none`) |
| `public-api-lists` | Alpha Vantage | https://www.alphavantage.co/support/#api-key | API key (`ALPHA_VANTAGE_API_KEY`) |
| `public-api-lists` | Polygon.io / Massive | https://polygon.io/dashboard/signup | API key (`POLYGON_API_KEY`) |
| `public-api-lists` | Tradier | https://developer.tradier.com/user/sign_up | Bearer token / OAuth (`TRADIER_TOKEN`) |
| `public-api-lists` | PredScope / Polymarket odds | - | No key required (`none`) |
| `public-api-lists` | CoinPaprika | - | No key required (`none`) |
| `public-api-lists` | DexPaprika | - | No key required (`none`) |
| `bytewax/awesome-public-real-time-datasets` | Coinbase Exchange market data | - | Public market-data WS is keyless (`none`) |
| `bytewax/awesome-public-real-time-datasets` | Binance public market streams | - | Public market-data WS is keyless (`none`) |
| `bytewax/awesome-public-real-time-datasets` | Finnhub | https://finnhub.io/register | API key (`FINNHUB_API_KEY`) |
| `bytewax/awesome-public-real-time-datasets` | Alpaca Markets | https://app.alpaca.markets/signup | Key + secret (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`) |
| `bytewax/awesome-public-real-time-datasets` | SEC EDGAR APIs | - | No key required (`none`) |
| `bytewax/awesome-public-real-time-datasets` | Polygon.io / Massive | https://polygon.io/dashboard/signup | API key (`POLYGON_API_KEY`) |
| `bytewax/awesome-public-real-time-datasets` | CoinPaprika | - | No key required (`none`) |
| `bytewax/awesome-public-real-time-datasets` | DexPaprika | - | No key required (`none`) |
| `bytewax/awesome-public-real-time-datasets` | Pyth Network | - | No key required for public feeds (`none`) |
| `AKShare` | TuShare, Currencyscoop, SGX, mixed public China-market sources | https://tushare.pro/register?reg=1 | Mixed: mostly keyless wrappers, source-specific when required (`TUSHARE_TOKEN` if selected) |
| `FinRL` | Yahoo Finance | - | No key required (`none`) |
| `FinRL` | Alpaca | https://app.alpaca.markets/signup | Key + secret (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`) |
| `FinRL` | Binance | https://www.binance.com/en/register | Public market data keyless; trading keys for private endpoints (`BINANCE_API_KEY`, `BINANCE_API_SECRET`) |
| `FinRL` | CCXT | - | Exchange-specific auth (`<EXCHANGE>_API_KEY`, `<EXCHANGE>_API_SECRET`) |
| `FinRL` | WRDS | https://wrds-www.wharton.upenn.edu/register/ | Institutional account (`WRDS_USERNAME`, `WRDS_PASSWORD`) |
| `awesome-ai-in-finance` | Yahoo Finance | - | No key required (`none`) |
| `awesome-ai-in-finance` | Nasdaq Data Link / Quandl | https://data.nasdaq.com/sign-up | API key (`NASDAQ_DATA_LINK_API_KEY`) |
| `awesome-ai-in-finance` | FinancialData.net | https://financialdata.net/documentation | API key (`FINANCIALDATA_API_KEY`) |
| `awesome-ai-in-finance` | CoinPaprika | - | No key required (`none`) |
| `awesome-ai-in-finance` | DexPaprika | - | No key required (`none`) |
| `awesome-finance` | Yahoo Finance | - | No key required (`none`) |
| `awesome-finance` | Alpha Vantage | https://www.alphavantage.co/support/#api-key | API key (`ALPHA_VANTAGE_API_KEY`) |
| `awesome-finance` | Nasdaq Data Link / Quandl | https://data.nasdaq.com/sign-up | API key (`NASDAQ_DATA_LINK_API_KEY`) |
| `awesome-finance` | FRED | https://fred.stlouisfed.org/docs/api/api_key.html | Query/header key (`FRED_API_KEY`) |

## Notes

- `public-api-lists` was listed twice in the input; deduplicated here.
- The `Backtest Tutorial` repository was not included because no exact GitHub URL was provided.
- `FinRL` still references `IEXCloud` in its README, but that source is effectively legacy and should not be part of the forward-looking Cerebro adoption path.
- `AKShare` is best treated as a wrapper ecosystem, not a single clean provider contract.

## Recommended Cerebro Adoption Order

### Tier 1 - Keyless and fast to adopt

- `yfinance`
- `SEC EDGAR`
- `FRED`
- `CoinPaprika`
- `DexPaprika`
- public `Binance` streams
- public `Coinbase` market-data streams

### Tier 2 - High-value paid / tokenized feeds

- `Polygon.io`
- `Alpaca`
- `Tradier`
- `FMP`
- `Finnhub`

### Tier 3 - Unification and taxonomy

- `OpenBB` as the provider abstraction layer
- `FinanceDatabase` for symbol taxonomy and classification
- `AKShare` for China-market optional expansion

### Tier 4 - Research and training

- `FinRL` for downstream RL and backtest experimentation
- `awesome-ai-in-finance` / `awesome-finance` as discovery surfaces, not runtime dependencies

## Recommended MVP Stack For Cerebro

- Equities / options:
  - `Polygon.io` or `Alpaca` + `Tradier`
- Macro:
  - `FRED`
- Scanner backfill / keyless fallback:
  - `yfinance`
- Crypto:
  - `CoinPaprika`
  - `DexPaprika`
  - public `Binance` and `Coinbase` streams
- Taxonomy:
  - `FinanceDatabase`
- Orchestration:
  - `OpenBB`

## Why OpenBB Is The Right Aggregation Surface

OpenBB is the one repo in this set that already behaves like the integration spine Cerebro needs:

- multiple providers behind one SDK
- Python, REST, MCP, and analyst-facing surfaces
- better fit for a growing agent stack than one-off scripts per vendor

That makes `Minsky`'s first strategic job very clear:

1. formalize Cerebro provider env names
2. map them into OpenBB where it reduces glue code
3. keep direct bespoke adapters only for lanes where OpenBB is not enough
