#!/bin/bash

set -e

echo "==================================="
echo "AI Platform Initialization Script"
echo "==================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Docker installation
print_info "Checking Docker installation..."
if ! command_exists docker; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi
print_success "Docker is installed"

# Check Docker Compose installation
print_info "Checking Docker Compose installation..."
if ! command_exists docker-compose && ! docker compose version >/dev/null 2>&1; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi
print_success "Docker Compose is installed"

# Check if Docker daemon is running
print_info "Checking Docker daemon..."
if ! docker info >/dev/null 2>&1; then
    print_error "Docker daemon is not running. Please start Docker first."
    exit 1
fi
print_success "Docker daemon is running"

# GPU Validation
print_info "Validating GPU availability..."
GPU_AVAILABLE=false

if command_exists nvidia-smi; then
    print_info "nvidia-smi found, checking GPU status..."
    if nvidia-smi >/dev/null 2>&1; then
        GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader | head -n 1)
        GPU_NAMES=$(nvidia-smi --query-gpu=name --format=csv,noheader)
        
        print_success "NVIDIA GPU(s) detected:"
        echo "$GPU_NAMES" | while IFS= read -r gpu; do
            echo "  - $gpu"
        done
        echo ""
        
        # Check NVIDIA Docker runtime
        print_info "Checking NVIDIA Docker runtime..."
        if docker run --rm --gpus all nvidia/cuda:11.8.0-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
            print_success "NVIDIA Docker runtime is properly configured"
            GPU_AVAILABLE=true
        else
            print_warning "NVIDIA Docker runtime is not available or not properly configured"
            print_warning "Please install nvidia-docker2 or nvidia-container-toolkit"
            GPU_AVAILABLE=false
        fi
    else
        print_warning "nvidia-smi failed to execute"
        GPU_AVAILABLE=false
    fi
else
    print_warning "nvidia-smi not found - no NVIDIA GPU available"
    GPU_AVAILABLE=false
fi

if [ "$GPU_AVAILABLE" = false ]; then
    print_warning "GPU support is not available. MAX Serve may not function properly."
    read -p "Do you want to continue without GPU support? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Initialization cancelled"
        exit 0
    fi
fi

# Create necessary directories
print_info "Creating directory structure..."
mkdir -p models
mkdir -p configs
mkdir -p init-scripts/postgres
mkdir -p logs
print_success "Directory structure created"

# Create PostgreSQL init script if it doesn't exist
if [ ! -f "init-scripts/postgres/init.sql" ]; then
    print_info "Creating PostgreSQL initialization script..."
    cat > init-scripts/postgres/init.sql <<'EOF'
-- Initialize AI Platform Database

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create tables
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS models (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    version VARCHAR(50) NOT NULL,
    type VARCHAR(100) NOT NULL,
    path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, version)
);

CREATE TABLE IF NOT EXISTS inference_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_id UUID REFERENCES models(id),
    user_id UUID REFERENCES users(id),
    input_size INTEGER,
    output_size INTEGER,
    latency_ms INTEGER,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_models_name ON models(name);
CREATE INDEX IF NOT EXISTS idx_inference_logs_model_id ON inference_logs(model_id);
CREATE INDEX IF NOT EXISTS idx_inference_logs_user_id ON inference_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_inference_logs_created_at ON inference_logs(created_at);

-- Insert sample data
INSERT INTO users (username, email) VALUES 
    ('admin', 'admin@ai-platform.local'),
    ('demo_user', 'demo@ai-platform.local')
ON CONFLICT (username) DO NOTHING;
EOF
    print_success "PostgreSQL initialization script created"
fi

# Create default configuration files if they don't exist
if [ ! -f "configs/max-serve.yaml" ]; then
    print_info "Creating default MAX Serve configuration..."
    cat > configs/max-serve.yaml <<'EOF'
# MAX Serve Configuration
server:
  host: 0.0.0.0
  port: 8080
  workers: 4

models:
  path: /models
  cache_size: 10GB

logging:
  level: INFO
  format: json
EOF
    print_success "MAX Serve configuration created"
fi

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    print_info "Creating .env file..."
    cat > .env <<'EOF'
# PostgreSQL Configuration
POSTGRES_DB=ai_platform
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=ai_password

# MinIO Configuration
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123

# Redis Configuration
REDIS_MAX_MEMORY=2gb

# Network Configuration
COMPOSE_PROJECT_NAME=ai-platform
EOF
    print_success ".env file created"
fi


# Compose file selection
COMPOSE_ARGS=(-f docker-compose.yaml)
if [ "${USE_DOCKER_CLOUD_CONFIG:-false}" = "true" ]; then
    if [ -f "docker-compose.observability.yml" ]; then
        COMPOSE_ARGS+=( -f docker-compose.observability.yml )
        print_info "Using Docker cloud/observability compose override: docker-compose.observability.yml"
    else
        print_warning "USE_DOCKER_CLOUD_CONFIG=true but docker-compose.observability.yml was not found"
    fi
fi

# Pull Docker images
print_info "Pulling Docker images (this may take a while)..."
if docker compose "${COMPOSE_ARGS[@]}" pull; then
    print_success "Docker images pulled successfully"
else
    print_error "Failed to pull Docker images"
    exit 1
fi

# Start services
print_info "Starting services..."
if docker compose "${COMPOSE_ARGS[@]}" up -d; then
    print_success "Services started successfully"
else
    print_error "Failed to start services"
    exit 1
fi

# Wait for services to be healthy
print_info "Waiting for services to be healthy..."
echo ""

SERVICES=("redis" "postgres" "minio" "qdrant" "max-serve-llama" "max-serve-qwen" "max-serve-deepseek" "api-server")
MAX_WAIT=60
WAIT_INTERVAL=5

for service in "${SERVICES[@]}"; do
    print_info "Checking $service..."
    elapsed=0
    while [ $elapsed -lt $MAX_WAIT ]; do
        if docker compose "${COMPOSE_ARGS[@]}" ps "$service" | grep -q "healthy\|Up"; then
            print_success "$service is ready"
            break
        fi
        sleep $WAIT_INTERVAL
        elapsed=$((elapsed + WAIT_INTERVAL))
    done
    
    if [ $elapsed -ge $MAX_WAIT ]; then
        print_warning "$service may not be fully ready yet"
    fi
done

echo ""
print_success "==================================="
print_success "Initialization Complete!"
print_success "==================================="
echo ""
print_info "Services Status:"
docker compose ps
echo ""
print_info "Service URLs:"
echo "  - MAX Serve:      http://localhost:8080"
echo "  - Qdrant:         http://localhost:6333"
echo "  - Qdrant (gRPC):  localhost:6334"
echo "  - Redis:          localhost:6379"
echo "  - PostgreSQL:     localhost:5432"
echo "  - MinIO API:      http://localhost:9000"
echo "  - MinIO Console:  http://localhost:9001"
echo ""
print_info "Default Credentials:"
echo "  PostgreSQL:"
echo "    - Database: ai_platform"
echo "    - User:     ai_user"
echo "    - Password: ai_password"
echo ""
echo "  MinIO:"
echo "    - User:     minioadmin"
echo "    - Password: minioadmin123"
echo ""
print_info "Useful Commands:"
echo "  - View logs:      docker compose logs -f [service_name]"
echo "  - Stop services:  docker compose down"
echo "  - Restart:        docker compose restart"
echo "  - Status:         docker compose ps"
echo ""
print_success "All systems ready! 🚀"
