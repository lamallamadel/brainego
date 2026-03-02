#!/bin/bash
# Deploy AI Platform to all regions
# This script orchestrates deployment across multiple regions with proper sequencing

set -euo pipefail

# Configuration
REGIONS=("us-west-1" "us-east-1" "eu-west-1" "ap-southeast-1")
PRIMARY_REGION="us-west-1"
CLUSTER_PREFIX="ai-platform"
VALUES_FILE="helm/ai-platform/values-multi-region.yaml"
DRY_RUN=false
SKIP_DNS=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

# Usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy AI Platform to all configured regions with cross-region replication.

OPTIONS:
    -h, --help              Show this help message
    -d, --dry-run           Perform dry run without making changes
    -p, --primary REGION    Set primary region (default: us-west-1)
    -r, --regions LIST      Comma-separated list of regions (default: us-west-1,us-east-1,eu-west-1,ap-southeast-1)
    -s, --skip-dns          Skip DNS configuration
    -v, --values FILE       Path to Helm values file (default: helm/ai-platform/values-multi-region.yaml)

EXAMPLES:
    # Deploy to all default regions
    $0

    # Dry run deployment
    $0 --dry-run

    # Deploy to specific regions
    $0 --regions us-west-1,us-east-1

    # Deploy with custom values file
    $0 --values my-values.yaml
