# Cerebro Graphify Integration

## Purpose

Graphify is the project’s structural knowledge-graph engine.

It gives Cerebro a persistent map across:

- source code
- planning docs
- memory logs
- PDFs
- screenshots and diagrams
- vault-style markdown research

## Installed Surface

- upstream repo: [vendor/graphify](/home/operator/.openclaw/workspace/vendor/graphify)
- local skill: [.agents/skills/graphify-agent/SKILL.md](/home/operator/.openclaw/workspace/.agents/skills/graphify-agent/SKILL.md)
- project runner: [ops/graphify_workspace.sh](/home/operator/.openclaw/workspace/ops/graphify_workspace.sh)
- repo ignore rules: [.graphifyignore](/home/operator/.openclaw/workspace/.graphifyignore)

## Default Run

```bash
bash /home/operator/.openclaw/workspace/ops/graphify_workspace.sh
```

Default behavior:

- creates or reuses `.venv-graphify`
- installs Graphify from the vendored repo
- runs Graphify against the workspace root
- writes output to `graphify-out/`

## High-Value Cerebro Workflows

### 1. Architecture Orientation

Use when the team needs to answer:

- what connects the Scanner to the HUD
- which files drive a specific product seam
- why a behavior exists across multiple surfaces

Suggested flow:

1. run Graphify on the workspace
2. read `graphify-out/GRAPH_REPORT.md`
3. query the graph for the seam in question
4. then patch the real implementation files

### 2. Brainstorm Corpus To Vault

Use when ingesting:

- roadmap PDFs
- screenshots
- Google Doc exports
- strategy notes

Suggested commands:

```bash
bash /home/operator/.openclaw/workspace/ops/graphify_workspace.sh /path/to/corpus --obsidian --wiki
```

### 3. Task Extraction And Planning

Use Graphify to identify:

- recurring entities
- repeated unresolved themes
- clusters of unfinished work
- hidden dependencies between plans and code

Then distill the findings into:

- [CEREBRO_EXECUTION_BOARD.md](/home/operator/.openclaw/workspace/CEREBRO_EXECUTION_BOARD.md)
- sprint docs
- `memory/YYYY-MM-DD.md`
- automation workflows

### 4. Future MCP Graph Access

Graphify can later expose `graph.json` as an MCP service so agents can query the knowledge graph directly instead of re-reading raw files.

That is a future-facing lane, not a current runtime dependency.

## Boundaries

Graphify should not replace:

- `EverOS` operational memory
- `MSA` long-context reasoning
- `entity_master.json`
- live scanner/HUD truth

Graphify is for structure, curation, and connection discovery.
