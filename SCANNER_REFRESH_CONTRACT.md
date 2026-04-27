# Scanner Refresh Contract

## Owner

- Primary: `Chandrasekhar`
- Supporting: `Dirac`

## Problem

The Scanner is currently refreshing on a live cron schedule, but the observed cadence is too sparse for a product that feels live and tactical.

## Current State

- Generator: `generate_seo_site.py`
- Pipeline entrypoint: `run_daily_sec_catalyst.sh`
- Live schedule: weekday cron at `08:05 UTC`
- Result: page freshness is likely perceived as stale outside the early-morning update window

## MVP Refresh Contract

### Contract

- Full refresh before US market open on weekdays
- Hourly refresh during US market hours on weekdays
- Page must render a visible `Last refreshed` timestamp
- If a refresh fails, the prior published page remains live

### Proposed schedule

- `08:05 UTC` weekday premarket run
- Hourly follow-up runs aligned to market hours
- Weekend behavior:
  - no hourly refreshes
  - optional one summary rebuild if needed for Monday prep

## Acceptance Criteria

- Scanner page updates on the agreed cadence without manual intervention
- Published page clearly shows freshness time
- Logs make it obvious whether the last run succeeded or failed
- Publish path is idempotent and does not break if a single run fails

## Risks

- More frequent refreshes may increase data/API usage
- A fragile pipeline can turn cadence into noise instead of trust
- Freshness UI without reliable timestamps will create confusion

## Implementation Notes

1. Lock the desired refresh windows
2. Add or verify timestamp rendering on the page
3. Move live schedule ownership into one documented place
4. Add a simple post-run verification step
5. Verify public cache behavior after deploy

## Decision

Recommended MVP mode: `Intraday Hourly`
