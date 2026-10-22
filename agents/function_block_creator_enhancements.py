"""
Enhanced prompts for function block creation to avoid common API errors.
"""

TRAJECTORY_PACKAGE_GUIDANCE = """
## Package-Specific Implementation Guidelines

### scFates (Trajectory Inference)
- **Note**: `scf.tl.tree()` (tree-shaped principal graph) and `scf.tl.curve()` (linear principal curve) are distinct methods; choose the one that matches the requested topology
- **Import**: `import scfates as scf`
- **Requirements**: numpy<1.24, scfates
- **Example**:
  ```python
  import scfates as scf
  # Linear principal curve (use scf.tl.tree for branching trajectories)
  scf.tl.curve(adata, Nodes=10, use_rep="X_pca", device="cpu", seed=42)
  # Store pseudotime
  adata.obs['scFates'] = adata.obs['t']
  ```

### Palantir (Pseudotime)
- **Import**: `import palantir`
- **Requirements**: palantir (NOT scanpy.external)
- **Example**:
  ```python
  import palantir
  import numpy as np
  # Set start cell from a user parameter or documented marker; if a random
  # choice is unavoidable, seed it and record the chosen cell in the outputs
  rng = np.random.default_rng(params.get('seed', 0))
  start_cell = params.get('start_cell') or adata.obs_names[rng.integers(len(adata))]
  adata.uns['palantir_start_cell'] = start_cell
  # Run palantir
  pr_res = palantir.core.run_palantir(
      adata, start_cell, use_early_cell_as_start=True
  )
  adata.obs['palantir'] = pr_res['pseudotime']
  ```

### CellRank (Fate Mapping)
- **Import**: `import cellrank as cr`
- **Requirements**: cellrank>=2.0
- **Example**:
  ```python
  import cellrank as cr
  from cellrank.kernels import PseudotimeKernel
  # Create kernel
  pk = PseudotimeKernel(adata, time_key='dpt_pseudotime')
  pk.compute_transition_matrix()
  # Get pseudotime
  adata.obs['cellrank'] = adata.obs['dpt_pseudotime']
  ```

### DTFLOW
- **NOT AVAILABLE ON PYPI** - do NOT substitute another method (e.g. PC1/UMAP1) and label it as DTFLOW.
- If the reference implementation cannot be installed, raise a clear error stating that DTFLOW
  was not run. Any fallback must be stored under an honest key (e.g. `adata.obs['pc1_pseudotime_fallback']`),
  print a warning, and record `adata.uns['pseudotime_method']` with the method actually used.

### General Guidelines
1. Always check if required embeddings exist (X_pca, X_umap)
2. Use try-except for imports to handle missing packages gracefully
3. Store results in adata.obs with the exact key specified by user
4. Save output with appropriate names (e.g., _node_anndata.h5ad for h5ad files)
"""

COMMON_ERROR_FIXES = """
## Common Errors and Solutions

### AttributeError: 'csr_matrix' object has no attribute 'A'
- Convert sparse to dense: `adata.X = adata.X.toarray() if scipy.sparse.issparse(adata.X) else adata.X`

### Missing PCA/UMAP
- Check before using: `if 'X_pca' not in adata.obsm: sc.pp.pca(adata)`

### Import Errors
- Use conditional imports:
  ```python
  try:
      import package
      HAS_PACKAGE = True
  except ImportError:
      HAS_PACKAGE = False
      raise ImportError("Required package is not available; install it rather than substituting another method")
  ```

### File I/O
- Input: Use flexible file discovery, don't assume specific names
- Output: Use descriptive names or '_node_anndata.h5ad' convention for h5ad files
- Example input discovery:
  ```python
  # Find h5ad files flexibly
  import glob
  h5ad_files = glob.glob(os.path.join(path_dict['input_dir'], '*.h5ad'))
  if h5ad_files:
      adata = sc.read_h5ad(h5ad_files[0])
  ```
"""

def get_enhanced_system_prompt():
    """Get enhanced system prompt for function block creation."""
    base_prompt = """You are an expert in single-cell RNA-seq analysis and Python programming.
Your task is to create function blocks that implement specific analysis steps.

CRITICAL REQUIREMENTS:
1. Use the exact function signature: def run(path_dict, params):
2. Load files from path_dict['input_dir'] - discover actual filenames
3. Save outputs to path_dict['output_dir'] with appropriate names
4. Include all dependencies in requirements list
5. Handle errors gracefully with informative messages
6. For previous nodes: Use the previous_nodes interface (see docs)
"""
    
    return base_prompt + "\n\n" + TRAJECTORY_PACKAGE_GUIDANCE + "\n\n" + COMMON_ERROR_FIXES