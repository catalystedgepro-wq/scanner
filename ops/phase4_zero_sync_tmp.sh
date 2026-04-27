#!/usr/bin/env bash
set -euo pipefail

HOST="root@67.205.148.181"

ssh "$HOST" "pgrep -f '[p]hase4_long_tail_burnin.py' | xargs -r kill || true"
ssh "$HOST" "cd /opt/catalyst && python3 /opt/catalyst/ops/phase4_long_tail_burnin.py --limit 0 --model qwen2:0.5b --write-cache --cooldown-seconds 0 --timeout-seconds 20 --max-load1 0 --max-mem-used-pct 0 --output /opt/catalyst/memory/phase4_cleanup_results.json --status-output /opt/catalyst/memory/phase4_cleanup_status.json --cache /opt/catalyst/.long_tail_sector_cache.json --company-cache /opt/catalyst/.phase4_company_info_cache.json"
