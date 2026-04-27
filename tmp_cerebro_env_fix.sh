set -euo pipefail
python3 - <<'PY'
from pathlib import Path
Path("/home/operator/.openclaw/workspace/.env").write_text("EVEROS_ENABLED=0\n", encoding="utf-8")
PY
od -An -tx1 -c /home/operator/.openclaw/workspace/.env
bash /home/operator/.openclaw/workspace/ops/check_mnemosyne_lanes.sh --mode runtime
