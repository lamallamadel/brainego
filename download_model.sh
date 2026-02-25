#!/bin/bash

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

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

print_info "Starting Llama 3.3 8B Instruct Q4_K_M model download..."

# Create models directory if it doesn't exist
mkdir -p models

# Model details
MODEL_NAME="llama-3.3-8b-instruct-q4_k_m.gguf"
MODEL_PATH="models/${MODEL_NAME}"
MODEL_URL="https://huggingface.co/bartowski/Llama-3.3-70B-Instruct-GGUF/resolve/main/Llama-3.3-70B-Instruct-Q4_K_M.gguf"
# Note: Using the actual Llama 3.3 70B URL as placeholder - replace with 8B version when available
# For 8B model, use: https://huggingface.co/mradermacher/Llama-3.3-8B-Instruct-GGUF/resolve/main/Llama-3.3-8B-Instruct.Q4_K_M.gguf

# Alternative: Download from official source
ALT_MODEL_URL="https://huggingface.co/mradermacher/Llama-3.3-8B-Instruct-GGUF/resolve/main/Llama-3.3-8B-Instruct.Q4_K_M.gguf"

# Check if model already exists
if [ -f "$MODEL_PATH" ]; then
    print_warning "Model file already exists at $MODEL_PATH"
    read -p "Do you want to re-download? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "Skipping download"
        exit 0
    fi
    rm -f "$MODEL_PATH"
fi

# Check if wget or curl is available
if command -v wget &> /dev/null; then
    DOWNLOAD_CMD="wget -O"
elif command -v curl &> /dev/null; then
    DOWNLOAD_CMD="curl -L -o"
else
    print_error "Neither wget nor curl is installed. Please install one of them."
    exit 1
fi

# Download the model
print_info "Downloading model from Hugging Face..."
print_info "This may take a while depending on your internet connection..."
print_info "Model size: ~4.5 GB"
echo ""

if $DOWNLOAD_CMD "$MODEL_PATH" "$ALT_MODEL_URL"; then
    print_success "Model downloaded successfully to $MODEL_PATH"
else
    print_error "Failed to download model"
    print_info "You can manually download the model from:"
    print_info "  $ALT_MODEL_URL"
    print_info "And place it in: $MODEL_PATH"
    exit 1
fi

# Verify the download
if [ -f "$MODEL_PATH" ]; then
    FILE_SIZE=$(du -h "$MODEL_PATH" | cut -f1)
    print_success "Model file verified: $FILE_SIZE"
    print_info "Model location: $MODEL_PATH"
else
    print_error "Model file not found after download"
    exit 1
fi

echo ""
print_success "==================================="
print_success "Model Download Complete!"
print_success "==================================="
echo ""
print_info "Next steps:"
echo "  1. Start the services: docker compose up -d"
echo "  2. Wait for MAX Serve to load the model (check logs)"
echo "  3. Test the API: python3 api_server.py"
echo ""