EOF
    exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            usage
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -p|--primary)
            PRIMARY_REGION="$2"
            shift 2
            ;;
        -r|--regions)
            IFS=',' read -ra REGIONS <<< "$2"
            shift 2
            ;;
        -s|--skip-dns)
            SKIP_DNS=true
            shift
            ;;
        -v|--values)
            VALUES_FILE="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Validate prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    local missing=()
    
    command -v kubectl &> /dev/null || missing+=("kubectl")
    command -v helm &> /dev/null || missing+=("helm")
    command -v python3 &> /dev/null || missing+=("python3")
    
    if [ ${#missing[@]} -gt 0 ]; then
        log_error "Missing required tools: ${missing[*]}"
        log_error "Please install missing tools and try again"
        exit 1
    fi
    
    log "✓ All prerequisites met"
}

# Deploy to a single region
deploy_region() {
    local region=$1
    local is_primary=$2
    
    log "==========================================="
    log "Deploying to region: $region"
    log "Primary region: $is_primary"
    log "==========================================="
    
    local cluster_name="${CLUSTER_PREFIX}-${region}"
    
    # Build deployment command
    local cmd="python3 scripts/deploy/deploy_region.py"
    cmd="$cmd --region $region"
    cmd="$cmd --cluster $cluster_name"
    cmd="$cmd --values-file $VALUES_FILE"
    
    if [ "$DRY_RUN" = true ]; then
        cmd="$cmd --dry-run"
    fi
    
    if [ "$SKIP_DNS" = true ]; then
        cmd="$cmd --skip-dns"
    fi
    
    log "Executing: $cmd"
    
    if eval "$cmd"; then
        log "✓ Successfully deployed to $region"
        return 0
    else
        log_error "✗ Failed to deploy to $region"
        return 1
    fi
}

# Setup replication between regions
setup_replication() {
    log "==========================================="
    log "Setting up cross-region replication"
    log "==========================================="
    
    # PostgreSQL replication
    log "Setting up PostgreSQL replication..."
    
    # Setup primary node
    log "Configuring PostgreSQL primary in $PRIMARY_REGION..."
    kubectl config use-context "${CLUSTER_PREFIX}-${PRIMARY_REGION}"
    
    kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform \
        -f /docker-entrypoint-initdb.d/postgres-replication-setup.sql || {
        log_error "Failed to initialize PostgreSQL replication"
        return 1
    }
    
    kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
        "SELECT setup_replication_node('${PRIMARY_REGION}', 'host=postgres.${PRIMARY_REGION}.ai-platform.svc.cluster.local port=5432 dbname=ai_platform user=replication_user password=replication_password');" || {
        log_error "Failed to create PostgreSQL replication node"
        return 1
    }
    
    kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
        "SELECT setup_replication_set('ai_platform_set');" || {
        log_error "Failed to create PostgreSQL replication set"
        return 1
    }
    
    log "✓ PostgreSQL primary configured"
    
    # Setup replicas
    for region in "${REGIONS[@]}"; do
        if [ "$region" != "$PRIMARY_REGION" ]; then
            log "Configuring PostgreSQL replica in $region..."
            kubectl config use-context "${CLUSTER_PREFIX}-${region}"
            
            kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c \
                "SELECT setup_replication_subscription('sub_from_${PRIMARY_REGION}', 'host=postgres.${PRIMARY_REGION}.ai-platform.svc.cluster.local port=5432 dbname=ai_platform user=replication_user password=replication_password');" || {
                log_warn "Failed to setup PostgreSQL subscription in $region"
            }
            
            log "✓ PostgreSQL replica configured in $region"
        fi
    done
    
    # Qdrant replication
    log "Setting up Qdrant cluster replication..."
    
    local regions_arg="${REGIONS[*]}"
    local cmd="python3 scripts/deploy/setup_qdrant_replication.py --regions ${regions_arg// / }"
    
    if [ "$DRY_RUN" = true ]; then
        cmd="$cmd --dry-run"
    fi
    
    if eval "$cmd"; then
        log "✓ Qdrant replication configured"
    else
        log_warn "Qdrant replication setup encountered issues"
    fi
}

# Verify deployment health
verify_deployment() {
    log "==========================================="
    log "Verifying deployment health"
    log "==========================================="
    
    local all_healthy=true
    
    for region in "${REGIONS[@]}"; do
        log "Checking $region..."
        kubectl config use-context "${CLUSTER_PREFIX}-${region}"
        
        # Check if all pods are running
        local total_pods=$(kubectl get pods -n ai-platform --no-headers | wc -l)
        local running_pods=$(kubectl get pods -n ai-platform --field-selector=status.phase=Running --no-headers | wc -l)
        
        log "  Pods: $running_pods/$total_pods running"
        
        if [ "$running_pods" -lt "$total_pods" ]; then
            log_warn "  Not all pods are running in $region"
            all_healthy=false
        else
            log "  ✓ All pods running"
        fi
        
        # Check service endpoints
        local services=("gateway" "agent-router" "qdrant" "postgres" "redis")
        for svc in "${services[@]}"; do
            if kubectl get service "$svc" -n ai-platform &> /dev/null; then
                log "  ✓ Service $svc exists"
            else
                log_warn "  ✗ Service $svc not found"
                all_healthy=false
            fi
        done
    done
    
    if [ "$all_healthy" = true ]; then
        log "✓ All regions are healthy"
        return 0
    else
        log_warn "Some regions have issues"
        return 1
    fi
}

# Print summary
print_summary() {
    cat << EOF

=========================================
DEPLOYMENT SUMMARY
=========================================
Primary Region: $PRIMARY_REGION
Regions: ${REGIONS[*]}
Dry Run: $DRY_RUN
Skip DNS: $SKIP_DNS

Next Steps:
1. Verify all services are running:
   kubectl get all -n ai-platform

2. Check replication status:
   kubectl exec -n ai-platform postgres-0 -- psql -U ai_user -d ai_platform -c "SELECT * FROM replication_status;"

3. Access Grafana dashboard:
   kubectl port-forward -n ai-platform svc/grafana 3000:3000
   Open: http://localhost:3000/d/cross-region-monitoring

4. Test geo-routing:
   curl https://us-west-1.ai-platform.example.com/health
   curl https://us-east-1.ai-platform.example.com/health
   curl https://eu-west-1.ai-platform.example.com/health
   curl https://ap-southeast-1.ai-platform.example.com/health

5. Monitor metrics:
   - Region health
   - Cross-region latency
   - Replication lag
   - Failover events

For more information, see: docs/MULTI_REGION_DEPLOYMENT.md
=========================================

EOF
}

# Main execution
main() {
    log "Starting multi-region deployment..."
    log "Primary region: $PRIMARY_REGION"
    log "All regions: ${REGIONS[*]}"
    
    if [ "$DRY_RUN" = true ]; then
        log_warn "DRY RUN MODE - No changes will be made"
    fi
    
    # Check prerequisites
    check_prerequisites
    
    # Deploy primary region first
    log "Step 1/4: Deploying primary region ($PRIMARY_REGION)..."
    if ! deploy_region "$PRIMARY_REGION" true; then
        log_error "Failed to deploy primary region. Aborting."
        exit 1
    fi
    
    # Deploy secondary regions
    log "Step 2/4: Deploying secondary regions..."
    local failed_regions=()
    
    for region in "${REGIONS[@]}"; do
        if [ "$region" != "$PRIMARY_REGION" ]; then
            if ! deploy_region "$region" false; then
                failed_regions+=("$region")
                log_warn "Deployment to $region failed, continuing with other regions..."
            fi
        fi
    done
    
    if [ ${#failed_regions[@]} -gt 0 ]; then
        log_warn "Some regions failed to deploy: ${failed_regions[*]}"
    fi
    
    # Setup replication
    if [ "$DRY_RUN" = false ]; then
        log "Step 3/4: Setting up cross-region replication..."
        if ! setup_replication; then
            log_warn "Replication setup encountered issues"
        fi
    else
        log "Step 3/4: Skipping replication setup (dry run mode)"
    fi
    
    # Verify deployment
    log "Step 4/4: Verifying deployment health..."
    if ! verify_deployment; then
        log_warn "Some health checks failed"
    fi
    
    # Print summary
    print_summary
    
    if [ ${#failed_regions[@]} -gt 0 ]; then
        log_warn "Deployment completed with failures in: ${failed_regions[*]}"
        exit 1
    else
        log "✓ Multi-region deployment completed successfully!"
        exit 0
    fi
}

# Run main function
main
