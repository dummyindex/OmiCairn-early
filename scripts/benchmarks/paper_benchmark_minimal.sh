#!/bin/bash

# Minimal Cost Paper Benchmark Script
# Runs each benchmark task ONCE per model with fixed hyperparameters to minimize API costs
#
# Default configuration (now configurable):
# - Bug fixer attempts: 4 (configurable with --max-trials)
# - Debug turns: 3 (configurable with --debug-turns)
# - Single seed: 31 (configurable with --seed)
# - Domain knowledge: enabled

set -e  # Exit on any error

echo "=================================================="
echo "MINIMAL COST PAPER BENCHMARK"
echo "=================================================="
echo ""
echo "This script runs a minimal set of benchmarks for paper evaluation."
echo "Each task is run ONCE per model with fixed hyperparameters."
echo ""
echo "Default configuration (configurable):"
echo "  - Bug fixer max attempts: 4 (--max-trials)"
echo "  - Debug turns: 3 (--debug-turns)"
echo "  - Seed: 31 (--seed)"
echo "  - Domain knowledge: enabled"
echo ""
echo "=================================================="

# Parse command line arguments first (for help)
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --models MODEL1 MODEL2    Specify models to test (default: gpt-4o-mini)"
    echo "  --tasks TASK1 TASK2       Specify tasks to run (default: all 4 tasks)"
    echo "  --output-dir DIR          Specify output directory (default: paper_benchmark_minimal)"
    echo "  --cheapest                Run only with cheapest model (gpt-4o-mini)"
    echo "  --all-models              Run with all available models (auto-detected)"
    echo "  --full-suite              Run with full fixed list of models (including GPT-5)"
    echo "  --no-domain-knowledge     Disable domain knowledge (adds _noDK suffix to output)"
    echo "  --both-dk-settings        Run experiments both WITH and WITHOUT domain knowledge (doubles # of experiments)"
    echo "  --enable-claude-cli-WebSearch Enable WebSearch tool for Claude CLI models (default: disabled)"
    echo "  --max-nodes NODES         Maximum nodes in the analysis tree (default: varies by benchmark type)"
    echo "  --docker-timeout SECONDS  Docker execution timeout in seconds (default: 1800 = 30 minutes)"
    echo "  --debug-turns TURNS       Number of debug turns per bug fixer session (default: 3)"
    echo "  --max-trials TRIALS       Maximum number of bug fixer sessions per node (default: 4)"
    echo "  --seed SEED               Random seed for reproducibility (default: 31)"
    echo "  --max-iterations ITERS    Maximum planning iterations for orchestrator (default: 20)"
    echo ""
    echo "Examples:"
    echo "  # Run only pseudotime with cheapest model (1 experiment, ~\$0.50)"
    echo "  $0 --tasks pseudotime"
    echo ""
    echo "  # Run pseudotime and clustering with gpt-4o-mini (2 experiments, ~\$1.00)"
    echo "  $0 --tasks pseudotime clustering"
    echo ""
    echo "  # Run only pseudotime with two models (2 experiments, ~\$1.00)"
    echo "  $0 --models gpt-4o-mini gpt-4o --tasks pseudotime"
    echo ""
    echo "  # Run all tasks with cheapest model (4 experiments, ~\$2.00)"
    echo "  $0 --cheapest"
    echo ""
    echo "  # Run pseudotime with and without domain knowledge (2 experiments, ~\$1.00)"
    echo "  $0 --tasks pseudotime --both-dk-settings"
    echo ""
    echo "  # Run with custom hyperparameters"
    echo "  $0 --tasks pseudotime --debug-turns 5 --max-trials 2 --seed 42"
    echo ""
    echo "Available models:"
    echo "  - gpt-4o-mini (cheapest, ~\$0.50/run)"
    echo "  - gpt-4o"
    echo "  - gpt-4-turbo"
    echo "  - gpt-3.5-turbo (cheap)"
    echo "  - claude-3-5-haiku-20241022 (cheap)"
    echo "  - claude-3-5-sonnet-20241022"
    echo "  - claude-cli-haiku (Claude Code CLI - no API key required)"
    echo "  - claude-cli-sonnet (Claude Code CLI - no API key required)"
    echo "  - claude-cli-sonnet-4.5 (Claude Code CLI Sonnet 4.5 - no API key required)"
    echo "  - claude-cli-opus (Claude Code CLI - no API key required)"
    echo ""
    echo "Available tasks:"
    echo "  - pseudotime       (trajectory inference)"
    echo "  - clustering       (cell clustering)"
    echo "  - annotation       (cell type annotation)"
    echo "  - spatial-case-1   (spatial transcriptomics case study 1)"
    echo "  - perturb-seq      (combinatorial perturbation prediction)"
    echo "  - perturb-seq-v2   (combinatorial perturbation prediction with flattened data)"
    echo "  - perturb-norman-analysis (comprehensive Norman CRISPRa analysis)"
    echo ""
    echo "EXPERIMENTS CALCULATION:"
    echo "  Total experiments = (number of models) × (number of tasks)"
    echo "  Cost estimate = Total experiments × \$0.50"
    echo ""
    exit 0
