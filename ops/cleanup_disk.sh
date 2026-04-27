#!/usr/bin/env bash
# cleanup_disk.sh — droplet hygiene to keep the catalyst pipeline alive.
#
# Targets the disk hogs found 2026-04-27 audit:
#   /opt/catalyst/social/*.mp4    (1GB of TikTok video archive)
#   /var/log/journal              (121MB systemd journal)
#   /var/log/catalyst.log         (27MB cron output, never rotated)
#   /var/log/sec_catalyst.log     (28MB)
#   entity_master.json.bak-junk-* (12MB stale backup)
#   sec_outcome_rows_*.csv        (~1.5MB/day × forever)
#
# Idempotent — safe to run multiple times. Designed for cron + manual.
#
# Usage:
#   bash /opt/catalyst/ops/cleanup_disk.sh           # full cleanup
#   bash /opt/catalyst/ops/cleanup_disk.sh --dry-run # preview
set -euo pipefail

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1
say() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] cleanup_disk: $*"; }
do_or_say() {
  if [[ $DRY -eq 1 ]]; then
    say "DRY: $*"
  else
    eval "$@"
  fi
}

ROOT="${CATALYST_ROOT:-/opt/catalyst}"
say "starting (root=$ROOT dry=$DRY)"
say "before: $(df -h "$ROOT" | tail -1)"

# 1. Social video archive — keep last 7 days of mp4, prune older.
SOCIAL="$ROOT/social"
if [[ -d "$SOCIAL" ]]; then
  count=$(find "$SOCIAL" -type f \( -name '*.mp4' -o -name '*.mov' \) -mtime +7 2>/dev/null | wc -l)
  say "social: pruning $count videos older than 7 days"
  do_or_say "find '$SOCIAL' -type f \\( -name '*.mp4' -o -name '*.mov' \\) -mtime +7 -delete 2>/dev/null || true"
fi

# 2. Stale entity_master backup — single .bak-junk-* file, 12MB.
junk_count=$(find "$ROOT" -maxdepth 1 -name 'entity_master.json.bak-junk-*' 2>/dev/null | wc -l)
if [[ $junk_count -gt 0 ]]; then
  say "deleting $junk_count stale entity_master backup(s)"
  do_or_say "find '$ROOT' -maxdepth 1 -name 'entity_master.json.bak-junk-*' -delete 2>/dev/null || true"
fi

# 3. sec_outcome_rows_*.csv — keep last 60 days, archive older to gzip.
ARCHIVE_DIR="$ROOT/archive/outcomes"
[[ $DRY -eq 0 ]] && mkdir -p "$ARCHIVE_DIR"
old_outcomes=$(find "$ROOT" -maxdepth 1 -name 'sec_outcome_rows_*.csv' -mtime +60 2>/dev/null | wc -l)
say "outcomes: gzipping $old_outcomes archive CSVs older than 60 days"
if [[ $old_outcomes -gt 0 && $DRY -eq 0 ]]; then
  find "$ROOT" -maxdepth 1 -name 'sec_outcome_rows_*.csv' -mtime +60 \
    -exec gzip -f {} \; \
    -exec mv {}.gz "$ARCHIVE_DIR/" \; 2>/dev/null || true
fi

# 4. Daily list-files (sec_clean_gappers_*.csv etc) — same 60-day rule.
for pattern in 'sec_clean_*.csv' 'sec_top_*.csv' 'sec_catalyst_*.csv'; do
  old=$(find "$ROOT" -maxdepth 1 -name "$pattern" -mtime +60 2>/dev/null | wc -l)
  [[ $old -eq 0 ]] && continue
  say "pruning $old files matching $pattern older than 60 days"
  do_or_say "find '$ROOT' -maxdepth 1 -name '$pattern' -mtime +60 -delete 2>/dev/null || true"
done

# 5. Logs — truncate, keep tail.
LOG_KEEP_LINES=2000
for log in /var/log/catalyst.log /var/log/sec_catalyst.log /var/log/catalyst_loop.log; do
  [[ ! -f "$log" ]] && continue
  size=$(stat -c %s "$log" 2>/dev/null || echo 0)
  if [[ $size -gt 5242880 ]]; then  # 5MB
    say "rotating $log (was $((size/1024/1024))MB)"
    if [[ $DRY -eq 0 ]]; then
      tail -n "$LOG_KEEP_LINES" "$log" > "${log}.tmp" && mv "${log}.tmp" "$log"
    fi
  fi
done

# 6. systemd journal — vacuum to 7 days.
if command -v journalctl >/dev/null 2>&1; then
  say "vacuuming journal to 7 days"
  do_or_say "journalctl --vacuum-time=7d 2>&1 | tail -2"
fi

# 7. apt cache (defensive — not always present in catalyst flows).
if command -v apt-get >/dev/null 2>&1; then
  do_or_say "apt-get clean 2>/dev/null || true"
fi

# 8. .bak file sweep across catalyst root (older than 30 days).
old_baks=$(find "$ROOT" -maxdepth 2 -name '*.bak' -mtime +30 2>/dev/null | wc -l)
if [[ $old_baks -gt 0 ]]; then
  say "deleting $old_baks .bak files older than 30 days"
  do_or_say "find '$ROOT' -maxdepth 2 -name '*.bak' -mtime +30 -delete 2>/dev/null || true"
fi

say "after:  $(df -h "$ROOT" | tail -1)"
say "done"
