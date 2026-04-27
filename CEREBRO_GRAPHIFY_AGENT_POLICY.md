# Cerebro Graphify Agent Policy

## Decision

`Graphify` is now a permanent project lane for knowledge-graph curation, vault mapping, and cross-source reasoning.

This makes Graphify a standing complement to:

- `EverOS` for operational memory and recall
- `MSA` for very large long-context reasoning

## Standing Owner

- `Graphify`
  - permanent knowledge-graph and vault-intelligence owner
  - owns structure discovery across code, docs, PDFs, screenshots, and markdown notes

## Lane Role

### Graphify = structural graph and curator

Use Graphify to:

- auto-discover entities and relationships across Cerebro source material
- turn mixed project inputs into a navigable graph and report
- generate an Obsidian-style vault or wiki from project research
- surface hidden links between plans, implementation files, and design references
- extract task clusters from notes and route them into planning and automation lanes

### EverOS = operational memory

Use EverOS to:

- persist event memory and API recall context
- preserve run outcomes and symbol histories
- keep runtime-safe memory continuity across sessions

### MSA = deep long-context sidecar

Use MSA to:

- reason over huge filing bundles and long retrospectives
- evaluate large corpora once Graphify has narrowed the surface
- support offline analysis, not low-latency UI/runtime paths

## Permanent Rules

### Rule 1: Graphify is always available in the project surface

The repo must keep the Graphify lane accessible through:

- [vendor/graphify](/home/operator/.openclaw/workspace/vendor/graphify)
- [.agents/skills/graphify-agent/SKILL.md](/home/operator/.openclaw/workspace/.agents/skills/graphify-agent/SKILL.md)
- [ops/graphify_workspace.sh](/home/operator/.openclaw/workspace/ops/graphify_workspace.sh)
- [.graphifyignore](/home/operator/.openclaw/workspace/.graphifyignore)

### Rule 2: Graphify is not runtime truth

Graphify must not be treated as the live source of truth for:

- scanner price/action data
- live HUD websocket state
- API contract enforcement
- production operational memory

It is a structural reasoning and curation surface.

### Rule 3: Graphify findings must be distilled back into project truth

When Graphify surfaces a meaningful connection, decision, or task cluster, the result must be written back into:

- execution docs
- project policy docs
- `memory/YYYY-MM-DD.md`
- task/automation surfaces

### Rule 4: Graphify should reduce raw-file thrash

Before broad architecture work, planning, or note-to-task distillation, prefer:

1. Graphify report
2. targeted graph query
3. raw file search only where needed

## Phase Interpretation

### Phase 1 / Phase 2

- Graphify is mainly a repo-mapping, planning, and vault-curation tool
- It helps connect the brainstorming corpus to the implementation corpus

### Phase 3+

- Graphify can expand into agent-facing MCP graph access
- Graphify outputs can feed richer wiki, task-routing, and vault workflows

## What “Always Deployed” Means Here

It does not mean:

- forcing Graphify into hot runtime request paths
- letting graph output override source-of-truth contracts

It does mean:

- the Graphify skill stays mounted
- the project-local runner stays maintained
- the lane has a permanent owner
- the team can graphify the repo or research corpus without re-deriving setup
