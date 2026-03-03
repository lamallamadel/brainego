#!/usr/bin/env bash
set -euo pipefail

# Daily PostgreSQL Backup Script
# Runs pg_dump via docker exec, stores backups with 30-day retention
# Logs metadata (size, checksum, timestamp) to manifest.log

# Configuration
BACKUP_DIR="/opt/brainego/backups/postgres"
MANIFEST_LOG="${BACKUP_DIR}/manifest.log"
RETENTION_DAYS=30
TIMESTAMP=$(date +%Y%m%d)
BACKUP_FILE="${BACKUP_DIR}/${TIMESTAMP}.sql.gz"
CONTAINER_NAME="postgres"
DB_USER="ai_user"
DB_NAME="ai_platform"

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

# Initialize manifest log if it doesn't exist
if [[ ! -f "${MANIFEST_LOG}" ]]; then
    echo "timestamp,filename,size_bytes,checksum_sha256,status" > "${MANIFEST_LOG}"
fi

# Function to log to manifest
log_manifest() {
    local timestamp="$1"
    local filename="$2"
    local size="$3"
    local checksum="$4"
    local status="$5"
    echo "${timestamp},${filename},${size},${checksum},${status}" >> "${MANIFEST_LOG}"
}

# Function to cleanup old backups
cleanup_old_backups() {
    echo "Cleaning up backups older than ${RETENTION_DAYS} days..."
    find "${BACKUP_DIR}" -name "*.sql.gz" -type f -mtime +${RETENTION_DAYS} -delete
    echo "Cleanup complete"
}

# Main backup process
echo "Starting PostgreSQL backup at $(date)"
echo "Backup file: ${BACKUP_FILE}"

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "ERROR: Container ${CONTAINER_NAME} is not running" >&2
    log_manifest "$(date -Iseconds)" "${TIMESTAMP}.sql.gz" "0" "NONE" "FAILED_CONTAINER_NOT_RUNNING"
    exit 1
fi

# Perform backup via docker exec
if ! docker exec "${CONTAINER_NAME}" pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "${BACKUP_FILE}"; then
    echo "ERROR: pg_dump failed" >&2
    log_manifest "$(date -Iseconds)" "${TIMESTAMP}.sql.gz" "0" "NONE" "FAILED_PG_DUMP"
    # Remove incomplete backup file if it exists
    rm -f "${BACKUP_FILE}"
    exit 2
fi

# Verify backup file was created and has content
if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "ERROR: Backup file was not created" >&2
    log_manifest "$(date -Iseconds)" "${TIMESTAMP}.sql.gz" "0" "NONE" "FAILED_FILE_NOT_CREATED"
    exit 3
fi

BACKUP_SIZE=$(stat -c%s "${BACKUP_FILE}" 2>/dev/null || stat -f%z "${BACKUP_FILE}" 2>/dev/null)
if [[ "${BACKUP_SIZE}" -eq 0 ]]; then
    echo "ERROR: Backup file is empty" >&2
    log_manifest "$(date -Iseconds)" "${TIMESTAMP}.sql.gz" "${BACKUP_SIZE}" "NONE" "FAILED_EMPTY_FILE"
    rm -f "${BACKUP_FILE}"
    exit 4
fi

# Calculate checksum
echo "Calculating checksum..."
CHECKSUM=$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')

# Log successful backup to manifest
log_manifest "$(date -Iseconds)" "${TIMESTAMP}.sql.gz" "${BACKUP_SIZE}" "${CHECKSUM}" "SUCCESS"

echo "Backup completed successfully"
echo "  Size: ${BACKUP_SIZE} bytes"
echo "  Checksum: ${CHECKSUM}"

# Cleanup old backups
cleanup_old_backups

echo "Backup process finished at $(date)"
exit 0
