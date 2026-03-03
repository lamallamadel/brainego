#!/bin/bash
set -euo pipefail

# deploy_vm.sh - Versioned release deployment for brainego
# Deploys to /opt/brainego/releases/<git_sha>/ with symlink to /opt/brainego/current
# Target: ≤30s downtime or measure/log actual downtime

# Configuration
DEPLOY_ROOT="${DEPLOY_ROOT:-/opt/brainego}"
RELEASES_DIR="${DEPLOY_ROOT}/releases"
CURRENT_SYMLINK="${DEPLOY_ROOT}/current"
ENV_FILE="${ENV_FILE:-${DEPLOY_ROOT}/env/prod.env}"
DEPLOYMENT_LOG="${DEPLOY_ROOT}/logs/deployment.log"
DOWNTIME_LOG="${DEPLOY_ROOT}/logs/downtime.log"
ROLLBACK_LOG="${DEPLOY_ROOT}/logs/rollback.log"
AUDIT_DIR="${DEPLOY_ROOT}/audit"
SKIP_SMOKE_LOG="${AUDIT_DIR}/skip-smoke.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] ${message}" | tee -a "${DEPLOYMENT_LOG}"
}

log_info() {
    log "INFO" "${BLUE}$@${NC}"
}

log_success() {
    log "SUCCESS" "${GREEN}$@${NC}"
}

log_warn() {
    log "WARN" "${YELLOW}$@${NC}"
}

log_error() {
    log "ERROR" "${RED}$@${NC}"
}

# Record downtime
record_downtime() {
    local action=$1
    local duration=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "${timestamp},${action},${duration}" >> "${DOWNTIME_LOG}"
}

# Measure command execution time
measure_time() {
    local start_time=$(date +%s.%N)
    "$@"
    local exit_code=$?
    local end_time=$(date +%s.%N)
    local duration=$(echo "$end_time - $start_time" | bc)
    echo "$duration"
    return $exit_code
}

# Send Slack notification
send_slack_notification() {
    local message=$1
    local color=${2:-"warning"}  # default to warning
    local webhook_url="${SLACK_WEBHOOK_URL:-}"
    
    if [[ -z "$webhook_url" ]]; then
        log_warn "SLACK_WEBHOOK_URL not set, skipping Slack notification"
        return 0
    fi
    
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local hostname=$(hostname)
    
    local payload=$(cat <<EOF
{
    "attachments": [
        {
            "color": "${color}",
            "title": "Deployment Alert - ${hostname}",
            "text": "${message}",
            "footer": "brainego deployment",
            "ts": $(date +%s)
        }
    ]
}
EOF
)
    
    if curl -X POST -H 'Content-type: application/json' \
        --data "${payload}" \
        --max-time 5 \
        "${webhook_url}" &> /dev/null; then
        log_info "Slack notification sent successfully"
    else
        log_warn "Failed to send Slack notification (non-critical)"
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if running as root or with sudo
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root or with sudo"
        exit 1
    fi
    
    # Check for required commands
    local required_cmds=("docker" "docker-compose" "git" "bc" "python3" "curl")
    for cmd in "${required_cmds[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            log_error "Required command not found: $cmd"
            exit 1
        fi
    done
    
    # Check if env file exists
    if [[ ! -f "${ENV_FILE}" ]]; then
        log_error "Environment file not found: ${ENV_FILE}"
        exit 1
    fi
    
    # Create necessary directories
    mkdir -p "${RELEASES_DIR}"
    mkdir -p "${DEPLOY_ROOT}/logs"
    mkdir -p "${DEPLOY_ROOT}/env"
    mkdir -p "${AUDIT_DIR}"
    
    log_success "Prerequisites check passed"
}

# Validate git SHA
validate_sha() {
    local sha=$1
    if [[ ! "$sha" =~ ^[0-9a-f]{7,40}$ ]]; then
        log_error "Invalid git SHA format: $sha"
        exit 1
    fi
}

# Get current deployed version
get_current_version() {
    if [[ -L "${CURRENT_SYMLINK}" ]]; then
        basename $(readlink -f "${CURRENT_SYMLINK}")
    else
        echo "none"
    fi
}

