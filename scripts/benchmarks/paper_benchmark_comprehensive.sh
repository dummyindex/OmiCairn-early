#!/bin/bash

# Enhanced Paper Benchmark Script
# Comprehensive benchmarking for technical paper with multiple models and parameters

set -e  # Exit on any error

echo "=================================================="
echo "COMPREHENSIVE PAPER BENCHMARK RUNNER"
echo "=================================================="

# Create output directory
OUTPUT_DIR="paper_benchmark_outputs"
mkdir -p "$OUTPUT_DIR"

# Check for required environment variables
if [[ -z "$OPENAI_API_KEY" ]]; then
    echo "❌ ERROR: OPENAI_API_KEY environment variable is required"
    exit 1
fi

echo "✅ OpenAI API Key found"
if [[ -n "$CLAUDE_API_KEY" ]]; then
    echo "✅ Claude API Key found"
else
    echo "⚠️  Claude API Key not found (optional)"
fi

# Configuration
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$OUTPUT_DIR/paper_benchmark_$TIMESTAMP.log"

echo "📋 Configuration:"
echo "  - Output Directory: $OUTPUT_DIR"
echo "  - Log File: $LOG_FILE"
echo "  - Timestamp: $TIMESTAMP"

# Run comprehensive benchmarking
echo ""
echo "🚀 Starting comprehensive benchmark suite..."
echo "   This will test multiple models and parameter combinations"
echo "   Expected duration: 2-4 hours depending on configuration"

# Option 1: Quick benchmark for testing
if [[ "$1" == "--quick" ]]; then
    echo "🏃 Running QUICK benchmark mode"
    python scripts/benchmarks/paper_benchmark_comprehensive.py \
        --quick \
        --output-dir "$OUTPUT_DIR" \
        --parallel \
        --max-workers 2 \
        --save-prefix "quick_benchmark_$TIMESTAMP" \
        2>&1 | tee "$LOG_FILE"
    
    RESULTS_FILE="$OUTPUT_DIR/quick_benchmark_${TIMESTAMP}_*.json"

# Option 2: Full comprehensive benchmark
elif [[ "$1" == "--full" ]]; then
    echo "📊 Running FULL comprehensive benchmark"
    python scripts/benchmarks/paper_benchmark_comprehensive.py \
        --output-dir "$OUTPUT_DIR" \
        --parallel \
        --max-workers 2 \
        --save-prefix "full_benchmark_$TIMESTAMP" \
        2>&1 | tee "$LOG_FILE"
    
    RESULTS_FILE="$OUTPUT_DIR/full_benchmark_${TIMESTAMP}_*.json"

# Option 3: Custom model selection
elif [[ "$1" == "--models" ]]; then
    shift  # Remove --models from args
    echo "🎯 Running benchmark with specific models: $@"
    python scripts/benchmarks/paper_benchmark_comprehensive.py \
        --models "$@" \
        --output-dir "$OUTPUT_DIR" \
        --parallel \
        --max-workers 2 \
        --save-prefix "custom_models_$TIMESTAMP" \
        2>&1 | tee "$LOG_FILE"
    
    RESULTS_FILE="$OUTPUT_DIR/custom_models_${TIMESTAMP}_*.json"

# Option 4: Specific benchmark types
elif [[ "$1" == "--benchmark-types" ]]; then
    shift  # Remove --benchmark-types from args
    echo "🔬 Running specific benchmark types: $@"
    python scripts/benchmarks/paper_benchmark_comprehensive.py \
        --benchmark-types "$@" \
        --output-dir "$OUTPUT_DIR" \
        --parallel \
        --max-workers 2 \
        --save-prefix "custom_benchmarks_$TIMESTAMP" \
        2>&1 | tee "$LOG_FILE"
    
    RESULTS_FILE="$OUTPUT_DIR/custom_benchmarks_${TIMESTAMP}_*.json"

