# Cerebro Memory Agent Policy

## Decision

`EverOS` and `MSA` are permanent project lanes, not optional add-ons.

This means Cerebro should always carry:

- an `EverOS` memory lane for persistence, recall, and cross-surface continuity
- an `MSA` long-context lane for offline research, retrospectives, and filing-bundle analysis

## Standing Owner

- `Mnemosyne`
  - permanent memory and long-context intelligence owner
  - owns the combined `EverOS` + `MSA` lane across Scanner, HUD, pipeline, and research workflows

## Lane Split

### EverOS = operational memory fabric

Use EverOS to:

- persist scanner and HUD event memory
- mirror deploy outcomes, pipeline runs, and artifact failures
- attach sympathy history and false-positive corrections to symbols
- provide recall context to `/api/ticker`, `/api/ai-summary`, and `/api/briefing`
- keep long-lived project and operator memory reusable across sessions

### MSA = long-context reasoning sidecar

Use MSA to:

- analyze large filing bundles
- run outcome retrospectives over long event windows
- compare long-context reasoning against the retrieval stack
- build research notebooks, evaluation jobs, and future training corpora

## Permanent Rules

### Rule 1: EverOS is always mounted

The repo must always keep the EverOS lane available through:

- [everos_memory_client.py](/home/operator/.openclaw/workspace/everos_memory_client.py)
- [everos_pipeline_ingest.py](/home/operator/.openclaw/workspace/everos_pipeline_ingest.py)
- [spoke_memory.py](/home/operator/.openclaw/workspace/spoke_memory.py)
- [build_sympathy_logger.py](/home/operator/.openclaw/workspace/build_sympathy_logger.py)
- [run_daily_sec_catalyst.sh](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh)

### Rule 2: EverOS does not own the hot path

EverOS must stay behind safe boundaries:

1. publish live signal
2. persist locally
3. mirror to EverOS
4. retrieve later for context

That keeps Scanner and HUD alive even if the remote memory backend is unavailable.

### Rule 3: MSA is always part of the project, but not the low-latency runtime

MSA should always be available as a research capability through:

- [vendor/evermind/MSA](/home/operator/.openclaw/workspace/vendor/evermind/MSA)
- [.agents/skills/msa-memory-sparse-attention/SKILL.md](/home/operator/.openclaw/workspace/.agents/skills/msa-memory-sparse-attention/SKILL.md)

But it should not be forced into:

- the live scanner page
- live HUD websocket rendering
- click-time low-latency API paths

until the infrastructure envelope is proven.

### Rule 4: Every major queue must expose a memory hook

- Reliability/deploy
  - deploy outcomes and failures should be mirrored into EverOS
- Data contract
  - API context surfaces should accept memory enrichment cleanly
- Intelligence scoring
  - sympathy and follow-through should become reusable memory
- HUD workflow
  - inspector and briefing surfaces should consume memory context
- Skill ingestion/research
  - MSA evaluations and EverOS retrieval patterns must stay current

## Phase Interpretation

### Phase 1 / Phase 2

- EverOS is required as the operational memory strategy
- MSA is required as a standing research lane

### Phase 3+

- EverOS becomes richer in API retrieval and case-memory usage
- MSA can graduate into benchmarked long-context workflows and offline analyst tooling

## What “Always Deployed” Means Here

It does not mean:

- forcing EverOS live in production before the environment is ready
- forcing MSA into hot runtime paths

It does mean:

- the skill wrappers stay mounted
- the code bridges stay in the deploy surface
- the lane has a permanent owner
- new work is expected to consider memory and long-context implications by default

## Immediate Enforcement

The project should now assume:

- `Mnemosyne` is always active as the memory/long-context sidecar
- `EverOS` is part of the permanent implementation surface
- `MSA` is part of the permanent research surface

This is now a project policy, not a suggestion.
