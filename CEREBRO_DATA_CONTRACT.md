# Cerebro Data Contract

Sprint 01 documentation artifact

## Purpose

This document defines the canonical data contract for Cerebro.
It locks the shape of the core entity record, the live API consumer contract, and the producer map for the daily pipeline.

The rules are simple:

- `entity_master.json` is the primary canonical universe artifact
- `api_server.py` is a consumer of canonical artifacts, not a second source of truth
- The HUD must only depend on documented fields
- Derived scores must be clearly labeled as derived

## Contract Scope

In scope for Sprint 01:

- Canonical entity schema
- Scoring semantics
- Producer / consumer boundaries
- API payload contract

Out of scope for Sprint 01:

- Runtime code changes
- New data sources
- New visualizations
- New trade execution logic

## Canonical Entity

The canonical entity record is the durable company/ticker object used across the pipeline, backend, and HUD.

### Entity Identity

Required fields:

- `ticker` - uppercase symbol and primary key
- `name` - company or issuer display name
- `cik` - SEC CIK as a zero-padded string when available
- `exchange` - primary exchange or venue code

Optional identity fields:

- `lei`
- `isin`
- `figi`

### Classification

Required classification fields:

- `gics` - object with sector and sub-classification values
- `sector` - short sector label used by the API and HUD

Recommended `gics` object shape:

```json
{
  "s": "tech",
  "ig": "software",
  "i": "application_software",
  "si": "application_software"
}
```

### Capitalization and Coverage

Optional fields:

- `mkt_cap_usd`
- `mkt_cap_tier`
- `etf`
- `etf_weights_sum`
- `etf_overlords`
- `is_rogue`

### Live Scoring Fields

Required or effectively required for API/UI use:

- `gravity` - base structural rank for the entity
- `brightness` - live composite score used by `/api/universe`
- `last_updated` - last successful entity refresh date or timestamp

Optional enrichment fields:

- `spark_velocity`
- `macro_multiplier`
- `short_interest_ratio`
- `squeeze_flag`
- `sympathy_count`

## Scoring Semantics

The score contract must keep these meanings separate:

- `gravity` - structural baseline from universe and classification logic
- `brightness` - live composite used for ranking in the HUD/API
- `priority_score` - final operational rank, if present in pipeline outputs
- `freshness` - how recent the underlying signal is
- `intensity` - how strong the catalyst or market signal is
- `bias` - directional interpretation, if any
- `macro_multiplier` - sector-level tailwind or headwind adjustment

Rules:

- Do not reuse one score field to mean multiple things
- Do not let a derived field masquerade as raw truth
- If a field is computed, label it as computed
- If a field is a fallback, label it as fallback

## Live API Contract

`api_server.py` is the public read interface for the canonical artifacts.

### Required endpoints

- `GET /api/health`
- `GET /api/universe`
- `GET /api/ticker/{symbol}`
- `GET /api/sectors`
- `GET /api/macro`
- `GET /api/options`
- `GET /api/spark`
- `GET /api/brightness/top`
- `WS /ws/live`

### `/api/universe`

The universe payload must remain paginated and must expose:

- `total`
- `page`
- `per_page`
- `pages`
- `tickers`

Each ticker row must include, at minimum:

- `ticker`
- `name`
- `gravity`
- `brightness`
- `cap_tier`
- `sector`
- `etf_weight`
- `etf_overlords`
- `is_rogue`

### `/api/ticker/{symbol}`

The ticker payload must include:

- identity fields
- classification fields
- live scoring fields
- spark or catalyst detail fields when available
- `velocity_event` using the Velocity Deck schema below

### Velocity Deck Schema

The Velocity Deck is the canonical live event contract for both REST and WebSocket consumers.

Rules:

- `GET /api/spark` returns `events` using the Velocity Deck schema
- `WS /ws/live` velocity messages embed the same object under `velocity_event`
- `GET /api/ticker/{symbol}` includes the current node event as `velocity_event`
- the HUD must render chips, severity, and primary driver from this schema, not by recomputing labels from raw numbers

Required Velocity Deck fields:

