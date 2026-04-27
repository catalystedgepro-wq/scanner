# Security Policy

## Reporting a Vulnerability

Please email security issues privately to the maintainer
([opensource@example.com](mailto:opensource@example.com)) rather than opening
public issues. We aim to respond within 48 hours.

## What this codebase contains

This is a catalyst-trading research toolkit. It reads public SEC filings,
free wire feeds, prediction markets, and disaster sensor APIs, then computes
Wilson-bounded conviction scores. **No keys, secrets, or personal financial
data are stored in the repository.**

## Where secrets MUST go

All credentials are read from environment variables, NOT files in the repo:

| Variable | Purpose |
|---|---|
| `ALPHAVANTAGE_API_KEY` | Tier-1 news sentiment |
| `NASA_FIRMS_MAP_KEY` | Wildfire detections |
| `CLOUDFLARE_API_TOKEN` | Internet outage radar |
| `GROQ_API_KEY` / `GEMINI_API_KEY` | Optional LLM scoop drafter |
| `TRADIER_API_TOKEN` / `TRADIER_ACCOUNT_ID` | Optional live trading |
| `COINBASE_API_KEY` / `COINBASE_API_SECRET` | Optional crypto agent |
| `SEC_USER_AGENT` | EDGAR compliance — required |

Use a `.env` file (gitignored) to populate these. **Never commit a `.env`.**

## Threat model

This software does not custody funds. It can only execute orders against
brokerage APIs you explicitly authorize via your own API keys. No data
leaves your machine except outbound API calls to documented services.

If you wire it to a live trading account: budget the live capital you can
afford to lose. Treat the code as a research toolkit, not investment advice.

## Reporting financial losses

This code is provided AS-IS under MIT. The maintainers are not liable for
trading losses. Read the LICENSE.
