# Database Migration System - Quick Start

## TL;DR

```bash
# Run migrations
./scripts/deploy/run_migrations.sh

# Check migration status
psql -h localhost -U ai_user -d ai_platform -c "SELECT * FROM schema_migrations ORDER BY version;"
```

## Structure

```
migrations/
├── 000_bootstrap.sql          # Creates schema_migrations table
├── 001_initial_schema.sql     # Initial schema (feedback, audit, drift, LoRA, jailbreak)
├── 002_add_workspaces.sql     # Workspace and metering tables
└── README.md                  # Full documentation
```

## Running Migrations

### Default (local development)

```bash
./scripts/deploy/run_migrations.sh
```

### Custom database

```bash
export PGHOST=db.example.com
export PGPORT=5432
export PGDATABASE=ai_platform
export PGUSER=ai_user
export PGPASSWORD=your_password

./scripts/deploy/run_migrations.sh
```

### Production deployment

```bash
export GIT_SHA=$(git rev-parse HEAD)
./scripts/deploy/run_migrations.sh || exit 1
```

## Creating New Migrations

### Step 1: Create file

```bash
# Naming: <version>_<description>.sql
touch migrations/003_add_user_settings.sql
```

### Step 2: Write SQL

```sql
-- migrations/003_add_user_settings.sql
CREATE TABLE IF NOT EXISTS user_settings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    settings JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings(user_id);

GRANT ALL PRIVILEGES ON TABLE user_settings TO ai_user;
GRANT ALL PRIVILEGES ON SEQUENCE user_settings_id_seq TO ai_user;
```

### Step 3: Test locally

```bash
./scripts/deploy/run_migrations.sh
```

### Step 4: Commit

```bash
git add migrations/003_add_user_settings.sql
git commit -m "feat: add user_settings table migration"
```

## Migration Status

### Check applied migrations

```sql
SELECT version, applied_at, LEFT(checksum, 8) as checksum_preview
FROM schema_migrations
ORDER BY version;
```

### Check if table exists

```sql
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'your_table_name'
);
```

## Logs

```bash
# View latest migration log
tail -f /opt/brainego/releases/$(git rev-parse HEAD)/migration.log

# View all logs
find /opt/brainego/releases -name migration.log -exec cat {} \;
```

## Troubleshooting

### Checksum mismatch

**Error**: Migration file modified after being applied

**Fix**: Revert changes, create new migration instead

### Connection refused

**Error**: Cannot connect to database

**Fix**: Check `PGHOST`, `PGPORT`, verify database is running

### psql not found

**Error**: Command not found

**Fix**: 
```bash
# Ubuntu/Debian
apt-get install postgresql-client

# macOS
brew install postgresql
```

## Best Practices

✅ **DO**:
- Use `IF NOT EXISTS` for tables and indexes
- Test migrations locally before committing
- Keep migrations small and focused
- Add comments explaining complex logic
- Grant permissions to `ai_user`

❌ **DON'T**:
- Modify applied migrations (create new one instead)
- Use `DROP TABLE` in production migrations
- Skip version numbers
- Put multiple unrelated changes in one migration

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PGHOST` | `localhost` | PostgreSQL host |
| `PGPORT` | `5432` | PostgreSQL port |
| `PGDATABASE` | `ai_platform` | Database name |
| `PGUSER` | `ai_user` | Database user |
| `PGPASSWORD` | `ai_password` | Database password |
| `GIT_SHA` | `git rev-parse HEAD` | Release SHA (for logs) |

## Exit Codes

- **0**: Success
- **1**: Failure (check logs)

## Full Documentation

See `migrations/README.md` and `MIGRATION_SYSTEM.md` for complete details.
