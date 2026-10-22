# Pseudotime Implementation Experience

This document captures implementation-specific fixes and troubleshooting for various pseudotime analysis methods based on real-world debugging experience.

## Palantir

### API Changes and Version Issues

**Issue**: `module 'palantir' has no attribute 'pseudotime'`

**Root Cause**: Palantir API changed between versions. The pseudotime functionality was moved.

**Solution**:
```python
# OLD (incorrect):
pseudotime = palantir.pseudotime(dm_res, early_cell)

# NEW (correct):
# First compute diffusion map
dm_res = palantir.utils.run_diffusion_maps(adata, n_components=10)

# Then determine multiscale space
ms_data = palantir.utils.determine_multiscale_space(dm_res)

# Finally run palantir
pr_res = palantir.core.run_palantir(
    ms_data,
    early_cell,
    knn=30,
    num_waypoints=500
)

# Extract pseudotime
adata.obs['palantir_pseudotime'] = pr_res.pseudotime
```

### Data Preparation Requirements

1. **PCA must be computed first**:
```python
if 'X_pca' not in adata.obsm:
    sc.pp.pca(adata, n_comps=50)
```

2. **UMAP coordinates in obs columns**:
```python
# Palantir expects 'x' and 'y' columns in adata.obs
if 'X_umap' in adata.obsm:
    adata.obs['x'] = adata.obsm['X_umap'][:, 0]
    adata.obs['y'] = adata.obsm['X_umap'][:, 1]
```

### Complete Working Example

```python
import palantir
import scanpy as sc
import pandas as pd

def run_palantir_analysis(adata, early_cell_id=None):
    # Ensure PCA
    if 'X_pca' not in adata.obsm:
        sc.pp.pca(adata, n_comps=50)
    
    # Add UMAP coordinates to obs
    if 'X_umap' in adata.obsm:
        adata.obs['x'] = adata.obsm['X_umap'][:, 0]
        adata.obs['y'] = adata.obsm['X_umap'][:, 1]
    
    # Run diffusion maps
    dm_res = palantir.utils.run_diffusion_maps(adata, n_components=10, knn=30)
    
    # Determine multiscale space
    ms_data = palantir.utils.determine_multiscale_space(dm_res)
    
    # Select start cell if not provided
    if early_cell_id is None:
        early_cell_id = adata.obs_names[0]
    
    # Run palantir
    pr_res = palantir.core.run_palantir(
        ms_data,
        early_cell_id,
        knn=30,
        num_waypoints=500
    )
    
    # Store results
    adata.obs['palantir_pseudotime'] = pr_res.pseudotime
    adata.obs['palantir_entropy'] = pr_res.entropy
    adata.obsm['palantir_fate_probabilities'] = pr_res.branch_probs
    
    return adata
```

## CellRank

### PseudotimeKernel Issues

**Issue**: CellRank PseudotimeKernel requires precomputed pseudotime

**Solution**: Always compute pseudotime first using another method:

```python
from cellrank.kernels import PseudotimeKernel
from cellrank.estimators import GPCCA

# Ensure pseudotime exists
if 'dpt_pseudotime' not in adata.obs:
    # Compute using DPT first
    sc.pp.neighbors(adata, n_neighbors=30)
    sc.tl.diffmap(adata)
    adata.uns['iroot'] = 0  # or select appropriate root
    sc.tl.dpt(adata)

# Now use with CellRank
pk = PseudotimeKernel(adata, time_key='dpt_pseudotime')
pk.compute_transition_matrix()

# Compute fate probabilities
g = GPCCA(pk)
g.compute_macrostates(n_states=5)
g.predict_terminal_states()
g.compute_fate_probabilities()
```

### Import Issues

**Common Error**: `ImportError: cannot import name 'PseudotimeKernel'`

**Solution**: Check CellRank version and import path:
```python
# Correct import
from cellrank.kernels import PseudotimeKernel

# NOT from cellrank.tl.kernels (old version)
```

