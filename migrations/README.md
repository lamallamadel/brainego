# Database Migration System

Idempotent, forward-only database migration system for brainego.

## Overview

This migration system provides:
- **Versioned migrations**: Sequential numbered SQL scripts
- **Idempotency**: Safe to run multiple times (only unapplied migrations run)
- **Checksum verification**: Detects if applied migrations have been modified
- **Logging**: All migration activity logged to `/opt/brainego/releases/<sha>/migration.log`
- **Forward-only**: No down migrations (production safety)

## File Structure

```
migrations/
├── 000_bootstrap.sql          # Creates schema_migrations table
├── 001_initial_schema.sql     # Initial database schema
├── 002_add_workspaces.sql     # Workspace and metering tables
└── README.md                  # This file
```

## Running Migrations

### Manual execution

```bash
cd /path/to/brainego
./scripts/deploy/run_migrations.sh
```

### Environment Variables

Configure PostgreSQL connection:

```bash
export PGHOST=localhost         # Default: localhost
export PGPORT=5432             # Default: 5432
export PGDATABASE=ai_platform  # Default: ai_platform
export PGUSER=ai_user          # Default: ai_user
export PGPASSWORD=ai_password  # Default: ai_password
export GIT_SHA=$(git rev-parse HEAD)  # Optional: for log directory
```

### Deployment Integration

Add to your deployment scripts:

```bash
# Before starting application
./scripts/deploy/run_migrations.sh || exit 1
```

## Migration Workflow

### 1. Bootstrap (000_bootstrap.sql)

Creates the `schema_migrations` table:

```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE NOT NULL,
    checksum TEXT NOT NULL
);
```

### 2. Apply Migrations

The runner:
1. Finds all `[0-9][0-9][0-9]_*.sql` files in `migrations/`
2. Checks `schema_migrations` for applied versions
3. Verifies checksums of applied migrations
4. Applies unapplied migrations in order
5. Records each migration with checksum

### 3. Checksum Verification

If a migration file is modified after being applied:
- **Error**: Checksum mismatch detected
- **Action**: Migration fails with non-zero exit
- **Fix**: Never modify applied migrations; create new migration instead

## Creating New Migrations

### Naming Convention

```
<version>_<description>.sql
```

- **version**: 3-digit zero-padded number (e.g., 003, 004, 010)
- **description**: Snake_case description

Examples:
- `003_add_user_preferences.sql`
- `004_create_cache_tables.sql`
- `010_add_performance_indexes.sql`

### Template

```sql
-- Description of what this migration does

-- Create tables
CREATE TABLE IF NOT EXISTS example_table (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_example_name ON example_table(name);

-- Grant permissions
GRANT ALL PRIVILEGES ON TABLE example_table TO ai_user;
GRANT ALL PRIVILEGES ON SEQUENCE example_table_id_seq TO ai_user;
```

### Best Practices

1. **Use IF NOT EXISTS**: Make migrations idempotent
2. **No destructive changes**: Never DROP tables in production migrations
3. **Test offline first**: Validate SQL syntax before committing
4. **Sequential versions**: Don't skip version numbers
5. **Atomic operations**: Each migration should be a complete, atomic change

## Logs

Migration logs are stored in:

```
/opt/brainego/releases/<git-sha>/migration.log
```

Example log output:

```
2025-03-02T23:15:00Z [INFO] ================================
2025-03-02T23:15:00Z [INFO] Database Migration Runner
2025-03-02T23:15:00Z [INFO] ================================
2025-03-02T23:15:00Z [INFO] Bootstrapping migration system...
2025-03-02T23:15:01Z [INFO] schema_migrations table already exists
2025-03-02T23:15:01Z [INFO] Starting migration run (SHA: abc123...)
2025-03-02T23:15:01Z [INFO] Found 2 migration file(s)
2025-03-02T23:15:01Z [INFO] Processing migration 001: 001_initial_schema.sql
2025-03-02T23:15:01Z [INFO] Migration 001 already applied (checksum verified)
2025-03-02T23:15:01Z [INFO] Processing migration 002: 002_add_workspaces.sql
2025-03-02T23:15:01Z [INFO] Applying migration 002...
2025-03-02T23:15:02Z [INFO] Migration 002 applied successfully (checksum: def456...)
2025-03-02T23:15:02Z [INFO] Migration run completed successfully
2025-03-02T23:15:02Z [INFO] Applied: 1, Skipped: 1
```

## Troubleshooting

### Migration fails with "checksum mismatch"

**Cause**: Migration file was modified after being applied

**Solution**:
1. Revert changes to the migration file
2. Create a new migration with the desired changes

### Migration fails with "psql: command not found"

**Cause**: PostgreSQL client not installed

**Solution**:
```bash
# Debian/Ubuntu
apt-get install -y postgresql-client

# RHEL/CentOS
yum install -y postgresql
```

### Migration fails with connection error

**Cause**: Incorrect connection parameters

**Solution**: Verify environment variables:
```bash
echo $PGHOST $PGPORT $PGDATABASE $PGUSER
```

## Schema Migrations Table

Query applied migrations:

```sql
SELECT version, applied_at, checksum
FROM schema_migrations
ORDER BY version;
```

Example output:

```
 version |         applied_at         |                           checksum
---------+----------------------------+--------------------------------------------------------------
       1 | 2025-03-02 23:10:00+00     | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
       2 | 2025-03-02 23:15:00+00     | d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2d2
```

## Exit Codes

- **0**: Success (all migrations applied)
- **1**: Failure (migration error, checksum mismatch, connection error)

## Integration with CI/CD

### Docker Entrypoint

```dockerfile
COPY scripts/deploy/run_migrations.sh /usr/local/bin/
COPY migrations/ /opt/brainego/migrations/

ENTRYPOINT ["/usr/local/bin/run_migrations.sh"]
```

### Kubernetes Init Container

```yaml
initContainers:
- name: migrate
  image: brainego:latest
  command: ["/scripts/deploy/run_migrations.sh"]
  env:
  - name: PGHOST
    value: postgres
  - name: PGDATABASE
    value: ai_platform
```

## Notes

- Migrations are **forward-only** (no rollback support)
- Always test migrations in staging before production
- Keep migrations small and focused
- Document breaking changes in migration comments
