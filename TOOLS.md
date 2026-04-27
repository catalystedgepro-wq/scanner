# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

### SSH

- `cerebro` -> `67.205.148.181`, user `root`

### Cerebro Deploy

- Runtime/API root: `/home/operator/.openclaw/workspace`
- Full scanner pipeline root: `/opt/catalyst`
- Systemd service: `cerebro.service`
- Repeatable deploy script: [ops/deploy_cerebro_droplet.sh](/home/operator/.openclaw/workspace/ops/deploy_cerebro_droplet.sh)
- Sympathy burst cron installer: [ops/install_sympathy_monitor_cron_droplet.sh](/home/operator/.openclaw/workspace/ops/install_sympathy_monitor_cron_droplet.sh)