fi

# Default output directory
OUTPUT_DIR="paper_benchmark_minimal"

# Check for required environment variables after parsing arguments to see what models are being used
# Will be checked later after we know which models are requested

# Parse all arguments first
MODELS=""
TASKS=""
USE_ALL_MODELS=false
USE_CHEAPEST=false
USE_FULL_SUITE=false
NO_DOMAIN_KNOWLEDGE=false
BOTH_DK_SETTINGS=false
ENABLE_CLAUDE_CLI_WEBSEARCH=false
MAX_NODES=""
DOCKER_TIMEOUT=""
DEBUG_TURNS=""
MAX_TRIALS=""
SEED=""
MAX_ITERATIONS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --cheapest)
            USE_CHEAPEST=true
            shift
            ;;
        --all-models)
            USE_ALL_MODELS=true
            shift
            ;;
        --full-suite)
            USE_FULL_SUITE=true
            shift
            ;;
        --no-domain-knowledge)
            NO_DOMAIN_KNOWLEDGE=true
            shift
            ;;
        --both-dk-settings)
            BOTH_DK_SETTINGS=true
            shift
            ;;
        --enable-claude-cli-WebSearch)
            ENABLE_CLAUDE_CLI_WEBSEARCH=true
            shift
            ;;
        --max-nodes)
            shift
            MAX_NODES="$1"
            shift
            ;;
        --docker-timeout)
            shift
            DOCKER_TIMEOUT="$1"
            shift
            ;;
        --debug-turns)
            shift
            DEBUG_TURNS="$1"
            shift
            ;;
        --max-trials)
            shift
            MAX_TRIALS="$1"
            shift
            ;;
        --seed)
            shift
            SEED="$1"
            shift
            ;;
        --max-iterations)
            shift
            MAX_ITERATIONS="$1"
            shift
            ;;
        --models)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
                MODELS="$MODELS $1"
                shift
            done
            ;;
        --tasks)
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
                TASKS="$TASKS $1"
                shift
            done
            ;;
        --output-dir)
            shift
            OUTPUT_DIR="$1"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Create output directory after parsing arguments
mkdir -p "$OUTPUT_DIR"

# Configuration (after parsing arguments)
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$OUTPUT_DIR/minimal_benchmark_$TIMESTAMP.log"

echo ""
echo "📋 Configuration:"
echo "  - Output Directory: $OUTPUT_DIR"
echo "  - Log File: $LOG_FILE"
echo "  - Timestamp: $TIMESTAMP"
echo ""

# Determine which models to run
if [[ "$USE_CHEAPEST" == true ]]; then
    echo "🏃 Running with CHEAPEST model only (gpt-4o-mini)"
    MODELS="gpt-4o-mini"
    SAVE_PREFIX="cheapest"
