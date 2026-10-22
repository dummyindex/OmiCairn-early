#!/bin/bash
#
# Clean up all test output directories
# Run this script from the tests/ directory or project root
#

echo "=========================================="
echo "Cleaning Test Output Directories"
echo "=========================================="

# Get the project root (parent of tests directory)
if [[ $(basename "$PWD") == "tests" ]]; then
    PROJECT_ROOT=".."
else
    PROJECT_ROOT="."
fi

cd "$PROJECT_ROOT"

# Counter for removed directories
REMOVED_COUNT=0

# Function to remove directory if it exists
remove_dir() {
    local dir=$1
    if [ -d "$dir" ]; then
        rm -rf "$dir"
        echo "✓ Removed $dir"
        ((REMOVED_COUNT++))
    fi
}

# Remove known test output directories
remove_dir "test_outputs"
remove_dir "test_CLI_main_agent"
remove_dir "test_tree_structure_output"
remove_dir "test_agent_mock_output"
remove_dir "test_enhanced_outputs"
remove_dir "test_scvelo_outputs"
remove_dir "test_scfates_outputs"
remove_dir "outputs"

# Remove directories matching test patterns
for dir in test_*_output* *_test_output* temp_test_*; do
    if [ -d "$dir" ]; then
        remove_dir "$dir"
    fi
done

# Clean __pycache__ directories
PYCACHE_COUNT=$(find . -type d -name "__pycache__" 2>/dev/null | wc -l)
if [ "$PYCACHE_COUNT" -gt 0 ]; then
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
    echo "✓ Removed $PYCACHE_COUNT __pycache__ directories"
fi

# Clean .pyc files
PYC_COUNT=$(find . -name "*.pyc" 2>/dev/null | wc -l)
if [ "$PYC_COUNT" -gt 0 ]; then
    find . -name "*.pyc" -delete
    echo "✓ Removed $PYC_COUNT .pyc files"
fi

# Clean test result files
if [ -f "tests/test_results.json" ]; then
    rm "tests/test_results.json"
    echo "✓ Removed test_results.json"
    ((REMOVED_COUNT++))
fi

echo "=========================================="
if [ "$REMOVED_COUNT" -eq 0 ]; then
    echo "ℹ No test directories found to clean"
else
    echo "✓ Cleaned $REMOVED_COUNT items"
fi
echo "=========================================="