## scFates

### CRITICAL API USAGE - scf.tl.root()

**The scf.tl.root() function expects an INTEGER cell index directly!**

```python
# ✅ CORRECT - Direct integer index
scf.tl.root(adata, 0)  # Use cell at index 0 as root
scf.tl.root(adata, 100)  # Use cell at index 100 as root

# ❌ WRONG - Common mistake
adata.uns['iroot'] = 0
scf.tl.root(adata, adata.uns['iroot'])  # DON'T DO THIS - will fail!

# ✅ CORRECT - Root chosen explicitly (the root choice changes the result; record it)
root_idx = int(params['root_cell_index'])  # e.g. selected from known progenitor markers
scf.tl.root(adata, root_idx)  # Pass the integer directly
```

### CRITICAL UPDATE (December 2024 Testing)

**IMPORTANT FINDINGS FROM COMPREHENSIVE TESTING**:

1. **Both PPT and EPG methods have issues in scFates 1.1.1**:
   - `method='epg'` (ElPiGraph): Fails with KeyError: 'epg' when computing pseudotime
   - `method='ppt'` (SimplePPT): Should work but has version compatibility issues
   
2. **Version Compatibility is Critical**:
   - scFates 1.1.1 has conflicts with numpy 2.x versions
   - Recommend using older, stable versions for production
   
3. **Method Recommendations**:
   - **For production**: Use `method='ppt'` (default) as it's more stable
   - **For research**: EPG is theoretically better but has implementation issues
   - **Fallback**: Always implement fallback pseudotime computation

### Robust Implementation Pattern (with Method Selection and Fallback)

```python
import scanpy as sc
import scFates as scf
import numpy as np

def run_scfates_pseudotime(adata, method='ppt'):
    """Robust scFates implementation with fallback.
    
    Args:
        adata: AnnData object
        method: 'ppt' (recommended) or 'epg' (experimental)
    """
    
    # 1. Ensure prerequisites
    adata.obs_names_make_unique()
    
    if 'X_pca' not in adata.obsm:
        print("Computing PCA...")
        sc.pp.pca(adata, n_comps=min(50, min(adata.shape) - 1))
    
    # 2. Try selected method with appropriate parameters
    success = False
    
    try:
        if method == 'ppt':
            # PPT method - more stable, use more nodes
            print("Using PPT (SimplePPT) method...")
            scf.tl.tree(adata, 
                       method='ppt',
                       Nodes=50,  # PPT works better with 50-200 nodes
                       use_rep='X_pca',
                       device='cpu',
                       seed=42,
                       ppt_sigma=0.025,
                       ppt_lambda=100)
        else:
            # EPG method - advanced but may fail
            print("Using EPG (ElPiGraph) method...")
            scf.tl.tree(adata,
                       method='epg', 
                       Nodes=10,  # EPG works better with 10-50 nodes
                       use_rep='X_pca',
                       device='cpu',
                       seed=42,
                       epg_lambda=0.01,
                       epg_mu=0.1)
        
        # Set root and compute pseudotime
        # CRITICAL: scf.tl.root() expects an integer cell index, NOT adata.uns['iroot']!
        scf.tl.root(adata, 0)  # Use cell at index 0 as root
        # Prefer an explicit, biologically justified root index; record the choice in outputs
        scf.tl.pseudotime(adata, n_jobs=1, n_map=1)
        
        if 't' in adata.obs.columns:
            adata.obs['scfates_pseudotime'] = adata.obs['t'].copy()
            success = True
            print(f"✓ Pseudotime computed successfully with {method}")
        
    except KeyError as e:
        print(f"✗ {method} method failed with KeyError: {e}")
        if method == 'epg':
            print("  This is a known issue with EPG in scFates 1.1.1")
    except Exception as e:
        print(f"✗ {method} method failed: {e}")
    
    # 3. Fallback if method failed
    if not success:
        print("Using fallback: diffusion-based pseudotime...")
        
        # Compute diffusion pseudotime as fallback
        if 'neighbors' not in adata.uns:
            sc.pp.neighbors(adata, n_neighbors=30)
        
        if 'X_diffmap' not in adata.obsm:
            sc.tl.diffmap(adata)
        
        # Store the fallback under an honest key - it is NOT scFates output
        pt = adata.obsm['X_diffmap'][:, 0]
        adata.obs['diffmap_pseudotime_fallback'] = (pt - pt.min()) / (pt.max() - pt.min())
        adata.uns['pseudotime_method'] = 'diffusion component 1 (fallback; scFates failed)'
        
        print("WARNING: scFates failed; fallback stored as 'diffmap_pseudotime_fallback'")
    
    return adata
```

