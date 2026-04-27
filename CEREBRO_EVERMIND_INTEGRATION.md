# Cerebro EverMind Integration

## Status

`EverOS` is now mounted as an operational memory lane in this workspace. `MSA` is mounted as a research and long-context strategy lane. They are not interchangeable.

## Permanent Project Policy

This repo now treats both lanes as permanent:

- `EverOS` is a standing operational-memory capability
- `MSA` is a standing long-context research capability

They should be assumed present throughout the project, even when:

- `EVEROS_ENABLED=0` in production
- `MSA` is not in the live runtime path

The governing policy is in [CEREBRO_MEMORY_AGENT_POLICY.md](/home/operator/.openclaw/workspace/CEREBRO_MEMORY_AGENT_POLICY.md).

## What Is Live

- Vendored source repos:
  - `vendor/evermind/EverOS`
  - `vendor/evermind/MSA`
- Workspace-local skill wrappers:
  - `.agents/skills/everos-memory-os/SKILL.md`
  - `.agents/skills/msa-memory-sparse-attention/SKILL.md`
- Local registry entries:
  - `.agents/plugins/marketplace.json`
- New runtime bridge:
  - `everos_memory_client.py`
- New pipeline ingester:
  - `everos_pipeline_ingest.py`
- Live event write-through:
  - `spoke_memory.py` now mirrors live Redis velocity events into EverOS after SQLite persistence
- Run-level write-through:
  - `run_daily_sec_catalyst.sh` now sends success and failure pipeline summaries into EverOS

## EverOS Application In Cerebro

### Live today

- `spoke_memory.py`
  - remains the first durable sink for live event data
  - now mirrors canonical velocity events into EverOS as write-through memory
- `run_daily_sec_catalyst.sh`
  - pushes scanner pipeline summaries into EverOS on both success and failure paths
- `everos_pipeline_ingest.py`
  - stores scanner artifact validity, section counts, top ranked catalyst candidates, and macro context

### Why this shape

EverOS belongs behind existing data boundaries, not inside the hot publish path. The safe order is:

1. publish to Redis
2. persist locally in SQLite
3. mirror into EverOS for recall and retrieval

That keeps Cerebro resilient even if the EverOS backend is offline.

### Best next EverOS lanes

- `api_server.py`
  - enrich `/api/ticker/{symbol}`, `/api/spark`, `/api/ai-summary/{ticker}`, and `/api/briefing` with historical memory context
- `build_sympathy_logger.py`
  - mirror sympathy snapshots and outcomes into reusable case memory
- scanner/operator memory
  - attach false-positive corrections, notes, and follow-through outcomes to tickers and event clusters

## MSA Application In Cerebro

### Current role

MSA is mounted as a long-context research lane, not a production dependency.

### Good MSA targets

- large filing bundles
- outcome retrospectives over long event windows
- offline experiments that compare long-context reasoning against the current retrieval stack
- research notebooks and evaluation jobs

### Not for now

- the live scanner page
- HUD websocket delivery
- low-latency API paths

## Safe End-To-End Interpretation

For this repo, end to end means:

1. the skills are mounted locally
2. the project has a real runtime memory bridge for EverOS
3. scanner runs and live velocity events can flow into memory
4. MSA is explicitly attached to the future research and evaluation lane

It does not mean forcing MSA or a remote memory dependency into the lowest-latency runtime paths before the infrastructure is ready.
