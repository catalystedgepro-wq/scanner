# Cerebro Skill Inventory Baseline

## Purpose

This inventory records:

1. Project-local skills and agent-related assets actually present
2. Global or doc-referenced skill categories Cerebro appears to rely on
3. MVP-relevant missing skills
4. A simple intake rubric for future skill or repo ingestion

This is a baseline, not a complete capability map.

## 1. Project-Local Skills And Assets Actually Present

### Project-local skill package

Confirmed under `.agents/skills`:

- `remotion-best-practices`
  - File: [SKILL.md](/home/operator/.openclaw/workspace/.agents/skills/remotion-best-practices/SKILL.md)
  - Includes detailed rule files for animation, compositions, assets, audio, captions, charts, maps, transitions, and video handling
- `cerebro-mcp-command-center`
  - File: [SKILL.md](/home/operator/.openclaw/workspace/.agents/skills/cerebro-mcp-command-center/SKILL.md)
  - Owns MCP setup, config generation, readiness checks, and safe activation for GitNexus, GitHub, Firecrawl, SQLite memory, fetch, and optional Postgres
- `gitnexus-code-graph`
  - File: [SKILL.md](/home/operator/.openclaw/workspace/.agents/skills/gitnexus-code-graph/SKILL.md)
  - Owns GitNexus topology mapping, blast-radius analysis, execution-flow tracing, and graph-integrity checks for launch-critical Cerebro changes

Current conclusion:

- The repo now has multiple Cerebro-core operational skill packages, not just one-off reference skills
- GitNexus is now a first-class project-local nervous-system lane alongside the MCP command center

### Project-local agent memory / knowledge artifacts

Confirmed in repo root:

- `agent_knowledge_2026-03-25.txt`
- `agent_knowledge_2026-03-26.txt`
- `agent_knowledge_2026-03-27.txt`
- `agent_knowledge_2026-03-28.txt`
- `agent_knowledge_2026-03-29.txt`
- `agent_knowledge_2026-03-30.txt`
- `agent_knowledge_2026-03-31.txt`
- `agent_knowledge_2026-04-02.txt`
- `agent_knowledge_2026-04-03.txt`
- `agentdb.rvf`
- `agentdb.rvf.lock`

Current conclusion:

- There is evidence of agent memory/logging infrastructure
- There is not yet a clear, repo-local Cerebro skill library built on top of it

### Project-local planning artifacts

- [CEREBRO_MVP_EXECUTION_PLAN.md](/home/operator/.openclaw/workspace/CEREBRO_MVP_EXECUTION_PLAN.md)

Current conclusion:

- The repo now has a documented MVP boundary
- It does not yet have a matching project-local skill inventory or skill-to-queue map

### Project-local domain assets that behave like internal capabilities

These are not skills in the packaging sense, but they are real reusable capability assets:

- Pipeline/orchestration:
  - [run_daily_sec_catalyst.sh](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh)
- Backend/API:
  - [api_server.py](/home/operator/.openclaw/workspace/api_server.py)
- HUD/frontend:
  - [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx)
- Entity and classification:
  - [build_universe_gravity.py](/home/operator/.openclaw/workspace/build_universe_gravity.py)
  - [build_gics_mapper.py](/home/operator/.openclaw/workspace/build_gics_mapper.py)
- Intelligence layers:
  - [build_macro_layer.py](/home/operator/.openclaw/workspace/build_macro_layer.py)
  - [build_short_interest.py](/home/operator/.openclaw/workspace/build_short_interest.py)
  - [build_sympathy_logger.py](/home/operator/.openclaw/workspace/build_sympathy_logger.py)

Current conclusion:

- The repo has meaningful internal capability code
- Those capabilities are not yet wrapped in project-local skills, runbooks, or intake guidance

## 2. Global Or Doc-Referenced Skill Categories We Appear To Rely On

Based on the known repo context, the planning docs, and the linked Google Docs, Cerebro appears to rely on these skill categories:

- Agent orchestration and queue ownership
  - coordinating parallel workers without multiplying scope
- Memory and research capture
  - maintaining summaries, findings, and reusable knowledge
- Repo cloning and external capability evaluation
  - pulling in open-source systems selectively rather than wholesale
- PDF and Google Docs ingestion
  - extracting and distilling planning artifacts
- Data ingestion and normalization
  - SEC, macro, short-interest, options/flow, sympathy, and related feeds
- Entity resolution and classification
  - ticker, company, CIK, sector, industry, and future graph relationships
- Backend/API contract design
  - stable canonical artifacts and producer/consumer boundaries
- Frontend/HUD workflow design
  - making the desktop operator experience coherent
- Production verification and deployment discipline
  - health checks, freshness guarantees, and live bundle/backend sync

## 3. MVP-Relevant Missing Skills

These are the highest-priority missing skills for the MVP lane:

- `cerebro-reliability-deploy`
  - for daily-run verification, deploy sync, restart behavior, and health checks
- `cerebro-data-contract`
  - for canonical entity schema, artifact definitions, and API contracts
- `cerebro-scoring-composition`
  - for score semantics, macro integration, short-interest integration, and explainability
- `cerebro-hud-workflow`
  - for desktop operator information architecture and backend-to-UI fit
- `cerebro-repo-intake`
  - for evaluating external repos/skills against MVP relevance before adoption
- `cerebro-data-qa`
  - for freshness, shape, and output consistency checks on published artifacts

Secondary but useful later:

- `cerebro-graph-research`
  - for deferred universal-graph expansion
- `cerebro-alt-data-intake`
  - for non-core future moat work such as logistics, legal, patents, and geospatial layers

## 4. Simple Intake Rubric

Every new skill, agent package, or external repo should be scored against this rubric before acceptance.

### Intake questions

- Relevance:
  - Does it directly improve the MVP loop now?
- Queue fit:
  - Which queue owns it: reliability, data contract, scoring, HUD, or deferred research?
- Integration target:
  - What exact file, artifact, or workflow would consume it?
- Novelty:
  - Does it add a missing capability, or duplicate code already present in the repo?
- Verification cost:
  - Can we prove it works without destabilizing production?
- Operational risk:
  - Does it increase complexity, drift, or maintenance burden?

### Decision outcomes

- `Accept`
  - clear MVP relevance, clear owner, clear integration point
- `Defer`
  - useful, but belongs to a post-MVP or research lane
- `Reject`
  - duplicates existing capability, lacks a clear integration target, or adds unjustified complexity

## Baseline Assessment

The current repo state shows a mismatch:

- Internal Cerebro capability code is already substantial
- Project-local skill packaging for Cerebro is minimal
- The documents imply a much larger skill and agent ecosystem than is materially present in this repo today

That means the immediate need is not "ingest everything."
The immediate need is to:

1. inventory reality
2. create Cerebro-specific skills for MVP queues
3. gate external repo/skill ingestion through a strict intake rubric
