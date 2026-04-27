# Cerebro GitNexus Nervous System

GitNexus is the code-topology lane for Cerebro.

Use it when the question is about:

- shared builder blast radius
- execution flows across multiple modules
- where to intercept a new cache or fallback with the least risk
- whether a new gate isolates a critical cluster

## Runtime Surface

- MCP server: `gitnexus`
- local index root: `/home/operator/.openclaw/workspace/.gitnexus`
- local repo analyzed from: `/home/operator/.openclaw/workspace`

Current graph snapshot after the latest forced re-index:

- `4,759 nodes`
- `12,087 edges`
- `386 clusters`
- `300 flows`
- indexed commit at last status check: `0034d71`

## Phase 4 Graph Integrity Report

### 1. Taxonomy Pipeline Map

GitNexus context confirms the current universe-build spine is:

- `build_universe_gravity.py:main`
- `apply_sector_recovery`
- `_recover_sector_detail`
- `_recover_sector_direct`
- `_sector_from_sic_cache`
- `_sector_from_bedrock`
- `_sector_from_long_tail_cache`
- `_sector_from_name`
- `_final_long_tail_fallback`

Additional unknown-entry remediation still attached to the same builder:

- `enrich_sic_for_unknowns`
- `enrich_unknown_sectors`

Interpretation:

- unknown symbols do not enter the system through one single edge
- the decisive normalization hub is `apply_sector_recovery -> _recover_sector_detail`
- the long-tail cache is not an orphan sidecar; it is a first-class branch under `_recover_sector_direct`

### 2. Ollama Burn-In Insertion Point

GitNexus context and impact on the burn-in lane show:

- `ops/phase4_long_tail_burnin.py:run` owns the entire burn-in sequence
- `_load_unknown_candidates` is called only by `run`
- `_call_ollama` is called only by `run`
- upstream impact for `_call_ollama` is low and isolated to the burn-in file

Lowest-latency safe insertion point:

- write accepted classifications into the long-tail cache consumed by `_sector_from_long_tail_cache`
- let the main builder absorb them through `apply_sector_recovery`

Why this is the right interception point:

- it avoids putting classification latency into live API request paths
- it keeps Ollama in a precompute lane instead of a hot runtime lane
- it plugs directly into the existing graph-central recovery chain

### 3. EverOS Gating Surfaces

GitNexus context identifies these EverOS entry points:

- `api_server.py` imports `everos_memory_client.py`
- `api_server.py:_everos_context_sync -> search_memories -> load_config -> _request`
- `everos_pipeline_ingest.py:main -> load_config -> save_messages`
- `build_sympathy_logger.py:_mirror_to_everos -> load_config`
- `spoke_memory.py` imports `everos_memory_client.py`
- `healthcheck` and `backend_available` also pass through `load_config`

Circular dependency assessment:

- GitNexus file context for `everos_memory_client.py` shows incoming imports from API/ingest/logger paths
- it shows no outgoing repo-import edges back into those callers
- current assessment: `no graph-visible circular dependency`

Dark-launch implication:

- EverOS gating remains non-destructive as long as the gates stay at `load_config`, `search_memories`, and `save_messages`
- do not move EverOS reads into the universe builder or the taxonomy cache path

### 4. Long-Tail Node Connectivity

Graph evidence that the long-tail lane is connected to the universe build:

- `impact _sector_from_long_tail_cache --direction downstream`
  - confirms the symbol is not isolated
  - shows it is attached to shared downstream processes
- `impact apply_sector_recovery --direction downstream`
  - `impactedCount: 22`
  - `processes_affected: 93`
  - marks the builder as graph-central
- `impact _recover_sector_detail --direction downstream`
  - `impactedCount: 22`
  - `processes_affected: 93`
  - confirms the unknown-resolution hub is deeply connected

Readiness conclusion:

- the new long-tail nodes are properly connected to the universe build
- the long-tail cache hook is integrated inside the shared recovery chain
- the Ollama burn-in lane is isolated enough to stress-test safely
- the EverOS gates are attached to runtime memory surfaces, not the taxonomy core

## Phase 4 Readiness Summary: Graph-First Taxonomy & EverOS Integration

**Status:** 🟢 READY  
**Primary Flow Anchors:** `proc_46_main` | `build_universe_gravity.py`

### 1. Topology & Graph Integrity

