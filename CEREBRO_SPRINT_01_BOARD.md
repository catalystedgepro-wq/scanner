# Cerebro Sprint 01 Board

## Sprint Window

- Timebox: 1 week
- Primary goal: stabilize the MVP foundation by locking reliability and the data contract
- Active queues: Reliability and Deploy, Canonical Data Contract
- Sidecar queues: Intelligence Scoring, HUD Workflow, Skill Ingestion and Research

## Sprint Goal

At the end of Sprint 01, we should be able to say:

- the daily run produces a known artifact set
- the backend can prove what it is serving
- the core entity/API contract is written down
- the HUD is no longer depending on undocumented backend shape

## Active Agents

- `Dirac` (`019d68e8-e581-7ff1-8dc7-a79640654ac6`) owns reliability and deploy
- `Mendel` (`019d68e8-fb91-7073-b37d-116d77fc9f96`) owns canonical data contract
- `Einstein` (`019d68e8-fe7e-7b72-9945-0eec1bf12b73`) is on standby for scoring follow-on
- `Ampere` (`019d68e9-1438-7eb0-a3a8-a5dd0563e788`) is on standby for HUD follow-on
- `Helmholtz` (`019d68e9-1678-7422-845f-2cabf7224b23`) runs sidecar skill-ingestion work

## Critical Path

1. `Mendel` defines the canonical entity and API shape
2. `Dirac` makes the pipeline and verifier prove which artifact set exists
3. `Mendel` locks backend contract expectations
4. `Dirac` turns those expectations into release/health gates
5. `Ampere` and `Einstein` consume the contract after it is stable

## Ticket Board

### S01-D1: Canonical Entity Spec

- Owner: `Mendel`
- Why: every other queue depends on one agreed record shape
- Files:
  - [api_server.py](/home/operator/.openclaw/workspace/api_server.py)
  - [build_universe_gravity.py](/home/operator/.openclaw/workspace/build_universe_gravity.py)
  - [build_gics_mapper.py](/home/operator/.openclaw/workspace/build_gics_mapper.py)
- Dependencies: none
- Done when:
  - a schema spec exists for `Entity`, `Classification`, `Event`, `MacroSeries`, `MarketSignal`, and `RelationshipEdge`
  - required vs optional fields are explicit
  - producer ownership is identified

### S01-D2: Producer Map

- Owner: `Mendel`
- Why: stale artifacts keep leaking when ownership is unclear
- Files:
  - [run_daily_sec_catalyst.sh](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh)
  - [api_server.py](/home/operator/.openclaw/workspace/api_server.py)
  - [cerebro_verify.py](/home/operator/.openclaw/workspace/cerebro_verify.py)
- Dependencies:
  - S01-D1
- Done when:
  - each critical artifact has one producer
  - each backend/HUD dependency has one source of truth

### S01-R1: Pipeline Manifest

- Owner: `Dirac`
- Why: the backend and HUD need one source of truth for what was built and when
- Files:
  - [run_daily_sec_catalyst.sh](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh)
  - [cerebro_verify.py](/home/operator/.openclaw/workspace/cerebro_verify.py)
- Dependencies: none
- Done when:
  - every daily run writes a versioned manifest
  - manifest includes timestamps, artifact paths, and build identifiers
  - verifier can read it

### S01-D3: API Contract Lock

- Owner: `Mendel`
- Why: the HUD and scanner need stable response shapes
- Files:
  - [api_server.py](/home/operator/.openclaw/workspace/api_server.py)
  - [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx)
- Dependencies:
  - S01-D1
  - S01-D2
- Done when:
  - `/api/universe`, `/api/health`, and ticker-detail payloads are documented
  - malformed or missing artifacts fail loudly

### S01-R2: Health Gate

- Owner: `Dirac`
- Why: bad deploys should stop pretending to be healthy
- Files:
  - [api_server.py](/home/operator/.openclaw/workspace/api_server.py)
  - [cerebro_verify.py](/home/operator/.openclaw/workspace/cerebro_verify.py)
- Dependencies:
  - S01-R1
  - S01-D3
- Done when:
  - one command checks `/api/health`, `/api/universe`, and artifact presence
  - command exits non-zero on drift or missing prerequisites

### S01-D4: Contract Verification Gate

