# Function Block Framework

## Overview

This document defines the standardized framework and conventions for function blocks in the OmiCairn Agent system for various data analysis workflows.

## Core Principles

### 1. Data Flow Convention

All function blocks follow a standardized input/output pattern:

```
Parent Node Outputs → Child Node Inputs → Processing → Child Node Outputs
```

**Key Rules:**
- ALL files in a parent node's `outputs/` folder automatically pass to child nodes' `input/` folder
- Child nodes receive ALL parent outputs in their `/workspace/input/` directory
- No explicit file path configuration needed between nodes
- Function blocks can use any appropriate filename based on their data type and analysis:
  - CSV files: `results.csv`, `processed_data.csv`, etc.
  - JSON files: `analysis_output.json`, `metadata.json`, etc.
  - H5AD files (for single-cell): `_node_anndata.h5ad` or descriptive names
  - RDS files (for R objects): `_node_seuratObject.rds` or descriptive names
  - Any other format as needed by the analysis
- **OUTPUT IS IMPORTANT**: Function blocks should create their output file for the pipeline to continue
- If the output file is not created, subsequent nodes will fail with "file not found"

### 2. Data Processing Convention

For data analysis workflows, function blocks **MUST** follow these conventions:

#### NEW FRAMEWORK CONVENTION (PATH_DICT + PARAMS)
```python
def run(path_dict, params):
    """Function block for data analysis.
    
    Args:
        path_dict: Dictionary containing paths:
            - input_dir: Input directory path
            - output_dir: Output directory path
        params: Dictionary of parameters for this function block
    """
    import os
    
    # Check available input files
    input_files = os.listdir(path_dict["input_dir"])
    print(f"Available input files: {input_files}")
    
    # Load appropriate files based on analysis needs
    # Examples:
    # - For CSV: pd.read_csv(os.path.join(path_dict["input_dir"], "data.csv"))
    # - For JSON: json.load(open(os.path.join(path_dict["input_dir"], "data.json")))
    # - For H5AD: sc.read_h5ad(os.path.join(path_dict["input_dir"], "data.h5ad"))
    
    # Process data using params
    # params is already a dictionary, no need to load from file
    
    # Save outputs with descriptive names
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    # Save your results in appropriate format
    
    # No return value needed - output is written to file
```

#### File Naming Guidelines
- **Be Flexible**: Check what files are available and adapt accordingly
- **Use Descriptive Names**: Name output files based on what they contain
- **Common Patterns**:
  - CSV data: `processed_data.csv`, `results.csv`
  - JSON data: `analysis_output.json`, `metadata.json`
  - Single-cell data: `_node_anndata.h5ad` (Python), `_node_seuratObject.rds` (R)
  - But any naming scheme that clearly describes the content is acceptable

### 3. Standard Directory Structure

Each node execution creates this structure:

```
node_NODE_ID/
├── function_block/     # Function block definition
│   ├── code.py (Python) or code.R (R)
│   ├── config.json
│   └── requirements.txt (dependencies - see note below)
├── jobs/              # Execution jobs
│   └── job_TIMESTAMP/
│       ├── input/     # ALL files from parent's outputs/ folder
│       │   └── ...    # Files with original names from parent
│       └── output/    # Output data
│           └── ...    # Files created by function block
│           └── figures/
├── outputs/           # Final outputs (copied from job)
│   └── figures/
└── agent_tasks/       # LLM interactions only
```

**Note on Dependencies**:
- **Python**: `requirements.txt` contains pip packages and is used directly
- **R**: `requirements.txt` contains R package names but is NOT used directly. Instead:
  - The R executor reads the `requirements` field from the function block
  - Dynamically generates `install_packages.R` with proper installation commands
  - Supports CRAN (`packagename`), Bioconductor (`Bioconductor::packagename`), and GitHub (`user/repo`) packages

## Function Block Template

### Python Function Block Template (PATH_DICT + PARAMS)