- `schema_version`
- `kind` = `velocity_event`
- `event_id`
- `event_type`
- `wire_event`
- `ticker`
- `name`
- `ts`
- `severity`
- `severity_rank`
- `polarity`
- `total_velocity`
- `active_sources`
- `source_chips`
- `primary_source`
- `primary_driver`
- `headline`
- `detail`
- `spark`
- `components`

Canonical `spark` component keys:

- `patent`
- `legal`
- `digital`
- `options`
- `weather`

Severity rules:

- `critical` = absolute total velocity >= 18
- `high` = absolute total velocity >= 10
- `medium` = absolute total velocity >= 5
- `low` = absolute total velocity > 0
- `dormant` = no active velocity

Consumer rules for Velocity Deck:

- chips must come from `source_chips`, not hardcoded UI guesses
- the primary explanatory line must come from `headline` and `detail`
- REST and WebSocket consumers must treat `event_id` as the stable identity key
- legacy aliases may exist temporarily, but new UI work should target the Velocity Deck schema only

## Producer Map

The table below captures the current producer / consumer boundary for Sprint 01.

| Artifact | Producer | Primary Consumers | Notes |
| --- | --- | --- | --- |
| `sec_catalyst_latest.csv` | `rank_sec_catalysts.py` / `classify_sec_catalysts.py` | downstream classifiers, scanner site | daily catalyst input |
| `sec_catalyst_tickers.txt` | `run_daily_sec_catalyst.sh` | gap scanner and related scanners | ticker-only universe slice |
| `entity_master.json` | `build_universe_gravity.py` + `gravity_engine.py` | `api_server.py`, HUD | primary canonical universe artifact |
| `sector_lookup.json` | `build_gics_mapper.py` | `build_sympathy_logger.py`, classification lanes | ticker to sector lookup |
| `gics_hierarchy.json` / hierarchy artifacts | `build_gics_hierarchy.py` | backend and future grouping logic | classification bedrock |
| `macro_layer.json` | `build_macro_layer.py` | `api_server.py`, scanner site | sector-level macro multipliers |
| `macro_pressure.json` | `macro_engine.py` / related macro layer scripts | backend and HUD | live macro pressure snapshot |
| `options_activity.json` | `spoke_options.py` | `build_options_flow.py` | raw options signal store |
| `options_flow.csv` | `build_options_flow.py` | scanner site, future enrichment | derived options flow view |
| `spark_velocities.json` | spark / velocity producers | `api_server.py` | live catalyst velocity input |
| `gap_scanner.csv` | `build_gap_scanner.py` | `build_sympathy_logger.py`, scanner site | momentum / gap discovery |
| `gap_scanner_top.csv` | `build_gap_scanner.py` | newsletter and curation flows | top-ranked gap subset |
| `short_interest.csv` | `build_short_interest.py` | squeeze and scoring lanes | squeeze candidate signal |
| `sympathy_events.csv` | `build_sympathy_logger.py` | future sympathy modeling | historical contagion log |
| `collision_alerts.json` | `collision_engine.py` | backend / operator alerts | conflict or overlap signal |

## Producer Rules

- Every canonical artifact has one primary writer
- Every live consumer must read from the canonical artifact, not from ad hoc scratch files
- Non-fatal enrichment scripts may create side artifacts, but they do not redefine the canonical contract
- If a producer changes a field, the consumer contract must be updated in the same sprint

## Consumer Rules

- `api_server.py` reads artifacts only
- `CerebroHUD.jsx` consumes the API contract only
- `docs/hud/index.html` is a build artifact, not a schema source
- The HUD may not infer new fields that are not documented here

## Validation Rules

The contract is considered valid when:

- the canonical entity schema is stable and documented
- the producer map names the current writers for each critical artifact
- the API response shape matches the documented contract
- the HUD depends only on fields that are guaranteed by the API
- stale or mock data cannot be mistaken for live truth

## Sprint 01 Lock

For this sprint, the locked decisions are:

- `entity_master.json` is the canonical universe artifact
- `api_server.py` is a consumer contract, not a data producer
- `brightness` is the live rank used by the universe API
- `gravity` remains the structural baseline
- `macro_layer.json`, `short_interest.csv`, and `sympathy_events.csv` are enrichment inputs, not replacements for the canonical entity record
- The HUD must treat missing fields as a first-class case

