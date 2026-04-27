#!/usr/bin/env bash
# install_discord_bot_service.sh
# Installs run_discord_bot.py as a systemd user service.
#
# Usage:   bash install_discord_bot_service.sh
# Logs:    journalctl --user -u catalyst-discord-bot -f
# Stop:    systemctl --user stop catalyst-discord-bot

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.sec_email_env"
SERVICE_NAME="catalyst-discord-bot"
SERVICE_DIR="$HOME/.config/systemd/user"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found"
    exit 1
fi

set -a && source "$ENV_FILE" && set +a
if [[ -z "${DISCORD_BOT_TOKEN:-}" ]]; then
    echo "ERROR: DISCORD_BOT_TOKEN not set in $ENV_FILE"
    echo "  Add it after creating a bot at: discord.com/developers/applications"
    exit 1
fi

mkdir -p "$SERVICE_DIR"

cat > "$SERVICE_DIR/$SERVICE_NAME.service" <<EOF
[Unit]
Description=Catalyst Edge Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
EnvironmentFile=$ENV_FILE
ExecStart=/usr/bin/python3 -u $SCRIPT_DIR/run_discord_bot.py
Restart=always
RestartSec=15
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user start "$SERVICE_NAME"

echo ""
echo "=== Catalyst Edge Discord Bot is running ==="
systemctl --user status "$SERVICE_NAME" --no-pager || true
echo ""
echo "  journalctl --user -u $SERVICE_NAME -f    # live logs"
echo "  systemctl --user restart $SERVICE_NAME   # restart"
echo "  systemctl --user stop $SERVICE_NAME      # stop"
