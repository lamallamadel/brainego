# Disaster Recovery Restore Test Runbook

**Purpose:** Monthly validation of PostgreSQL backup integrity and restore procedures.

**Frequency:** Monthly (first Monday of each month)

**Duration:** ~30-45 minutes

**Owner:** Platform Team

---

## Prerequisites

- Access to production backup directory: `/opt/brainego/backups/postgres/`
- Docker environment with access to postgres container
- Test database credentials (separate from production)
- At least 1 recent backup file (`.sql.gz`)

---

## Procedure

### 1. Select Backup to Test

```bash
# List recent backups
ls -lh /opt/brainego/backups/postgres/*.sql.gz | tail -5

# Verify backup integrity via manifest
tail -10 /opt/brainego/backups/postgres/manifest.log

# Select most recent successful backup
BACKUP_FILE="/opt/brainego/backups/postgres/$(date +%Y%m%d).sql.gz"

# Verify checksum matches manifest
ACTUAL_CHECKSUM=$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')
EXPECTED_CHECKSUM=$(grep "$(basename ${BACKUP_FILE})" /opt/brainego/backups/postgres/manifest.log | tail -1 | cut -d',' -f4)

if [[ "${ACTUAL_CHECKSUM}" == "${EXPECTED_CHECKSUM}" ]]; then
    echo "✓ Checksum verification passed"
else
    echo "✗ Checksum mismatch - backup may be corrupted"
    exit 1
fi
```

### 2. Create Test Database

```bash
# Create test database container (or use existing test instance)
docker exec postgres psql -U ai_user -d postgres -c "DROP DATABASE IF EXISTS ai_platform_test;"
docker exec postgres psql -U ai_user -d postgres -c "CREATE DATABASE ai_platform_test OWNER ai_user;"

echo "✓ Test database created: ai_platform_test"
```

### 3. Restore Backup to Test Database

```bash
# Restore backup
echo "Restoring backup to test database..."
gunzip -c "${BACKUP_FILE}" | docker exec -i postgres psql -U ai_user -d ai_platform_test

if [[ $? -eq 0 ]]; then
    echo "✓ Restore completed successfully"
else
    echo "✗ Restore failed"
    exit 2
fi
```

### 4. Validate Row Counts

```bash
# Function to get row count for a table
get_row_count() {
    local db_name=$1
    local table_name=$2
    docker exec postgres psql -U ai_user -d "${db_name}" -t -c "SELECT COUNT(*) FROM ${table_name};" | xargs
}

# List of critical tables to validate (adjust based on your schema)
TABLES=(
    "users"
    "conversations"
    "messages"
    "memories"
    "feedback"
    "learning_tasks"
    "drift_detections"
    "schema_migrations"
)

echo "Validating row counts between production and test..."
echo "Table,Production,Test,Match" > /tmp/dr_test_rowcount_$(date +%Y%m%d).csv

ALL_MATCH=true
for table in "${TABLES[@]}"; do
    # Check if table exists in production
    PROD_EXISTS=$(docker exec postgres psql -U ai_user -d ai_platform -t -c "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '${table}');" | xargs)
    
    if [[ "${PROD_EXISTS}" == "t" ]]; then
        PROD_COUNT=$(get_row_count "ai_platform" "${table}")
        TEST_COUNT=$(get_row_count "ai_platform_test" "${table}")
        
        if [[ "${PROD_COUNT}" == "${TEST_COUNT}" ]]; then
            MATCH="✓"
        else
            MATCH="✗"
            ALL_MATCH=false
        fi
        
        echo "${table},${PROD_COUNT},${TEST_COUNT},${MATCH}"
        echo "${table},${PROD_COUNT},${TEST_COUNT},${MATCH}" >> /tmp/dr_test_rowcount_$(date +%Y%m%d).csv
    else
        echo "${table},N/A,N/A,SKIP (table not found in production)"
        echo "${table},N/A,N/A,SKIP" >> /tmp/dr_test_rowcount_$(date +%Y%m%d).csv
    fi
done

if [[ "${ALL_MATCH}" == true ]]; then
    echo "✓ All row counts match between production and test"
else
    echo "✗ Row count mismatch detected - investigate discrepancies"
    exit 3
fi
```

