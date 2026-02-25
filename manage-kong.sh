#!/bin/bash
# Kong Gateway Management Script
# Manage Kong consumers, credentials, and configuration

set -euo pipefail

NAMESPACE="${NAMESPACE:-ai-platform}"
KONG_ADMIN_URL="${KONG_ADMIN_URL:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

function print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

function print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

function print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

function get_kong_admin_url() {
    if [ -n "$KONG_ADMIN_URL" ]; then
        echo "$KONG_ADMIN_URL"
        return
    fi
    
    # Try to get from service
    local url=$(kubectl get svc -n "$NAMESPACE" kong-admin -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
    if [ -z "$url" ]; then
        url=$(kubectl get svc -n "$NAMESPACE" kong-admin -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "")
    fi
    
    if [ -z "$url" ]; then
        # Use port-forward
        print_warning "Kong admin service not exposed, using port-forward"
        kubectl port-forward -n "$NAMESPACE" svc/kong-admin 8001:8001 &
        PF_PID=$!
        sleep 2
        url="localhost"
    fi
    
    echo "http://$url:8001"
}

function create_consumer() {
    local username="$1"
    local custom_id="${2:-}"
    
    print_info "Creating consumer: $username"
    
    local payload="{\"username\": \"$username\""
    if [ -n "$custom_id" ]; then
        payload="$payload, \"custom_id\": \"$custom_id\""
    fi
    payload="$payload}"
    
    local admin_url=$(get_kong_admin_url)
    
    curl -s -X POST "$admin_url/consumers" \
        -H "Content-Type: application/json" \
        -d "$payload" | jq .
    
    print_info "Consumer created successfully"
}

function add_jwt_credential() {
    local username="$1"
    local key="$2"
    local public_key_path="${3:-}"
    
    print_info "Adding JWT credential for consumer: $username"
    
    local admin_url=$(get_kong_admin_url)
    
    if [ -n "$public_key_path" ] && [ -f "$public_key_path" ]; then
        # Read public key
        local public_key=$(cat "$public_key_path")
        
        curl -s -X POST "$admin_url/consumers/$username/jwt" \
            -F "key=$key" \
            -F "algorithm=RS256" \
            -F "rsa_public_key=$public_key" | jq .
    else
        curl -s -X POST "$admin_url/consumers/$username/jwt" \
            -F "key=$key" \
            -F "algorithm=RS256" | jq .
    fi
    
    print_info "JWT credential added successfully"
}

function add_oauth2_credential() {
    local username="$1"
    local name="$2"
    local client_id="${3:-}"
    local client_secret="${4:-}"
    local redirect_uri="${5:-https://example.com/callback}"
    
    print_info "Adding OAuth2 credential for consumer: $username"
    
    local admin_url=$(get_kong_admin_url)
    
    local cmd="curl -s -X POST \"$admin_url/consumers/$username/oauth2\""
    cmd="$cmd -d \"name=$name\""
    cmd="$cmd -d \"redirect_uris[]=$redirect_uri\""
    
    if [ -n "$client_id" ]; then
        cmd="$cmd -d \"client_id=$client_id\""
    fi
    
    if [ -n "$client_secret" ]; then
        cmd="$cmd -d \"client_secret=$client_secret\""
    fi
    
    eval "$cmd | jq ."
    
    print_info "OAuth2 credential added successfully"
}

function list_consumers() {
    local admin_url=$(get_kong_admin_url)
    
    print_info "Listing consumers"
    curl -s "$admin_url/consumers" | jq '.data[] | {username, custom_id, id}'
}

function list_plugins() {
    local admin_url=$(get_kong_admin_url)
    
    print_info "Listing enabled plugins"
    curl -s "$admin_url/plugins/enabled" | jq .
}

function list_routes() {
    local admin_url=$(get_kong_admin_url)
    
    print_info "Listing routes"
    curl -s "$admin_url/routes" | jq '.data[] | {name, paths, methods}'
}

function list_services() {
    local admin_url=$(get_kong_admin_url)
    
    print_info "Listing services"
    curl -s "$admin_url/services" | jq '.data[] | {name, url, protocol}'
}

function get_kong_status() {
    local admin_url=$(get_kong_admin_url)
    
    print_info "Kong Gateway Status"
    curl -s "$admin_url/status" | jq .
}

function export_config() {
    local output_file="${1:-kong-config-export.yaml}"
    
    print_info "Exporting Kong configuration to $output_file"
    
    kubectl exec -n "$NAMESPACE" -it \
        $(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=kong -o jsonpath='{.items[0].metadata.name}') \
        -- kong config db_export /tmp/kong-export.yaml
    
    kubectl cp "$NAMESPACE/$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=kong -o jsonpath='{.items[0].metadata.name}'):/tmp/kong-export.yaml" \
        "$output_file"
    
    print_info "Configuration exported to $output_file"
}

function import_config() {
    local input_file="$1"
    
    if [ ! -f "$input_file" ]; then
        print_error "File not found: $input_file"
        exit 1
    fi
    
    print_info "Importing Kong configuration from $input_file"
    
    local pod=$(kubectl get pod -n "$NAMESPACE" -l app.kubernetes.io/name=kong -o jsonpath='{.items[0].metadata.name}')
    
    kubectl cp "$input_file" "$NAMESPACE/$pod:/tmp/kong-import.yaml"
    
    kubectl exec -n "$NAMESPACE" -it "$pod" \
        -- kong config db_import /tmp/kong-import.yaml
    
    print_info "Configuration imported successfully"
}

function view_audit_logs() {
    local lines="${1:-100}"
    
    print_info "Viewing last $lines audit log entries"
    
    kubectl logs -n "$NAMESPACE" \
        -l app.kubernetes.io/name=kong \
        --tail="$lines" | grep -i audit || print_warning "No audit logs found"
}

function check_rate_limits() {
    local ip="${1:-}"
    
    print_info "Checking rate limit counters in Redis"
    
    kubectl exec -n "$NAMESPACE" -it redis-0 -- redis-cli --scan --pattern "ratelimit:*" | head -20
    
    if [ -n "$ip" ]; then
        print_info "Checking rate limits for IP: $ip"
        kubectl exec -n "$NAMESPACE" -it redis-0 -- \
            redis-cli --scan --pattern "ratelimit:$ip:*"
    fi
}

function check_token_budget() {
    local workspace_id="${1:-default}"
    local date=$(date +%Y-%m-%d)
    
    print_info "Checking token budget for workspace: $workspace_id"
    
    local key="token_budget:$workspace_id:$date"
    local used=$(kubectl exec -n "$NAMESPACE" -it redis-0 -- redis-cli get "$key" 2>/dev/null | tr -d '\r' || echo "0")
    
    echo "Workspace: $workspace_id"
    echo "Date: $date"
    echo "Tokens used: ${used:-0}"
}

function rotate_jwt_keys() {
    local new_keys_dir="${1:-kong-jwt-keys-new}"
    
    print_info "Rotating JWT keys"
    print_warning "This will generate new keys and update the secret"
    print_warning "Make sure to update all clients with new public key"
    
    read -p "Continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        print_info "Aborted"
        exit 0
    fi
    
    # Generate new keys
    ./generate-kong-jwt-keys.sh "$new_keys_dir" 4096
    
    # Update Kubernetes secret
    kubectl create secret generic kong-jwt-keypair \
        --from-file=private_key="$new_keys_dir/kong-jwt-private.pem" \
        --from-file=public_key="$new_keys_dir/kong-jwt-public.pem" \
        --namespace "$NAMESPACE" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    print_info "Keys rotated successfully"
    print_info "Restarting Kong..."
    
    kubectl rollout restart deployment/kong -n "$NAMESPACE"
    
    print_info "Done! Clients need to use new public key from $new_keys_dir/kong-jwt-public.pem"
}

function usage() {
    cat << EOF
Kong Gateway Management Script

Usage: $0 <command> [options]

Commands:
  create-consumer <username> [custom_id]
      Create a new Kong consumer
      
  add-jwt-credential <username> <key> [public_key_path]
      Add JWT credential to a consumer
      
  add-oauth2-credential <username> <name> [client_id] [client_secret] [redirect_uri]
      Add OAuth2 credential to a consumer
      
  list-consumers
      List all consumers
      
  list-plugins
      List enabled plugins
      
  list-routes
      List all routes
      
  list-services
      List all services
      
  status
      Get Kong Gateway status
      
  export-config [output_file]
      Export Kong configuration to file
      
  import-config <input_file>
      Import Kong configuration from file
      
  view-logs [lines]
      View audit logs (default: 100 lines)
      
  check-rate-limits [ip]
      Check rate limit counters
      
  check-token-budget [workspace_id]
      Check token budget for workspace
      
  rotate-jwt-keys [new_keys_dir]
      Rotate JWT keypair

Environment Variables:
  NAMESPACE         - Kubernetes namespace (default: ai-platform)
  KONG_ADMIN_URL    - Kong admin API URL (auto-detected if not set)

Examples:
  # Create consumer and add JWT credential
  $0 create-consumer john-doe user-123
  $0 add-jwt-credential john-doe john-key kong-jwt-keys/kong-jwt-public.pem
  
  # Add OAuth2 credential
  $0 add-oauth2-credential john-doe "John's App"
  
  # Check rate limits for IP
  $0 check-rate-limits 192.168.1.100
  
  # View audit logs
  $0 view-logs 50
  
  # Export configuration
  $0 export-config backup-$(date +%Y%m%d).yaml
EOF
}

# Main
if [ $# -eq 0 ]; then
    usage
    exit 0
fi

COMMAND="$1"
shift

case "$COMMAND" in
    create-consumer)
        create_consumer "$@"
        ;;
    add-jwt-credential)
        add_jwt_credential "$@"
        ;;
    add-oauth2-credential)
        add_oauth2_credential "$@"
        ;;
    list-consumers)
        list_consumers
        ;;
    list-plugins)
        list_plugins
        ;;
    list-routes)
        list_routes
        ;;
    list-services)
        list_services
        ;;
    status)
        get_kong_status
        ;;
    export-config)
        export_config "$@"
        ;;
    import-config)
        import_config "$@"
        ;;
    view-logs)
        view_audit_logs "$@"
        ;;
    check-rate-limits)
        check_rate_limits "$@"
        ;;
    check-token-budget)
        check_token_budget "$@"
        ;;
    rotate-jwt-keys)
        rotate_jwt_keys "$@"
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        print_error "Unknown command: $COMMAND"
        echo ""
        usage
        exit 1
        ;;
esac

# Cleanup port-forward if created
if [ -n "${PF_PID:-}" ]; then
    kill $PF_PID 2>/dev/null || true
fi