### Alternative Implementation for Visualization Nodes

If you're creating a node that visualizes existing scFates results:

```python
def visualize_scfates_results(adata):
    """Visualize scFates pseudotime results."""
    import matplotlib.pyplot as plt
    import scanpy as sc
    import os
    
    # Check if scfates_pseudotime exists
    if 'scfates_pseudotime' not in adata.obs.columns:
        # Try to find it under different names
        if 't' in adata.obs.columns:
            adata.obs['scfates_pseudotime'] = adata.obs['t']
        else:
            raise ValueError("No scFates pseudotime found. Expected 'scfates_pseudotime' or 't' in adata.obs")
    
    # Create figures directory
    figures_dir = os.path.join(output_dir, 'figures')
    os.makedirs(figures_dir, exist_ok=True)
    
    # Plot UMAP colored by pseudotime
    if 'X_umap' in adata.obsm:
        sc.pl.umap(adata, color='scfates_pseudotime', 
                   show=False, 
                   save='_scfates_pseudotime.pdf')
        print("Saved UMAP plot colored by scFates pseudotime")
    
    # Plot curve if available
    if 'curve' in adata.uns:
        scf.pl.curve(adata, show=False, save='_scfates_curve.pdf')
        print("Saved scFates curve plot")
    
    return adata
```

### Device Selection

**Issue**: scFates may fail on systems without CUDA

**Solution**: Always specify device='cpu':
```python
import scFates as scf

# Always use CPU to avoid CUDA issues
scf.tl.tree(adata, method='ppt', Nodes=30, use_rep='X_pca', device='cpu')
```

### IMPORTANT API Note