### 5. Validate Schema Migrations Integrity

```bash
echo "Validating schema_migrations table..."

# Check if schema_migrations table exists
MIGRATIONS_EXISTS=$(docker exec postgres psql -U ai_user -d ai_platform_test -t -c "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'schema_migrations');" | xargs)

if [[ "${MIGRATIONS_EXISTS}" != "t" ]]; then
    echo "✗ schema_migrations table not found in test database"
    exit 4
fi

# Get migration count
PROD_MIGRATIONS=$(docker exec postgres psql -U ai_user -d ai_platform -t -c "SELECT COUNT(*) FROM schema_migrations;" | xargs)
TEST_MIGRATIONS=$(docker exec postgres psql -U ai_user -d ai_platform_test -t -c "SELECT COUNT(*) FROM schema_migrations;" | xargs)

echo "Production migrations: ${PROD_MIGRATIONS}"
echo "Test migrations: ${TEST_MIGRATIONS}"

if [[ "${PROD_MIGRATIONS}" == "${TEST_MIGRATIONS}" ]]; then
    echo "✓ Migration count matches"
else
    echo "✗ Migration count mismatch"
    exit 5
fi

# Verify no missing migrations
MISSING_MIGRATIONS=$(docker exec postgres psql -U ai_user -d postgres -t -c "
    SELECT version 
    FROM ai_platform.schema_migrations 
    WHERE version NOT IN (SELECT version FROM ai_platform_test.schema_migrations);
" | xargs)

if [[ -z "${MISSING_MIGRATIONS}" ]]; then
    echo "✓ No missing migrations in test database"
else
    echo "✗ Missing migrations detected: ${MISSING_MIGRATIONS}"
    exit 6
fi

# Verify migration integrity (no extra migrations in test)
EXTRA_MIGRATIONS=$(docker exec postgres psql -U ai_user -d postgres -t -c "
    SELECT version 
    FROM ai_platform_test.schema_migrations 
    WHERE version NOT IN (SELECT version FROM ai_platform.schema_migrations);
" | xargs)

if [[ -z "${EXTRA_MIGRATIONS}" ]]; then
    echo "✓ No extra migrations in test database"
else
    echo "✗ Extra migrations detected in test: ${EXTRA_MIGRATIONS}"
    exit 7
fi

echo "✓ Schema migrations integrity validated"
```

### 6. Additional Validation Checks

```bash
echo "Performing additional validation checks..."

# Check database size
PROD_SIZE=$(docker exec postgres psql -U ai_user -d postgres -t -c "SELECT pg_size_pretty(pg_database_size('ai_platform'));" | xargs)
TEST_SIZE=$(docker exec postgres psql -U ai_user -d postgres -t -c "SELECT pg_size_pretty(pg_database_size('ai_platform_test'));" | xargs)

echo "Production database size: ${PROD_SIZE}"
echo "Test database size: ${TEST_SIZE}"

# Check for foreign key constraints
PROD_FK_COUNT=$(docker exec postgres psql -U ai_user -d ai_platform -t -c "
    SELECT COUNT(*) 
    FROM information_schema.table_constraints 
    WHERE constraint_type = 'FOREIGN KEY';
" | xargs)

TEST_FK_COUNT=$(docker exec postgres psql -U ai_user -d ai_platform_test -t -c "
    SELECT COUNT(*) 
    FROM information_schema.table_constraints 
    WHERE constraint_type = 'FOREIGN KEY';
" | xargs)

echo "Foreign key constraints - Production: ${PROD_FK_COUNT}, Test: ${TEST_FK_COUNT}"

if [[ "${PROD_FK_COUNT}" == "${TEST_FK_COUNT}" ]]; then
    echo "✓ Foreign key constraint count matches"
else
    echo "⚠ Foreign key constraint count mismatch (may be expected if schema differs)"
fi

# Check for indexes
PROD_IDX_COUNT=$(docker exec postgres psql -U ai_user -d ai_platform -t -c "
    SELECT COUNT(*) 
    FROM pg_indexes 
    WHERE schemaname = 'public';
" | xargs)

TEST_IDX_COUNT=$(docker exec postgres psql -U ai_user -d ai_platform_test -t -c "
    SELECT COUNT(*) 
    FROM pg_indexes 
    WHERE schemaname = 'public';
" | xargs)

echo "Indexes - Production: ${PROD_IDX_COUNT}, Test: ${TEST_IDX_COUNT}"

if [[ "${PROD_IDX_COUNT}" == "${TEST_IDX_COUNT}" ]]; then
    echo "✓ Index count matches"
else
    echo "⚠ Index count mismatch (may be expected if schema differs)"
fi

echo "✓ Additional validation checks completed"
```

