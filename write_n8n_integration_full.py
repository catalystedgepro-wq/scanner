from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


FILES = {
    ROOT / ".agents/skills/n8n-automation-orchestrator/SKILL.md": """---
name: n8n-automation-orchestrator
description: "Workflow automation skill for Cerebro. Use for scheduled scanner runs, verifier gates, agent-pod orchestration, operator notifications, webhook routing, and multimodal downstream automation."
---

# n8n Automation Orchestrator

n8n is the workflow automation skill for Cerebro. It is the right fit when the task is about scheduling, routing, gating, or fanning out work across the scanner, API, memory layer, and operator channels.

Primary source in this workspace:

- `vendor/n8n/n8n`
- `vendor/n8n/n8n/README.md`
- `vendor/n8n/n8n/docker/images/n8n/README.md`
- `ops/n8n`

## Use This Skill For

- Premarket and intraday scanner cadence orchestration
- Running `run_daily_sec_catalyst.sh` behind schedule or webhook triggers
- Manifest and artifact gating before publish or alert fan-out
- Calling Cerebro APIs for `/api/health`, `/api/spark`, `/api/ticker/{symbol}`, `/api/ai-summary/{ticker}`, and `/api/briefing`
- Routing operator notifications and human-review queues
- Building agent-pod workflows that combine scanner output, memory context, and AI summaries
- Later-phase multimodal packaging such as voice briefings, screenshot cards, or recap clips

## Do Not Use This Skill For

- Core ranking, scoring, or market-data computation
- Direct HUD rendering or client-side interaction fixes
- Replacing the live Redis/WebSocket event loop
- Bypassing `scanner_artifact_status.json` or `cerebro_verify.py`
- Automating the public scanner or HUD DOM when stable APIs or artifact files already exist

## Cerebro Integration Targets

- `run_daily_sec_catalyst.sh`
  - top-level premarket and intraday run surface
- `cerebro_verify.py`
  - manifest and contract gate
- `scanner_artifact_status.json`
  - non-zero scanner publish guard
- `pipeline_manifest.json`
  - machine-readable run outcome envelope
- `api_server.py`
  - `/api/health`, `/api/universe`, `/api/spark`, `/api/ticker/{symbol}`, `/api/ai-summary/{ticker}`, `/api/briefing`, `/ws/live`
- `cerebro_publisher.py`
  - event seam for `pipeline_complete`, `macro_update`, `spark_update`, `options_sweep`
- `build_sympathy_logger.py`, `spoke_memory.py`, `everos_pipeline_ingest.py`
  - memory, sympathy, and post-run recall lanes

## Agent Pod Mapping

- Gatekeeper pod
  - schedule scanner runs
  - verify manifest
  - reject zero-content artifacts
- Intelligence pod
  - fetch ticker intelligence and briefings
  - attach sympathy and EverOS recall
  - route fallback states to review
- Notification pod
  - send operator alerts to internal channels
  - keep social/public fan-out behind approval gates
- Multimodal pod
  - package briefings into voice, image, or recap workflows after truth gates pass

## Implementation Bias

- Start with the scanner gatekeeper and operator workflows
- Keep n8n outside the hot publish and scoring path
- Prefer file and API seams over UI scraping
- Treat scanner validity and manifest verification as hard gates, not optional checks
- Keep external distribution under human approval until the automation lane has earned trust
""",
    ROOT / "CEREBRO_N8N_AUTOMATION_MVP.md": """# Cerebro n8n Automation MVP

## Status

`n8n` is now vendored into the workspace at `vendor/n8n/n8n` and mounted as a local automation skill at `.agents/skills/n8n-automation-orchestrator/SKILL.md`.

The MVP goal is not "automate everything." The goal is to automate the safest, highest-value seams first:

- scanner cadence
- manifest and artifact gating
- operator intelligence retrieval
- memory and sympathy handoff
- multimodal follow-through only after truth gates pass

## Pod Workflow

```mermaid
flowchart LR
    A["Schedule Trigger or Webhook"] --> B["run_daily_sec_catalyst.sh"]
    B --> C["pipeline_manifest.json"]
    B --> D["scanner_artifact_status.json"]
    C --> E["cerebro_verify.py"]
    D --> F["Artifact Gate"]
    E --> G["API Probes"]
    F --> G
    G --> H["Ticker + Briefing Intelligence"]
    H --> I["EverOS + Sympathy Context"]
    I --> J["Operator Notifications"]
    J --> K["Later: Audio / Image / Video Packaging"]
    F --> L["Human Review Queue"]
    E --> L
```

## MVP Pods

### 1. Gatekeeper Pod

Owns run timing and release quality.

- Trigger premarket full runs
- Trigger intraday scanner refreshes
- Verify `pipeline_manifest.json`
- Reject empty scanner deploys using `scanner_artifact_status.json`
- Probe `/api/health` and `/api/universe` before declaring success

### 2. Intelligence Pod

Owns operator-facing enrichment.

- Fetch `/api/ticker/{symbol}`
- Fetch `/api/ai-summary/{ticker}`
- Fetch `/api/briefing`
- Branch when `model_metadata` indicates fallback or review-required state
- Attach sympathy and memory context

### 3. Notification Pod

Owns internal fan-out.

- Send internal alerts after gates pass
- Route failures into a human review queue
- Keep social and public posting behind explicit approval

### 4. Multimodal Pod

This is real, but later in the MVP.

- Voice briefings
- Screenshot cards for scanner/HUD state
- Video recap workflows

The multimodal pod should only consume already-validated outputs. It should never become the truth source.

## Workflow Pack

The initial workflow pack lives in `ops/n8n/workflows`:

- `cerebro_intraday_refresh_gatekeeper.json`
- `cerebro_premarket_pipeline.json`
- `cerebro_operator_intelligence_webhook.json`

## Deployment Shape

Use a self-hosted n8n container on the droplet and keep it off the public scanner/HUD hot path.

- bind n8n to `127.0.0.1:5678`
- proxy it separately if you want a browser UI
- mount `/opt/catalyst` into the n8n container so command nodes can run project scripts
- start with `EVEROS_ENABLED=0` in n8n-side workflows if you want a low-risk initial rollout

Reference files:

- `ops/n8n/docker-compose.yml.example`
- `ops/n8n/.env.example`

## Order Of Operations

1. Bring up n8n in Docker
2. Import the workflow JSON files
3. Adjust schedule nodes to match the scanner refresh contract
4. Test the intraday workflow first
5. Test the premarket full pipeline next
6. Only then attach notifications and multimodal outputs

## Safe MVP Boundary

The safe line is:

- automate orchestration
- automate validation
- automate internal enrichment

Do not let n8n own:

- raw scoring logic
- live HUD rendering logic
- truth generation for filings
- public posting without review
""",
    ROOT / "ops/n8n/README.md": """# n8n Operations

This folder contains the first Cerebro automation pack for `n8n`.

## Files

- `.env.example`
- `docker-compose.yml.example`
- `workflows/cerebro_intraday_refresh_gatekeeper.json`
- `workflows/cerebro_premarket_pipeline.json`
- `workflows/cerebro_operator_intelligence_webhook.json`

## Quick Start

1. Copy `.env.example` to `.env` and replace the placeholder values.
2. Start n8n with Docker Compose.
3. Import the JSON workflows from `workflows/`.
4. Adjust the schedule triggers to match the production cadence.
5. Test the intraday workflow before the full premarket workflow.

## Recommended First Live Sequence

1. `cerebro_intraday_refresh_gatekeeper.json`
2. `cerebro_premarket_pipeline.json`
3. `cerebro_operator_intelligence_webhook.json`

## Why This Order

The scanner cadence and validation layer are already the most stable outputs in the repo:

- `run_daily_sec_catalyst.sh`
- `pipeline_manifest.json`
- `scanner_artifact_status.json`
- `cerebro_verify.py`

That makes them the right first automation seam.
""",
    ROOT / "ops/n8n/.env.example": """N8N_IMAGE_TAG=stable
N8N_PORT=5678
N8N_HOST=n8n.catalystedgescanner.com
N8N_PROTOCOL=https
N8N_EDITOR_BASE_URL=https://n8n.catalystedgescanner.com
WEBHOOK_URL=https://n8n.catalystedgescanner.com/
GENERIC_TIMEZONE=America/New_York
N8N_SECURE_COOKIE=true
N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER=change-me
N8N_BASIC_AUTH_PASSWORD=change-me

CEREBRO_BASE_URL=http://127.0.0.1:8000
CEREBRO_WORKDIR=/opt/catalyst
EVEROS_ENABLED=0
""",
    ROOT / "ops/n8n/docker-compose.yml.example": """services:
  n8n:
    image: docker.n8n.io/n8nio/n8n:${N8N_IMAGE_TAG:-stable}
    restart: unless-stopped
    ports:
      - "127.0.0.1:${N8N_PORT:-5678}:5678"
    env_file:
      - .env
    environment:
      - N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true
      - N8N_RUNNERS_ENABLED=true
      - N8N_HOST=${N8N_HOST}
      - N8N_PORT=5678
      - N8N_PROTOCOL=${N8N_PROTOCOL}
      - WEBHOOK_URL=${WEBHOOK_URL}
      - N8N_EDITOR_BASE_URL=${N8N_EDITOR_BASE_URL}
      - GENERIC_TIMEZONE=${GENERIC_TIMEZONE}
      - TZ=${GENERIC_TIMEZONE}
      - NODE_ENV=production
      - N8N_SECURE_COOKIE=${N8N_SECURE_COOKIE}
      - N8N_BASIC_AUTH_ACTIVE=${N8N_BASIC_AUTH_ACTIVE}
      - N8N_BASIC_AUTH_USER=${N8N_BASIC_AUTH_USER}
      - N8N_BASIC_AUTH_PASSWORD=${N8N_BASIC_AUTH_PASSWORD}
    volumes:
      - n8n_data:/home/node/.n8n
      - /opt/catalyst:/opt/catalyst
      - ./local-files:/files

volumes:
  n8n_data:
""",
}