# Get previous deployed version
get_previous_version() {
    local current=$(get_current_version)
    if [[ "$current" == "none" ]]; then
        echo "none"
        return
    fi
    
    # Find the second most recent deployment
    local versions=$(ls -t "${RELEASES_DIR}" 2>/dev/null || true)
    local prev_version=""
    local found_current=false
    
    for version in $versions; do
        if [[ "$found_current" == true ]]; then
            prev_version="$version"
            break
        fi
        if [[ "$version" == "$current" ]]; then
            found_current=true
        fi
    done
    
    if [[ -z "$prev_version" ]]; then
        echo "none"
    else
        echo "$prev_version"
    fi
}

# Mark release as failed in metadata file
mark_release_failed() {
    local sha=$1
    local reason=$2
    local metadata_file="${RELEASES_DIR}/${sha}/.release_metadata"
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    cat > "${metadata_file}" << EOF
status=failed
reason=${reason}
failed_at=${timestamp}
sha=${sha}
EOF
    
    log_error "Release ${sha} marked as failed: ${reason}"
    log_error "Metadata saved to: ${metadata_file}"
}

# Mark release as successful in metadata file
mark_release_success() {
    local sha=$1
    local metadata_file="${RELEASES_DIR}/${sha}/.release_metadata"
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    cat > "${metadata_file}" << EOF
status=success
deployed_at=${timestamp}
sha=${sha}
EOF
    
    log_success "Release ${sha} marked as successful"
}

# Log skip-smoke decision to audit trail
log_skip_smoke() {
    local sha=$1
    local reason=$2
    local actor=${3:-$(whoami)}
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    local audit_entry="${timestamp}|${sha}|${actor}|${reason}"
    
    echo "${audit_entry}" >> "${SKIP_SMOKE_LOG}"
    
    log_warn "RISK ACCEPTED: Smoke tests skipped for ${sha}"
    log_warn "Reason: ${reason}"
    log_warn "Actor: ${actor}"
    log_warn "Audit logged to: ${SKIP_SMOKE_LOG}"
}

# Run smoke tests
run_smoke_tests() {
    local sha=$1
    local release_dir=$2
    local smoke_script="${release_dir}/scripts/deploy/prod_smoke_tests.py"
    local smoke_log="${DEPLOY_ROOT}/logs/smoke_tests_${sha}.log"
    
    log_info "Running post-deployment smoke tests..."
    
    # Check if smoke test script exists
    if [[ ! -f "${smoke_script}" ]]; then
        log_error "Smoke test script not found: ${smoke_script}"
        return 1
    fi
    
    # Determine base URL (fallback to localhost if not set)
    local base_url="${SMOKE_TEST_BASE_URL:-http://localhost:8000}"
    local workspace_id="${SMOKE_TEST_WORKSPACE_ID:-default}"
    local auth_token="${SMOKE_TEST_AUTH_TOKEN:-}"
    
    log_info "Smoke test configuration:"
    log_info "  Base URL: ${base_url}"
    log_info "  Workspace ID: ${workspace_id}"
    log_info "  Log file: ${smoke_log}"
    
    # Build smoke test command
    local smoke_cmd=(
        python3 "${smoke_script}"
        --base-url "${base_url}"
        --workspace-id "${workspace_id}"
    )
    
    # Add optional parameters
    if [[ -n "${auth_token}" ]]; then
        smoke_cmd+=(--auth-token "${auth_token}")
    fi
    
    if [[ -n "${PROMETHEUS_URL:-}" ]]; then
        smoke_cmd+=(--prometheus-url "${PROMETHEUS_URL}")
    fi
    
    if [[ -n "${KONG_ADMIN_URL:-}" ]]; then
        smoke_cmd+=(--kong-admin-url "${KONG_ADMIN_URL}")
    fi
    
    # Run smoke tests
    if "${smoke_cmd[@]}" > "${smoke_log}" 2>&1; then
        log_success "Smoke tests passed"
        log_info "Smoke test log: ${smoke_log}"
        return 0
    else
        local exit_code=$?
        log_error "Smoke tests failed with exit code: ${exit_code}"
        log_error "Smoke test log: ${smoke_log}"
        
        # Show last 30 lines of smoke test output
        log_error "Smoke test failures (last 30 lines):"
        tail -n 30 "${smoke_log}" | while IFS= read -r line; do
            log_error "  ${line}"
        done
        
        return 1
    fi
}