`scf.tl.tree()` (tree-shaped principal graph) and `scf.tl.curve()` (linear principal curve) are distinct,
co-existing scFates methods. Use `scf.tl.tree(method='ppt')` for branching trajectories and
`scf.tl.curve()` for linear ones; consult the scFates documentation for your installed version.
(Observations in this section come from the authors' development environment and may not apply to other versions.)

### VALIDATED Issues and Solutions (Tested - December 2024)

1. **"KeyError: 'epg'" when using EPG method**:
   - **VALIDATED FINDING**: EPG method is broken in scFates 1.1.1 due to integration issues
   - **SOLUTION**: Use PPT method instead: `scf.tl.tree(adata, method='ppt')`
   - **Note**: This is a known bug in the current scFates release

2. **Version Compatibility Issues**:
   - **VALIDATED WORKING VERSIONS** (discovered through auto-resolve, then pinned):
     - scanpy==1.11.4
     - scFates==1.1.1
     - numpy==1.25.2 (NOT numpy 2.x which causes import errors)
   - **BEST PRACTICE**: 
     1. First test with unpinned versions to let pip auto-resolve
     2. Record the working versions that pip installs
     3. Pin those specific versions in requirements.txt for reproducibility
   - **SOLUTION**: Use these pinned versions in requirements.txt:
     ```txt
     scanpy==1.11.4
     scFates==1.1.1
     numpy==1.25.2
     matplotlib
     scipy
     ```

3. **"ValueError: You need to run `tl.root` or `tl.roots` before projecting cells"**:
   - **VALIDATED**: This error occurs if you skip the root setting step
   - **SOLUTION**: Always call `scf.tl.root(adata, cell_index)` after tree inference and before pseudotime
   - Example: `scf.tl.root(adata, 0)` to use first cell as root

4. **Missing 'scfates_pseudotime' in downstream nodes**:
   - **VALIDATED**: scFates stores pseudotime in 't' column, not 'scfates_pseudotime'
   - **SOLUTION**: Always copy: `adata.obs['scfates_pseudotime'] = adata.obs['t'].copy()`

5. **CUDA/GPU errors**:
   - **VALIDATED**: GPU usage can cause failures in containerized environments
   - **SOLUTION**: Always use `device='cpu'` parameter in all scFates functions

6. **Missing prerequisites**:
   - **VALIDATED**: scFates requires PCA to be pre-computed
   - **SOLUTION**: Check and compute if missing: `if 'X_pca' not in adata.obsm: sc.pp.pca(adata)`

### Minimal Working Example (RECOMMENDED - TESTED AND VALIDATED)

```python
# Recommended implementation using PPT method with fallback
# REQUIRES: scanpy==1.11.4, scFates==1.1.1, numpy==1.25.2
import scanpy as sc
import scFates as scf
import numpy as np

# Optional: Verify versions at runtime
assert sc.__version__ == "1.11.4", f"Expected scanpy 1.11.4, got {sc.__version__}"
assert scf.__version__ == "1.1.1", f"Expected scFates 1.1.1, got {scf.__version__}"
assert np.__version__.startswith("1.25"), f"Expected numpy 1.25.x, got {np.__version__}"

# Prerequisites
if 'X_pca' not in adata.obsm:
    n_comps = min(30, min(adata.shape) - 1)
    sc.pp.pca(adata, n_comps=n_comps)

# Make observation names unique (required by scFates)
adata.obs_names_make_unique()

try:
    # Use PPT method (EPG is broken in scFates 1.1.1)
    scf.tl.tree(adata, 
               method='ppt',
               Nodes=30,
               use_rep='X_pca',
               device='cpu',
               seed=42,
               ppt_sigma=0.025,
               ppt_lambda=100,
               ppt_nsteps=50)
    
    scf.tl.root(adata, 0)  # Use first cell as root
    scf.tl.pseudotime(adata, n_jobs=1, n_map=1)
    
    # Copy to standard location
    if 't' in adata.obs.columns:
        adata.obs['scfates_pseudotime'] = adata.obs['t'].copy()
        print(f"Pseudotime computed: range [{adata.obs['t'].min():.4f}, {adata.obs['t'].max():.4f}]")
    else:
        raise ValueError("Pseudotime 't' column not created")
        
except Exception as e:
    print(f"scFates failed: {e}")
    # Fallback to diffusion pseudotime
    if 'neighbors' not in adata.uns:
        sc.pp.neighbors(adata, n_neighbors=30)
    sc.tl.diffmap(adata)
    # Store the fallback under an honest key - it is NOT scFates output
    pt = adata.obsm['X_diffmap'][:, 0]
    adata.obs['diffmap_pseudotime_fallback'] = (pt - pt.min()) / (pt.max() - pt.min())
    adata.uns['pseudotime_method'] = 'diffusion component 1 (fallback; scFates failed)'
    print("WARNING: scFates failed; fallback stored as 'diffmap_pseudotime_fallback'")
```

### Validation Pattern

```python
def validate_scfates_results(adata):
    """Validate scFates computation was successful."""
    # Check for the 't' column (native scFates output)
    if 't' not in adata.obs.columns:
        print("Warning: scFates 't' column not found")
        return False
    
    # Check for our standardized column
    if 'scfates_pseudotime' not in adata.obs.columns:
        print("Warning: 'scfates_pseudotime' not found, copying from 't'")
        adata.obs['scfates_pseudotime'] = adata.obs['t']
    
    # Validate values
    pt = adata.obs['scfates_pseudotime']
    if pt.isna().any():
        print("Warning: Pseudotime contains NaN values")
        return False
    
    print(f"scFates validation passed: {len(pt)} cells, range [{pt.min():.3f}, {pt.max():.3f}]")
    return True
```

## DPT (Diffusion Pseudotime)

### Root Cell Selection

**Issue**: DPT requires a root cell but selection can fail

**Solution**: Robust root cell selection:
```python
# Option 1: Use first cell (simple but may not be optimal)
adata.uns['iroot'] = 0

# Option 2: Select based on marker expression
if 'CD34' in adata.var_names:
    cd34_expr = adata[:, 'CD34'].X.toarray().flatten()
    adata.uns['iroot'] = int(np.argmax(cd34_expr))
else:
    # No marker available: require an explicit root (the choice changes the result)
    raise ValueError("No root cell marker found; pass a root cell explicitly via params")

# Run DPT
sc.tl.dpt(adata)
```

### Prerequisites Check

```python
# DPT requires neighbors and diffmap
if 'neighbors' not in adata.uns:
    sc.pp.neighbors(adata, n_neighbors=15)

if 'X_diffmap' not in adata.obsm:
    sc.tl.diffmap(adata)

# Then run DPT
sc.tl.dpt(adata)
```

## DTFLOW (Diffusion-based Trajectory Flow)

DTFLOW is from the paper: "DTFLOW: Inference and Visualization of Single-cell Pseudotime Trajectory Using Diffusion Propagation"
GitHub: https://github.com/statway/DTFLOW

### Availability note

At the time this prototype was developed, DTFLOW was not available as a pip/conda package. If you need the
reference method, follow the instructions in the upstream repository (https://github.com/statway/DTFLOW) and cite
the original paper.

The snippet below is a **simplified, DTFLOW-inspired diffusion pseudotime** (random walk with restart on a kNN
Gaussian kernel). It is **not** the reference DTFLOW implementation and has not been validated against it.
Its outputs are therefore stored under distinct keys (`rwr_pseudotime`, `X_rwr_embedding`) and the method used is
recorded in `adata.uns['pseudotime_method']`. Never report its results as DTFLOW results.

### Simplified DTFLOW-inspired implementation (not the reference method)

```python
# Simplified approximation (dense O(n^2); suitable for small datasets only)
import numpy as np
import scipy.sparse as sp
from sklearn.neighbors import kneighbors_graph
from scipy.linalg import eigh

def build_transition_matrix(X, k=15):
    """Build adaptive Gaussian kernel transition matrix"""
    # k-NN graph
    knn_graph = kneighbors_graph(X, k, mode='distance', include_self=False)
    
    # Adaptive bandwidth (sigma) for each cell
    distances = knn_graph.data
    sigmas = np.mean(distances.reshape(-1, k), axis=1)
    
    # Build Gaussian kernel
    n = X.shape[0]
    W = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i != j:
                dist = np.linalg.norm(X[i] - X[j])
                W[i, j] = np.exp(-dist**2 / (2 * sigmas[i] * sigmas[j]))
    
    # Row-normalize to get transition matrix
    row_sums = W.sum(axis=1)
    M = W / row_sums[:, np.newaxis]
    return M

def random_walk_with_restart(M, restart_prob=0.85, max_iter=100):
    """Perform Random Walk with Restart"""
    n = M.shape[0]
    I = np.eye(n)
    S = (1 - restart_prob) * np.linalg.inv(I - restart_prob * M)
    return S

def compute_dtflow_embedding(S, n_components=2):
    """Compute a DTFLOW-inspired embedding via eigendecomposition (approximation)"""
    # Bhattacharyya kernel
    K = np.log(S + 1e-10)
    
    # Eigendecomposition
    eigenvalues, eigenvectors = eigh(K)
    
    # Sort by eigenvalues (descending)
    idx = eigenvalues.argsort()[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]
    
    # Return top components
    return eigenvectors[:, 1:(n_components+1)]

def calculate_pseudotime(S, root_index):
    """Calculate pseudotime as diffusion distance from root"""
    # Diffusion distance from root
    distances = -np.log(S[root_index, :] + 1e-10)
    
    # Normalize to [0, 1]
    pseudotime = (distances - distances.min()) / (distances.max() - distances.min())
    return pseudotime

def run(path_dict, params):
    import scanpy as sc
    import os
    from pathlib import Path
    
    # Parameters
    k_neighbors = params.get('k_neighbors', 15)
    restart_prob = params.get('restart_prob', 0.85)
    n_pca = params.get('n_pca', 50)
    
    # Load data dynamically
    input_dir = Path(path_dict['input_dir'])
    if (input_dir / 'previous_nodes').exists():
        from function_block_runtime import previous_nodes
        nodes = previous_nodes.list()
        adata = None
        for node in nodes:
            h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
            if h5ad_files:
                path = previous_nodes.get_file_path(node['index'], h5ad_files[0])
                if path:
                    adata = sc.read_h5ad(path)
                    break
        if adata is None:
            raise FileNotFoundError("No h5ad files found")
    else:
        h5ad_files = list(input_dir.glob('*.h5ad'))
        if h5ad_files:
            adata = sc.read_h5ad(h5ad_files[0])
        else:
            raise FileNotFoundError("No h5ad files found")
    
    # Get PCA representation
    if 'X_pca' not in adata.obsm:
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        sc.pp.scale(adata, max_value=10)
        sc.tl.pca(adata, n_comps=n_pca)
    
    X_pca = adata.obsm['X_pca'][:, :n_pca]
    
    # Step 1: Build transition matrix
    M = build_transition_matrix(X_pca, k=k_neighbors)
    
    # Step 2: Random Walk with Restart
    S = random_walk_with_restart(M, restart_prob=restart_prob)
    
    # Step 3: Compute embedding
    Y = compute_dtflow_embedding(S, n_components=2)
    
    # Step 4: Find root cell (use first cell as default)
    root_index = 0
    if 'root_cell' in adata.obs.columns:
        root_candidates = adata.obs[adata.obs['root_cell'] == True].index
        if len(root_candidates) > 0:
            root_index = adata.obs.index.get_loc(root_candidates[0])
    
    # Step 5: Calculate pseudotime
    pseudotime = calculate_pseudotime(S, root_index)
    
    # Store results
    adata.obs['rwr_pseudotime'] = pseudotime
    adata.obsm['X_rwr_embedding'] = Y
    adata.uns['pseudotime_method'] = 'simplified DTFLOW-inspired RWR diffusion (not reference DTFLOW)'
    
    # Save output
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
```

### Key Algorithm Components

1. **Transition Matrix**: k-NN with adaptive Gaussian kernel
2. **Diffusion**: Random Walk with Restart (RWR)
3. **Bhattacharyya Kernel**: Log transform of diffusion similarity
4. **Pseudotime**: Diffusion distance from root cells

### Requirements
```txt
numpy>=1.20.0
scipy>=1.7.0
pandas>=1.3.0
scanpy>=1.8.0
scikit-learn>=0.24.0
matplotlib>=3.3.0
```

### Common Issues and Solutions

1. **Matplotlib style error**:
```python
# Update style names for newer matplotlib
try:
    plt.style.use(["seaborn-v0_8-darkgrid"])
except:
    pass  # Use default
```

2. **PCA components validation**:
```python
n_comps = min(n_pca, adata.n_vars - 1, adata.n_obs - 1)
if n_comps <= 0:
    n_comps = min(10, adata.n_vars, adata.n_obs - 1)
```

## PAGA + DPT Combination

### Correct Order of Operations

```python
# 1. Clustering first
if 'leiden' not in adata.obs:
    sc.tl.leiden(adata)

# 2. PAGA
sc.tl.paga(adata, groups='leiden')

# 3. Diffusion map
sc.tl.diffmap(adata)

# 4. Select root using PAGA
# Find cluster with highest connectivity
connectivities = adata.uns['paga']['connectivities'].toarray()
root_cluster = np.argmax(np.sum(connectivities, axis=1))
cells_in_cluster = adata.obs['leiden'] == str(root_cluster)
adata.uns['iroot'] = np.where(cells_in_cluster)[0][0]

# 5. DPT
sc.tl.dpt(adata)
```

## General Best Practices

### 1. Always Check Prerequisites

```python
def check_pseudotime_prerequisites(adata):
    """Check if data is ready for pseudotime analysis."""
    checks = {
        'has_pca': 'X_pca' in adata.obsm,
        'has_neighbors': 'neighbors' in adata.uns,
        'has_umap': 'X_umap' in adata.obsm,
        'has_clustering': any(col.startswith(('leiden', 'louvain')) for col in adata.obs.columns),
        'has_diffmap': 'X_diffmap' in adata.obsm
    }
    
    print("Pseudotime prerequisites:")
    for check, status in checks.items():
        print(f"  {check}: {'✓' if status else '✗'}")
    
    return all(checks.values())
```

### 2. Consistent Naming

```python
# Always save pseudotime with method prefix
adata.obs['palantir_pseudotime'] = palantir_result
adata.obs['dpt_pseudotime'] = adata.obs['dpt_pseudotime']
adata.obs['scfates_pseudotime'] = adata.obs['t']
```

### 3. Error Recovery Pattern

```python
def safe_pseudotime_analysis(adata, method='dpt'):
    """Run pseudotime with fallbacks."""
    try:
        if method == 'palantir':
            return run_palantir_analysis(adata)
    except Exception as e:
        print(f"Palantir failed: {e}, trying DPT")
        
    try:
        # Fallback to DPT
        sc.pp.neighbors(adata, n_neighbors=30)
        sc.tl.diffmap(adata)
        adata.uns['iroot'] = 0
        sc.tl.dpt(adata)
        return adata
    except Exception as e:
        print(f"DPT failed: {e}")
        raise
```

### 4. Validation

```python
def validate_pseudotime_results(adata, time_key):
    """Validate pseudotime computation."""
    if time_key not in adata.obs:
        raise ValueError(f"Pseudotime key '{time_key}' not found")
    
    pt = adata.obs[time_key]
    
    # Check for NaN values
    if pt.isna().any():
        raise ValueError("Pseudotime contains NaN values")
    
    # Check range
    if pt.min() < 0 or pt.max() > 1:
        print(f"Warning: Pseudotime range [{pt.min():.3f}, {pt.max():.3f}] outside [0,1]")
    
    print(f"Pseudotime validation passed: {len(pt)} cells, range [{pt.min():.3f}, {pt.max():.3f}]")
    return True
```

## Common Error Messages and Solutions

1. **"AttributeError: module 'palantir' has no attribute 'pseudotime'"**
   - Use the new API: `palantir.core.run_palantir()`

2. **"ValueError: n_neighbors > n_samples"**
   - Reduce n_neighbors or check if data is too small

3. **"KeyError: 'X_pca'"**
   - Run `sc.pp.pca(adata)` first

4. **"RuntimeError: No CUDA GPUs are available"**
   - Use `device='cpu'` for scFates

5. **"ValueError: Cannot find root cell"**
   - Manually set `adata.uns['iroot']`

6. **"ImportError: cannot import name 'run_palantir'"**
   - Check palantir version: `pip install palantir`