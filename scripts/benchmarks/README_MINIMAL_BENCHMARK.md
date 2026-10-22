# Minimal Cost Paper Benchmark

## Overview

The minimal cost benchmark suite is designed to evaluate the system for paper publication with **minimal API costs**. Unlike the comprehensive benchmark that runs multiple parameter combinations and seeds, this minimal version runs each benchmark task **exactly once** per model with fixed default hyperparameters chosen a priori to limit API cost (they were not tuned on benchmark outcomes).

> Note: this document is from an early-stage research version and may be partly outdated relative to the scripts (task and model lists). The benchmarks measure execution completion, not scientific accuracy.

## Key Features

- **Single run per model/task**: No parameter sweeps or multiple seeds
- **Fixed hyperparameters**: chosen a priori to limit cost
  - Bug fixer max attempts: 4
  - Debug turns: 3
  - Seed: 31
  - Domain knowledge: enabled
- **Cost estimate**: ~$0.50 per benchmark run
- **Total cost**: ~$2 for single model, ~$8 for all 4 tasks with 4 models

## Scripts

### 1. `paper_benchmark_minimal.sh`

Interactive shell script for running the minimal benchmark.

```bash
# Run with cheapest model only (gpt-4o-mini)
./scripts/benchmarks/paper_benchmark_minimal.sh --cheapest

# Run with all available models
./scripts/benchmarks/paper_benchmark_minimal.sh --all-models

# Run with specific models
./scripts/benchmarks/paper_benchmark_minimal.sh --models gpt-4o-mini gpt-4o

# Run specific tasks only
./scripts/benchmarks/paper_benchmark_minimal.sh --tasks pseudotime clustering

# Show help
./scripts/benchmarks/paper_benchmark_minimal.sh --help
```

### 2. `paper_benchmark_minimal_cost.py`

Python script that implements the minimal benchmark logic.

```bash
# Run with default (gpt-4o-mini, all tasks)
python scripts/benchmarks/paper_benchmark_minimal_cost.py

# Specify models
python scripts/benchmarks/paper_benchmark_minimal_cost.py --models gpt-4o-mini gpt-4o

# Specify tasks
python scripts/benchmarks/paper_benchmark_minimal_cost.py --benchmark-types pseudotime clustering

# Custom output directory
python scripts/benchmarks/paper_benchmark_minimal_cost.py --output-dir my_results
```

## Benchmark Tasks

1. **Pseudotime**: Trajectory inference analysis
2. **Clustering**: Cell clustering analysis
3. **Annotation**: Cell type annotation
4. **Spatial**: Spatial transcriptomics analysis

## Models Supported

### OpenAI Models (requires `OPENAI_API_KEY`)
- `gpt-4o-mini` (cheapest, ~$0.15/1M tokens)
- `gpt-4o` (balanced performance)
- `gpt-4-turbo` (older, still effective)

### Claude Models (requires `CLAUDE_API_KEY`)
- `claude-3-5-haiku-20241022` (cheaper, released Oct 22, 2024)
- `claude-3-5-sonnet-20241022` (more capable, updated Oct 22, 2024)
- `claude-3-haiku-20240307` (older, stable version)
- `claude-3-5-sonnet-20240620` (June 2024 release)

## Experiment Count & Cost Breakdown

### Formula
**Total Experiments = (Number of Models) × (Number of Tasks) × 1 run each**

### Common Configurations

| Configuration | Models | Tasks | Total Experiments | Estimated Cost |
|--------------|--------|-------|-------------------|----------------|
| **Minimal (pseudotime only)** | 1 (gpt-4o-mini) | 1 (pseudotime) | **1** | ~$0.50 |
| **Single task, all models** | 5 | 1 | **5** | ~$2.50 |
| **Two tasks, one model** | 1 | 2 | **2** | ~$1.00 |
| **Default (one model, all tasks)** | 1 | 4 | **4** | ~$2.00 |
| **Two models, all tasks** | 2 | 4 | **8** | ~$4.00 |
| **Comprehensive (all models, all tasks)** | 5 | 4 | **20** | ~$10.00 |

### Task-Specific Runs

To run only specific tasks (reducing experiment count):

