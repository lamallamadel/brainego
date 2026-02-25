#!/bin/bash
# Manual Backup Script
# Run immediate backup of all databases

set -e

echo "========================================="
echo "Manual Backup - AI Platform"
echo "========================================="
echo ""

# Check if backup service is running
if ! docker ps | grep -q backup-service; then
    echo "Warning: backup-service container not running"
    echo "Starting one-shot backup..."
    docker compose run --rm backup-service python backup_service.py --run-once
else
    echo "Running backup via existing service..."
    docker compose exec backup-service python backup_service.py --run-once
fi

echo ""
echo "========================================="
echo "Backup Complete"
echo "========================================="
echo ""
echo "To list backups, run:"
echo "  python restore_backup.py --list"
echo ""
echo "To validate backups, run:"
echo "  python validate_data_integrity.py"