# Perform rollback due to smoke test failure
perform_smoke_rollback() {
    local failed_sha=$1
    local previous_sha=$2
    local failure_reason=$3
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    log_error "=" * 70
    log_error "INITIATING AUTO-ROLLBACK DUE TO SMOKE TEST FAILURE"
    log_error "=" * 70
    log_error "Failed release: ${failed_sha}"
    log_error "Rolling back to: ${previous_sha}"
    log_error "Reason: ${failure_reason}"
    log_error ""
    
    # Log rollback to audit trail
    local rollback_entry="${timestamp}|${failed_sha}|${previous_sha}|smoke_test_failure|${failure_reason}"
    echo "${rollback_entry}" >> "${ROLLBACK_LOG}"
    
    # Restore symlink to previous release
    local previous_dir="${RELEASES_DIR}/${previous_sha}"
    
    if [[ ! -d "${previous_dir}" ]]; then
        log_error "Previous release directory not found: ${previous_dir}"
        log_error "CRITICAL: Cannot rollback - manual intervention required!"
        mark_release_failed "${failed_sha}" "rollback_failed_no_previous_release"
        return 1
    fi
    
    log_info "Stopping services from failed release ${failed_sha}..."
    cd "${CURRENT_SYMLINK}"
    docker-compose -f docker-compose.yaml down --remove-orphans || true
    
    log_info "Restoring symlink to previous release ${previous_sha}..."
    local temp_symlink="${CURRENT_SYMLINK}.rollback_tmp"
    ln -sfn "${previous_dir}" "${temp_symlink}"
    mv -Tf "${temp_symlink}" "${CURRENT_SYMLINK}"
    
    log_info "Restarting services from previous release..."
    cd "${CURRENT_SYMLINK}"
    export IMAGE_TAG="${previous_sha}"
    
    if docker-compose -f docker-compose.yaml restart; then
        log_success "Services restarted successfully"
        
        # Wait for services to stabilize
        log_info "Waiting for services to stabilize..."
        sleep 10
        
        # Verify services are running
        if docker-compose -f docker-compose.yaml ps | grep -q "Up"; then
            log_success "Rollback completed successfully"
            log_success "Active release: ${previous_sha}"
            
            # Mark failed release in metadata
            mark_release_failed "${failed_sha}" "smoke_test_failure_auto_rollback"
            
            # Log successful rollback
            local success_entry="${timestamp}|${failed_sha}|${previous_sha}|rollback_success"
            echo "${success_entry}" >> "${ROLLBACK_LOG}"
            
            return 0
        else
            log_error "Services failed to start after rollback"
            log_error "CRITICAL: Manual intervention required!"
            return 1
        fi
    else
        log_error "Failed to restart services after rollback"
        log_error "CRITICAL: Manual intervention required!"
        return 1
    fi
}

