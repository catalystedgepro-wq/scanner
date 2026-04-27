#!/bin/bash
# memory_backup.sh — Weekly Cerebro Memory Bank backup
#
# Compresses .cerebro_memory.db into a dated archive and keeps the last 4 copies.
# No S3 required — runs locally on the droplet, safe against accidental data loss.
#
# Add to S3/DO Spaces later by un-commenting the aws/s3cmd block at the bottom.
#
# Cron (every Sunday 02:00 server time):
#   0 2 * * 0 /bin/bash /opt/catalyst/memory_backup.sh >> /var/log/cerebro_backup.log 2>&1

set -euo pipefail

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DB_PATH="/opt/catalyst/.cerebro_memory.db"
BACKUP_DIR="/opt/catalyst/backups"
ARCHIVE="${BACKUP_DIR}/cerebro_memory_${TIMESTAMP}.tar.gz"
KEEP=4   # number of weekly backups to retain

echo "=== [${TIMESTAMP}] Cerebro Memory Backup ==="

mkdir -p "${BACKUP_DIR}"

# 1. Verify the database exists and is non-empty
if [[ ! -f "${DB_PATH}" ]]; then
    echo "WARN: ${DB_PATH} not found — nothing to back up."
    exit 0
fi

DB_SIZE=$(du -sh "${DB_PATH}" | cut -f1)
echo "  Source: ${DB_PATH} (${DB_SIZE})"

# 2. Compress into a dated archive
tar -czf "${ARCHIVE}" -C "$(dirname "${DB_PATH}")" "$(basename "${DB_PATH}")"
ARCHIVE_SIZE=$(du -sh "${ARCHIVE}" | cut -f1)
echo "  Archive: ${ARCHIVE} (${ARCHIVE_SIZE})"

# 3. Rotate — delete oldest archives beyond KEEP limit
EXISTING=$(ls -t "${BACKUP_DIR}"/cerebro_memory_*.tar.gz 2>/dev/null | wc -l)
if (( EXISTING > KEEP )); then
    ls -t "${BACKUP_DIR}"/cerebro_memory_*.tar.gz | tail -n +$((KEEP + 1)) | xargs rm -f
    echo "  Rotated: kept ${KEEP} most recent backups"
fi

# 4. Log row count from the database
ROW_COUNT=$(python3 -c "
import sqlite3, sys
try:
    conn = sqlite3.connect('${DB_PATH}')
    n = conn.execute('SELECT COUNT(*) FROM velocity_sparks').fetchone()[0]
    print(n)
    conn.close()
except: print('unknown')
" 2>/dev/null)
echo "  Rows backed up: ${ROW_COUNT}"

# ── Optional: push to DigitalOcean Spaces or AWS S3 ──────────────────────────
# Uncomment and configure when ready to add off-site redundancy:
#
# S3_BUCKET="s3://cerebro-data-vault/backups/"
# if command -v aws &>/dev/null; then
#     aws s3 cp "${ARCHIVE}" "${S3_BUCKET}"
#     echo "  Pushed to: ${S3_BUCKET}"
# elif command -v s3cmd &>/dev/null; then
#     s3cmd put "${ARCHIVE}" "${S3_BUCKET}"
#     echo "  Pushed to: ${S3_BUCKET}"
# else
#     echo "  NOTE: Install aws-cli or s3cmd for off-site backup"
# fi

echo "  ✅ Backup complete"
