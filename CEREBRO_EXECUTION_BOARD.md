# Cerebro Execution Board

## Mission

Operate Cerebro as an MVP-first build.

The near-term product is:

- an always-on catalyst intelligence engine
- a stable backend contract
- a desktop-first HUD/scanner workflow

The near-term product is not:

- the full universal economic graph
- the complete Trade Architect engine
- the mobile app

## Queue Structure

This board turns the MVP plan in [CEREBRO_MVP_EXECUTION_PLAN.md](/home/operator/.openclaw/workspace/CEREBRO_MVP_EXECUTION_PLAN.md) into execution queues with explicit agent ownership.

## Queue A: Reliability and Deploy

Assigned agent:

- `Dirac` (`019d68e8-e581-7ff1-8dc7-a79640654ac6`)

Objective:

- Make the pipeline deterministic, always-on, and safe to deploy

Repo surfaces:

- [run_daily_sec_catalyst.sh](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh)
- [cerebro_verify.py](/home/operator/.openclaw/workspace/cerebro_verify.py)
- [cerebro.service](/home/operator/.openclaw/workspace/cerebro.service)
- [cerebro-logger.service](/home/operator/.openclaw/workspace/cerebro-logger.service)
- deploy/restart/publish scripts

Definition of done:

- daily run completes unattended
- production restart path is documented and reliable
- backend and HUD deploy together without drift
- live verification is routine, not ad hoc

First sprint:

1. define the production verification checklist
2. formalize deploy sync between backend artifacts and HUD bundle
3. classify pipeline failures into hard fail vs degraded success

## Queue B: Canonical Data Contract

Assigned agent:

- `Mendel` (`019d68e8-fb91-7073-b37d-116d77fc9f96`)

Objective:

- Create one canonical entity and API contract shared by pipeline, backend, and HUD

Repo surfaces:

- [api_server.py](/home/operator/.openclaw/workspace/api_server.py)
- [build_universe_gravity.py](/home/operator/.openclaw/workspace/build_universe_gravity.py)
- [build_gics_mapper.py](/home/operator/.openclaw/workspace/build_gics_mapper.py)
- related universe/entity artifact builders

Definition of done:

- entity records are explicit and stable
- scoring fields are not overloaded
- API responses are documented and testable
- producer/consumer boundaries are clear

First sprint:

1. document canonical entity shape
2. document universe endpoint contract
3. separate identity, scoring, and display fields

## Queue C: Intelligence Scoring

Assigned agent:

- `Einstein` (`019d68e8-fe7e-7b72-9945-0eec1bf12b73`)

Objective:

- Make scores explainable, composable, and useful for real operator decisions

Repo surfaces:

- [build_macro_layer.py](/home/operator/.openclaw/workspace/build_macro_layer.py)
- [build_short_interest.py](/home/operator/.openclaw/workspace/build_short_interest.py)
- [build_options_flow.py](/home/operator/.openclaw/workspace/build_options_flow.py)
- [build_sympathy_logger.py](/home/operator/.openclaw/workspace/build_sympathy_logger.py)
- ranking and scoring scripts in the build pipeline

Definition of done:

- final rank is explainable
- freshness is separate from directional bias
- macro and positioning factors are visible in score composition
- sympathy logging starts producing reusable training data

First sprint:

1. inventory all score-producing scripts and fields
2. define the final scoring stack
3. identify stale or duplicated score semantics to remove

## Queue D: HUD Workflow

Assigned agent:

- `Ampere` (`019d68e9-1438-7eb0-a3a8-a5dd0563e788`)

Objective:

- Make the HUD the primary desktop operator workflow for the MVP

Repo surfaces:

- [CerebroHUD.jsx](/home/operator/.openclaw/workspace/hud/src/CerebroHUD.jsx)
- [index.html](/home/operator/.openclaw/workspace/docs/hud/index.html)
- scanner/content surfaces such as [generate_seo_site.py](/home/operator/.openclaw/workspace/generate_seo_site.py)

Definition of done:

- HUD reflects backend truth clearly
- operator can understand what is moving and why
- scanner/HUD product boundaries are explicit
- desktop workflow is coherent before mobile concepts expand

First sprint:

1. map the core operator journey in the HUD
2. identify information-density and hierarchy issues
3. define the boundary between scanner site and Cerebro HUD

## Queue E: Skill Ingestion and Research

Assigned agent:

- `Helmholtz` (`019d68e9-1678-7422-845f-2cabf7224b23`)

Objective:

- Build the capability-ingestion lane without blocking the MVP

Current reality:

- project-local `.agents/skills` currently exposes only `remotion-best-practices`
- the broader skill/repo-cloning ambition exists in the docs, but is not yet organized into a repo-native operating system

Scope:

- skill inventory
- repo-cloning triage
- future capability ingestion
- research backlog shaping

Definition of done:

- skills are categorized by MVP relevance
- repo-cloning targets are sequenced instead of dumped into one giant list
- future capabilities are attached to the correct queue
- non-MVP research stops polluting core build focus

