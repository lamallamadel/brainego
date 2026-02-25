#!/bin/bash
# Manual Restore Script
# Interactive script for restoring backups

set -e

echo "========================================="
echo "Manual Restore - AI Platform"
echo "========================================="
echo ""
echo "WARNING: This will restore data from backups"
echo "and may overwrite current data."
echo ""

# Function to list backups
list_backups() {
    echo "Available backups:"
    python restore_backup.py --list
}

# Function to restore specific type
restore_type() {
    local TYPE=$1
    echo ""
    echo "Restoring $TYPE..."
    echo ""
    
    # List available backups
    python restore_backup.py --list --type "$TYPE"
    
    echo ""
    read -p "Enter backup ID (or press Enter for latest): " BACKUP_ID
    
    if [ -z "$BACKUP_ID" ]; then
        python restore_backup.py --type "$TYPE"
    else
        python restore_backup.py --type "$TYPE" --backup-id "$BACKUP_ID"
    fi
    
    echo ""
    echo "$TYPE restore complete!"
}

# Function to restore all
restore_all() {
    echo ""
    echo "Restoring all databases..."
    echo ""
    
    python restore_backup.py --type all
    
    echo ""
    echo "All databases restored!"
}

# Main menu
echo "What would you like to restore?"
echo "1) Qdrant only"
echo "2) Neo4j only"
echo "3) PostgreSQL only"
echo "4) All databases"
echo "5) List backups and exit"
echo "6) Cancel"
echo ""

read -p "Enter choice [1-6]: " CHOICE

case $CHOICE in
    1)
        restore_type "qdrant"
        ;;
    2)
        restore_type "neo4j"
        ;;
    3)
        restore_type "postgres"
        ;;
    4)
        restore_all
        ;;
    5)
        list_backups
        exit 0
        ;;
    6)
        echo "Cancelled"
        exit 0
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "========================================="
echo "Restore Complete"
echo "========================================="
echo ""
echo "Running validation..."
python validate_data_integrity.py

echo ""
echo "Please verify services are working:"
echo "  docker compose ps"
echo "  docker compose logs -f"
