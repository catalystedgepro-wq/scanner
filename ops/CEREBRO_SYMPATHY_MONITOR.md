# Cerebro Sympathy Burst Monitor

The droplet-side sympathy monitor is a dedicated five-minute watch lane for live sector-wide sympathy flares.

## Files

- `ops/sympathy_burst_watch.sh`
  - refreshes `build_sympathy_logger.py`
  - reads `sympathy_burst_status.json`
  - writes `sympathy_burst_alert.json`
  - writes `sympathy_burst_alert.md`
  - writes `sympathy_burst_watch_state.json`
  - emits syslog entries via `logger -t cerebro-sympathy-watch`
- `ops/install_sympathy_monitor_cron_droplet.sh`
  - syncs the monitor scripts to the droplet
  - installs `/etc/cron.d/cerebro-sympathy-watch`

## Alert Behavior

- Runs every 5 minutes on weekdays
- Only emits a new alert when the burst signature changes
- Keeps the latest alert artifact in the root app directory
- Uses the same sympathy-density logic the HUD consumes (`full`, `grouped`, `suppressed`)

## Live Audit Artifacts

- `sympathy_burst_status.json`
- `sympathy_burst_alert.json`
- `sympathy_burst_alert.md`
- `logs/sympathy_burst_watch.log`

## Install

```bash
bash /home/operator/.openclaw/workspace/ops/install_sympathy_monitor_cron_droplet.sh
```
