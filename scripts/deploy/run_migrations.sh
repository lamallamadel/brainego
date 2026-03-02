#!/usr/bin/env bash
set -euo pipefail

# Idempotent database migration runner
# Applies only unapplied migrations, logs results, and tracks checksums

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MIGRATIONS_DIR="${REPO_ROOT}/migrations"

# PostgreSQL connection parameters (from environment or defaults)
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:-ai_platform}"
PGUSER="${PGUSER:-ai_user}"
PGPASSWORD="${PGPASSWORD:-ai_password}"

# Git SHA for release tracking
GIT_SHA="${GIT_SHA:-$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo "unknown")}"
LOG_DIR="/opt/brainego/releases/${GIT_SHA}"
LOG_FILE="${LOG_DIR}/migration.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    echo "${timestamp} [${level}] ${message}" | tee -a "${LOG_FILE}"
}

log_info() {
    log "INFO" "$@"
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    log "WARN" "$@"
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    log "ERROR" "$@"
    echo -e "${RED}[ERROR]${NC} $*"
}

# Compute SHA256 checksum of a file
compute_checksum() {
    local file="$1"
    sha256sum "${file}" | awk '{print $1}'
}

# Execute SQL and capture result
execute_sql() {
    local sql="$1"
    PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -t -A -c "${sql}"
}

# Execute SQL file
execute_sql_file() {
    local file="$1"
    PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -f "${file}"
}

# Check if migration version has been applied
is_migration_applied() {
    local version="$1"
    local count
    count=$(execute_sql "SELECT COUNT(*) FROM schema_migrations WHERE version = ${version};")
    [[ "${count}" -gt 0 ]]
}

# Get stored checksum for a migration version
get_stored_checksum() {
    local version="$1"
    execute_sql "SELECT checksum FROM schema_migrations WHERE version = ${version};"
}

# Record migration in schema_migrations table
record_migration() {
    local version="$1"
    local checksum="$2"
    execute_sql "INSERT INTO schema_migrations (version, applied_at, checksum) VALUES (${version}, CURRENT_TIMESTAMP, '${checksum}');"
}

# Bootstrap: ensure schema_migrations table exists
bootstrap_migration_system() {
    log_info "Bootstrapping migration system..."
    
    local bootstrap_file="${MIGRATIONS_DIR}/000_bootstrap.sql"
    
    if [[ ! -f "${bootstrap_file}" ]]; then
        log_error "Bootstrap migration file not found: ${bootstrap_file}"
        exit 1
    fi
    
    # Check if schema_migrations table exists
    local table_exists
    table_exists=$(execute_sql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'schema_migrations';")
    
    if [[ "${table_exists}" -eq 0 ]]; then
        log_info "Creating schema_migrations table..."
        if execute_sql_file "${bootstrap_file}" >> "${LOG_FILE}" 2>&1; then
            log_info "Bootstrap completed successfully"
        else
            log_error "Bootstrap failed"
            exit 1
        fi
    else
        log_info "schema_migrations table already exists"
    fi
}

# Main migration logic
run_migrations() {
    log_info "Starting migration run (SHA: ${GIT_SHA})"
    log_info "Migrations directory: ${MIGRATIONS_DIR}"
    log_info "Database: ${PGDATABASE} on ${PGHOST}:${PGPORT}"
    
    # Find all migration files (excluding bootstrap)
    local migration_files=()
    while IFS= read -r -d '' file; do
        migration_files+=("${file}")
    done < <(find "${MIGRATIONS_DIR}" -name '[0-9][0-9][0-9]_*.sql' -print0 | sort -z)
    
    if [[ ${#migration_files[@]} -eq 0 ]]; then
        log_warn "No migration files found in ${MIGRATIONS_DIR}"
        return 0
    fi
    
    log_info "Found ${#migration_files[@]} migration file(s)"
    
    local applied_count=0
    local skipped_count=0
    local failed=0
    
    for migration_file in "${migration_files[@]}"; do
        local filename
        filename="$(basename "${migration_file}")"
        local version
        version=$(echo "${filename}" | grep -oE '^[0-9]+')
        
        log_info "Processing migration ${version}: ${filename}"
        
        # Check if already applied
        if is_migration_applied "${version}"; then
            local stored_checksum
            stored_checksum=$(get_stored_checksum "${version}")
            local current_checksum
            current_checksum=$(compute_checksum "${migration_file}")
            
            if [[ "${stored_checksum}" != "${current_checksum}" ]]; then
                log_error "Checksum mismatch for migration ${version}!"
                log_error "  Stored:  ${stored_checksum}"
                log_error "  Current: ${current_checksum}"
                log_error "Migration files should never be modified after being applied."
                exit 1
            fi
            
            log_info "Migration ${version} already applied (checksum verified)"
            ((skipped_count++))
            continue
        fi
        
        # Apply migration
        log_info "Applying migration ${version}..."
        local checksum
        checksum=$(compute_checksum "${migration_file}")
        
        if execute_sql_file "${migration_file}" >> "${LOG_FILE}" 2>&1; then
            # Record migration
            if record_migration "${version}" "${checksum}"; then
                log_info "Migration ${version} applied successfully (checksum: ${checksum})"
                ((applied_count++))
            else
                log_error "Failed to record migration ${version} in schema_migrations table"
                failed=1
                break
            fi
        else
            log_error "Failed to apply migration ${version}"
            log_error "Check ${LOG_FILE} for details"
            failed=1
            break
        fi
    done
    
    if [[ ${failed} -eq 1 ]]; then
        log_error "Migration run failed"
        log_error "Applied: ${applied_count}, Skipped: ${skipped_count}"
        return 1
    fi
    
    log_info "Migration run completed successfully"
    log_info "Applied: ${applied_count}, Skipped: ${skipped_count}"
    return 0
}

# Main execution
main() {
    log_info "================================"
    log_info "Database Migration Runner"
    log_info "================================"
    
    # Check prerequisites
    if ! command -v psql &> /dev/null; then
        log_error "psql command not found. Please install PostgreSQL client."
        exit 1
    fi
    
    if [[ ! -d "${MIGRATIONS_DIR}" ]]; then
        log_error "Migrations directory not found: ${MIGRATIONS_DIR}"
        exit 1
    fi
    
    # Bootstrap migration system
    bootstrap_migration_system
    
    # Run migrations
    if run_migrations; then
        log_info "All migrations completed successfully"
        exit 0
    else
        log_error "Migration process failed"
        exit 1
    fi
}

main "$@"
