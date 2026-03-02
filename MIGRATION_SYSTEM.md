# Database Migration System Implementation

## Overview

Implemented an idempotent, forward-only database migration system for brainego with versioned SQL scripts, checksum verification, and comprehensive logging.

## Components Created

### 1. Migration Directory Structure

```
migrations/
├── 000_bootstrap.sql          # Creates schema_migrations tracking table
├── 001_initial_schema.sql     # Initial schema (moved from init.sql)
├── 002_add_workspaces.sql     # Workspace and metering tables
└── README.md                  # Complete migration documentation
```

### 2. Migration Runner Script

**File**: `scripts/deploy/run_migrations.sh`

**Features**:
- Idempotent execution (safe to run multiple times)
- Checksum verification (detects modified migrations)
- Sequential version application
- Comprehensive logging to `/opt/brainego/releases/<sha>/migration.log`
- Non-zero exit on failure
- Bootstrap support (auto-creates schema_migrations table)

**Environment Variables**:
```bash
PGHOST=localhost         # PostgreSQL host
PGPORT=5432             # PostgreSQL port
PGDATABASE=ai_platform  # Database name
PGUSER=ai_user          # Database user
PGPASSWORD=ai_password  # Database password
GIT_SHA=<sha>           # Release SHA for logging
```

### 3. Schema Tracking Table

**Table**: `schema_migrations`

```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE NOT NULL,
    checksum TEXT NOT NULL
);
```

**Purpose**: Tracks which migrations have been applied and their checksums

### 4. Migration Files