WORKFLOW_INTRADAY = {
    "name": "Cerebro Intraday Refresh Gatekeeper",
    "nodes": [
        {
            "parameters": {"rule": {"interval": [{}]}},
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 220],
            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d001",
            "name": "Schedule Trigger",
        },
        {
            "parameters": {"command": "cd /opt/catalyst && CEREBRO_RUN_MODE=intraday ./run_daily_sec_catalyst.sh"},
            "type": "n8n-nodes-base.executeCommand",
            "typeVersion": 1,
            "position": [240, 220],
            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d002",
            "name": "Run Intraday Refresh",
        },
        {
            "parameters": {"command": "cat /opt/catalyst/scanner_artifact_status.json"},
            "type": "n8n-nodes-base.executeCommand",
            "typeVersion": 1,
            "position": [480, 220],
            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d003",
            "name": "Read Scanner Artifact Status",
        },
        {
            "parameters": {
                "jsCode": "const raw = $json.stdout || '{}';\nconst parsed = JSON.parse(raw);\nconst counts = parsed.counts || {};\nconst primarySectionCount = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);\nreturn [{\n  valid: Boolean(parsed.valid),\n  generated_at: parsed.generated_at || null,\n  primarySectionCount,\n  counts,\n  raw: parsed,\n}];"
            },
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [720, 220],
            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d004",
            "name": "Parse Artifact Status",
        },
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "strict",
                        "version": 2,
                    },
                    "conditions": [
                        {
                            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d004-cond",
                            "leftValue": "={{ $json.primarySectionCount }}",
                            "rightValue": 0,
                            "operator": {"type": "number", "operation": "gt"},
                        }
                    ],
                    "combinator": "and",
                },
                "options": {},
            },
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [960, 220],
            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d005",
            "name": "Artifacts Valid?",
        },
        {
            "parameters": {
                "url": "http://127.0.0.1:8000/api/health",
                "options": {"allowUnauthorizedCerts": True},
            },
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1200, 120],
            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d006",
            "name": "Probe API Health",
        },
        {
            "parameters": {
                "assignments": {
                    "assignments": [
                        {
                            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d007-status",
                            "name": "workflow_status",
                            "value": "refresh_ok",
                            "type": "string",
                        },
                        {
                            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d007-health",
                            "name": "health_status",
                            "value": "={{ $json.status || 'unknown' }}",
                            "type": "string",
                        },
                        {
                            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d007-next",
                            "name": "next_action",
                            "value": "notify_operator",
                            "type": "string",
                        },
                    ]
                },
                "options": {},
            },
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [1440, 120],
            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d007",
            "name": "Build Success Packet",
        },
        {
            "parameters": {
                "assignments": {
                    "assignments": [
                        {
                            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d008-status",
                            "name": "workflow_status",
                            "value": "refresh_review_required",
                            "type": "string",
                        },
                        {
                            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d008-reason",
                            "name": "reason",
                            "value": "scanner_artifact_invalid_or_empty",
                            "type": "string",
                        },
                        {
                            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d008-next",
                            "name": "next_action",
                            "value": "route_to_human_review",
                            "type": "string",
                        },
                    ]
                },
                "options": {},
            },
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [1200, 340],
            "id": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d008",
            "name": "Build Failure Packet",
        },
    ],
    "connections": {
        "Schedule Trigger": {"main": [[{"node": "Run Intraday Refresh", "type": "main", "index": 0}]]},
        "Run Intraday Refresh": {"main": [[{"node": "Read Scanner Artifact Status", "type": "main", "index": 0}]]},
        "Read Scanner Artifact Status": {"main": [[{"node": "Parse Artifact Status", "type": "main", "index": 0}]]},
        "Parse Artifact Status": {"main": [[{"node": "Artifacts Valid?", "type": "main", "index": 0}]]},
        "Artifacts Valid?": {
            "main": [
                [{"node": "Probe API Health", "type": "main", "index": 0}],
                [{"node": "Build Failure Packet", "type": "main", "index": 0}],
            ]
        },
        "Probe API Health": {"main": [[{"node": "Build Success Packet", "type": "main", "index": 0}]]},
    },
    "pinData": {},
    "active": False,
    "settings": {},
    "versionId": "c4e54d13-c3fd-4ab8-9fe2-d2c69121d009",
    "id": "cerebro-intraday-refresh-gatekeeper",
    "meta": {"templateCredsSetupCompleted": False},
    "tags": [],
}