First sprint:

1. build a skill inventory with MVP relevance tags
2. separate immediate-use skills from future-research skills
3. propose a repeatable ingestion workflow for new skills/repos

## Queue G: Memory Fabric and Long-Context Intelligence

Assigned agent:

- `Mnemosyne`

Objective:

- Make `EverOS` and `MSA` permanent cross-project capabilities instead of optional sidecars

Repo surfaces:

- [everos_memory_client.py](/home/operator/.openclaw/workspace/everos_memory_client.py)
- [everos_pipeline_ingest.py](/home/operator/.openclaw/workspace/everos_pipeline_ingest.py)
- [spoke_memory.py](/home/operator/.openclaw/workspace/spoke_memory.py)
- [build_sympathy_logger.py](/home/operator/.openclaw/workspace/build_sympathy_logger.py)
- [CEREBRO_EVERMIND_INTEGRATION.md](/home/operator/.openclaw/workspace/CEREBRO_EVERMIND_INTEGRATION.md)
- [CEREBRO_MEMORY_AGENT_POLICY.md](/home/operator/.openclaw/workspace/CEREBRO_MEMORY_AGENT_POLICY.md)
- [vendor/evermind/EverOS](/home/operator/.openclaw/workspace/vendor/evermind/EverOS)
- [vendor/evermind/MSA](/home/operator/.openclaw/workspace/vendor/evermind/MSA)

Definition of done:

- EverOS remains part of the operational deploy surface
- MSA remains part of the standing research surface
- every major queue exposes a clean memory hook
- low-latency product paths stay protected from premature long-context/runtime coupling

First sprint:

1. codify the permanent EverOS/MSA policy
2. keep memory bridges in deploy and verification paths
3. identify the next memory-enriched API and sympathy surfaces
4. define the first real MSA evaluation backlog

## Queue H: Knowledge Graph and Vault Intelligence

Assigned agent:

- `Graphify`

Objective:

- Turn Cerebro’s mixed-source project material into a persistent graph for architecture discovery, vault organization, and task extraction

Repo surfaces:

- [vendor/graphify](/home/operator/.openclaw/workspace/vendor/graphify)
- [.agents/skills/graphify-agent/SKILL.md](/home/operator/.openclaw/workspace/.agents/skills/graphify-agent/SKILL.md)
- [ops/graphify_workspace.sh](/home/operator/.openclaw/workspace/ops/graphify_workspace.sh)
- [.graphifyignore](/home/operator/.openclaw/workspace/.graphifyignore)
- [CEREBRO_GRAPHIFY_AGENT_POLICY.md](/home/operator/.openclaw/workspace/CEREBRO_GRAPHIFY_AGENT_POLICY.md)
- [CEREBRO_GRAPHIFY_INTEGRATION.md](/home/operator/.openclaw/workspace/CEREBRO_GRAPHIFY_INTEGRATION.md)

Definition of done:

- the project can graph code, docs, PDFs, and screenshots without re-deriving setup
- graph output is used for planning and architecture work before raw-file thrash
- wiki/Obsidian export is available for the research corpus
- Graphify findings are distilled back into execution docs and memory

First sprint:

1. mount Graphify as a project-local skill and runner
2. define Graphify’s boundary against EverOS and MSA
3. create the project ignore rules and integration runbook
4. prepare the first repo graph and vault graph workflows

## Queue I: Market Data Connectivity and Provider Strategy

Assigned agent:

- `Minsky`

Objective:

- reduce provider sprawl, remove data bottlenecks, and open the next real market-data lanes for crypto, prediction markets, and better macro/options coverage

Repo surfaces:

- [CEREBRO_MARKET_DATA_CONNECTIVITY_MATRIX.md](/home/operator/.openclaw/workspace/CEREBRO_MARKET_DATA_CONNECTIVITY_MATRIX.md)
- [api_server.py](/home/operator/.openclaw/workspace/api_server.py)
- [run_daily_sec_catalyst.sh](/home/operator/.openclaw/workspace/run_daily_sec_catalyst.sh)
- [spoke_options.py](/home/operator/.openclaw/workspace/spoke_options.py)
- [build_macro_layer.py](/home/operator/.openclaw/workspace/build_macro_layer.py)
- [generate_seo_site.py](/home/operator/.openclaw/workspace/generate_seo_site.py)

Definition of done:

- provider choices are deliberate instead of ad hoc
- keyless and paid lanes have a documented fallback ladder
- provider auth/env-var names are standardized
- OpenBB is used where it meaningfully reduces bespoke code
- crypto and prediction-market expansion has a clear, staged ingestion plan

First sprint:

1. publish the market data connectivity matrix
2. define the standardized provider env-var contract
3. identify the MVP provider spine for equities, options, macro, and crypto
4. propose which current bespoke adapters should remain direct and which should move behind OpenBB

## Queue F: Human Integrator

Assigned owner:

- main session coordinator

Role:

