#!/usr/bin/env bash
# pull_digital_updates.sh — Lightweight git pull for digital velocity updates.
# Runs every hour on the droplet to pick up spark_velocities.json pushes
# from the residential Windows machine running spoke_digital.py.
# Add to crontab: 15 * * * * /opt/catalyst/pull_digital_updates.sh

set -euo pipefail
cd /opt/catalyst

# Stash any pipeline-generated changes before pulling
git stash --quiet 2>/dev/null || true
git pull --rebase origin main --quiet 2>/dev/null && \
  echo "$(date '+%F %T') digital_pull_ok" >> /opt/catalyst/digital_pull.log || \
  echo "$(date '+%F %T') digital_pull_failed" >> /opt/catalyst/digital_pull.log
git stash pop --quiet 2>/dev/null || true