WORKFLOW_PREMARKET = {
    "name": "Cerebro Premarket Pipeline",
    "nodes": [
        {
            "parameters": {"rule": {"interval": [{}]}},
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 220],
            "id": "6fb7956e-7af8-4d68-9240-4df8fe6bf001",
            "name": "Schedule Trigger",
        },
        {
            "parameters": {"command": "cd /opt/catalyst && CEREBRO_RUN_MODE=build_only ./run_daily_sec_catalyst.sh"},
            "type": "n8n-nodes-base.executeCommand",
            "typeVersion": 1,
            "position": [240, 220],
            "id": "6fb7956e-7af8-4d68-9240-4df8fe6bf002",
            "name": "Run Premarket Pipeline",
        },
        {
            "parameters": {
                "command": "cd /opt/catalyst && python3 cerebro_verify.py --mode manifest --manifest /opt/catalyst/pipeline_manifest.json --base-url http://127.0.0.1:8000"
            },
            "type": "n8n-nodes-base.executeCommand",
            "typeVersion": 1,
            "position": [480, 220],
            "id": "6fb7956e-7af8-4d68-9240-4df8fe6bf003",
            "name": "Verify Pipeline Manifest",
        },
        {
            "parameters": {"command": "cat /opt/catalyst/scanner_artifact_status.json"},
            "type": "n8n-nodes-base.executeCommand",
            "typeVersion": 1,
            "position": [720, 220],
            "id": "6fb7956e-7af8-4d68-9240-4df8fe6bf004",
            "name": "Read Scanner Artifact Status",
        },
        {
            "parameters": {
                "jsCode": "const raw = $json.stdout || '{}';\nconst parsed = JSON.parse(raw);\nconst counts = parsed.counts || {};\nconst primarySectionCount = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);\nreturn [{\n  valid: Boolean(parsed.valid),\n  primarySectionCount,\n  generated_at: parsed.generated_at || null,\n  counts,\n  raw: parsed,\n}];"
            },
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [960, 220],
            "id": "6fb7956e-7af8-4d68-9240-4df8fe6bf005",
            "name": "Parse Artifact Status",
        },
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "strict",
                        "version": 2,
                    },
                    "conditions": [
                        {
                            "id": "6fb7956e-7af8-4d68-9240-4df8fe6bf005-cond",
                            "leftValue": "={{ $json.primarySectionCount }}",
                            "rightValue": 0,
                            "operator": {"type": "number", "operation": "gt"},
                        }
                    ],
                    "combinator": "and",
                },
                "options": {},
            },
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [1200, 220],
            "id": "6fb7956e-7af8-4d68-9240-4df8fe6bf006",
            "name": "Artifacts Valid?",
        },
        {
            "parameters": {
                "url": "http://127.0.0.1:8000/api/briefing",
                "options": {"allowUnauthorizedCerts": True},
            },
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1440, 120],
            "id": "6fb7956e-7af8-4d68-9240-4df8fe6bf007",
            "name": "Fetch Briefing",
        },
        {
            "parameters": {
                "jsCode": "return [{\n  workflow_status: 'premarket_ok',\n  next_action: 'route_briefing_to_operator_channels',\n  briefing: $json,\n}];"
            },
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1680, 120],
            "id": "6fb7956e-7af8-4d68-9240-4df8fe6bf008",
            "name": "Build Premarket Packet",
        },
        {
            "parameters": {
                "assignments": {
                    "assignments": [
                        {
                            "id": "6fb7956e-7af8-4d68-9240-4df8fe6bf009-status",
                            "name": "workflow_status",
                            "value": "premarket_review_required",
                            "type": "string",
                        },
                        {
                            "id": "6fb7956e-7af8-4d68-9240-4df8fe6bf009-reason",
                            "name": "reason",
                            "value": "artifact_invalid_or_manifest_review_required",
                            "type": "string",
                        },
                        {
                            "id": "6fb7956e-7af8-4d68-9240-4df8fe6bf009-next",
                            "name": "next_action",
                            "value": "route_to_human_review",
                            "type": "string",
                        },
                    ]
                },
                "options": {},
            },
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [1440, 340],
            "id": "6fb7956e-7af8-4d68-9240-4df8fe6bf009",
            "name": "Build Failure Packet",
        },
    ],
    "connections": {
        "Schedule Trigger": {"main": [[{"node": "Run Premarket Pipeline", "type": "main", "index": 0}]]},
        "Run Premarket Pipeline": {"main": [[{"node": "Verify Pipeline Manifest", "type": "main", "index": 0}]]},
        "Verify Pipeline Manifest": {"main": [[{"node": "Read Scanner Artifact Status", "type": "main", "index": 0}]]},
        "Read Scanner Artifact Status": {"main": [[{"node": "Parse Artifact Status", "type": "main", "index": 0}]]},
        "Parse Artifact Status": {"main": [[{"node": "Artifacts Valid?", "type": "main", "index": 0}]]},
        "Artifacts Valid?": {
            "main": [
                [{"node": "Fetch Briefing", "type": "main", "index": 0}],
                [{"node": "Build Failure Packet", "type": "main", "index": 0}],
            ]
        },
        "Fetch Briefing": {"main": [[{"node": "Build Premarket Packet", "type": "main", "index": 0}]]},
    },
    "pinData": {},
    "active": False,
    "settings": {},
    "versionId": "6fb7956e-7af8-4d68-9240-4df8fe6bf010",
    "id": "cerebro-premarket-pipeline",
    "meta": {"templateCredsSetupCompleted": False},
    "tags": [],
}