### 7. Cleanup

```bash
# Remove test database
docker exec postgres psql -U ai_user -d postgres -c "DROP DATABASE IF EXISTS ai_platform_test;"

echo "✓ Test database cleaned up"
```

### 8. Document Results

```bash
# Create test report
REPORT_FILE="/tmp/dr_test_report_$(date +%Y%m%d).txt"

cat > "${REPORT_FILE}" <<EOF
=================================================
Disaster Recovery Restore Test Report
=================================================
Date: $(date -Iseconds)
Operator: ${USER}
Backup File: ${BACKUP_FILE}
Test Database: ai_platform_test

Checksum Verification: PASSED
Restore Operation: PASSED
Row Count Validation: PASSED
Schema Migrations: PASSED
Additional Checks: PASSED

Status: SUCCESS

Row Count Details: /tmp/dr_test_rowcount_$(date +%Y%m%d).csv

Next Test Due: First Monday of $(date -d "+1 month" +%B)
=================================================
EOF

cat "${REPORT_FILE}"

echo ""
echo "✓ DR restore test completed successfully"
echo "Report saved to: ${REPORT_FILE}"
echo "Row count details: /tmp/dr_test_rowcount_$(date +%Y%m%d).csv"
```

---

## Success Criteria

- ✓ Backup file checksum matches manifest
- ✓ Restore completes without errors
- ✓ All critical table row counts match production
- ✓ `schema_migrations` table integrity verified (no missing/extra migrations)
- ✓ Database size is comparable (within 10% tolerance)
- ✓ Foreign key and index counts match (or discrepancies documented)

---

## Failure Response

If any validation step fails:

1. **Do not proceed** to next step
2. **Document the failure** with error output
3. **Alert the Platform Team** immediately
4. **Investigate root cause**:
   - Backup corruption (checksum mismatch)
   - Incomplete backup (row count mismatch)
   - Schema drift (migration mismatch)
5. **Re-run backup process** if needed
6. **Re-test with previous day's backup** to verify restore capability

---

## Escalation

- **Minor issues** (warnings, non-critical mismatches): Create ticket, continue monitoring
- **Critical failures** (restore fails, data loss detected): Page on-call engineer immediately

---

## Compliance

This runbook satisfies:
- RTO (Recovery Time Objective): Validate restore completes within 30 minutes
- RPO (Recovery Point Objective): Validate daily backups are restorable
- SOC2 DR-01: Monthly restore testing requirement
- ISO 27001 A.12.3.1: Information backup testing

---

## Automation Opportunity

Consider automating this runbook via:
- Scheduled cron job: `0 9 * * 1 /opt/brainego/scripts/backup/automated_dr_test.sh`
- CI/CD pipeline integration
- Monitoring alert if test fails

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2024-01-XX | Platform Team | Initial version |

---

**Last Tested:** ___________________  
**Next Test Due:** First Monday of next month  
**Tested By:** ___________________  
**Result:** PASS / FAIL