```python
def run(path_dict, params):
    """
    Standard function block for data analysis.
    
    Args:
        path_dict: Dictionary with paths:
            - input_dir: Input directory
            - output_dir: Output directory
        params: Dictionary of parameters
    """
    import os
    import glob
    import scanpy as sc
    import matplotlib.pyplot as plt
    
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    # Check available input files
    input_files = os.listdir(path_dict["input_dir"])
    print(f"Available input files: {input_files}")
    
    # Find and load appropriate files based on your analysis needs
    # This is just an example - adapt to your specific requirements
    
    # Ensure output directories exist
    figures_dir = os.path.join(path_dict["output_dir"], "figures")
    os.makedirs(figures_dir, exist_ok=True)
    
    # Load input data from standard location
    print(f"Loading data from {input_file}")
    adata = sc.read_h5ad(input_file)
    print(f"Input data shape: {adata.shape}")
    
    # ========================================
    # MAIN PROCESSING LOGIC HERE
    # ========================================
    
    # Example: Quality control using params directly
    if params.get('perform_qc', False):
        sc.pp.filter_cells(adata, min_genes=params.get('min_genes', 200))
        sc.pp.filter_genes(adata, min_cells=params.get('min_cells', 3))
    
    # ========================================
    # SAVE OUTPUTS
    # ========================================
    
    # Save processed data with standard name
    print(f"Saving processed data to {output_file}")
    adata.write(output_file)
    
    # Save any figures
    if params.get('generate_plots', False):
        fig, ax = plt.subplots(figsize=(10, 6))
        # ... plotting code ...
        plt.savefig(os.path.join(figures_dir, 'analysis_plot.png'), dpi=150, bbox_inches='tight')
        plt.close()
    
    print(f"Output data shape: {adata.shape}")
    # No return value needed - output is written to file
```

### R Function Block Template (PATH_DICT + PARAMS)

```r
run <- function(path_dict, params) {
    # Function block with path dictionary and parameters
    # path_dict contains:
    #   - input_dir: Input directory
    #   - output_dir: Output directory
    # params is a list of parameters
    
    # Load required libraries
    library(Seurat)
    
    # Construct standard file paths
    input_r <- file.path(path_dict$input_dir, "_node_seuratObject.rds")
    input_py <- file.path(path_dict$input_dir, "_node_anndata.h5ad")
    output_r <- file.path(path_dict$output_dir, "_node_seuratObject.rds")
    output_py <- file.path(path_dict$output_dir, "_node_anndata.h5ad")
    
    # Create output directories
    figures_dir <- file.path(path_dict$output_dir, "figures")
    dir.create(figures_dir, recursive = TRUE, showWarnings = FALSE)
    
    # Load input data from standard location
    # Try standard R object name first
    if (file.exists(input_r)) {
        cat(paste("Loading Seurat object from", input_r, "\n"))
        seurat_obj <- readRDS(input_r)
    } else if (file.exists(input_py)) {
        # Load from Python parent node
        library(anndata)
        cat(paste("Loading from h5ad:", input_py, "\n"))
        adata <- read_h5ad(input_py)
        # Convert to Seurat object
        seurat_obj <- CreateSeuratObject(counts = adata$X)
        # Transfer metadata if available
        if (!is.null(adata$obs)) {
            seurat_obj@meta.data <- cbind(seurat_obj@meta.data, adata$obs)
        }
    } else {
        stop(paste("No input data found in", path_dict$input_dir))
    }
    
    # ========================================
    # MAIN PROCESSING LOGIC HERE
    # ========================================
    
    # Example: Normalization using params directly
    if (!is.null(params$normalize) && params$normalize) {
        seurat_obj <- NormalizeData(seurat_obj)
    }
    
    # ========================================
    # SAVE OUTPUTS
    # ========================================
    
    # Save Seurat object with standard name
    cat(paste("Saving Seurat object to", output_r, "\n"))
    saveRDS(seurat_obj, output_r)
    
    # Optionally also save as h5ad for Python compatibility
    if (!is.null(params$save_h5ad) && params$save_h5ad) {
        library(anndata)
        adata <- Convert(from = seurat_obj, to = "anndata")
        write_h5ad(adata, output_py)
    }
    
    # No return value needed - output is written to file
}
```

## File Passing Rules

### Automatic File Passing

1. **Parent → Child Transfer**
   - ALL files in parent's `outputs/` folder are copied to child's `input/` folder
   - Python nodes: `_node_anndata.h5ad` is the standard data file
   - R nodes: `_node_seuratObject.rds` is the standard data file
   - ALL supplementary files preserved with original names

