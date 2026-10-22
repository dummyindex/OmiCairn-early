#!/bin/bash
# Build minimal Docker images for omicairn-agent-local (faster, fewer packages)

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Building minimal omicairn-agent-local Docker images..."
echo "============================================="

# Build Python execution environment
echo "Building minimal Python execution environment..."
docker build -f "$SCRIPT_DIR/python_image_variants/Dockerfile.python.minimal" -t omicairn-python:minimal "$SCRIPT_DIR"
echo "✓ Python environment built successfully"

# Build R execution environment
echo ""
echo "Building minimal R execution environment..."
docker build -f "$SCRIPT_DIR/Dockerfile.r.minimal" -t omicairn-r:minimal "$SCRIPT_DIR"
echo "✓ R environment built successfully"

echo ""
echo "All minimal images built successfully!"
echo "Note: config.py defaults to omicairn-python:local; set config.python_image to omicairn-python:minimal to use the minimal Python image."
docker images | grep omicairn || true