#### 000_bootstrap.sql
- Creates `schema_migrations` table
- Grants permissions to `ai_user`
- Always runs first (if table doesn't exist)

#### 001_initial_schema.sql
Content moved from `init-scripts/postgres/init.sql`:
- `feedback` table (AI feedback collection)
- `audit_events` table (structured audit logs)
- `drift_metrics`, `finetuning_triggers`, `drift_incidents` (drift monitoring)
- `lora_adapters`, `lora_performance` (LoRA tracking)
- `adversarial_test_results`, `safety_judge_results` (jailbreak testing)
- Materialized views and functions
- All indexes and triggers

#### 002_add_workspaces.sql
- `workspaces` table (tenant lifecycle management)
- `workspace_metering_events` table (metering and billing)
- Indexes for efficient querying
- Triggers for `updated_at` timestamps

## Migration Workflow

### Step-by-Step Process

1. **Bootstrap** (first run only):
   ```bash
   # Creates schema_migrations table if it doesn't exist
   ./scripts/deploy/run_migrations.sh
   ```

2. **Check Applied Migrations**:
   ```bash
   # Queries schema_migrations for existing versions
   # Computes checksums of migration files
   # Verifies checksums match stored values
   ```

3. **Apply Unapplied Migrations**:
   ```bash
   # Finds all [0-9][0-9][0-9]_*.sql files
   # Sorts by version number
   # Applies only unapplied migrations
   # Records each with checksum
   ```

4. **Logging**:
   ```bash
   # All operations logged to:
   # /opt/brainego/releases/<sha>/migration.log
   ```

### Running Migrations

**Manual execution**:
```bash
cd /path/to/brainego
./scripts/deploy/run_migrations.sh
```

**With environment variables**:
```bash
export PGHOST=db.example.com
export PGPORT=5432
export PGDATABASE=ai_platform
export PGUSER=ai_user
export PGPASSWORD=secure_password
export GIT_SHA=$(git rev-parse HEAD)

./scripts/deploy/run_migrations.sh
```

**In deployment scripts**:
```bash
# Pre-deployment migration
./scripts/deploy/run_migrations.sh || exit 1

# Start application
docker-compose up -d
```

## Key Features

### Idempotency

✅ **Safe to run multiple times**
- Already-applied migrations are skipped
- Checksums verified on each run
- No duplicate table/index creation (uses `IF NOT EXISTS`)

### Checksum Verification

✅ **Detects modified migrations**
- SHA256 checksum computed for each migration file
- Stored in `schema_migrations` table
- Compared on each run
- **Fails with error** if mismatch detected

Example error:
```
[ERROR] Checksum mismatch for migration 001!
[ERROR]   Stored:  e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
[ERROR]   Current: d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2
[ERROR] Migration files should never be modified after being applied.
```

### Comprehensive Logging

✅ **All activity logged**

Log location: `/opt/brainego/releases/<sha>/migration.log`

Example log:
```
2025-03-02T23:15:00Z [INFO] ================================
2025-03-02T23:15:00Z [INFO] Database Migration Runner
2025-03-02T23:15:00Z [INFO] ================================
2025-03-02T23:15:00Z [INFO] Bootstrapping migration system...
2025-03-02T23:15:01Z [INFO] Creating schema_migrations table...
2025-03-02T23:15:01Z [INFO] Bootstrap completed successfully
2025-03-02T23:15:01Z [INFO] Starting migration run (SHA: abc123...)
2025-03-02T23:15:01Z [INFO] Found 2 migration file(s)
2025-03-02T23:15:01Z [INFO] Processing migration 001: 001_initial_schema.sql
2025-03-02T23:15:01Z [INFO] Applying migration 001...
2025-03-02T23:15:02Z [INFO] Migration 001 applied successfully (checksum: e3b0c44...)
2025-03-02T23:15:02Z [INFO] Processing migration 002: 002_add_workspaces.sql
2025-03-02T23:15:02Z [INFO] Applying migration 002...
2025-03-02T23:15:03Z [INFO] Migration 002 applied successfully (checksum: d2d2d2...)
2025-03-02T23:15:03Z [INFO] Migration run completed successfully
2025-03-02T23:15:03Z [INFO] Applied: 2, Skipped: 0
```

### Forward-Only

✅ **No down migrations**
- Production-safe approach
- Backward-incompatible changes require new migrations
- No accidental data loss from rollbacks

### Exit Codes

- **0**: Success (all migrations applied)
- **1**: Failure (migration error, checksum mismatch, connection error)

## Creating New Migrations

### Naming Convention

```
<version>_<description>.sql
```

- **version**: 3-digit zero-padded (e.g., 003, 004, 010)
- **description**: Snake_case description

**Examples**:
- `003_add_user_preferences.sql`
- `004_create_cache_tables.sql`
- `010_add_performance_indexes.sql`

### Template

```sql
-- Description of what this migration does

-- Create tables
CREATE TABLE IF NOT EXISTS example_table (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_example_name ON example_table(name);

-- Grant permissions
GRANT ALL PRIVILEGES ON TABLE example_table TO ai_user;
GRANT ALL PRIVILEGES ON SEQUENCE example_table_id_seq TO ai_user;
```

### Best Practices

1. **Use `IF NOT EXISTS`**: Makes migrations idempotent
2. **No destructive changes**: Never `DROP` tables in production
3. **Test offline**: Validate SQL syntax before committing
4. **Sequential versions**: Don't skip version numbers
5. **Atomic operations**: Each migration = one logical change
6. **Document changes**: Add comments explaining complex logic

## Backward Compatibility

### init-scripts/postgres/init.sql

**Status**: Kept for backward compatibility

The original `init.sql` file has been updated with a deprecation notice but **remains functional** for:
- Existing Docker Compose setups
- Local development environments
- Backward compatibility with older deployments

**Recommendation**: New deployments should use `run_migrations.sh` instead.

## Integration Examples

### Docker Entrypoint

```dockerfile
# Dockerfile
COPY scripts/deploy/run_migrations.sh /usr/local/bin/
COPY migrations/ /opt/brainego/migrations/

ENTRYPOINT ["/usr/local/bin/run_migrations.sh"]
```

### Kubernetes Init Container

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: brainego-api
spec:
  template:
    spec:
      initContainers:
      - name: migrate
        image: brainego:latest
        command: ["/scripts/deploy/run_migrations.sh"]
        env:
        - name: PGHOST
          value: postgres.default.svc.cluster.local
        - name: PGDATABASE
          value: ai_platform
        - name: PGUSER
          valueFrom:
            secretKeyRef:
              name: postgres-credentials
              key: username
        - name: PGPASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-credentials
              key: password
```

### CI/CD Pipeline

```yaml
# .github/workflows/deploy.yml
- name: Run Database Migrations
  run: |
    export PGHOST=${{ secrets.PGHOST }}
    export PGDATABASE=ai_platform
    export PGUSER=${{ secrets.PGUSER }}
    export PGPASSWORD=${{ secrets.PGPASSWORD }}
    export GIT_SHA=${{ github.sha }}
    
    ./scripts/deploy/run_migrations.sh || exit 1
```

## Troubleshooting

### Checksum Mismatch

**Problem**: Migration file modified after being applied

**Solution**:
1. Revert changes to the migration file
2. Create a new migration with the desired changes

### Connection Error

**Problem**: Cannot connect to PostgreSQL

**Solution**: Verify environment variables:
```bash
echo "Host: $PGHOST"
echo "Port: $PGPORT"
echo "Database: $PGDATABASE"
echo "User: $PGUSER"
```

### psql Not Found

**Problem**: PostgreSQL client not installed

**Solution**:
```bash
# Debian/Ubuntu
apt-get install -y postgresql-client

# RHEL/CentOS
yum install -y postgresql
```

## Querying Migration Status

```sql
-- List all applied migrations
SELECT version, applied_at, checksum
FROM schema_migrations
ORDER BY version;

-- Check if specific migration applied
SELECT EXISTS(
    SELECT 1 FROM schema_migrations WHERE version = 1
) AS is_applied;
```

## Summary

✅ **Implemented**:
- `migrations/` directory with versioned SQL scripts
- `000_bootstrap.sql` (creates `schema_migrations` table)
- `001_initial_schema.sql` (content from `init.sql`)
- `002_add_workspaces.sql` (workspace tables)
- `scripts/deploy/run_migrations.sh` (idempotent runner)
- Checksum verification
- Comprehensive logging to `/opt/brainego/releases/<sha>/migration.log`
- Forward-only migrations (no down migrations)
- Exit codes (0 = success, 1 = failure)
- Complete documentation (`migrations/README.md`)

✅ **Updated**:
- `.gitignore` (migration log exclusion)
- `init-scripts/postgres/init.sql` (deprecation notice)

✅ **Key Features**:
- Idempotent (safe to run multiple times)
- Checksum verification (detects modifications)
- Sequential application (maintains order)
- Production-ready (comprehensive error handling)
- Well-documented (README + inline comments)
