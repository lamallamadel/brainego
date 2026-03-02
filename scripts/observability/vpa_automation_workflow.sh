#!/bin/bash
set -euo pipefail

# VPA Automation Workflow Script
# Automates the full VPA recommendation and application process

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROMETHEUS_URL="${PROMETHEUS_URL:-http://prometheus:9090}"
NAMESPACE="${NAMESPACE:-ai-platform}"
DRY_RUN="${DRY_RUN:-true}"
LOOKBACK_DAYS="${LOOKBACK_DAYS:-7}"

# Output paths
RECOMMENDATIONS_FILE="$PROJECT_ROOT/resource_recommendations.json"
VPA_SUMMARY_FILE="$PROJECT_ROOT/vpa_application_summary.json"
VPA_HELM_TEMPLATE="$PROJECT_ROOT/helm/ai-platform/templates/vpa.yaml"
VPA_RAW_DIR="$PROJECT_ROOT/manifests/vpa"
GRAFANA_DASHBOARD="$PROJECT_ROOT/configs/grafana/dashboards/cost-optimization.json"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo ""
    echo "========================================================================"
    echo "$1"
    echo "========================================================================"
    echo ""
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is required but not installed"
        exit 1
    fi
    
    # Check if scripts exist
    if [ ! -f "$SCRIPT_DIR/analyze_resource_usage.py" ]; then
        log_error "analyze_resource_usage.py not found in $SCRIPT_DIR"
        exit 1
    fi
    
    if [ ! -f "$SCRIPT_DIR/apply_vpa_recommendations.py" ]; then
        log_error "apply_vpa_recommendations.py not found in $SCRIPT_DIR"
        exit 1
    fi
    
    # Check Prometheus connectivity
    if command -v curl &> /dev/null; then
        if ! curl -s -f "$PROMETHEUS_URL/api/v1/status/config" > /dev/null 2>&1; then
            log_warning "Cannot connect to Prometheus at $PROMETHEUS_URL"
            log_warning "VPA recommendations will use cached data if available"
        else
            log_success "Prometheus is reachable at $PROMETHEUS_URL"
        fi
    fi
    
    log_success "Prerequisites check completed"
}

analyze_resources() {
    print_header "Step 1: Analyzing Resource Usage"
    
    log_info "Querying Prometheus for $LOOKBACK_DAYS days of metrics..."
    log_info "Output: $RECOMMENDATIONS_FILE"
    
    cd "$PROJECT_ROOT"
    
    PROMETHEUS_URL="$PROMETHEUS_URL" \
    OUTPUT_FILE="$RECOMMENDATIONS_FILE" \
    LOOKBACK_DAYS="$LOOKBACK_DAYS" \
    python3 "$SCRIPT_DIR/analyze_resource_usage.py"
    
    if [ $? -eq 0 ]; then
        log_success "Resource analysis completed"
        
        # Show summary
        if command -v jq &> /dev/null && [ -f "$RECOMMENDATIONS_FILE" ]; then
            echo ""
            log_info "Summary:"
            jq -r '.summary | "  Workloads analyzed: \(.total_workloads_analyzed)\n  Recommendations: \(.recommendations_generated)\n  Monthly savings: $\(.cost_savings.estimated_monthly_savings_usd)\n  Annual savings: $\(.cost_savings.estimated_annual_savings_usd)"' "$RECOMMENDATIONS_FILE"
        fi
    else
        log_error "Resource analysis failed"
        exit 1
    fi
}

apply_recommendations() {
    print_header "Step 2: Applying VPA Recommendations"
    
    if [ "$DRY_RUN" = "true" ]; then
        log_warning "Running in DRY-RUN mode (no changes will be applied)"
    else
        log_info "Running in PRODUCTION mode (changes will be applied)"
    fi
    
    log_info "Input: $RECOMMENDATIONS_FILE"
    log_info "Output Helm template: $VPA_HELM_TEMPLATE"
    log_info "Output raw manifests: $VPA_RAW_DIR"
    log_info "Summary: $VPA_SUMMARY_FILE"
    
    cd "$PROJECT_ROOT"
    
    INPUT_FILE="$RECOMMENDATIONS_FILE" \
    OUTPUT_HELM_TEMPLATE="$VPA_HELM_TEMPLATE" \
    OUTPUT_RAW_DIR="$VPA_RAW_DIR" \
    GRAFANA_DASHBOARD="$GRAFANA_DASHBOARD" \
    NAMESPACE="$NAMESPACE" \
    DRY_RUN="$DRY_RUN" \
    SUMMARY_OUTPUT="$VPA_SUMMARY_FILE" \
    python3 "$SCRIPT_DIR/apply_vpa_recommendations.py"
    
    if [ $? -eq 0 ]; then
        log_success "VPA recommendations applied"
        
        # Show summary
        if command -v jq &> /dev/null && [ -f "$VPA_SUMMARY_FILE" ]; then
            echo ""
            log_info "VPA Summary:"
            jq -r '.summary | "  Total VPAs: \(.total_vpas_generated)\n  Auto mode: \(..) | .update_modes.auto\n  Initial mode: \(..) | .update_modes.initial\n  Validation errors: \(.validation_errors)"' "$VPA_SUMMARY_FILE" 2>/dev/null || true
            
            echo ""
            log_info "Cost Savings:"
            jq -r '.cost_savings | "  CPU cores saved: \(.total_cpu_cores_saved)\n  Memory saved: \(.total_memory_gi_saved) Gi\n  Monthly savings: $\(.estimated_monthly_savings_usd)\n  Annual savings: $\(.estimated_annual_savings_usd)"' "$VPA_SUMMARY_FILE" 2>/dev/null || true
        fi
    else
        log_error "VPA application failed"
        exit 1
    fi
}

