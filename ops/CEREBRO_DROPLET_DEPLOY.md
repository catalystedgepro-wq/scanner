# Cerebro Droplet Deploy

This is the repeatable deploy path for the DigitalOcean Cerebro droplet.

## Current Production Targets

- SSH host alias: `cerebro`
- Hostname: `67.205.148.181`
- Runtime/API root: `/home/operator/.openclaw/workspace`
- Full scanner pipeline root: `/opt/catalyst`
- Systemd service: `cerebro.service`
- Public HUD/API base URL: `http://67.205.148.181`

## Why This Exists

The parity rollout exposed a trust problem:

- Scanner picks could be real
- the HUD could still fail to find them
- the fix depended on a manual, memory-driven push

This script turns that rollout into a repeatable operator path so the team can stage, verify, restart, and confirm parity without reconstructing the steps from chat history.

## Script

- [deploy_cerebro_droplet.sh](/home/operator/.openclaw/workspace/ops/deploy_cerebro_droplet.sh)

## What It Does

### Stage

- auto-detects live remote roots instead of assuming only one
- syncs backend files to both the runtime root and the legacy scanner root when both exist
- syncs compiled `docs/hud/` assets to each live root
- does not restart when you use `--stage-only`

### Environment Guard

- checks the live droplet for `EVEROS_ENABLED`
- fails if production is not pinned to `0`

### Mnemosyne Gate

- checks the local release surface for permanent EverOS/MSA coverage
- syncs the Mnemosyne policy and skill wrapper surfaces to the droplet
- checks the remote runtime-facing Mnemosyne surface before restart

### Atomic Restart

- compiles remote `api_server.py`
- restarts `cerebro.service`
- fails fast if systemd does not come back active

### Public Verification

- checks `GET /api/health`
- reads the live HUD bundle reference from `/`
- derives live canaries from the current ranked/public feed and verifies them through `GET /api/ticker/:ticker`

## Common Usage

### Full Deploy

```bash
bash ops/deploy_cerebro_droplet.sh
```

### Stage Only

```bash
bash ops/deploy_cerebro_droplet.sh --stage-only
```

### Restart + Verify Only

```bash
bash ops/deploy_cerebro_droplet.sh --restart-only
```

### Verify the Current Live Canary Set

```bash
bash ops/deploy_cerebro_droplet.sh --verify-only
```

### Probe Manual Tickers Too

```bash
bash ops/deploy_cerebro_droplet.sh --verify-only --verify-ticker <current-ranked-ticker> --verify-ticker <secondary-live-ticker>
```

## Release Checklist

- [CEREBRO_RELEASE_CHECKLIST.md](/home/operator/.openclaw/workspace/ops/CEREBRO_RELEASE_CHECKLIST.md)

## Current Canary Guidance

- Let the deploy helper derive the primary live canaries from the current ranked/public feed.
- Use `--verify-ticker` only as an extra manual probe when you already know the symbol is still live.

## Notes

- This script verifies backend rescue/parity through the public API.
- A live browser audit is still the right final check for command-search UX and target lock behavior.
- The deploy helper now includes explicit Mnemosyne checks so EverOS/MSA stay part of the release system even when production memory is pinned off.
- The droplet currently has split-brain filesystem history: the API service runs from the workspace root, while the fully hydrated scanner pipeline still lives in `/opt/catalyst`.
- The deploy helper is now root-aware so it can stage both surfaces without relying on memory or chat history.
