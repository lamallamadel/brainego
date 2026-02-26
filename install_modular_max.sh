#!/usr/bin/env bash

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

if ! command -v python3 >/dev/null 2>&1; then
  print_error "python3 is required but was not found in PATH."
  exit 1
fi

if ! command -v pip3 >/dev/null 2>&1; then
  print_error "pip3 is required but was not found in PATH."
  exit 1
fi

print_info "Installing/Updating Modular Python package (modular)..."
pip3 install --upgrade modular

print_info "Verifying MAX CLI installation..."
if ! command -v max >/dev/null 2>&1; then
  print_error "MAX CLI was not found after installing modular."
  print_error "Ensure your Python user/bin directory is in PATH, then retry."
  exit 1
fi

MAX_VERSION="$(max --version)"
print_success "MAX CLI is available: ${MAX_VERSION}"