WORKFLOW_WEBHOOK = {
    "name": "Cerebro Operator Intelligence Webhook",
    "nodes": [
        {
            "parameters": {
                "path": "cerebro-operator-intelligence",
                "responseMode": "lastNode",
                "options": {},
            },
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 1.1,
            "position": [0, 220],
            "id": "d5bf37f1-2b1c-4bc8-bf5c-a2bd7d9f0001",
            "name": "Webhook",
            "webhookId": "cerebro-operator-intelligence",
        },
        {
            "parameters": {
                "jsCode": "const body = $json.body || {};\nconst query = $json.query || {};\nconst ticker = String(body.ticker || query.ticker || 'SPY').toUpperCase();\nreturn [{\n  ticker,\n  base_url: String(body.base_url || query.base_url || 'http://127.0.0.1:8000'),\n  requested_by: body.requested_by || query.requested_by || 'n8n-operator',\n}];"
            },
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [240, 220],
            "id": "d5bf37f1-2b1c-4bc8-bf5c-a2bd7d9f0002",
            "name": "Normalize Request",
        },
        {
            "parameters": {
                "url": "={{ $('Normalize Request').item.json.base_url + '/api/ticker/' + $('Normalize Request').item.json.ticker }}",
                "options": {"allowUnauthorizedCerts": True},
            },
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [480, 220],
            "id": "d5bf37f1-2b1c-4bc8-bf5c-a2bd7d9f0003",
            "name": "Fetch Ticker Intelligence",
        },
        {
            "parameters": {
                "jsCode": "return [{\n  workflow_status: 'ticker_intelligence_ready',\n  ticker: $('Normalize Request').item.json.ticker,\n  requested_by: $('Normalize Request').item.json.requested_by,\n  packet: $json,\n}];"
            },
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [720, 220],
            "id": "d5bf37f1-2b1c-4bc8-bf5c-a2bd7d9f0004",
            "name": "Build Operator Packet",
        },
    ],
    "connections": {
        "Webhook": {"main": [[{"node": "Normalize Request", "type": "main", "index": 0}]]},
        "Normalize Request": {"main": [[{"node": "Fetch Ticker Intelligence", "type": "main", "index": 0}]]},
        "Fetch Ticker Intelligence": {"main": [[{"node": "Build Operator Packet", "type": "main", "index": 0}]]},
    },
    "pinData": {},
    "active": False,
    "settings": {"executionOrder": "v1"},
    "versionId": "d5bf37f1-2b1c-4bc8-bf5c-a2bd7d9f0005",
    "id": "cerebro-operator-intelligence-webhook",
    "meta": {"templateCredsSetupCompleted": False},
    "tags": [],
}