# Run migrations as preflight step
run_preflight_migrations() {
    local sha=$1
    local release_dir=$2
    local migration_script="${release_dir}/scripts/deploy/run_migrations.sh"
    local migration_log="${release_dir}/migration_preflight.log"
    
    log_info "Checking for migration script at: ${migration_script}"
    
    if [[ ! -f "${migration_script}" ]]; then
        log_warn "Migration script not found - skipping migrations"
        return 0
    fi
    
    log_info "Executing migrations for release ${sha}..."
    
    # Set environment for migration script
    export GIT_SHA="${sha}"
    
    # Capture both stdout and stderr
    if bash "${migration_script}" > "${migration_log}" 2>&1; then
        log_success "Migrations completed successfully"
        
        # Extract and log applied migration versions
        local applied_versions=$(grep -E "Migration [0-9]+ applied successfully" "${migration_log}" | grep -oE "Migration [0-9]+" | awk '{print $2}' || echo "")
        if [[ -n "${applied_versions}" ]]; then
            log_info "Applied migration versions: ${applied_versions}"
        else
            log_info "No new migrations applied (all up to date)"
        fi
        
        # Log migration summary
        local migration_summary=$(grep -E "Applied: [0-9]+, Skipped: [0-9]+" "${migration_log}" | tail -n 1 || echo "")
        if [[ -n "${migration_summary}" ]]; then
            log_info "Migration summary: ${migration_summary}"
        fi
        
        return 0
    else
        local exit_code=$?
        log_error "Migration execution failed with exit code: ${exit_code}"
        
        # Extract failed migration version from log
        local failed_version=$(grep -E "Failed to apply migration [0-9]+" "${migration_log}" | grep -oE "migration [0-9]+" | awk '{print $2}' | head -n 1 || echo "unknown")
        log_error "Failed migration version: ${failed_version}"
        
        # Log stderr content (last 20 lines)
        log_error "Migration error details (last 20 lines):"
        tail -n 20 "${migration_log}" | while IFS= read -r line; do
            log_error "  ${line}"
        done
        
        # Save detailed error to metadata
        local error_summary="Migration ${failed_version} failed. See ${migration_log} for full details."
        log_error "${error_summary}"
        
        # Create extended metadata with migration failure details
        local metadata_file="${RELEASES_DIR}/${sha}/.release_metadata"
        local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
        
        cat > "${metadata_file}" << EOF
status=failed
reason=migration_failed
failed_at=${timestamp}
sha=${sha}
migration_version=${failed_version}
migration_log=${migration_log}
error_summary=${error_summary}
EOF
        
        return 1
    fi
}

