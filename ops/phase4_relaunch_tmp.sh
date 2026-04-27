#!/usr/bin/env bash
set -euo pipefail

HOST="root@67.205.148.181"

ssh "$HOST" 'ps -ef | awk '"'"'/[p]hase4_long_tail_burnin.py/ {print $2}'"'"' | xargs -r kill || true'

ssh "$HOST" "cd /opt/catalyst && python3 -c \"import json; from datetime import datetime, timezone; from pathlib import Path; from ops.phase4_long_tail_burnin import _sanitize_cache_symbols; p=Path('/opt/catalyst/.long_tail_sector_cache.json'); payload=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {'metadata': {}, 'symbols': {}}; payload['symbols']=_sanitize_cache_symbols(payload); meta=payload.get('metadata'); meta=meta if isinstance(meta, dict) else {}; meta['updated_at']=datetime.now(timezone.utc).isoformat(); meta['cached_symbol_count']=len(payload['symbols']); payload['metadata']=meta; p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8'); print('sanitized_cache_symbols', len(payload['symbols']))\""

ssh "$HOST" 'rm -f /opt/catalyst/memory/phase4_cleanup_results.json /opt/catalyst/memory/phase4_cleanup_status.json /opt/catalyst/logs/phase4_long_tail_burnin.log'

ssh "$HOST" 'cd /opt/catalyst && setsid bash -lc '"'"'nice -n 15 python3 /opt/catalyst/ops/phase4_long_tail_burnin.py --limit 0 --model qwen2:0.5b --write-cache --cooldown-seconds 1.0 --timeout-seconds 20 --max-load1 2.0 --max-mem-used-pct 90.5 --output /opt/catalyst/memory/phase4_cleanup_results.json --status-output /opt/catalyst/memory/phase4_cleanup_status.json --cache /opt/catalyst/.long_tail_sector_cache.json --company-cache /opt/catalyst/.phase4_company_info_cache.json > /opt/catalyst/logs/phase4_long_tail_burnin.log 2>&1 < /dev/null'"'"' >/dev/null 2>&1 &'