elif [[ "$USE_ALL_MODELS" == true ]]; then
    echo "📊 Running with ALL available models (auto-detected from API keys)"
    # Don't set MODELS - let Python auto-detect based on available API keys
    SAVE_PREFIX="all_models"
elif [[ "$USE_FULL_SUITE" == true ]]; then
    echo "🚀 Running with FULL SUITE of models (including GPT-5 series)"
    # Fixed comprehensive list with all available models
    MODELS="gpt-4o-mini gpt-4o gpt-4-turbo gpt-3.5-turbo gpt-5 gpt-5-mini gpt-5-nano"
    if [[ -n "$CLAUDE_API_KEY" ]]; then
        # Use full model IDs with dates for Claude models
        MODELS="$MODELS claude-3-5-haiku-20241022 claude-3-5-sonnet-20241022"
    fi
    SAVE_PREFIX="full_suite"
elif [[ -n "$MODELS" ]]; then
    echo "🎯 Running with specific models: $MODELS"
    SAVE_PREFIX="custom_models"
else
    # Default: cheapest model only
    echo "📌 Using default: cheapest model (gpt-4o-mini)"
    echo "   Use --all-models to test all available models"
    echo "   Use --full-suite to test complete model list (including GPT-5)"
    echo "   Use --models MODEL1 MODEL2 to specify models"
    MODELS="gpt-4o-mini"
    SAVE_PREFIX="default"
fi

# Build Python command
PYTHON_CMD="python scripts/benchmarks/paper_benchmark_minimal_cost.py"
PYTHON_CMD="$PYTHON_CMD --output-dir $OUTPUT_DIR"
PYTHON_CMD="$PYTHON_CMD --save-prefix ${SAVE_PREFIX}_${TIMESTAMP}"

# Add max-nodes if specified
if [[ -n "$MAX_NODES" ]]; then
    PYTHON_CMD="$PYTHON_CMD --max-nodes $MAX_NODES"
    echo "🔧 Max nodes override: $MAX_NODES"
fi

# Add docker-timeout if specified
if [[ -n "$DOCKER_TIMEOUT" ]]; then
    PYTHON_CMD="$PYTHON_CMD --docker-execution-timeout $DOCKER_TIMEOUT"
    echo "🔧 Docker timeout override: $DOCKER_TIMEOUT seconds"
fi

# Add debug-turns if specified
if [[ -n "$DEBUG_TURNS" ]]; then
    PYTHON_CMD="$PYTHON_CMD --debug-turns $DEBUG_TURNS"
    echo "🔧 Debug turns override: $DEBUG_TURNS"
fi

# Add max-trials if specified
if [[ -n "$MAX_TRIALS" ]]; then
    PYTHON_CMD="$PYTHON_CMD --max-trials $MAX_TRIALS"
    echo "🔧 Max trials override: $MAX_TRIALS"
fi

# Add seed if specified
if [[ -n "$SEED" ]]; then
    PYTHON_CMD="$PYTHON_CMD --seed $SEED"
    echo "🔧 Seed override: $SEED"
fi

# Add max iterations if specified
if [[ -n "$MAX_ITERATIONS" ]]; then
    PYTHON_CMD="$PYTHON_CMD --max-iterations $MAX_ITERATIONS"
    echo "🔧 Max iterations override: $MAX_ITERATIONS"
fi

if [[ -n "$MODELS" ]]; then
    PYTHON_CMD="$PYTHON_CMD --models $MODELS"
fi

# Add tasks if specified
if [[ -n "$TASKS" ]]; then
    PYTHON_CMD="$PYTHON_CMD --benchmark-types $TASKS"
    echo "📝 Running specific tasks: $TASKS"
fi

