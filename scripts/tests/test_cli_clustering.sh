#!/bin/bash
# Test CLI with clustering benchmark request

# User request for clustering benchmark
USER_REQUEST="Your job is to benchmark different clustering methods on the given dataset. Process scRNA-seq data. Calculate UMAP visualization first with different parameters. Then process the single-cell genomics data. Run at least five clustering methods, and calculate multiple metrics for each clustering method, better based on the ground-truth cell type key provided in the cell meta data. Save the metrics results to anndata object, and output to outputs/."

# Input data
INPUT_FILE="test_data/zebrafish.h5ad"

# Output directory with timestamp
OUTPUT_DIR="test_outputs/cli_clustering_$(date +%Y%m%d_%H%M%S)"

echo "=========================================="
echo "TESTING CLI WITH CLUSTERING BENCHMARK"
echo "=========================================="
echo ""
echo "Input: $INPUT_FILE"
echo "Output: $OUTPUT_DIR"
echo ""
echo "User Request:"
echo "$USER_REQUEST"
echo ""
echo "=========================================="
echo ""

# Run the CLI command
python -m omicairn_agent_local.cli analyze \
    "$INPUT_FILE" \
    "$USER_REQUEST" \
    --output "$OUTPUT_DIR" \
    --max-nodes 10 \
    --max-children 1 \
    --mode only_new \
    --model gpt-4o-mini \
    --verbose

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ CLI test completed successfully!"
    echo "📁 Results saved to: $OUTPUT_DIR"
else
    echo ""
    echo "❌ CLI test failed!"
    exit 1
fi