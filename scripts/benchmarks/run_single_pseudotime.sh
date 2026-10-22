#!/bin/bash

# Example: Run ONLY pseudotime benchmark with minimal cost
# This runs just 1 experiment with the cheapest model (gpt-4o-mini)
# Estimated cost: ~$0.50

set -e

echo "=================================================="
echo "SINGLE PSEUDOTIME BENCHMARK (Minimal Cost)"
echo "=================================================="
echo ""
echo "This will run ONLY the pseudotime benchmark with gpt-4o-mini"
echo "Total experiments: 1"
echo "Estimated cost: ~\$0.50"
echo ""

# Check for API key
if [[ -z "$OPENAI_API_KEY" ]]; then
    echo "❌ ERROR: OPENAI_API_KEY is required"
    echo "Set it with: export OPENAI_API_KEY='your-key'"
    exit 1
fi

echo "✅ OpenAI API key found"
echo ""

# Run the benchmark
echo "Starting pseudotime benchmark..."
python scripts/benchmarks/paper_benchmark_minimal_cost.py \
    --models gpt-4o-mini \
    --benchmark-types pseudotime \
    --output-dir paper_benchmark_pseudotime \
    --save-prefix pseudotime_only

echo ""
echo "✅ Pseudotime benchmark complete!"
echo "Results saved in: paper_benchmark_pseudotime/"