# Deploy a specific version
deploy() {
    local sha=$1
    local skip_smoke=${2:-false}
    local skip_reason=${3:-""}
    local skip_actor=${4:-$(whoami)}
    
    validate_sha "$sha"
    
    check_prerequisites
    
    local release_dir="${RELEASES_DIR}/${sha}"
    local current_version=$(get_current_version)
    local previous_version=$(get_previous_version)
    
    log_info "Starting deployment of version: ${sha}"
    log_info "Current version: ${current_version}"
    log_info "Previous version: ${previous_version}"
    
    # Check if release already exists
    if [[ -d "${release_dir}" ]]; then
        log_warn "Release ${sha} already exists at ${release_dir}"
        log_info "Redeploying existing release..."
    else
        log_info "Creating new release directory: ${release_dir}"
        mkdir -p "${release_dir}"
        
        # Clone/copy the repository at the specific SHA
        # Assuming the script is run from the repo or git is available
        if [[ -d ".git" ]]; then
            log_info "Copying repository files for ${sha}..."
            # Create a clean export of the SHA
            git archive "${sha}" | tar -x -C "${release_dir}"
        else
            log_error "Not in a git repository. Cannot deploy SHA ${sha}"
            exit 1
        fi
    fi
    
    # Copy environment file
    log_info "Copying environment configuration..."
    cp "${ENV_FILE}" "${release_dir}/.env"
    
    # Build Docker images with tagged versions (no latest)
    log_info "Building Docker images for ${sha}..."
    cd "${release_dir}"
    
    # Export image tag for docker-compose
    export IMAGE_TAG="${sha}"
    
    # Pull/build images
    if ! docker-compose -f docker-compose.yaml build --no-cache; then
        log_error "Failed to build Docker images"
        exit 1
    fi
    
    # Tag images with SHA
    log_info "Tagging images with version ${sha}..."
    docker-compose -f docker-compose.yaml config --services | while read service; do
        local image_name=$(docker-compose -f docker-compose.yaml config | grep -A 5 "^  ${service}:" | grep "image:" | awk '{print $2}')
        if [[ -n "$image_name" ]] && [[ "$image_name" != *"${sha}"* ]]; then
            docker tag "${image_name}" "${image_name}:${sha}"
        fi
    done
    
    # Run migrations as preflight step
    log_info "Running database migrations as preflight step..."
    if ! run_preflight_migrations "${sha}" "${release_dir}"; then
        log_error "Migration preflight check failed - deployment aborted"
        mark_release_failed "${sha}" "migration_failed"
        exit 1
    fi
    
    # Measure downtime
    log_info "Stopping current services and starting new version..."
    log_warn "Beginning service switchover - downtime measurement starting"
    
    local downtime_duration=$(measure_time perform_switchover "${sha}" "${current_version}")
    
    log_success "Switchover complete. Downtime: ${downtime_duration}s"
    record_downtime "deploy:${sha}" "${downtime_duration}"
    
    # Check if downtime exceeded target
    if (( $(echo "$downtime_duration > 30" | bc -l) )); then
        log_warn "⚠️  DOWNTIME EXCEEDED TARGET: ${downtime_duration}s > 30s"
    else
        log_success "✓ Downtime within target: ${downtime_duration}s ≤ 30s"
    fi
    
    # Health check
    log_info "Performing health checks..."
    if ! health_check; then
        log_error "Health check failed. Consider rollback."
        mark_release_failed "${sha}" "health_check_failed"
        exit 1
    fi
    
    # Run smoke tests (post-deploy hook)
    if [[ "${skip_smoke}" == "true" ]]; then
        log_warn "=" * 70
        log_warn "SMOKE TESTS SKIPPED - RISK ACCEPTED"
        log_warn "=" * 70
        
        # Log skip decision to audit trail
        log_skip_smoke "${sha}" "${skip_reason}" "${skip_actor}"
        
        # Send Slack warning
        local slack_msg="⚠️ DEPLOYMENT WARNING: Smoke tests skipped for release ${sha}\nReason: ${skip_reason}\nActor: ${skip_actor}\nHost: $(hostname)\n\n⚠️ This deployment has NOT been validated via smoke tests."
        send_slack_notification "${slack_msg}" "warning"
        
        log_warn "Proceeding without smoke test validation"
    else
        log_info "=" * 70
        log_info "POST-DEPLOY HOOK: Running Smoke Tests"
        log_info "=" * 70
        
        if ! run_smoke_tests "${sha}" "${release_dir}"; then
            log_error "=" * 70
            log_error "SMOKE TESTS FAILED - INITIATING AUTO-ROLLBACK"
            log_error "=" * 70
            
            # Attempt automatic rollback
            if [[ "${previous_version}" != "none" ]]; then
                if perform_smoke_rollback "${sha}" "${previous_version}" "smoke_tests_failed"; then
                    log_error "Deployment FAILED and ROLLED BACK to ${previous_version}"
                    log_error "Review smoke test logs before redeploying"
                    
                    # Send Slack alert
                    local slack_msg="🚨 DEPLOYMENT FAILED: Release ${sha} failed smoke tests and was auto-rolled back to ${previous_version}\nHost: $(hostname)\n\nAction required: Review smoke test logs and fix issues before redeploying."
                    send_slack_notification "${slack_msg}" "danger"
                    
                    exit 1
                else
                    log_error "=" * 70
                    log_error "CRITICAL: ROLLBACK FAILED!"
                    log_error "=" * 70
                    log_error "Deployment failed AND rollback failed"
                    log_error "Manual intervention required immediately"
                    
                    # Send critical Slack alert
                    local slack_msg="🔥 CRITICAL: Deployment ${sha} failed smoke tests AND rollback failed\nHost: $(hostname)\n\n⚠️ IMMEDIATE ACTION REQUIRED - System may be unstable!"
                    send_slack_notification "${slack_msg}" "danger"
                    
                    exit 1
                fi
            else
                log_error "No previous version available for rollback"
                mark_release_failed "${sha}" "smoke_test_failed_no_rollback"
                
                # Send Slack alert
                local slack_msg="🚨 DEPLOYMENT FAILED: Release ${sha} failed smoke tests\nHost: $(hostname)\n\nNo previous version available for rollback. Manual intervention required."
                send_slack_notification "${slack_msg}" "danger"
                
                exit 1
            fi
        fi
        
        log_success "Smoke tests passed - deployment validated"
    fi
    
    # Mark release as successful
    mark_release_success "${sha}"
    
    log_success "=" * 70
    log_success "Deployment of ${sha} completed successfully!"
    log_success "=" * 70
    log_info "Release directory: ${release_dir}"
    log_info "Current symlink: ${CURRENT_SYMLINK} -> ${release_dir}"
    
    # Send success notification to Slack
    local success_msg="✅ DEPLOYMENT SUCCESS: Release ${sha} deployed and validated\nHost: $(hostname)\nPrevious: ${previous_version}"
    send_slack_notification "${success_msg}" "good"
}

