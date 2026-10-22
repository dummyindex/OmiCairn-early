#!/bin/bash
# Build Docker images for omicairn-agent-local (built locally; not pulled from any registry)

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "Building omicairn-agent-local Docker images..."
echo "============================================="

# Build Python image (tag matches config.python_image; the second tag is used by some integration tests)
echo "Building Python execution environment..."
docker build -t omicairn-python:local -t omicairn/python-executor:latest \
    -f "$SCRIPT_DIR/Dockerfile.python" "$SCRIPT_DIR"
echo "✓ Python image built successfully"

# Build R image (tag matches config.r_image)
echo ""
echo "Building R execution environment..."
docker build -t omicairn-r:minimal -f "$SCRIPT_DIR/Dockerfile.r.minimal" "$SCRIPT_DIR"
echo "✓ R image built successfully"

echo ""
echo "Docker images built successfully!"
echo ""
echo "Available images:"
docker images | grep -E "(omicairn-python|omicairn-r|omicairn/python-executor)" || true