- Owner: `Mendel`
- Support: `Dirac`
- Why: schema drift needs to be caught before the HUD sees it
- Files:
  - [cerebro_verify.py](/home/operator/.openclaw/workspace/cerebro_verify.py)
  - [api_server.py](/home/operator/.openclaw/workspace/api_server.py)
- Dependencies:
  - S01-D3
  - S01-R2
- Done when:
  - required artifact fields are asserted
  - backend readiness is tied to real contract checks

### S01-R3: Restart Order

- Owner: `Dirac`
- Why: recovery should be predictable after deploys and failures
- Files:
  - [cerebro.service](/home/operator/.openclaw/workspace/cerebro.service)
  - [cerebro-logger.service](/home/operator/.openclaw/workspace/cerebro-logger.service)
  - [run_daily_sec_catalyst.sh](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh)
- Dependencies:
  - S01-R1
- Done when:
  - restart steps are documented
  - restart order is enforced or scriptable

### S01-R4: Deploy Sync Check

- Owner: `Dirac`
- Why: live backend and HUD bundle cannot drift again
- Files:
  - [index.html](/home/operator/.openclaw/workspace/docs/hud/index.html)
  - [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx)
  - [api_server.py](/home/operator/.openclaw/workspace/api_server.py)
- Dependencies:
  - S01-R2
  - S01-D3
- Done when:
  - live bundle hash and backend contract version are both verifiable before release

### S01-D5: HUD Consumer Audit

- Owner: `Ampere`
- Why: the frontend should consume only guaranteed fields
- Files:
  - [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx)
  - [index.html](/home/operator/.openclaw/workspace/docs/hud/index.html)
- Dependencies:
  - S01-D3
- Done when:
  - HUD field assumptions are documented
  - missing data paths are graceful
  - unstable backend assumptions are identified

### S01-S1: Score Field Inventory

- Owner: `Einstein`
- Why: scoring cleanup should start as soon as contract terms are stable
- Files:
  - [build_convergence_score.py](/home/operator/.openclaw/workspace/build_convergence_score.py)
  - [build_macro_layer.py](/home/operator/.openclaw/workspace/build_macro_layer.py)
  - [build_short_interest.py](/home/operator/.openclaw/workspace/build_short_interest.py)
  - [build_options_flow.py](/home/operator/.openclaw/workspace/build_options_flow.py)
  - [build_sympathy_logger.py](/home/operator/.openclaw/workspace/build_sympathy_logger.py)
- Dependencies:
  - S01-D1
- Done when:
  - score-producing fields are inventoried
  - duplicated semantic concepts are flagged

### S01-K1: Skill Inventory Baseline

- Owner: `Helmholtz`
- Why: docs imply more skills than the repo actually materializes
- Files:
  - [.agents/skills/remotion-best-practices/SKILL.md](/home/operator/.openclaw/workspace/.agents/skills/remotion-best-practices/SKILL.md)
  - [agent_knowledge_2026-04-03.txt](/home/operator/.openclaw/workspace/agent_knowledge_2026-04-03.txt)
  - [agentdb.rvf](/home/operator/.openclaw/workspace/agentdb.rvf)
- Dependencies: none
- Done when:
  - project-local, global, and desired skills are inventoried
  - MVP-relevant skill gaps are listed

## Suggested Day-by-Day Flow

### Day 1

- `Mendel`: S01-D1
- `Dirac`: S01-R1
- `Helmholtz`: S01-K1

### Day 2

- `Mendel`: S01-D2
- `Dirac`: begin S01-R2 groundwork
- `Einstein`: begin S01-S1 if D1 is sufficiently stable

### Day 3

- `Mendel`: S01-D3
- `Dirac`: S01-R2
- `Ampere`: prep for S01-D5

### Day 4

- `Mendel` + `Dirac`: S01-D4
- `Dirac`: S01-R3
- `Ampere`: S01-D5

### Day 5

- `Dirac`: S01-R4
- `Einstein`: finish S01-S1
- Integrator: review outputs, trim spillover, set Sprint 02

## Sprint Exit Criteria

- canonical schema exists
- producer map exists
- pipeline manifest exists
- health/contract gate exists
- deploy sync check exists
- HUD consumer assumptions are documented

## Not in Sprint 01

- full score reweighting
- trade architect implementation
- major HUD redesign
- mobile work
- universal graph expansion
- broad repo-cloning spree