# Default: Interactive mode
else
    echo "🤖 Interactive benchmark configuration"
    echo ""
    echo "Available options:"
    echo "  1) Quick test (minimal parameters)"
    echo "  2) Full comprehensive benchmark"
    echo "  3) Custom model selection"
    echo "  4) Custom benchmark types"
    echo ""
    read -p "Select option (1-4): " choice
    
    case $choice in
        1)
            echo "Running quick benchmark..."
            python scripts/benchmarks/paper_benchmark_comprehensive.py \
                --quick \
                --output-dir "$OUTPUT_DIR" \
                --parallel \
                --max-workers 2 \
                --save-prefix "interactive_quick_$TIMESTAMP" \
                2>&1 | tee "$LOG_FILE"
            RESULTS_FILE="$OUTPUT_DIR/interactive_quick_${TIMESTAMP}_*.json"
            ;;
        2)
            echo "Running full comprehensive benchmark..."
            python scripts/benchmarks/paper_benchmark_comprehensive.py \
                --output-dir "$OUTPUT_DIR" \
                --parallel \
                --max-workers 2 \
                --save-prefix "interactive_full_$TIMESTAMP" \
                2>&1 | tee "$LOG_FILE"
            RESULTS_FILE="$OUTPUT_DIR/interactive_full_${TIMESTAMP}_*.json"
            ;;
        3)
            echo "Available models: gpt-4o-mini gpt-4o gpt-4-turbo claude-3-5-sonnet-20241022 claude-3-5-haiku-20241022"
            read -p "Enter models (space-separated): " models
            python scripts/benchmarks/paper_benchmark_comprehensive.py \
                --models $models \
                --output-dir "$OUTPUT_DIR" \
                --parallel \
                --max-workers 2 \
                --save-prefix "interactive_models_$TIMESTAMP" \
                2>&1 | tee "$LOG_FILE"
            RESULTS_FILE="$OUTPUT_DIR/interactive_models_${TIMESTAMP}_*.json"
            ;;
        4)
            echo "Available benchmarks: pseudotime clustering annotation spatial-case-1"
            read -p "Enter benchmark types (space-separated): " benchmarks
            python scripts/benchmarks/paper_benchmark_comprehensive.py \
                --benchmark-types $benchmarks \
                --output-dir "$OUTPUT_DIR" \
                --parallel \
                --max-workers 2 \
                --save-prefix "interactive_benchmarks_$TIMESTAMP" \
                2>&1 | tee "$LOG_FILE"
            RESULTS_FILE="$OUTPUT_DIR/interactive_benchmarks_${TIMESTAMP}_*.json"
            ;;
        *)
            echo "Invalid choice. Running default quick benchmark."
            python scripts/benchmarks/paper_benchmark_comprehensive.py \
                --quick \
                --output-dir "$OUTPUT_DIR" \
                --parallel \
                --max-workers 2 \
                --save-prefix "default_quick_$TIMESTAMP" \
                2>&1 | tee "$LOG_FILE"
            RESULTS_FILE="$OUTPUT_DIR/default_quick_${TIMESTAMP}_*.json"
            ;;
    esac
fi

# Check if benchmark completed successfully
if [[ $? -eq 0 ]]; then
    echo ""
    echo "✅ Benchmark completed successfully!"
    
    # Find the results file
    RESULTS_JSON=$(ls "$OUTPUT_DIR"/*_${TIMESTAMP}*.json 2>/dev/null | head -1)
    
    if [[ -f "$RESULTS_JSON" ]]; then
        echo "📊 Results file: $RESULTS_JSON"
        
        echo ""
        echo "BENCHMARK RUN COMPLETE"
        echo "=================================================="
        echo "Benchmark Results: $RESULTS_JSON"
        echo "Log File: $LOG_FILE"
        echo "Note: 'success' means the run completed, not that results were scientifically validated."
        echo "=================================================="
        
        # Show quick summary
        echo ""
        echo "📋 Quick Summary:"
        if command -v jq >/dev/null 2>&1; then
            echo "  - Total Benchmarks: $(jq '.metadata.total_benchmarks' "$RESULTS_JSON")"
            echo "  - Success Rate: $(jq -r '.metadata.successful_benchmarks' "$RESULTS_JSON")/$(jq '.metadata.total_benchmarks' "$RESULTS_JSON") ($(jq -r '(.metadata.successful_benchmarks / .metadata.total_benchmarks * 100 | floor)' "$RESULTS_JSON")%)"
            echo "  - Duration: $(jq -r '.metadata.end_time' "$RESULTS_JSON" | cut -d'T' -f2 | cut -d'.' -f1)"
        else
            echo "  - Install 'jq' for detailed summary"
            echo "  - Check $RESULTS_JSON for full results"
        fi
    else
        echo "⚠️  Results file not found, but benchmark may have succeeded"
        echo "   Check $OUTPUT_DIR for output files"
    fi
else
    echo ""
    echo "❌ Benchmark failed!"
    echo "📋 Check log file for details: $LOG_FILE"
    exit 1
fi

echo ""
echo "🏁 Paper benchmark script completed!"