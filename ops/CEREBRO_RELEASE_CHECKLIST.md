# Cerebro Release Checklist

Use this checklist for any production release that touches Cerebro backend, HUD assets, memory bridges, or automation workflows.

## 1. Mnemosyne Release Gate

Run the local memory-lane check before staging anything:

```bash
bash ops/check_mnemosyne_lanes.sh --mode release
```

This must pass before release.

It confirms:

- EverOS skill wrapper is present
- MSA skill wrapper is present
- EverOS runtime bridge files are present
- policy/integration docs are present
- vendored EverOS/MSA repos still exist locally

## 2. Stage To Droplet Without Restart

```bash
bash ops/deploy_cerebro_droplet.sh --stage-only
```

This should:

- sync backend and `docs/hud/`
- sync Mnemosyne policy + skill wrapper surfaces
- confirm production `EVEROS_ENABLED=0`
- confirm the remote runtime-facing Mnemosyne lane is intact

## 3. Atomic Restart

```bash
bash ops/deploy_cerebro_droplet.sh --restart-only
```

This should:

- re-check `EVEROS_ENABLED`
- re-check the remote Mnemosyne runtime surface
- restart `cerebro.service`
- verify public health and the current live ranked canary set

## 4. Browser Truth Check

After restart, confirm one real operator path in the live HUD:

- search one same-day ranked Scanner symbol from the live feed
- confirm the NodeInspector opens
- confirm the parity bridge state is clear

## 5. Memory Lane Rules

- Do not flip `EVEROS_ENABLED` during unrelated parity/UI releases.
- EverOS must remain deploy-visible even when production memory is pinned off.
- MSA must remain project-visible even when it is not in the live runtime path.

## 6. n8n Gate

Before enabling or editing live automation workflows, the Mnemosyne gate should be present in the n8n pod:

- [check_mnemosyne_lanes.sh](/home/operator/.openclaw/workspace/ops/check_mnemosyne_lanes.sh)
- [cerebro_mnemosyne_gate.json](/home/operator/.openclaw/workspace/ops/n8n/workflows/cerebro_mnemosyne_gate.json)

This keeps automation from silently drifting away from the permanent memory architecture.
