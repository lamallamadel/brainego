#!/bin/bash
# Production Validation Runner Script
# Simplified execution of production validation tests

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Python is available
check_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed"
        exit 1
    fi
    print_success "Python 3 found: $(python3 --version)"
}

# Check if services are running
check_services() {
    print_info "Checking if services are running..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    
    # Check critical services
    services=("api-server" "gateway" "mcpjungle-gateway" "postgres" "redis" "qdrant")
    all_running=true
    
    for service in "${services[@]}"; do
        if docker ps --format '{{.Names}}' | grep -q "^${service}$"; then
            print_success "Service running: $service"
        else
            print_warning "Service not running: $service"
            all_running=false
        fi
    done
    
    if [ "$all_running" = false ]; then
        print_warning "Some services are not running. Start with: docker compose up -d"
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Install dependencies
install_deps() {
    print_info "Installing production validation dependencies..."
    pip install -q -r requirements-production-validation.txt
    print_success "Dependencies installed"
}

# Check optional tools
check_optional_tools() {
    if command -v k6 &> /dev/null; then
        print_success "k6 installed: $(k6 version)"
    else
        print_warning "k6 not installed (optional)"
        print_info "Install from: https://k6.io/docs/getting-started/installation/"
    fi
    
    if command -v trivy &> /dev/null; then
        print_success "Trivy installed: $(trivy --version | head -n1)"
    else
        print_warning "Trivy not installed (optional)"
        print_info "Install from: https://aquasecurity.github.io/trivy/"
    fi
}

# Run validation
run_validation() {
    mode=$1
    print_info "Running production validation in $mode mode..."
    
    case $mode in
        quick)
            python3 run_production_validation.py --quick
            ;;
        full)
            python3 run_production_validation.py --full
            ;;
        locust)
            print_info "Running Locust load test..."
            locust -f locust_load_test.py \
                --host=http://localhost:8000 \
                --users=50 \
                --spawn-rate=5 \
                --run-time=10m \
                --headless \
                --html=locust_report.html
            ;;
        k6)
            if ! command -v k6 &> /dev/null; then
                print_error "k6 is not installed"
                exit 1
            fi
            print_info "Running k6 load test..."
            k6 run --vus 50 --duration 10m k6_load_test.js
            ;;
        chaos)
            print_info "Running chaos engineering tests..."
            python3 chaos_engineering.py
            ;;
        security)
            print_info "Running security audit..."
            python3 security_audit.py
            ;;
        backup)
            print_info "Running backup/restore tests..."
            python3 test_backup_restore.py
            ;;
        *)
            print_error "Unknown mode: $mode"
            show_usage
            exit 1
            ;;
    esac
    
    exit_code=$?
    if [ $exit_code -eq 0 ]; then
        print_success "Validation completed successfully"
    else
        print_error "Validation failed with exit code $exit_code"
    fi
    
    return $exit_code
}

# Show results
show_results() {
    print_info "Validation Results:"
    echo ""
    
    if [ -f "production_validation_report.json" ]; then
        print_info "Overall Status:"
        python3 -c "import json; data=json.load(open('production_validation_report.json')); print(f\"  {data['overall_status']}\")"
        
        print_info "SLO Compliance:"
        python3 -c "
import json
data = json.load(open('production_validation_report.json'))
compliance = data.get('slo_compliance', {})
for metric, details in compliance.items():
    met = '✓' if details.get('met') else '✗'
    target = details.get('target', 'N/A')
    actual = details.get('actual', 'N/A')
    print(f\"  {met} {metric}: Target={target}, Actual={actual}\")
"
    fi
    
    print_info "Generated Reports:"
    reports=(
        "production_validation_report.json"
        "locust_results.json"
        "locust_report.html"
        "k6_results.json"
        "chaos_report.json"
        "security_audit_report.json"
        "backup_restore_report.json"
    )
    
    for report in "${reports[@]}"; do
        if [ -f "$report" ]; then
            size=$(ls -lh "$report" | awk '{print $5}')
            print_success "  $report ($size)"
        fi
    done
}

# Show usage
show_usage() {
    cat << EOF
Usage: $0 [command]

Commands:
  quick       Run quick validation (skip chaos and k6)
  full        Run full validation suite (default)
  locust      Run only Locust load test
  k6          Run only k6 load test
  chaos       Run only chaos engineering tests
  security    Run only security audit
  backup      Run only backup/restore tests
  install     Install dependencies only
  check       Check prerequisites only
  results     Show latest results
  clean       Clean up result files
  help        Show this help message

Examples:
  $0 quick                # Quick validation
  $0 full                 # Full validation
  $0 locust               # Just load testing
  $0 check                # Check system status

EOF
}

# Clean up results
clean_results() {
    print_info "Cleaning up result files..."
    rm -f k6_results.json
    rm -f locust_results.json
    rm -f locust_report.html
    rm -f chaos_report.json
    rm -f security_audit_report.json
    rm -f trivy_scan_results.json
    rm -f backup_restore_report.json
    rm -f production_validation_report.json
    print_success "Cleaned up result files"
}

# Main execution
main() {
    echo ""
    echo "=========================================="
    echo "  Production Validation Runner"
    echo "=========================================="
    echo ""
    
    command=${1:-full}
    
    case $command in
        help|--help|-h)
            show_usage
            exit 0
            ;;
        install)
            check_python
            install_deps
            check_optional_tools
            exit 0
            ;;
        check)
            check_python
            check_services
            check_optional_tools
            exit 0
            ;;
        results)
            show_results
            exit 0
            ;;
        clean)
            clean_results
            exit 0
            ;;
        quick|full|locust|k6|chaos|security|backup)
            check_python
            check_services
            run_validation $command
            show_results
            ;;
        *)
            print_error "Unknown command: $command"
            show_usage
            exit 1
            ;;
    esac
}

# Run main
main "$@"