MARKETPLACE_ENTRY = {
    "id": "n8n-automation-orchestrator",
    "name": "n8n-automation-orchestrator",
    "category": "automation",
    "version": "0.1.0",
    "source": "/home/operator/.openclaw/workspace/vendor/n8n/n8n",
    "skill_path": "/home/operator/.openclaw/workspace/.agents/skills/n8n-automation-orchestrator",
    "description": "n8n workflow automation lane for Cerebro scanner cadence, verifier gates, operator intelligence, and multimodal agent-pod orchestration.",
}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    for path, content in FILES.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    write_json(ROOT / "ops/n8n/workflows/cerebro_intraday_refresh_gatekeeper.json", WORKFLOW_INTRADAY)
    write_json(ROOT / "ops/n8n/workflows/cerebro_premarket_pipeline.json", WORKFLOW_PREMARKET)
    write_json(ROOT / "ops/n8n/workflows/cerebro_operator_intelligence_webhook.json", WORKFLOW_WEBHOOK)

    marketplace_path = ROOT / ".agents/plugins/marketplace.json"
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    plugins = marketplace.setdefault("plugins", [])
    if not any(item.get("id") == MARKETPLACE_ENTRY["id"] for item in plugins):
        plugins.append(MARKETPLACE_ENTRY)
    marketplace_path.write_text(json.dumps(marketplace, indent=2) + "\n", encoding="utf-8")

    temp_helper = ROOT / "tmp_find_n8n_workflow_examples.py"
    if temp_helper.exists():
        temp_helper.unlink()


if __name__ == "__main__":
    main()