2. **Multi-Parent Handling**
   - When a node has multiple parents, inputs are merged or selected based on node logic
   - Convention: Use the most recent parent's output as primary input

3. **File Discovery Priority**
   ```python
   # Python: Priority order for finding input data
   search_order = [
       '/workspace/input/_node_anndata.h5ad',  # Standard Python data
       'any .h5ad file in /workspace/input/',  # Any h5ad from parent
   ]
   
   # R: Priority order for finding input data
   search_order = [
       '/workspace/input/_node_seuratObject.rds',  # Standard R data
       'any .rds file in /workspace/input/',       # Any RDS from parent
       'any .h5ad file (convert to Seurat)',       # Cross-language support
   ]
   ```

## Best Practices

### 1. Always Check Input Existence

```python
import os

if not os.path.exists('/workspace/input/_node_anndata.h5ad'):
    print("Warning: No input data found, using alternative source")
    # Handle missing input appropriately
```

### 2. Preserve Data Lineage

```python
# Add processing history to adata
adata.uns['processing_history'] = adata.uns.get('processing_history', [])
adata.uns['processing_history'].append({
    'step': 'current_analysis',
    'timestamp': str(datetime.now()),
    'parameters': parameters
})
```

### 3. Handle Large Files Efficiently

```python
# For large datasets, use backed mode when possible
adata = sc.read_h5ad('/workspace/input/_node_anndata.h5ad', backed='r')
# Process in chunks if needed
```

### 4. Validate Outputs

```python
# Always validate output before saving
assert adata.n_obs > 0, "Output has no cells"
assert adata.n_vars > 0, "Output has no genes"

# Save with compression
adata.write('/workspace/output/_node_anndata.h5ad', compression='gzip')
```

### 5. Error Handling - NEVER Hide Errors

**CRITICAL**: Do not use try-except blocks to mask problems. Fix the root cause instead.

```python
# ❌ WRONG - Hiding errors with try-except
try:
    result = risky_operation()
except:
    pass  # This hides the real problem!
    
# ❌ WRONG - Using fallback to avoid fixing issues
try:
    adata = sc.read_h5ad(input_file)
except:
    # Just create empty data to avoid error
    adata = sc.AnnData()  # This masks the real issue!

# ✅ CORRECT - Validate and fail with clear message
if not os.path.exists(input_file):
    raise FileNotFoundError(f"Input file not found: {input_file}")
    
# ✅ CORRECT - Log errors and re-raise
try:
    result = external_api_call()
except Exception as e:
    logger.error(f"API call failed: {e}")
    raise  # Re-raise to preserve error visibility

# ✅ CORRECT - Validate inputs with helpful messages
if 'required_column' not in adata.obs:
    available = list(adata.obs.columns)
    raise ValueError(f"Required column 'required_column' not found. Available: {available}")
```

**Key Principles**:
- Fix the root cause, don't mask symptoms
- Fail fast with descriptive error messages
- Log errors before re-raising
- Help users understand what went wrong
- The goal is correct outputs, not avoiding crashes

### 6. Document Parameters

```python
def run(path_dict, params):
    """
    Comprehensive docstring explaining:
    - What the function does
    - path_dict contains input/output directories
    - params contains all parameters
    - Expected input format: _node_anndata.h5ad in input_dir
    - Output format: _node_anndata.h5ad in output_dir
    
    Args:
        path_dict: Dictionary with keys:
            - input_dir: Input directory path
            - output_dir: Output directory path
        params: Dictionary with parameters:
            - min_genes: int, default 200 - minimum genes per cell
            - max_genes: int, default 5000 - maximum genes per cell  
            - max_mt_percent: float, default 20 - maximum mitochondrial percentage
    """
    # Use parameters directly with defaults
    min_genes = params.get('min_genes', 200)
    max_genes = params.get('max_genes', 5000)
    max_mt_percent = params.get('max_mt_percent', 20)
```

## Integration with Agents

### Function Creator Agent

When creating new function blocks, the agent MUST:
1. Follow the standard template above
2. Include data loading from `/workspace/input/_node_anndata.h5ad`
3. Save outputs to `/workspace/output/_node_anndata.h5ad`
4. Handle missing inputs gracefully

### Bug Fixer Agent