- **Long-Tail Connectivity:** Confirmed the Ollama classification script is downstream-connected to the main builder via `_sector_from_long_tail_cache` at [build_universe_gravity.py:681](/home/operator/.openclaw/workspace/build_universe_gravity.py#L681). Incoming graph edge remains `_recover_sector_direct -> _sector_from_long_tail_cache`, so new labels are not orphaned.
- **EverOS Safety:** Confirmed EverOS remains a leaf memory hub. Live GitNexus context shows:
  - [api_server.py:_everos_context_sync](/home/operator/.openclaw/workspace/api_server.py#L1318) -> `search_memories`
  - [everos_memory_client.py:search_memories](/home/operator/.openclaw/workspace/everos_memory_client.py#L221) -> `load_config` -> `_request`
  - upstream callers for `search_memories` are only `_everos_context_sync` in `api_server.py` and `tmp_live_api_server.py`
  - no circular dependency into the taxonomy builder was introduced

### 2. Taxonomy Pipeline Patches (The Fixes)

- **Ollama Burn-in Hook:** Wired into the daily runner at [run_daily_sec_catalyst.sh:336](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh#L336) through [run_daily_sec_catalyst.sh:357](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh#L357), before [build_universe_gravity.py](/home/operator/.openclaw/workspace/build_universe_gravity.py) executes.
- **Cache Interceptor:** Accepted labels continue to persist into `.long_tail_sector_cache.json` from [ops/phase4_long_tail_burnin.py:543](/home/operator/.openclaw/workspace/ops/phase4_long_tail_burnin.py#L543) through [ops/phase4_long_tail_burnin.py:556](/home/operator/.openclaw/workspace/ops/phase4_long_tail_burnin.py#L556), which is the exact handoff absorbed by `_sector_from_long_tail_cache`.
- **Budget-Gate Bypass:** Addressed the inert `UNIVERSE_SECTOR_LIMIT=0` throttle by raising the runner default to `250` at [run_daily_sec_catalyst.sh:65](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh#L65). The Ollama precompute lane is no longer waiting for the Yahoo rescue budget to fire first.
- **Burn-in Throughput Tuning:** Matched the local Gemma 4 reality by:
  - reducing runner batch default to `10` at [run_daily_sec_catalyst.sh:68](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh#L68)
  - raising timeout to `120` seconds at [run_daily_sec_catalyst.sh:72](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh#L72)
  - disabling SEC fetch in the default daily path at [run_daily_sec_catalyst.sh:78](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh#L78)
  - shrinking the worker prompt and generation budget at [ops/phase4_long_tail_burnin.py:249](/home/operator/.openclaw/workspace/ops/phase4_long_tail_burnin.py#L249) through [ops/phase4_long_tail_burnin.py:280](/home/operator/.openclaw/workspace/ops/phase4_long_tail_burnin.py#L280)
- **Latency Tracking:** Active. The burn-in script records per-symbol latency and system pressure via [ops/phase4_long_tail_burnin.py:526](/home/operator/.openclaw/workspace/ops/phase4_long_tail_burnin.py#L526) through [ops/phase4_long_tail_burnin.py:573](/home/operator/.openclaw/workspace/ops/phase4_long_tail_burnin.py#L573).
- **Verification Snapshot:** A live one-symbol proof on `AVO` completed with `status=accepted`, `sector=consumer`, `confidence=0.9`, `latency_seconds=3.356`, and persisted the result into `.long_tail_sector_cache.json`.

### 3. Dark Launch Status

- **EverOS Helpers:** Deployed and still dark. Graph context shows they remain inert-but-structurally-sound runtime helpers rather than new taxonomy-core dependencies.
- **Fallback Labels:** Integrated into the Universe Build pipeline through the long-tail cache path. The builder consumes them without requiring live API inference.

**Sign-off:** Ariadne (Code-Graph Owner)

## Recommended Query Set

```bash
npx gitnexus status
npx gitnexus analyze --force
npx gitnexus context main --file build_universe_gravity.py
npx gitnexus context apply_sector_recovery --file build_universe_gravity.py
npx gitnexus context _recover_sector_detail --file build_universe_gravity.py
npx gitnexus context _sector_from_long_tail_cache --file build_universe_gravity.py
npx gitnexus context run --file ops/phase4_long_tail_burnin.py
npx gitnexus context _call_ollama --file ops/phase4_long_tail_burnin.py
npx gitnexus context everos_memory_client.py
npx gitnexus context "Function:api_server.py:_everos_context_sync"
npx gitnexus impact _recover_sector_detail --direction downstream
```

## Known Tooling Caveat

On this workstation, some narrow symbol probes after a force re-index can throw a LadybugDB WAL assertion from GitNexus.

Operational workaround:

1. rerun `npx gitnexus analyze --force`
2. use file-level or builder-level symbol context
3. avoid repeated narrow probing until the upstream GitNexus runtime is stable again
