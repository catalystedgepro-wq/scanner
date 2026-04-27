#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="/opt/catalyst/.env"

if [[ -f "$ENV_FILE" ]]; then
  if grep -q '^EVEROS_ENABLED=' "$ENV_FILE"; then
    sed -i 's/^EVEROS_ENABLED=.*/EVEROS_ENABLED=0/' "$ENV_FILE"
  else
    printf '\nEVEROS_ENABLED=0\n' >> "$ENV_FILE"
  fi
else
  printf 'EVEROS_ENABLED=0\n' > "$ENV_FILE"
fi

mkdir -p /opt/catalyst/docs/hud

python3 -m py_compile \
  /opt/catalyst/api_server.py \
  /opt/catalyst/everos_memory_client.py \
  /opt/catalyst/build_sympathy_logger.py \
  /opt/catalyst/velocity_deck_schema.py

systemctl restart cerebro
sleep 2

printf 'cerebro_status='
systemctl is-active cerebro

printf '\nhealth:\n'
curl -s http://127.0.0.1:8000/api/health

printf '\n---\nai_summary:\n'
curl -s http://127.0.0.1:8000/api/ai-summary/CAR

printf '\n---\nbriefing:\n'
curl -s http://127.0.0.1:8000/api/briefing