# Perform the actual switchover
perform_switchover() {
    local new_sha=$1
    local old_version=$2
    local new_release_dir="${RELEASES_DIR}/${new_sha}"
    
    # Stop old services if they exist
    if [[ -L "${CURRENT_SYMLINK}" ]] && [[ -d "${CURRENT_SYMLINK}" ]]; then
        cd "${CURRENT_SYMLINK}"
        docker-compose -f docker-compose.yaml down --remove-orphans || true
    fi
    
    # Update symlink atomically
    local temp_symlink="${CURRENT_SYMLINK}.tmp"
    ln -sfn "${new_release_dir}" "${temp_symlink}"
    mv -Tf "${temp_symlink}" "${CURRENT_SYMLINK}"
    
    # Start new services
    cd "${CURRENT_SYMLINK}"
    export IMAGE_TAG="${new_sha}"
    docker-compose -f docker-compose.yaml up -d
    
    # Wait for critical services to be ready
    sleep 5
}

# Health check
health_check() {
    local max_attempts=30
    local attempt=0
    
    log_info "Waiting for services to be healthy..."
    
    cd "${CURRENT_SYMLINK}"
    
    while [[ $attempt -lt $max_attempts ]]; do
        local all_healthy=true
        
        # Check docker-compose services health
        local services=$(docker-compose -f docker-compose.yaml ps --services 2>/dev/null || echo "")
        
        for service in $services; do
            local health=$(docker-compose -f docker-compose.yaml ps "$service" 2>/dev/null | grep "$service" | grep -o "healthy\|unhealthy\|starting" || echo "unknown")
            
            if [[ "$health" != "healthy" ]] && [[ "$health" != "unknown" ]]; then
                all_healthy=false
                break
            fi
        done
        
        if [[ "$all_healthy" == true ]]; then
            log_success "All services are healthy"
            return 0
        fi
        
        attempt=$((attempt + 1))
        sleep 2
    done
    
    log_error "Services failed to become healthy after ${max_attempts} attempts"
    return 1
}

# Show deployment status
status() {
    log_info "=== Deployment Status ==="
    
    local current_version=$(get_current_version)
    local previous_version=$(get_previous_version)
    
    echo ""
    echo "Current version: ${current_version}"
    if [[ -L "${CURRENT_SYMLINK}" ]]; then
        echo "Current path: $(readlink -f ${CURRENT_SYMLINK})"
        local current_metadata="${RELEASES_DIR}/${current_version}/.release_metadata"
        if [[ -f "${current_metadata}" ]]; then
            echo "Current release metadata:"
            cat "${current_metadata}" | sed 's/^/  /'
        fi
    fi
    
    echo "Previous version: ${previous_version}"
    
    echo ""
    echo "Available releases:"
    for release_dir in $(ls -t "${RELEASES_DIR}" 2>/dev/null); do
        local metadata_file="${RELEASES_DIR}/${release_dir}/.release_metadata"
        if [[ -f "${metadata_file}" ]]; then
            local status=$(grep "^status=" "${metadata_file}" | cut -d'=' -f2)
            echo "  ${release_dir} [${status}]"
        else
            echo "  ${release_dir} [no metadata]"
        fi
    done
    
    echo ""
    if [[ -d "${CURRENT_SYMLINK}" ]]; then
        echo "Running services:"
        cd "${CURRENT_SYMLINK}"
        docker-compose -f docker-compose.yaml ps
    else
        echo "No services currently running"
    fi
    
    echo ""
    echo "Recent downtime log (last 10 entries):"
    if [[ -f "${DOWNTIME_LOG}" ]]; then
        tail -n 10 "${DOWNTIME_LOG}" | column -t -s ','
    else
        echo "  No downtime records"
    fi
    
    echo ""
    echo "Recent rollback log (last 10 entries):"
    if [[ -f "${ROLLBACK_LOG}" ]]; then
        echo "Timestamp|Failed SHA|Restored SHA|Trigger|Reason" | column -t -s '|'
        tail -n 10 "${ROLLBACK_LOG}" | column -t -s '|'
    else
        echo "  No rollback records"
    fi
    
    echo ""
    echo "Smoke test skip audit (last 10 entries):"
    if [[ -f "${SKIP_SMOKE_LOG}" ]]; then
        echo "Timestamp|SHA|Actor|Reason" | column -t -s '|'
        tail -n 10 "${SKIP_SMOKE_LOG}" | column -t -s '|'
    else
        echo "  No skip-smoke records"
    fi
}

