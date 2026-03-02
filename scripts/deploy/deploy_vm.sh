#!/bin/bash
set -euo pipefail

# deploy_vm.sh - Versioned release deployment for brainego
# Deploys to /opt/brainego/releases/<git_sha>/ with symlink to /opt/brainego/current
# Target: ≤30s downtime or measure/log actual downtime

# Configuration
DEPLOY_ROOT="/opt/brainego"
RELEASES_DIR="${DEPLOY_ROOT}/releases"
CURRENT_SYMLINK="${DEPLOY_ROOT}/current"
ENV_FILE="${DEPLOY_ROOT}/env/prod.env"
DEPLOYMENT_LOG="${DEPLOY_ROOT}/logs/deployment.log"
DOWNTIME_LOG="${DEPLOY_ROOT}/logs/downtime.log"

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

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if running as root or with sudo
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root or with sudo"
        exit 1
    fi
    
    # Check for required commands
    local required_cmds=("docker" "docker-compose" "git" "bc")
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

# Deploy a specific version
deploy() {
    local sha=$1
    validate_sha "$sha"
    
    check_prerequisites
    
    local release_dir="${RELEASES_DIR}/${sha}"
    local current_version=$(get_current_version)
    
    log_info "Starting deployment of version: ${sha}"
    log_info "Current version: ${current_version}"
    
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
        exit 1
    fi
    
    log_success "Deployment of ${sha} completed successfully!"
    log_info "Release directory: ${release_dir}"
    log_info "Current symlink: ${CURRENT_SYMLINK} -> ${release_dir}"
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
    fi
    
    echo "Previous version: ${previous_version}"
    
    echo ""
    echo "Available releases:"
    ls -lht "${RELEASES_DIR}" 2>/dev/null || echo "  No releases found"
    
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
    deploy <sha>              Deploy a specific git SHA
    status                    Show current deployment status
    rollback previous         Rollback to previous version
    rollback <sha>            Rollback to specific version
    logs <service> [lines]    Show logs for a service (default: all services, 100 lines)
    
Examples:
    $0 deploy abc123f
    $0 status
    $0 rollback previous
    $0 rollback def456a
    $0 logs api-server 50
    $0 logs

Environment:
    DEPLOY_ROOT              Deployment root directory (default: /opt/brainego)
    ENV_FILE                 Production environment file (default: /opt/brainego/env/prod.env)

Deployment Structure:
    /opt/brainego/
    ├── releases/
    │   ├── <sha1>/          Versioned release directories
    │   ├── <sha2>/
    │   └── <sha3>/
    ├── current -> releases/<active_sha>/  Symlink to active release
    ├── env/
    │   └── prod.env         Production environment configuration
    └── logs/
        ├── deployment.log   Deployment actions log
        └── downtime.log     Downtime measurements (CSV format)

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
            if [[ $# -ne 1 ]]; then
                log_error "deploy command requires a git SHA argument"
                usage
                exit 1
            fi
            deploy "$1"
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
