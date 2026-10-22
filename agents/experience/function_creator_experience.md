# Function Creator Experience and Best Practices

This document contains accumulated experience from creating function blocks for single-cell RNA-seq analysis pipelines. These patterns lead to more robust and error-free implementations.

## Critical Implementation Patterns

### 1. Always Include Required Imports
```python
def run(path_dict, params):
    import scanpy as sc
    import pandas as pd
    import numpy as np
    import os
    from pathlib import Path
    import matplotlib.pyplot as plt
    
    # Set matplotlib backend for containers
    plt.switch_backend('Agg')
```

### 2. Robust Input File Handling
```python
# Don't assume the filename - check what's available
input_files = list(Path(path_dict['input_dir']).glob('*.h5ad'))
if not input_files:
    raise FileNotFoundError(f"No .h5ad files found in {path_dict['input_dir']}")

# Use the standard name if it exists, otherwise use the first h5ad file
standard_input = Path(path_dict['input_dir']) / '_node_anndata.h5ad'
if standard_input.exists():
    adata = sc.read_h5ad(standard_input)
else:
    adata = sc.read_h5ad(input_files[0])
    print(f"Using input file: {input_files[0].name}")
```

### 3. Essential Preprocessing Checks
Before any analysis, ensure required preprocessing:
```python
# For clustering methods
if 'neighbors' not in adata.uns:
    print("Computing neighbors...")
    if 'X_pca' not in adata.obsm:
        print("Computing PCA first...")
        sc.tl.pca(adata, svd_solver='arpack')
    sc.pp.neighbors(adata, n_pcs=40)

# For plotting gene expression
if 'log1p' not in adata.uns:
    print("Data may not be log-normalized. Plots might look unusual.")
```

### 4. Calculate Common Metrics
```python
# These are frequently needed but often missing
if 'n_genes' not in adata.obs.columns:
    adata.obs['n_genes'] = (adata.X > 0).sum(axis=1).A1 if hasattr(adata.X, 'A1') else (adata.X > 0).sum(axis=1)

if 'n_counts' not in adata.obs.columns:
    adata.obs['n_counts'] = adata.X.sum(axis=1).A1 if hasattr(adata.X, 'A1') else adata.X.sum(axis=1)

if 'percent_mito' not in adata.obs.columns:
    # Calculate mitochondrial percentage
    mito_genes = adata.var_names.str.startswith('MT-') | adata.var_names.str.startswith('mt-')
    adata.obs['percent_mito'] = np.sum(adata[:, mito_genes].X, axis=1).A1 / np.sum(adata.X, axis=1).A1 * 100 if hasattr(adata.X, 'A1') else np.sum(adata[:, mito_genes].X, axis=1) / np.sum(adata.X, axis=1) * 100
```

### 5. Output Directory Creation
```python
# Always ensure output directory exists
output_dir = Path(path_dict['output_dir'])
output_dir.mkdir(parents=True, exist_ok=True)

# Create figures subdirectory if needed
figures_dir = output_dir / 'figures'
figures_dir.mkdir(exist_ok=True)
```

### 6. Comprehensive Requirements Lists

**For basic analysis**:
```python
requirements = ["scanpy", "pandas", "numpy", "matplotlib", "seaborn"]
```

**For clustering**:
```python
requirements = ["scanpy", "pandas", "numpy", "matplotlib", "leidenalg", "python-igraph"]
```

**For trajectory inference**:
```python
# Palantir
requirements = ["scanpy", "pandas", "numpy", "matplotlib", "palantir"]

# scFates  
requirements = ["scanpy", "pandas", "numpy", "matplotlib", "scfates"]

# CellRank
requirements = ["scanpy", "pandas", "numpy", "matplotlib", "cellrank", "scvelo"]
```

## Common Implementation Mistakes to Avoid

### 1. Plotting Errors
❌ **Wrong**:
```python
sc.pl.umap(adata, color='highly_variable')  # This is a gene attribute!
```