# Rollback to a previous version
rollback() {
    local target_version=$1
    
    check_prerequisites
    
    local current_version=$(get_current_version)
    
    if [[ "$target_version" == "previous" ]]; then
        target_version=$(get_previous_version)
        if [[ "$target_version" == "none" ]]; then
            log_error "No previous version available for rollback"
            exit 1
        fi
        log_info "Rolling back to previous version: ${target_version}"
    else
        validate_sha "$target_version"
        log_info "Rolling back to specified version: ${target_version}"
    fi
    
    local target_dir="${RELEASES_DIR}/${target_version}"
    
    if [[ ! -d "${target_dir}" ]]; then
        log_error "Target version ${target_version} not found at ${target_dir}"
        exit 1
    fi
    
    if [[ "$target_version" == "$current_version" ]]; then
        log_warn "Target version ${target_version} is already current"
        exit 0
    fi
    
    log_warn "Rolling back from ${current_version} to ${target_version}"
    
    # Measure rollback downtime
    local downtime_duration=$(measure_time perform_switchover "${target_version}" "${current_version}")
    
    log_success "Rollback complete. Downtime: ${downtime_duration}s"
    record_downtime "rollback:${target_version}" "${downtime_duration}"
    
    # Health check
    log_info "Performing health checks..."
    if ! health_check; then
        log_error "Health check failed after rollback"
        exit 1
    fi
    
    log_success "Rollback to ${target_version} completed successfully!"
}

# Show logs for a service
logs() {
    local service=$1
    local lines=${2:-100}
    
    if [[ ! -L "${CURRENT_SYMLINK}" ]] || [[ ! -d "${CURRENT_SYMLINK}" ]]; then
        log_error "No current deployment found"
        exit 1
    fi
    
    cd "${CURRENT_SYMLINK}"
    
    if [[ -z "$service" ]]; then
        log_info "Showing logs for all services (last ${lines} lines)..."
        docker-compose -f docker-compose.yaml logs --tail="${lines}" -f
    else
        log_info "Showing logs for service: ${service} (last ${lines} lines)..."
        docker-compose -f docker-compose.yaml logs --tail="${lines}" -f "$service"
    fi
}

