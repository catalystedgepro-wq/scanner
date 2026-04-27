# Cerebro MVP Execution Plan

## Purpose

This document converts the current Cerebro vision into an executable MVP-first workflow.
It is grounded in:

- The current repository and live deployment state
- The PDF brainstorming/roadmap/mapping documents
- The linked Google Docs

The goal is to prevent scope collapse. Cerebro is not being treated as a single giant build. It is being split into:

1. A shippable MVP
2. The next intelligence layer
3. The long-horizon universal economic graph vision

## Current Truth

The project is not at zero.

It already has:

- A real daily scanner/pipeline centered on [run_daily_sec_catalyst.sh](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh)
- A live FastAPI backend in [api_server.py](/home/operator/.openclaw/workspace/api_server.py)
- A live HUD frontend in [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx)
- A deployed static HUD build in [index.html](/home/operator/.openclaw/workspace/docs/hud/index.html)
- Existing reporting/distribution hooks such as [send_sec_catalyst_email.py](/home/operator/.openclaw/workspace/send_sec_catalyst_email.py)

The project is currently much closer to:

- "always-on catalyst scanner + backend + HUD"

than to:

- "complete Google Earth of the economy"

That is good news. The near-term problem is organization and contract clarity, not invention.

## Product Layers

### Layer 1: MVP

The MVP is a truthful, always-on catalyst intelligence system for public equities.

It must deliver:

- Reliable ingestion and daily refresh
- Canonical entity and sector mapping
- Clean scoring/ranking
- Macro-aware context
- A desktop-first operator workflow
- A usable HUD/scanner surface backed by real data

### Layer 2: Intelligence Expansion

This layer adds:

- Sympathy capture and contagion modeling
- ETF/index tethering and exposure effects
- Better short-interest and options pressure integration
- Probability-oriented trade framing

### Layer 3: Universal Economic Graph

This is the larger vision described in the docs:

- Supply chain and physical asset mapping
- Geospatial overlays
- Legal/regulatory/patent layers
- Alternative data moat
- Full "Google Earth of the Economy" rendering

This is not the MVP.

## Hard MVP Cut

### What ships in MVP

- SEC catalyst ingestion centered on 8-K and Form 4 signal flow
- Broad universe mapping via canonical company/entity records
- Sector and industry classification that is stable enough for clustering and HUD rendering
- Macro layer that affects ranking/context at sector level
- Daily rebuild on always-on infrastructure
- Backend contract for universe, sectors, ticker detail, macro, and live updates
- Desktop HUD that visualizes the real universe and current catalysts
- Clear distinction between score, freshness, intensity, and directional bias

### What is deferred

- Mobile app
- Full geospatial asset engine
- PACER/legal ingestion
- Weather/disaster/logistics intelligence as core MVP dependencies
- Heavy machine learning
- Full dark-pool/options moat as a blocker for shipping
- Full "trade architect" execution engine
- Full universal graph ontology across every economic layer

## MVP Workflow

The MVP workflow should be one daily operating loop:

1. Ingest and normalize source data
2. Resolve entities and classifications
3. Compute scoring and context layers
4. Publish canonical artifacts for the backend
5. Serve the backend consistently
6. Render the HUD/scanner from that backend
7. Capture operator feedback and logging for future sympathy/probability modeling

If a feature does not improve that loop, it should probably wait.

## Phase Plan

## Phase 1: Operational Spine

Objective:
Make the scanner truthful, deterministic, and always-on.

Primary surfaces:

- [run_daily_sec_catalyst.sh](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh)
- Deploy/restart/publish scripts
- Production health checks around [api_server.py](/home/operator/.openclaw/workspace/api_server.py)

Tasks:

- Remove remaining local-machine dependency from the daily run
- Make deploy artifacts and live bundle synchronization explicit
- Add verification for backend health, universe shape, and HUD bundle freshness
- Make daily outputs deterministic and timestamped
- Define "pipeline succeeded" vs "pipeline partially degraded"

Acceptance bar:

- Daily run completes unattended
- Live API always serves current canonical artifacts
- HUD and backend stay in sync after deploys

## Phase 2: Canonical Data Model

Objective:
Make entity identity and scoring contracts explicit.

Primary surfaces:

- [api_server.py](/home/operator/.openclaw/workspace/api_server.py)
- Entity-building scripts such as [build_universe_gravity.py](/home/operator/.openclaw/workspace/build_universe_gravity.py)
- Classification/mapping scripts such as [build_gics_mapper.py](/home/operator/.openclaw/workspace/build_gics_mapper.py)

Tasks:

- Define canonical entity shape for company/ticker records
- Separate identity fields from scoring fields from display fields
- Standardize score meanings:
  - priority/final rank
  - catalyst intensity
  - freshness
  - directional bias
  - macro drag/tailwind
- Lock universe API pagination and response contract
- Document required artifacts and their producers

Acceptance bar:

- The same entity means the same thing across pipeline, API, and HUD
- Scores are explainable and non-duplicative
- No mock or stale fallback leaks into production

## Phase 3: Intelligence Layer

Objective:
Improve decision quality without exploding scope.

Primary surfaces:

- Macro and ranking scripts such as [build_macro_layer.py](/home/operator/.openclaw/workspace/build_macro_layer.py)
- Short-interest/options/sympathy enrichment in the pipeline
- Backend endpoints in [api_server.py](/home/operator/.openclaw/workspace/api_server.py)

Tasks:

- Confirm macro inputs affect ranking the way the docs intend
- Integrate short-interest cleanly into the final score path
- Start or normalize sympathy logging as a data collection lane
- Separate "activity heat" from "bullishness"
- Prepare data structures for future contagion/probability features

Acceptance bar:

- Score movement is attributable
- Macro and positioning data influence output in a measurable way
- Future "sympathy web" work has real logs to learn from

## Phase 4: Operator Experience

Objective:
Turn the existing HUD into the primary MVP control surface.

Primary surfaces:

- [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx)
- Supporting scanner/frontend output

Tasks:

- Align HUD views to one operator workflow instead of multiple product fantasies
- Make sector, ticker, catalyst, and macro context readable at a glance
- Keep desktop-first focus
- Remove ambiguity between scanner site, HUD, and future mobile concepts
- Treat the HUD as a readout of the engine, not a substitute for missing engine logic

Acceptance bar:

- A user can answer: what is moving, why, where it lives, and what is connected

## Phase 5: Deferred Expansion

Only begin after Phases 1-4 are stable.

Deferred programs:

- Trade Architect probability engine
- Full sympathy contagion graph
- Supply chain / asset geospatial layer
- Alternative data moat
- Universal economic graph
- Mobile expression of the product

## Recommended Workstreams

To execute cleanly, use these workstreams:

### Workstream A: Reliability and Deploy

- Own the daily run, deploy sync, health checks, restart behavior, and production verification

### Workstream B: Canonical Data Contract

- Own entity schema, scoring semantics, artifacts, and API contract

### Workstream C: Intelligence Scoring

- Own macro, short-interest, options, sympathy, and ranking composition

### Workstream D: HUD Workflow

- Own the operator-facing desktop experience and keep it tightly coupled to real backend truth

### Workstream E: Future Graph Research

- Own the longer-horizon repository cloning, skill ingestion, and universal graph expansion work
- This should not block MVP shipping

## Ruflo / Agent Guidance

The external docs point toward a large number of research and implementation lanes, but the MVP should use agents narrowly.

Recommended agent usage:

- Reliability agent: pipeline/deploy/health checks
- Data-contract agent: entity model and API schema
- Scoring agent: macro + ranking + enrichment composition
- UX agent: HUD workflow and information architecture
- Research agent: longer-horizon repo cloning and alternative-data scouting

Do not use agent parallelism to multiply scope. Use it to separate ownership.

## Immediate Next Actions

1. Freeze the MVP definition in writing
2. Write the canonical entity/API contract
3. Add production verification around daily run + backend + HUD bundle
4. Audit score composition and remove duplicated or ambiguous score semantics
5. Align the HUD around one operator workflow
6. Move all non-MVP universal graph ambitions into a deferred roadmap

## Decision Rule

When a new idea appears, ask:

"Does this make the daily catalyst intelligence loop more truthful, reliable, and useful right now?"

If yes, it belongs in the MVP lane.
If no, it goes into the expansion roadmap.