✅ **Correct**:
```python
sc.pl.umap(adata, color='leiden', save='_leiden.png')  # Use cell attributes
```

### 2. Sparse Matrix Handling
❌ **Wrong**:
```python
gene_counts = adata.X.sum(axis=1)  # Returns matrix, not array
```

✅ **Correct**:
```python
gene_counts = adata.X.sum(axis=1).A1 if hasattr(adata.X, 'A1') else adata.X.sum(axis=1)
```

### 3. Missing Output Files
❌ **Wrong**:
```python
# Forgetting to save the output
sc.tl.leiden(adata)
# Function ends without saving
```

✅ **Correct**:
```python
sc.tl.leiden(adata)
output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
adata.write(output_file)
print(f"Saved output to {output_file}")
```

### 4. Import Patterns
❌ **Wrong**:
```python
from palantir import palantir  # Incorrect
```

✅ **Correct**:
```python
import palantir  # Correct
```

## Function Block Templates

### Basic Preprocessing Block
```python
def run(path_dict, params):
    import scanpy as sc
    import numpy as np
    import os
    
    # Load data
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)
    
    # Basic QC metrics
    adata.obs['n_genes'] = (adata.X > 0).sum(axis=1).A1 if hasattr(adata.X, 'A1') else (adata.X > 0).sum(axis=1)
    adata.obs['n_counts'] = adata.X.sum(axis=1).A1 if hasattr(adata.X, 'A1') else adata.X.sum(axis=1)
    
    # Filter cells and genes
    sc.pp.filter_cells(adata, min_genes=params.get('min_genes', 200))
    sc.pp.filter_genes(adata, min_cells=params.get('min_cells', 3))
    
    # Normalize and log-transform
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    
    # Save output
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
```

### Clustering Block
```python
def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Load data
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)
    
    # Ensure neighbors are computed
    if 'neighbors' not in adata.uns:
        if 'X_pca' not in adata.obsm:
            sc.tl.pca(adata, svd_solver='arpack')
        sc.pp.neighbors(adata)
    
    # Perform clustering
    resolution = params.get('resolution', 1.0)
    sc.tl.leiden(adata, resolution=resolution)
    
    # Create UMAP if missing
    if 'X_umap' not in adata.obsm:
        sc.tl.umap(adata)
    
    # Save output
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
```

## Parameter Handling Best Practices

1. **Always provide defaults**:
   ```python
   min_genes = params.get('min_genes', 200)
   n_top_genes = params.get('n_top_genes', 2000)
   ```

2. **Handle lists properly**:
   ```python
   resolutions = params.get('resolutions', [0.5, 1.0, 1.5])
   if not isinstance(resolutions, list):
       resolutions = [resolutions]
   ```

3. **Validate parameters**:
   ```python
   n_neighbors = params.get('n_neighbors', 30)
   n_neighbors = max(2, min(n_neighbors, adata.n_obs - 1))
   ```

## Testing Patterns

Include print statements for debugging:
```python
print(f"Input data shape: {adata.shape}")
print(f"Available columns: {list(adata.obs.columns)}")
print(f"Available embeddings: {list(adata.obsm.keys())}")
print(f"Processing with parameters: {params}")
```

## Memory Management

For large datasets:
```python
# Use chunked operations
if adata.n_obs > 50000:
    sc.pp.highly_variable_genes(adata, n_top_genes=2000, subset=True, inplace=True)
    
# Clear unnecessary data
if 'raw' in adata.uns:
    del adata.raw
```

## Error Prevention Checklist

Before submitting a function block, verify:
- [ ] All necessary imports are included
- [ ] Input file reading handles both standard and custom names
- [ ] Output directory is created with `exist_ok=True`
- [ ] Output file is saved to `_node_anndata.h5ad`
- [ ] All parameters have default values
- [ ] Sparse matrices are handled correctly
- [ ] Required preprocessing is checked/performed
- [ ] Print statements provide useful feedback
- [ ] Requirements list includes all packages

Remember: It's better to be defensive and check for prerequisites than to assume they exist. This prevents most downstream errors.