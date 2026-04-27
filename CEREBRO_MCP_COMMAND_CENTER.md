# Cerebro MCP Command Center

## Mission

Turn MCP into the command layer that lets Cerebro bridge:

- code
- tactical web acquisition
- local operational memory
- future structured market stores

This is how the project gets closer to a live market command center instead of a static app.

## Owner

- `Argus`
  - Role: MCP Command Center and Tactical Data Acquisition
  - Pairs with:
    - `Minsky` for provider strategy
    - `Graphify` for repo and domain mapping
    - `Mnemosyne` for memory surfaces
    - `Hermes` for workflow automation bus orchestration
    - `Peirce` for UI synthesis surfaces
    - `Dirac` for deploy/runtime safety

## Activated Now

### 1. OpenAI Docs MCP

- Purpose:
  - official OpenAI developer documentation
  - MCP, Responses API, Codex, model, and Apps SDK reference
- Runtime:
  - remote MCP server at `https://developers.openai.com/mcp`

### 2. GitHub MCP

- Purpose:
  - repo explanation
  - code-aware changes
  - architecture/documentation access
- Runtime:
  - official GitHub MCP server through Docker

### 3. Firecrawl MCP

- Purpose:
  - tactical acquisition of reports, market news, and messy webpages
  - convert noisy pages into structured content the agent can reason on
- Runtime:
  - `npx -y firecrawl-mcp`

### 4. Cerebro Memory SQLite MCP

- Purpose:
  - expose `.cerebro_memory.db` as a natural-language query surface
  - let agents inspect spark history and operational memory directly
- Runtime:
  - `npx -y mcp-sqlite`

### 5. Fetch MCP

- Purpose:
  - lightweight JSON and simple web acquisition
  - faster than a full crawl when all we need is clean endpoint data
- Runtime:
  - local workspace venv with `mcp-server-fetch`

### 6. Google Search MCP

- Purpose:
  - anti-bot live search for catalyst verification and fresh market context
  - a direct search sweep when Firecrawl or fetch are the wrong tool
- Runtime:
  - `npx -y @mcp-server/google-search-mcp@latest`
- Assigned lane:
  - `Argus`

### 7. n8n MCP

- Purpose:
  - bridge Cerebro agents into n8n workflows and executions
  - give the command center a workflow bus instead of one-off webhook glue
- Runtime:
  - `npx -y @leonardsellem/n8n-mcp-server`
- Assigned lane:
  - `Hermes` with `Argus`

### 8. 21st.dev Magic MCP

- Purpose:
  - accelerate UI/component acquisition for Scanner and HUD work
  - give `Peirce` a first-class MCP lane for component generation instead of ad hoc copy/paste
- Runtime:
  - `npx -y @21st-dev/magic@latest`
- Assigned lane:
  - `Peirce` with `Argus`

### 9. Perplexity MCP

- Purpose:
  - live reasoning and deep-research lane for market/operator questions
  - a stronger research surface than raw search alone when we need synthesis
- Runtime:
  - `npx --yes --quiet @perplexity-ai/mcp-server`
- Assigned lane:
  - `Argus`

### 10. GPT Runtime Lane

- Purpose:
  - enable OpenAI-backed project tooling with a first-class `OPENAI_API_KEY` env lane
  - keep GPT runtime activation separate from docs access
- Current state:
  - optional
  - enabled by adding `OPENAI_API_KEY` to `~/.codex/cerebro-mcp.env`

### 11. Optional Postgres MCP

- Purpose:
  - future market store lane if/when Cerebro gets a real Postgres backbone
- Current state:
  - optional
  - not treated as the primary DB today

## Explicit Intake Decision

`Proux` is being interpreted as the Perplexity lane.

We are not auto-adding Puppeteer or Proxmox here:

- Puppeteer would duplicate Playwright and Firecrawl browser tooling already mounted in Cerebro
- Proxmox is infra/homelab management, not a current command-center lane for this repo

## Curated Next Tier

These are part of the architecture backlog, but not auto-activated in tracked config yet:

- SEC EDGAR MCP
- Wolfram Alpha MCP
- Trading Economics MCP
- Google Developer Knowledge MCP
- community yfinance MCP surfaces
- prediction-market MCP surfaces

These remain curated until their package/runtime path is verified and they can be added without turning the stack into connector drift.

## Project Principle

MCP servers should reinforce Cerebro's existing truth surfaces:

- [market_data_contract.py](/home/operator/.openclaw/workspace/market_data_contract.py)
- [openbb_bridge.py](/home/operator/.openclaw/workspace/openbb_bridge.py)
- [spoke_memory.py](/home/operator/.openclaw/workspace/spoke_memory.py)

They should not create a second, parallel source-of-truth architecture.

## Operational Rule

- secrets live in the environment
- tracked config contains commands only
- WSL is the primary runtime for this project