show_next_steps() {
    print_header "Next Steps"
    
    if [ "$DRY_RUN" = "true" ]; then
        echo "This was a DRY-RUN. To apply changes for real:"
        echo ""
        echo "  1. Review the generated files:"
        echo "     - Recommendations: $RECOMMENDATIONS_FILE"
        echo "     - VPA Summary: $VPA_SUMMARY_FILE"
        echo "     - Helm template: $VPA_HELM_TEMPLATE"
        echo "     - Raw manifests: $VPA_RAW_DIR/"
        echo ""
        echo "  2. Run again in production mode:"
        echo "     DRY_RUN=false $0"
        echo ""
    else
        echo "VPA manifests have been generated. To deploy:"
        echo ""
        echo "  Option 1: Deploy via Helm"
        echo "    helm upgrade ai-platform helm/ai-platform \\"
        echo "      --set vpa.enabled=true \\"
        echo "      --namespace $NAMESPACE"
        echo ""
        echo "  Option 2: Deploy via kubectl"
        echo "    kubectl apply -f $VPA_RAW_DIR/"
        echo ""
        echo "  Option 3: Review first, then deploy"
        echo "    kubectl diff -f $VPA_RAW_DIR/"
        echo "    kubectl apply -f $VPA_RAW_DIR/"
        echo ""
    fi
    
    echo "Monitor VPA status:"
    echo "  kubectl get vpa -n $NAMESPACE"
    echo "  kubectl describe vpa <name>-vpa -n $NAMESPACE"
    echo ""
    echo "View in Grafana:"
    echo "  Dashboard: Cost Optimization & FinOps"
    echo "  Look for: VPA Potential Monthly Savings panel"
    echo ""
}

show_usage() {
    cat << EOF
VPA Automation Workflow Script

Usage: $0 [OPTIONS]

Options:
  -h, --help              Show this help message
  -d, --dry-run          Run in dry-run mode (default: true)
  -p, --production       Run in production mode (applies changes)
  -l, --lookback DAYS    Days of metrics to analyze (default: 7)
  -n, --namespace NS     Kubernetes namespace (default: ai-platform)
  -u, --prometheus URL   Prometheus URL (default: http://prometheus:9090)

Environment Variables:
  PROMETHEUS_URL         Prometheus endpoint
  NAMESPACE             Kubernetes namespace
  DRY_RUN               Dry-run mode (true/false)
  LOOKBACK_DAYS         Days of metrics to analyze

Examples:
  # Dry-run (safe, no changes)
  $0

  # Production mode (applies changes)
  $0 --production

  # Custom lookback period
  $0 --lookback 14

  # Custom Prometheus URL
  PROMETHEUS_URL=http://prom.example.com:9090 $0

Full Workflow:
  1. Analyzes resource usage from Prometheus
  2. Generates right-sizing recommendations
  3. Creates VPA manifests with smart updateMode selection
  4. Validates changes (50% delta threshold)
  5. Updates Grafana cost dashboard
  6. Outputs summary report

EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -p|--production)
            DRY_RUN=false
            shift
            ;;
        -l|--lookback)
            LOOKBACK_DAYS="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -u|--prometheus)
            PROMETHEUS_URL="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    print_header "VPA Automation Workflow"
    
    log_info "Configuration:"
    echo "  Prometheus URL: $PROMETHEUS_URL"
    echo "  Namespace: $NAMESPACE"
    echo "  Lookback Days: $LOOKBACK_DAYS"
    echo "  Dry-Run Mode: $DRY_RUN"
    echo ""
    
    check_prerequisites
    analyze_resources
    apply_recommendations
    show_next_steps
    
    print_header "Workflow Complete"
    
    if [ "$DRY_RUN" = "true" ]; then
        log_warning "DRY-RUN mode: No changes were applied"
    else
        log_success "Production mode: VPA manifests generated and ready for deployment"
    fi
}

# Run main
main