```bash
# Run ONLY pseudotime with cheapest model (1 experiment, ~$0.50)
./scripts/benchmarks/paper_benchmark_minimal.sh --tasks pseudotime

# Run pseudotime AND clustering (2 experiments, ~$1.00)
./scripts/benchmarks/paper_benchmark_minimal.sh --tasks pseudotime clustering

# Run pseudotime with TWO models (2 experiments, ~$1.00)
./scripts/benchmarks/paper_benchmark_minimal.sh --models gpt-4o-mini gpt-4o --tasks pseudotime

# Use the dedicated single pseudotime script (1 experiment, ~$0.50)
./scripts/benchmarks/run_single_pseudotime.sh
```

## Output Structure

```
paper_benchmark_minimal/
├── minimal_benchmark_TIMESTAMP.log      # Execution log
├── minimal_benchmark_results_TIMESTAMP.json  # Results summary
└── benchmark_runs/                      # Individual run outputs
    ├── minimal_gpt_4o_mini_pseudotime/
    ├── minimal_gpt_4o_mini_clustering/
    └── ...
```

## Results Format

The results JSON contains:
- **metadata**: Overall statistics, timing, configuration
- **results**: Individual benchmark results
- **summary_by_model**: Performance grouped by model
- **summary_by_benchmark**: Performance grouped by task

Example:
```json
{
  "metadata": {
    "type": "minimal_cost_benchmark",
    "total_benchmarks": 4,
    "successful_benchmarks": 3,
    "success_rate": 0.75,
    "fixed_parameters": {
      "debug_turns": 3,
      "max_trials": 4,
      "seed": 31
    }
  },
  "results": [...],
  "summary_by_model": {...},
  "summary_by_benchmark": {...}
}
```

## Comparison with Comprehensive Benchmark

| Aspect | Minimal | Comprehensive |
|--------|---------|---------------|
| Runs per config | 1 | Multiple seeds (3) |
| Parameter combinations | Fixed (1) | Grid search (6+) |
| Domain knowledge | Always on | With/without ablation |
| Estimated cost (4 tasks) | ~$2 | ~$50+ |
| Runtime | ~30 min | ~4 hours |
| Statistical significance | No | Yes |

## When to Use

### Use Minimal Benchmark for:
- Quick evaluation of system changes
- Initial testing of new models
- Cost-conscious evaluation
- Single-point performance metrics
- Development and debugging

### Use Comprehensive Benchmark for:
- Paper publication data
- Statistical analysis
- Parameter sensitivity studies
- Domain knowledge ablation studies
- Reproducibility studies (multiple seeds)

## Quick Start

1. Set up API keys:
```bash
export OPENAI_API_KEY="your-key"
export CLAUDE_API_KEY="your-key"  # Optional
```

2. Run minimal benchmark with cheapest model:
```bash
./scripts/benchmarks/paper_benchmark_minimal.sh --cheapest
```

3. View results:
```bash
cat paper_benchmark_minimal/minimal_benchmark_results_*.json | jq '.metadata'
```

## Tips for Cost Reduction

1. **Start with cheapest model**: Use `gpt-4o-mini` for initial tests
2. **Run single tasks**: Test one benchmark type at a time
3. **Monitor costs**: Check the cost estimate before confirming
4. **Use fixed parameters**: The parameters (3 turns, 4 attempts) were fixed in advance to limit API cost
5. **Sequential execution**: Runs tasks one by one to avoid rate limits

## Troubleshooting

### Common Issues

1. **API Key Missing**
   ```
   ERROR: OPENAI_API_KEY environment variable is required
   ```
   Solution: `export OPENAI_API_KEY="your-key"`

2. **Rate Limits**
   - The script runs sequentially with 2-second pauses
   - If rate limited, wait and retry

3. **Docker Issues**
   - Ensure Docker is running
   - Check Docker images are built: `make docker-build-minimal`

## Development

To modify the fixed parameters, edit these constants in `paper_benchmark_minimal_cost.py`:

```python
FIXED_DEBUG_TURNS = 3      # Bug fixer debug turns
FIXED_MAX_TRIALS = 4       # Bug fixer max attempts
FIXED_SEED = 31           # Random seed
ENABLE_DOMAIN_KNOWLEDGE = True  # Domain knowledge flag
```

## Summary

The minimal cost benchmark provides a budget-friendly way to evaluate the system's performance across different models and tasks. With fixed default parameters and single runs, it gives indicative results at a fraction of the cost of comprehensive benchmarking.