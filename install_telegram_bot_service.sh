#!/usr/bin/env bash
# install_telegram_bot_service.sh
# Installs run_telegram_bot.py as a systemd user service (no root needed).
# The service auto-restarts on crash and survives reboots.
#
# Usage:
#   bash install_telegram_bot_service.sh
#
# To check status:   systemctl --user status catalyst-telegram-bot
# To view logs:      journalctl --user -u catalyst-telegram-bot -f
# To stop:           systemctl --user stop catalyst-telegram-bot
# To disable:        systemctl --user disable catalyst-telegram-bot

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.sec_email_env"
SERVICE_NAME="catalyst-telegram-bot"
SERVICE_DIR="$HOME/.config/systemd/user"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found — cannot read TELEGRAM_BOT_TOKEN"
    exit 1
fi

# Source env file to validate token is present
set -a && source "$ENV_FILE" && set +a
if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN not set in $ENV_FILE"
    exit 1
fi

mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_DIR/$SERVICE_NAME.service" <<EOF
[Unit]
Description=Catalyst Edge Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$(which python3) -u $SCRIPT_DIR/run_telegram_bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

echo "Service file written to $SERVICE_DIR/$SERVICE_NAME.service"

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user start "$SERVICE_NAME"

echo ""
echo "=== Catalyst Edge Telegram Bot is running ==="
echo ""
systemctl --user status "$SERVICE_NAME" --no-pager || true
echo ""
echo "Useful commands:"
echo "  journalctl --user -u $SERVICE_NAME -f       # live logs"
echo "  systemctl --user status $SERVICE_NAME        # status"
echo "  systemctl --user restart $SERVICE_NAME       # restart"
echo "  systemctl --user stop $SERVICE_NAME          # stop"
