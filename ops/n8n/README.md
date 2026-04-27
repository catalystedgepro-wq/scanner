# n8n Operations

This folder contains the first Cerebro automation pack for `n8n`.

## Files

- `.env.example`
- `docker-compose.yml.example`
- `workflows/cerebro_mnemosyne_gate.json`
- `workflows/cerebro_intraday_refresh_gatekeeper.json`
- `workflows/cerebro_premarket_pipeline.json`
- `workflows/cerebro_operator_intelligence_webhook.json`

## Quick Start

1. Copy `.env.example` to `.env` and replace the placeholder values.
2. Start n8n with Docker Compose.
3. Import the JSON workflows from `workflows/`.
4. Adjust the schedule triggers to match the production cadence.
5. Test the Mnemosyne gate first, then the intraday workflow, then the full premarket workflow.

## Recommended First Live Sequence

1. `cerebro_mnemosyne_gate.json`
2. `cerebro_intraday_refresh_gatekeeper.json`
3. `cerebro_premarket_pipeline.json`
4. `cerebro_operator_intelligence_webhook.json`

## Why This Order

The scanner cadence and validation layer are already the most stable outputs in the repo:

- `run_daily_sec_catalyst.sh`
- `pipeline_manifest.json`
- `scanner_artifact_status.json`
- `cerebro_verify.py`

That makes them the right first automation seam.

## Mnemosyne Pod Rule

The automation pod now treats `Mnemosyne` as a first-class gate:

- EverOS must stay present as the operational memory lane
- MSA must stay present as the long-context research lane
- production can keep `EVEROS_ENABLED=0`
- but the memory lane itself cannot silently disappear from the release surface

Use [check_mnemosyne_lanes.sh](/home/operator/.openclaw/workspace/ops/check_mnemosyne_lanes.sh) as the shared gate command.