# Handle domain knowledge settings
if [[ "$BOTH_DK_SETTINGS" == true ]]; then
    PYTHON_CMD="$PYTHON_CMD --both-dk-settings"
    echo "🔄 Running experiments with BOTH domain knowledge settings (enabled AND disabled)"
elif [[ "$NO_DOMAIN_KNOWLEDGE" == true ]]; then
    PYTHON_CMD="$PYTHON_CMD --no-domain-knowledge"
    echo "🚫 Domain knowledge: DISABLED"
else
    echo "✅ Domain knowledge: ENABLED (default)"
fi

# Check if any models are Claude CLI models
HAS_CLAUDE_CLI_MODELS=false
HAS_NON_CLI_MODELS=false
if [[ -n "$MODELS" ]]; then
    for model in $MODELS; do
        if [[ "$model" == claude-cli-* ]]; then
            HAS_CLAUDE_CLI_MODELS=true
        else
            HAS_NON_CLI_MODELS=true
        fi
    done
fi

# Check for required API keys based on models being used
if [[ "$HAS_NON_CLI_MODELS" == true ]]; then
    # Non-CLI models need API keys
    if [[ -z "$OPENAI_API_KEY" && -z "$CLAUDE_API_KEY" ]]; then
        echo "❌ ERROR: API keys required for non-CLI models"
        echo "   Set OPENAI_API_KEY for OpenAI models or CLAUDE_API_KEY for Claude models"
        exit 1
    fi
    
    if [[ -n "$OPENAI_API_KEY" ]]; then
        echo "✅ OpenAI API Key found"
    fi
    if [[ -n "$CLAUDE_API_KEY" ]]; then
        echo "✅ Claude API Key found"
    fi
elif [[ "$HAS_CLAUDE_CLI_MODELS" == true ]]; then
    # Only Claude CLI models - no API keys needed
    echo "🔧 Using Claude CLI models - no API keys required"
else
    echo "❌ ERROR: No valid models specified"
    exit 1
fi

# Add Claude CLI WebSearch flag if specified and relevant
if [[ "$ENABLE_CLAUDE_CLI_WEBSEARCH" == true ]]; then
    if [[ "$HAS_CLAUDE_CLI_MODELS" == true ]]; then
        PYTHON_CMD="$PYTHON_CMD --enable-claude-cli-WebSearch"
        echo "🔍 Claude CLI WebSearch: ENABLED"
    else
        echo "⚠️  Warning: --enable-claude-cli-WebSearch specified but no Claude CLI models detected"
        echo "    This option only affects claude-cli-* models"
    fi
else
    if [[ "$HAS_CLAUDE_CLI_MODELS" == true ]]; then
        echo "🚫 Claude CLI WebSearch: DISABLED (default)"
    fi
fi

# Estimate cost
echo ""
echo "💰 COST ESTIMATE:"

# Count number of models
if [[ -z "$MODELS" ]]; then
    # Will use all available models - count based on API keys
    NUM_MODELS=0
    if [[ -n "$OPENAI_API_KEY" ]]; then
        # OpenAI models: gpt-4o-mini, gpt-4o, gpt-4-turbo, gpt-3.5-turbo, gpt-5, gpt-5-mini, gpt-5-nano
        NUM_MODELS=$((NUM_MODELS + 7))
    fi
    if [[ -n "$CLAUDE_API_KEY" ]]; then
        # Claude models: claude-3-5-haiku-20241022, claude-3-5-sonnet-20241022
        NUM_MODELS=$((NUM_MODELS + 2))
    fi
    if [[ $NUM_MODELS -eq 0 ]]; then
        echo "❌ ERROR: No API keys found. Cannot auto-detect models."
        exit 1
    fi
else
    NUM_MODELS=$(echo $MODELS | wc -w | tr -d ' ')
fi

# Count number of tasks
if [[ -n "$TASKS" ]]; then
    NUM_TASKS=$(echo $TASKS | wc -w | tr -d ' ')
