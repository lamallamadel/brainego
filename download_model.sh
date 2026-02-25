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

print_info "Starting multi-model download (Llama 3.3 8B, Qwen 2.5 Coder 7B, DeepSeek R1 7B)..."

# Create models directory if it doesn't exist
mkdir -p models

# Model details
declare -A MODELS
MODELS["llama-3.3-8b-instruct-q4_k_m.gguf"]="https://huggingface.co/mradermacher/Llama-3.3-8B-Instruct-GGUF/resolve/main/Llama-3.3-8B-Instruct.Q4_K_M.gguf"
MODELS["qwen2.5-coder-7b-instruct-q4_k_m.gguf"]="https://huggingface.co/bartowski/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf"
MODELS["deepseek-r1-distill-qwen-7b-q4_k_m.gguf"]="https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf"

# Check if wget or curl is available
if command -v wget &> /dev/null; then
    DOWNLOAD_CMD="wget -O"
elif command -v curl &> /dev/null; then
    DOWNLOAD_CMD="curl -L -o"
else
    print_error "Neither wget nor curl is installed. Please install one of them."
    exit 1
fi

# Download all models
FAILED_DOWNLOADS=()
SUCCESSFUL_DOWNLOADS=()

for MODEL_NAME in "${!MODELS[@]}"; do
    MODEL_PATH="models/${MODEL_NAME}"
    MODEL_URL="${MODELS[$MODEL_NAME]}"
    
    # Check if model already exists
    if [ -f "$MODEL_PATH" ]; then
        print_warning "Model file already exists at $MODEL_PATH"
        FILE_SIZE=$(du -h "$MODEL_PATH" | cut -f1)
        print_info "Existing file size: $FILE_SIZE"
        SUCCESSFUL_DOWNLOADS+=("$MODEL_NAME (existing)")
        continue
    fi
    
    print_info "Downloading $MODEL_NAME from Hugging Face..."
    print_info "This may take a while depending on your internet connection..."
    print_info "Estimated size: ~4-5 GB"
    echo ""
    
    if $DOWNLOAD_CMD "$MODEL_PATH" "$MODEL_URL"; then
        FILE_SIZE=$(du -h "$MODEL_PATH" | cut -f1)
        print_success "Model downloaded successfully: $MODEL_NAME ($FILE_SIZE)"
        SUCCESSFUL_DOWNLOADS+=("$MODEL_NAME")
    else
        print_error "Failed to download $MODEL_NAME"
        print_info "You can manually download from: $MODEL_URL"
        FAILED_DOWNLOADS+=("$MODEL_NAME")
    fi
    echo ""
done

echo ""
print_success "==================================="
print_success "Model Download Summary"
print_success "==================================="
echo ""

if [ ${#SUCCESSFUL_DOWNLOADS[@]} -gt 0 ]; then
    print_success "Successfully downloaded/verified models:"
    for model in "${SUCCESSFUL_DOWNLOADS[@]}"; do
        echo "  ✓ $model"
    done
    echo ""
fi

if [ ${#FAILED_DOWNLOADS[@]} -gt 0 ]; then
    print_error "Failed downloads:"
    for model in "${FAILED_DOWNLOADS[@]}"; do
        echo "  ✗ $model"
    done
    echo ""
    exit 1
fi

print_success "All models ready!"
echo ""
print_info "Next steps:"
echo "  1. Start the services: docker compose up -d"
echo "  2. Wait for MAX Serve instances to load models (check logs)"
echo "  3. Test the API: curl http://localhost:8000/health"
echo ""