- resolve cross-queue dependencies
- keep scope disciplined
- decide what gets deferred
- integrate output from queue owners into one coherent build

Rules:

- no queue expands its own scope without checking against MVP
- no speculative research can block production reliability
- no UI ambition outruns backend truth

## Suggested Build Order

1. Queue A: Reliability and Deploy
2. Queue B: Canonical Data Contract
3. Queue C: Intelligence Scoring
4. Queue D: HUD Workflow
5. Queue E: Skill Ingestion and Research
6. Queue G: Memory Fabric and Long-Context Intelligence
7. Queue H: Knowledge Graph and Vault Intelligence
8. Queue I: Market Data Connectivity and Provider Strategy
9. Queue J: MCP Command Center and Tactical Acquisition
10. Queue K: Code Graph Integrity and Nervous System

Queue E, Queue G, Queue I, and Queue K should run in parallel as non-blocking sidecars.

## Queue J: MCP Command Center and Tactical Acquisition

Assigned agent:

- `Argus`

Paired agents:

- `Hermes`
- `Peirce`

Objective:

- make MCP a first-class Cerebro operating layer for code intelligence, tactical web acquisition, and local database access

Repo surfaces:

- [CEREBRO_MCP_COMMAND_CENTER.md](/home/operator/.openclaw/workspace/CEREBRO_MCP_COMMAND_CENTER.md)
- [ops/mcp/README.md](/home/operator/.openclaw/workspace/ops/mcp/README.md)
- [ops/mcp/build_cerebro_mcp_config.py](/home/operator/.openclaw/workspace/ops/mcp/build_cerebro_mcp_config.py)
- [ops/mcp/check_cerebro_mcp_stack.py](/home/operator/.openclaw/workspace/ops/mcp/check_cerebro_mcp_stack.py)
- wrapper launchers in [ops/mcp](/home/operator/.openclaw/workspace/ops/mcp)

Definition of done:

- Cerebro has env-safe MCP config generation for real clients
- GitHub and Firecrawl are operational as command-center surfaces
- Google Search and Perplexity are mounted as live research surfaces
- n8n is mounted as the workflow-bus lane
- 21st.dev Magic is mounted for the UI generation lane
- SQLite memory can be queried through MCP
- future database and research servers have a curated intake path instead of ad hoc sprawl

First sprint:

1. generate WSL and Unix MCP config artifacts
2. validate runtime readiness without exposing secrets
3. align MCP servers to market-data and memory reality
4. assign Google Search and Perplexity to `Argus`
5. assign n8n to `Hermes`
6. assign 21st.dev Magic to `Peirce`
7. document which servers are activated now vs curated next

## Queue K: Code Graph Integrity and Nervous System

Assigned agent:

- `Ariadne`

Objective:

- make GitNexus the first-stop topology lane for shared builders, long-tail recovery hooks, EverOS gates, and launch-risk blast-radius checks

Repo surfaces:

- [CEREBRO_GITNEXUS_NERVOUS_SYSTEM.md](/home/operator/.openclaw/workspace/CEREBRO_GITNEXUS_NERVOUS_SYSTEM.md)
- [.agents/skills/gitnexus-code-graph/SKILL.md](/home/operator/.openclaw/workspace/.agents/skills/gitnexus-code-graph/SKILL.md)
- [build_universe_gravity.py](/home/operator/.openclaw/workspace/build_universe_gravity.py)
- [ops/phase4_long_tail_burnin.py](/home/operator/.openclaw/workspace/ops/phase4_long_tail_burnin.py)
- [everos_memory_client.py](/home/operator/.openclaw/workspace/everos_memory_client.py)
- [api_server.py](/home/operator/.openclaw/workspace/api_server.py)

Definition of done:

- every unknown-entry edge in the taxonomy pipeline is mapped
- the Ollama burn-in hook is attached at the lowest-latency safe path
- EverOS dark-launch helpers do not isolate critical clusters
- each risky Phase 4 change ships with a graph-integrity report

First sprint:

1. trace all unknown-entry edges into the universe build
2. validate the long-tail cache as the lowest-latency Ollama insertion point
3. simulate EverOS gate impact through file/context/impact queries
4. publish the first Phase 4 graph integrity report

## Weekly Rhythm

### Monday

- review queue status
- confirm blocked/unblocked items
- freeze the week’s MVP goals

### Midweek

- verify production health
- validate data/API/HUD alignment
- trim anything that drifted outside MVP

### Friday

- review what actually shipped
- record lessons
- move any unfinished noncritical work back to backlog

## Immediate Next Deliverables

1. canonical entity/API contract document
2. production verification checklist
3. score-composition inventory
4. HUD operator workflow map
5. skill-ingestion rubric and backlog
6. market-data connectivity matrix and provider strategy
7. Phase 4 graph integrity report and topology-backed launch gate

## Backlog Discipline

Ideas from the grand vision belong in one of three places:

- active MVP queue
- deferred expansion roadmap
- research/skill-ingestion backlog

If an idea does not clearly fit one of those, it is not ready to enter execution.