else
    NUM_TASKS=7  # All tasks (including perturb-seq, perturb-seq-v2, and perturb-norman-analysis)
fi

# Calculate total runs and cost
TOTAL_RUNS=$((NUM_MODELS * NUM_TASKS))
# Double the runs if using both DK settings
if [[ "$BOTH_DK_SETTINGS" == true ]]; then
    TOTAL_RUNS=$((TOTAL_RUNS * 2))
    DK_MULTIPLIER="× 2 DK settings "
else
    DK_MULTIPLIER=""
fi
ESTIMATED_COST=$(echo "scale=2; $TOTAL_RUNS * 0.5" | bc)

echo "   - $NUM_MODELS model(s) × $NUM_TASKS task(s) ${DK_MULTIPLIER}× 1 run = $TOTAL_RUNS total experiment(s)"
echo "   - Estimated cost: ~\$$ESTIMATED_COST (at ~\$0.50 per run)"
echo ""
echo "   Breakdown:"
if [[ -z "$MODELS" ]]; then
    echo -n "   - Models: auto-detected ("
    if [[ -n "$OPENAI_API_KEY" ]]; then
        echo -n "7 OpenAI"
    fi
    if [[ -n "$OPENAI_API_KEY" && -n "$CLAUDE_API_KEY" ]]; then
        echo -n " + "
    fi
    if [[ -n "$CLAUDE_API_KEY" ]]; then
        echo -n "2 Claude"
    fi
    echo ")"
    echo "     OpenAI: gpt-4o-mini, gpt-4o, gpt-4-turbo, gpt-3.5-turbo, gpt-5, gpt-5-mini, gpt-5-nano"
    if [[ -n "$CLAUDE_API_KEY" ]]; then
        echo "     Claude: claude-3-5-haiku-20241022, claude-3-5-sonnet-20241022"
    fi
else
    echo "   - Models: $MODELS"
fi
echo "   - Tasks: ${TASKS:-all (pseudotime, clustering, annotation, spatial-case-1, perturb-seq, perturb-seq-v2, perturb-norman-analysis)}"

echo ""
read -p "Continue with benchmark? (y/n): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Benchmark cancelled."
    exit 0
fi

# Run the benchmark
echo ""
echo "🚀 Starting minimal cost benchmark..."
echo ""
echo "📝 Full command:"
echo "   $PYTHON_CMD"
echo ""

# Execute with logging
$PYTHON_CMD 2>&1 | tee "$LOG_FILE"

# Check if benchmark completed successfully
if [[ ${PIPESTATUS[0]} -eq 0 ]]; then
    echo ""
    echo "✅ Minimal cost benchmark completed successfully!"
    echo ""
    
    # Find the results file
    RESULTS_JSON=$(ls "$OUTPUT_DIR"/*_${TIMESTAMP}*.json 2>/dev/null | head -1)
    
    if [[ -f "$RESULTS_JSON" ]]; then
        echo "📊 Results saved to: $RESULTS_JSON"
        
        # Show quick summary if jq is available
        if command -v jq >/dev/null 2>&1; then
            echo ""
            echo "📋 Quick Summary:"
            echo "  - Total runs: $(jq '.metadata.total_benchmarks' "$RESULTS_JSON")"
            echo "  - Successful: $(jq '.metadata.successful_benchmarks' "$RESULTS_JSON")"
            echo "  - Success rate: $(jq -r '.metadata.success_rate * 100 | floor' "$RESULTS_JSON")%"
            echo "  - Total duration: $(jq -r '.metadata.total_duration | floor' "$RESULTS_JSON") seconds"
        fi
    fi
    
    echo ""
    echo "📋 Log file: $LOG_FILE"
    echo ""
    echo "🎉 MINIMAL COST BENCHMARK COMPLETE!"
    echo "=================================================="
else
    echo ""
    echo "❌ Benchmark failed!"
    echo "📋 Check log file for details: $LOG_FILE"
    exit 1
fi