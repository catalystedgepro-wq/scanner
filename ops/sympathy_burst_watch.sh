#!/usr/bin/env bash
set -euo pipefail

detect_root() {
  local explicit="${CEREBRO_ROOT:-}"
  local script_root
  script_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  local candidate
  for candidate in \
    "$explicit" \
    "$script_root" \
    "/opt/catalyst" \
    "/home/operator/.openclaw/workspace"
  do
    [[ -n "$candidate" ]] || continue
    [[ -f "$candidate/build_sympathy_logger.py" && -f "$candidate/ops/check_sympathy_burst.py" ]] || continue
    printf '%s\n' "$candidate"
    return 0
  done
  return 1
}

ROOT="$(detect_root)"
cd "$ROOT"

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

STATE_PATH="$ROOT/sympathy_burst_watch_state.json"
ALERT_JSON="$ROOT/sympathy_burst_alert.json"
ALERT_MD="$ROOT/sympathy_burst_alert.md"
FLAG_PATH="$ROOT/sympathy_live_audit_required.flag"
STATUS_PATH="$ROOT/sympathy_burst_status.json"
STAMP_UTC="$(date -u +%FT%TZ)"

echo "[$STAMP_UTC] sympathy_burst_watch: refreshing logger state"
/usr/bin/python3 "$ROOT/build_sympathy_logger.py"

if [[ ! -f "$STATUS_PATH" ]]; then
  echo "[$STAMP_UTC] sympathy_burst_watch: missing $STATUS_PATH after logger refresh" >&2
  exit 1
fi

set +e
/usr/bin/python3 - "$STATUS_PATH" "$STATE_PATH" "$ALERT_JSON" "$ALERT_MD" "$FLAG_PATH" "$STAMP_UTC" <<'PY'
import json
import sys
from pathlib import Path

status_path = Path(sys.argv[1])
state_path = Path(sys.argv[2])
alert_json_path = Path(sys.argv[3])
alert_md_path = Path(sys.argv[4])
flag_path = Path(sys.argv[5])
stamp_utc = sys.argv[6]

status = json.loads(status_path.read_text(encoding="utf-8"))
state = {}
if state_path.exists():
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}

top = status.get("top_sector") or {}
leaders = top.get("leaders") or []
leader_preview = ", ".join(leaders[:3]) if leaders else "none"
signature = "|".join(
    [
        str(status.get("today", "")),
        str(top.get("sector", "none")),
        str(top.get("count", 0)),
        str(status.get("ui_density_mode", "full")),
        ",".join(leaders[:5]),
    ]
)

state.update(
    {
        "last_checked_at": stamp_utc,
        "last_signature": signature,
        "last_active_burst": bool(status.get("active_burst")),
        "last_top_sector": top.get("sector", "none"),
        "last_top_count": int(top.get("count", 0) or 0),
        "last_ui_density_mode": status.get("ui_density_mode", "full"),
        "last_leaders": leaders[:5],
    }
)

if status.get("active_burst"):
    already_alerted = state.get("last_alert_signature") == signature
    title = f"Live Audit Required: {str(top.get('sector', 'unknown')).title()} Sympathy Burst ({int(top.get('count', 0) or 0)} Entities)"
    report = {
        "title": title,
        "priority": "high",
        "generated_at": stamp_utc,
        "bundle": "assets/index-lZQhsETW.js",
        "active_burst": True,
        "sector": top.get("sector", "unknown"),
        "count": int(top.get("count", 0) or 0),
        "ui_density_mode": status.get("ui_density_mode", "full"),
        "leaders": leaders[:5],
        "verification_tasks": [
            "Shield efficacy: confirm suppressed mode hides non-critical sympathy labels while selected and hovered links remain legible.",
            "Frame rate: ensure the active burst does not degrade operator-side HUD smoothness during the particle bleed pass.",
            "Lead clarity: verify the sympathy lead remains clearly distinguished from followers in the NodeInspector.",
        ],
        "recommendation": "Log into the live HUD and perform a visual audit before the market cools.",
    }
    alert_json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    alert_md_path.write_text(
        "\n".join(
            [
                f"# {title}",
                "",
                f"- Priority: High",
                f"- Generated: {stamp_utc}",
                f"- Sector: {report['sector']}",
                f"- Entity Count: {report['count']}",
                f"- UI Density Mode: {report['ui_density_mode']}",
                f"- Leaders: {leader_preview}",
                "",
                "## Verification Tasks",
                "- Shield efficacy: confirm suppressed mode hides non-critical sympathy labels while selected and hovered links remain legible.",
                "- Frame rate: ensure the active burst does not degrade operator-side HUD smoothness during the particle bleed pass.",
                "- Lead clarity: verify the sympathy lead remains clearly distinguished from followers in the NodeInspector.",
                "",
                "## Recommendation",
                "Log into the live HUD and perform a visual audit before the market cools.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    flag_path.write_text(title + "\n", encoding="utf-8")
    if not already_alerted:
        print(f"ALERT {title} | leaders={leader_preview} | mode={status.get('ui_density_mode', 'full')}")
        state["last_alert_signature"] = signature
        state["last_alert_at"] = stamp_utc
        state["last_alert_title"] = title
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        raise SystemExit(10)
    print(f"ACTIVE {title} | leaders={leader_preview} | mode={status.get('ui_density_mode', 'full')}")
else:
    print("OK no active sympathy burst")

state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
PY

exit_code=$?
set -e

if [[ $exit_code -eq 10 ]]; then
  summary="$(/usr/bin/python3 "$ROOT/ops/check_sympathy_burst.py" || true)"
  echo "[$STAMP_UTC] sympathy_burst_watch: $summary"
  logger -t cerebro-sympathy-watch -- "Live Audit Required | $summary"
  exit 0
fi

if [[ $exit_code -ne 0 ]]; then
  logger -t cerebro-sympathy-watch -- "sympathy_burst_watch failed with exit $exit_code"
  exit $exit_code
fi

summary="$(/usr/bin/python3 "$ROOT/ops/check_sympathy_burst.py" || true)"
echo "[$STAMP_UTC] sympathy_burst_watch: $summary"
exit 0