When fixing function blocks, the agent MUST:
1. Preserve the input/output conventions
2. Check for file existence before operations
3. Ensure output directories exist
4. Maintain data flow compatibility

### Orchestrator Agent

The orchestrator MUST:
1. Ensure parent outputs are available to child nodes
2. Validate data flow between nodes
3. Handle multi-parent scenarios appropriately

## Validation Checklist

Before deploying a function block, verify:

- [ ] Loads data from `/workspace/input/_node_anndata.h5ad` when not provided
- [ ] Saves primary output to `/workspace/output/_node_anndata.h5ad`
- [ ] Creates output directories if they don't exist
- [ ] Handles missing input files gracefully
- [ ] Preserves data shape information in logs
- [ ] Includes appropriate error handling
- [ ] Follows naming conventions
- [ ] Documents all parameters
- [ ] Validates output before saving

## Common Patterns

### Pattern 1: Quality Control
```python
def run(path_dict, params):
    # Load data → Filter → Save
    import scanpy as sc
    import os
    
    # Construct file paths
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    adata = sc.read_h5ad(input_file)
    
    min_genes = params.get('min_genes', 200)
    max_genes = params.get('max_genes', 5000)
    
    # Process...
    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_genes(adata, min_cells=3)
    
    adata.write(output_file)
```

### Pattern 2: Normalization
```python
def run(path_dict, params):
    # Load data → Normalize → Log-transform → Save
    import scanpy as sc
    import os
    
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    adata = sc.read_h5ad(input_file)
    target_sum = params.get('target_sum', 1e4)
    
    # Normalize and save
    sc.pp.normalize_total(adata, target_sum=target_sum)
    sc.pp.log1p(adata)
    adata.write(output_file)
```

### Pattern 3: Dimensionality Reduction
```python
def run(path_dict, params):
    # Load data → PCA/UMAP → Save with embeddings
    import scanpy as sc
    import os
    
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    adata = sc.read_h5ad(input_file)
    n_components = params.get('n_components', 50)
    
    # PCA and save
    sc.tl.pca(adata, n_comps=n_components)
    adata.write(output_file)
```

### Pattern 4: Clustering
```python
def run(path_dict, params):
    # Load data → Cluster → Save with labels
    import scanpy as sc
    import os
    
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    adata = sc.read_h5ad(input_file)
    resolution = params.get('resolution', 0.5)
    
    # Cluster and save
    sc.tl.leiden(adata, resolution=resolution)
    adata.write(output_file)
```

### Pattern 5: Differential Expression
```python
def run(path_dict, params):
    # Load data → Compare groups → Save with DE results
    import scanpy as sc
    import os
    
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    adata = sc.read_h5ad(input_file)
    group_by = params.get('group_by', 'leiden')
    
    # DE analysis and save
    sc.tl.rank_genes_groups(adata, group_by)
    adata.write(output_file)
```

## Error Handling

### Standard Error Messages

```python
# File not found
raise FileNotFoundError(
    "Input data not found at /workspace/input/_node_anndata.h5ad. "
    "Ensure parent node completed successfully."
)

# Invalid input
raise ValueError(
    f"Expected AnnData object, got {type(adata)}. "
    "Check data loading logic."
)

# Output failure
raise IOError(
    f"Failed to save output to /workspace/output/_node_anndata.h5ad. "
    "Check disk space and permissions."
)
```

## Testing Requirements

All function blocks MUST be tested for:

1. **Input handling**: Missing files, corrupted data, wrong format
2. **Processing logic**: Expected transformations, edge cases
3. **Output generation**: File creation, correct format, accessibility
4. **Parameter validation**: Type checking, range validation
5. **Error scenarios**: Graceful failures, informative messages

## Version Compatibility

- **AnnData**: >= 0.8.0
- **Scanpy**: >= 1.9.0
- **Python**: >= 3.8
- **R**: >= 4.0 (for R function blocks)

## References

- [AnnData Documentation](https://anndata.readthedocs.io/)
- [Scanpy Best Practices](https://scanpy.readthedocs.io/en/stable/tutorials.html)
- [Single-cell Best Practices Book](https://www.sc-best-practices.org/)

---

*This framework ensures consistent, reliable data flow through the analysis pipeline while maintaining flexibility for diverse analytical approaches.*