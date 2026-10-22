# Clustering Tests

This directory contains clustering benchmark tests for the OmiCairn Agent system.

## Test Files

### 1. `test_clustering_simulation.py`
- **Type**: Simulation test (no LLM required)
- **Purpose**: Tests the clustering benchmark pipeline with predefined function blocks
- **Features**:
  - Creates synthetic test data if not available
  - Runs complete clustering pipeline (QC → Normalization → PCA → UMAP → Clustering → Metrics → Report)
  - Tests multiple clustering methods (Leiden, Louvain with different resolutions)
  - Calculates clustering metrics (ARI, NMI, Silhouette score)
  - Generates reports and visualizations
  - Uses the new `run(path_dict, params)` function block signature
  - No LLM/API calls required

### 2. `test_clustering_benchmark_llm.py` 
- **Location**: `tests/llm_required/test_clustering_benchmark_llm.py`
- **Type**: LLM-based test (requires OpenAI API)
- **Purpose**: Tests clustering benchmark using Main Agent with GPT-4o-mini

## Running Tests

### Run simulation test (no API required):
```bash
python tests/clustering/test_clustering_simulation.py
```

### Run LLM-based test (requires OpenAI API):
```bash
# Set API key first
export OPENAI_API_KEY="your-api-key"

python tests/llm_required/test_clustering_benchmark_llm.py
```

## Test Outputs

Tests create outputs in `test_outputs/clustering_simulation/` with the following structure:

```
test_outputs/clustering_simulation/run_<timestamp>/
├── analysis_tree.json              # Pipeline structure
├── <tree_id>/
│   └── nodes/
│       └── node_<node_id>/         # One per pipeline step
│           ├── function_block/     # Function block code
│           ├── jobs/               # Execution jobs
│           │   └── job_<timestamp>/
│           │       ├── input/      # Input data
│           │       ├── output/     # Output data
│           │       │   ├── _node_anndata.h5ad
│           │       │   ├── clustering_metrics.csv
│           │       │   ├── clustering_report.txt
│           │       │   └── figures/
│           │       └── logs/       # Execution logs
│           └── outputs/           # Final outputs
```

## Expected Results

A successful test run should:
1. Complete all 7 pipeline nodes (QC, Normalization, PCA, UMAP, Clustering, Metrics, Report)
2. Generate 5 clustering results (3 Leiden + 2 Louvain)
3. Calculate metrics for each method (ARI, NMI, Silhouette)
4. Create visualization figures (UMAP plots, metrics comparison)
5. Generate a summary report with best performing methods

## Test Data

If test data doesn't exist, the simulation automatically creates synthetic data with:
- 500 cells
- 2000 genes
- 3 cell types (TypeA, TypeB, TypeC)
- 2 batches (Batch1, Batch2)
- 20 mitochondrial genes (marked with 'MT-' prefix)

## Key Changes

All tests now use the new function block signature:
```python
def run(path_dict, params):
    # path_dict contains input_dir and output_dir
    # params is passed directly as a dictionary
```

This is a breaking change from the old signature that used `path_dict` with file paths.