# Show usage
usage() {
    cat << EOF
Usage: $0 <command> [arguments]

Commands:
    deploy <sha> [--skip-smoke]              Deploy a specific git SHA with optional smoke test skip
    status                                   Show current deployment status
    rollback previous                        Rollback to previous version
    rollback <sha>                           Rollback to specific version
    logs <service> [lines]                   Show logs for a service (default: all services, 100 lines)
    
Deploy Options:
    --skip-smoke                             Skip smoke tests (requires --skip-reason)
    --skip-reason <reason>                   Reason for skipping smoke tests
    --skip-actor <actor>                     Actor requesting skip (default: current user)
    
Examples:
    # Normal deployment with smoke tests
    $0 deploy abc123f
    
    # Deploy with smoke tests skipped (emergency hotfix)
    $0 deploy abc123f --skip-smoke --skip-reason "Emergency hotfix for P0 incident"
    
    # Other commands
    $0 status
    $0 rollback previous
    $0 rollback def456a
    $0 logs api-server 50
    $0 logs

Environment Variables:
    DEPLOY_ROOT                    Deployment root directory (default: /opt/brainego)
    ENV_FILE                       Production environment file (default: /opt/brainego/env/prod.env)
    SMOKE_TEST_BASE_URL            Base URL for smoke tests (default: http://localhost:8000)
    SMOKE_TEST_WORKSPACE_ID        Workspace ID for smoke tests (default: default)
    SMOKE_TEST_AUTH_TOKEN          Auth token for smoke tests (optional)
    PROMETHEUS_URL                 Prometheus URL for metrics validation (optional)
    KONG_ADMIN_URL                 Kong Admin API URL (optional)
    SLACK_WEBHOOK_URL              Slack webhook for deployment notifications (optional)

Deployment Structure:
    /opt/brainego/
    ├── releases/
    │   ├── <sha1>/                   Versioned release directories
    │   ├── <sha2>/
    │   └── <sha3>/
    ├── current -> releases/<active_sha>/  Symlink to active release
    ├── env/
    │   └── prod.env                  Production environment configuration
    ├── logs/
    │   ├── deployment.log            Deployment actions log
    │   ├── downtime.log              Downtime measurements (CSV format)
    │   ├── rollback.log              Rollback audit trail
    │   └── smoke_tests_<sha>.log     Smoke test results per release
    └── audit/
        └── skip-smoke.log            Audit trail for skipped smoke tests

Smoke Test Auto-Rollback:
    If smoke tests fail after deployment, the script automatically:
    1. Restores symlink to previous release
    2. Restarts services via 'docker-compose restart'
    3. Logs rollback with release ID, timestamp, and failure reason
    4. Sends Slack alert (if configured)

EOF
}

# Main command dispatcher
main() {
    if [[ $# -eq 0 ]]; then
        usage
        exit 1
    fi
    
    local command=$1
    shift
    
    case "$command" in
        deploy)
            if [[ $# -lt 1 ]]; then
                log_error "deploy command requires a git SHA argument"
                usage
                exit 1
            fi
            
            local sha=$1
            shift
            
            # Parse deploy options
            local skip_smoke=false
            local skip_reason=""
            local skip_actor=$(whoami)
            
            while [[ $# -gt 0 ]]; do
                case "$1" in
                    --skip-smoke)
                        skip_smoke=true
                        shift
                        ;;
                    --skip-reason)
                        if [[ $# -lt 2 ]]; then
                            log_error "--skip-reason requires an argument"
                            usage
                            exit 1
                        fi
                        skip_reason="$2"
                        shift 2
                        ;;
                    --skip-actor)
                        if [[ $# -lt 2 ]]; then
                            log_error "--skip-actor requires an argument"
                            usage
                            exit 1
                        fi
                        skip_actor="$2"
                        shift 2
                        ;;
                    *)
                        log_error "Unknown option: $1"
                        usage
                        exit 1
                        ;;
                esac
            done
            
            # Validate skip-smoke requirements
            if [[ "${skip_smoke}" == "true" ]] && [[ -z "${skip_reason}" ]]; then
                log_error "--skip-smoke requires --skip-reason to be specified"
                log_error "Example: $0 deploy ${sha} --skip-smoke --skip-reason 'Emergency P0 hotfix'"
                exit 1
            fi
            
            deploy "${sha}" "${skip_smoke}" "${skip_reason}" "${skip_actor}"
            ;;
        status)
            status
            ;;
        rollback)
            if [[ $# -ne 1 ]]; then
                log_error "rollback command requires 'previous' or a git SHA argument"
                usage
                exit 1
            fi
            rollback "$1"
            ;;
        logs)
            logs "${1:-}" "${2:-100}"
            ;;
        *)
            log_error "Unknown command: $command"
            usage
            exit 1
            ;;
    esac
}

main "$@"
