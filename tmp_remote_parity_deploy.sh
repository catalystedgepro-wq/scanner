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

printf 'EVEROS_ENABLED='
grep '^EVEROS_ENABLED=' "$ENV_FILE" | tail -n 1 | cut -d= -f2-

python3 -m py_compile /opt/catalyst/api_server.py

systemctl restart cerebro
sleep 3

if ! systemctl is-active --quiet cerebro; then
  systemctl status cerebro --no-pager -n 60
  exit 1
fi

printf '\nhealth:\n'
curl -fsS http://127.0.0.1:8000/api/health

printf '\n\n---\nBRRW:\n'
curl -fsS http://127.0.0.1:8000/api/ticker/BRRW | head -c 900

printf '\n\n---\nVLDX:\n'
curl -fsS http://127.0.0.1:8000/api/ticker/VLDX | head -c 900
printf '\n'
