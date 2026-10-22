# Function Block Complete Working Examples

This document provides **example function block implementations** that you can adapt. These examples handle common edge cases and follow best practices.

## Table of Contents
1. [Universal Data Loading Pattern](#universal-data-loading-pattern)
2. [Pseudotime Analysis Examples](#pseudotime-analysis-examples)
3. [Clustering Analysis](#clustering-analysis)
4. [Visualization Patterns](#visualization-patterns)

---

## Universal Data Loading Pattern

### ✅ ALWAYS Use This Pattern for Loading Data

```python
def run(path_dict, params):
    import os
    import scanpy as sc
    from pathlib import Path
    
    # CRITICAL: Check if previous nodes exist
    prev_nodes_dir = os.path.join(path_dict['input_dir'], 'previous_nodes')
    
    if os.path.exists(prev_nodes_dir):
        # We have previous nodes - use the runtime interface
        from function_block_runtime import previous_nodes
        
        # List all available nodes
        nodes = previous_nodes.list()
        print(f"Found {len(nodes)} previous nodes")
        
        # Find h5ad file from most recent node
        adata = None
        for node in reversed(nodes):  # Start from most recent
            h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
            if h5ad_files:
                # CRITICAL: Use node['index'], NOT hardcoded numbers!
                path = previous_nodes.get_file_path(node['index'], h5ad_files[0])
                if path and path.exists():
                    adata = sc.read_h5ad(path)
                    print(f"Loaded data from node {node['index']}: {adata.shape}")
                    break
        
        if adata is None:
            raise FileNotFoundError("No h5ad files found in previous nodes")
    else:
        # Root node - files are directly in input_dir
        input_dir = Path(path_dict['input_dir'])
        h5ad_files = list(input_dir.glob('*.h5ad'))
        
        if h5ad_files:
            adata = sc.read_h5ad(h5ad_files[0])
            print(f"Loaded data from input: {adata.shape}")
        else:
            # Try other formats
            csv_files = list(input_dir.glob('*.csv'))
            if csv_files:
                import pandas as pd
                df = pd.read_csv(csv_files[0])
                # Convert to AnnData if needed
                adata = sc.AnnData(df)
            else:
                raise FileNotFoundError("No data files found")
    
    # ALWAYS ensure unique names
    adata.obs_names_make_unique()
    
    # Your analysis here...
    
    # ALWAYS save output
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
    print(f"Saved output to {output_file}")
    
    return adata
```

### ⚠️ CRITICAL Rules for Data Loading

1. **NEVER hardcode node indices**: Always use `node['index']` from the list
2. **NEVER assume node 0 exists**: Nodes are 1-indexed! 
3. **ALWAYS check if previous_nodes directory exists** before importing the runtime
4. **ALWAYS make observation names unique**: Use `adata.obs_names_make_unique()`
5. **ALWAYS save to output_dir**: Don't forget to create the directory first

---

## Pseudotime Analysis Examples

### Simplified DTFLOW-inspired Pseudotime (approximation, NOT the reference DTFLOW)

```python
def run(path_dict, params):
    """Simplified DTFLOW-inspired random-walk-with-restart pseudotime.

    This is an approximation, not the reference DTFLOW implementation; outputs are stored
    under distinct keys and must not be reported as DTFLOW results.
    """
    import os
    import numpy as np
    import scanpy as sc
    from pathlib import Path
    from sklearn.neighbors import kneighbors_graph
    from scipy.linalg import eigh
    
    # Parameters
    k_neighbors = params.get('k_neighbors', 15)
    restart_prob = params.get('restart_prob', 0.85)
    n_pca = params.get('n_pca', 50)
    
    # === LOAD DATA (use universal pattern) ===
    prev_nodes_dir = os.path.join(path_dict['input_dir'], 'previous_nodes')
    
    if os.path.exists(prev_nodes_dir):
        from function_block_runtime import previous_nodes
        nodes = previous_nodes.list()
        adata = None
        for node in reversed(nodes):
            h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
            if h5ad_files:
                path = previous_nodes.get_file_path(node['index'], h5ad_files[0])
                if path and path.exists():
                    adata = sc.read_h5ad(path)
                    break
        if adata is None:
            raise FileNotFoundError("No h5ad files found")
    else:
        input_dir = Path(path_dict['input_dir'])
        h5ad_files = list(input_dir.glob('*.h5ad'))
        if h5ad_files:
            adata = sc.read_h5ad(h5ad_files[0])
        else:
            raise FileNotFoundError("No h5ad files found")
    
    adata.obs_names_make_unique()
    
    # === PREPARE DATA ===
    if 'X_pca' not in adata.obsm:
        print("Computing PCA...")
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        sc.pp.scale(adata, max_value=10)
        sc.tl.pca(adata, n_comps=n_pca)
    
    X_pca = adata.obsm['X_pca'][:, :min(n_pca, adata.obsm['X_pca'].shape[1])]
    
    # === DTFLOW-INSPIRED ALGORITHM (approximation) ===
    print("Building transition matrix...")
    # 1. k-NN graph
    knn_graph = kneighbors_graph(X_pca, k_neighbors, mode='distance', include_self=False)
    
    # 2. Adaptive Gaussian kernel
    n_cells = X_pca.shape[0]
    W = np.zeros((n_cells, n_cells))
    
    # Convert sparse to dense for easier manipulation
    distances = knn_graph.toarray()
    
    # Compute adaptive bandwidth (sigma) for each cell
    for i in range(n_cells):
        # Get k-nearest neighbor distances for cell i
        neighbor_dists = distances[i][distances[i] > 0]
        if len(neighbor_dists) > 0:
            sigma_i = np.mean(neighbor_dists)
        else:
            sigma_i = 1.0
        
        for j in range(n_cells):
            if i != j and distances[i, j] > 0:  # Only for actual neighbors
                W[i, j] = np.exp(-distances[i, j]**2 / (2 * sigma_i**2))
    
    # Row-normalize to get transition matrix
    row_sums = W.sum(axis=1)
    row_sums[row_sums == 0] = 1  # Avoid division by zero
    M = W / row_sums[:, np.newaxis]
    
    print("Performing Random Walk with Restart...")
    # 3. Random Walk with Restart
    I = np.eye(n_cells)
    S = (1 - restart_prob) * np.linalg.inv(I - restart_prob * M)
    
    print("Computing DTFLOW-inspired embedding (approximation)...")
    # 4. Bhattacharyya kernel and embedding
    K = np.log(S + 1e-10)
    eigenvalues, eigenvectors = eigh(K)
    
    # Sort by eigenvalues (descending)
    idx = eigenvalues.argsort()[::-1]
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]
    
    # Take top 2 components (skip first which is trivial)
    Y = eigenvectors[:, 1:3]
    
    print("Calculating pseudotime...")
    # 5. Find root cell (use first cell or specific marker)
    root_index = 0
    if 'root_cell' in adata.obs.columns:
        root_mask = adata.obs['root_cell'] == True
        if root_mask.any():
            root_index = np.where(root_mask)[0][0]
    
    # 6. Calculate pseudotime as diffusion distance from root
    distances_from_root = -np.log(S[root_index, :] + 1e-10)
    
    # Normalize to [0, 1]
    pseudotime = (distances_from_root - distances_from_root.min()) / (distances_from_root.max() - distances_from_root.min() + 1e-10)
    
    # === SAVE RESULTS ===
    adata.obs['rwr_pseudotime'] = pseudotime
    adata.obsm['X_rwr_embedding'] = Y
    adata.uns['pseudotime_method'] = 'simplified DTFLOW-inspired RWR diffusion (not reference DTFLOW)'
    
    # Save output
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
    print(f"DTFLOW-inspired (approximate) analysis complete. Saved to {output_file}")
    
    # Optional: Save visualization
    if 'X_umap' in adata.obsm:
        import matplotlib.pyplot as plt
        fig_dir = os.path.join(path_dict['output_dir'], 'figures')
        os.makedirs(fig_dir, exist_ok=True)
        
        fig, ax = plt.subplots(figsize=(8, 6))
        scatter = ax.scatter(adata.obsm['X_umap'][:, 0], 
                           adata.obsm['X_umap'][:, 1],
                           c=pseudotime, cmap='viridis', s=10)
        plt.colorbar(scatter, ax=ax, label='RWR pseudotime (DTFLOW-inspired)')
        ax.set_xlabel('UMAP 1')
        ax.set_ylabel('UMAP 2')
        ax.set_title('RWR pseudotime (DTFLOW-inspired approximation)')
        plt.savefig(os.path.join(fig_dir, 'rwr_pseudotime.png'), dpi=150, bbox_inches='tight')
        plt.close()
        print("Saved visualization")
    
    return adata
```

### Palantir Pseudotime (Working with Current API)

```python
def run(path_dict, params):
    """Palantir Pseudotime - Complete Working Implementation"""
    import os
    import scanpy as sc
    import palantir
    import numpy as np
    from pathlib import Path
    
    # === LOAD DATA ===
    prev_nodes_dir = os.path.join(path_dict['input_dir'], 'previous_nodes')
    
    if os.path.exists(prev_nodes_dir):
        from function_block_runtime import previous_nodes
        nodes = previous_nodes.list()
        adata = None
        for node in reversed(nodes):
            h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
            if h5ad_files:
                path = previous_nodes.get_file_path(node['index'], h5ad_files[0])
                if path and path.exists():
                    adata = sc.read_h5ad(path)
                    break
        if adata is None:
            raise FileNotFoundError("No h5ad files found")
    else:
        input_dir = Path(path_dict['input_dir'])
        h5ad_files = list(input_dir.glob('*.h5ad'))
        if h5ad_files:
            adata = sc.read_h5ad(h5ad_files[0])
        else:
            raise FileNotFoundError("No h5ad files found")
    
    adata.obs_names_make_unique()
    
    # === PREPARE FOR PALANTIR ===
    # Palantir needs PCA
    if 'X_pca' not in adata.obsm:
        print("Computing PCA...")
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        sc.pp.highly_variable_genes(adata, n_top_genes=2000)
        adata = adata[:, adata.var.highly_variable]
        sc.pp.scale(adata, max_value=10)
        sc.tl.pca(adata, n_comps=50)
    
    # Palantir needs UMAP coordinates in obs
    if 'X_umap' in adata.obsm:
        adata.obs['x'] = adata.obsm['X_umap'][:, 0]
        adata.obs['y'] = adata.obsm['X_umap'][:, 1]
    else:
        # Compute UMAP if needed
        if 'neighbors' not in adata.uns:
            sc.pp.neighbors(adata, n_neighbors=30)
        sc.tl.umap(adata)
        adata.obs['x'] = adata.obsm['X_umap'][:, 0]
        adata.obs['y'] = adata.obsm['X_umap'][:, 1]
    
    # === RUN PALANTIR ===
    print("Running Palantir...")
    
    # 1. Compute diffusion map
    dm_res = palantir.utils.run_diffusion_maps(adata, n_components=10)
    
    # 2. Determine multiscale space
    ms_data = palantir.utils.determine_multiscale_space(dm_res)
    
    # 3. Find start cell (use random or marker-based)
    # Option 1 (arbitrary default; disclose in outputs): first cell
    start_cell = adata.obs_names[0]
    
    # Option 2: Use stem cell markers if available
    stem_markers = ['Sox2', 'Nanog', 'Kit']
    available_markers = [m for m in stem_markers if m in adata.var_names]
    if available_markers:
        marker_expr = adata[:, available_markers].X
        if hasattr(marker_expr, 'toarray'):
            marker_expr = marker_expr.toarray()
        mean_expr = marker_expr.mean(axis=1)
        start_idx = np.argmax(mean_expr)
        start_cell = adata.obs_names[start_idx]
        print(f"Selected start cell based on markers: {start_cell}")
    
    # 4. Run Palantir
    pr_res = palantir.core.run_palantir(
        ms_data,
        start_cell,
        knn=30,
        num_waypoints=500
    )
    
    # 5. Extract results
    adata.obs['palantir_pseudotime'] = pr_res.pseudotime
    adata.obs['palantir_entropy'] = pr_res.entropy
    adata.obsm['X_palantir_dm'] = dm_res['EigenVectors'].values
    
    # Store branch probabilities if they exist
    if hasattr(pr_res, 'branch_probs'):
        for branch in pr_res.branch_probs.columns:
            adata.obs[f'palantir_branch_{branch}'] = pr_res.branch_probs[branch]
    
    print("Palantir analysis complete")
    
    # === SAVE OUTPUT ===
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
    print(f"Saved to {output_file}")
    
    return adata
```

### DPT with PAGA (Scanpy Built-in)

```python
def run(path_dict, params):
    """DPT Pseudotime with PAGA - Example Implementation"""
    import os
    import numpy as np
    import scanpy as sc
    from pathlib import Path
    
    # === LOAD DATA ===
    prev_nodes_dir = os.path.join(path_dict['input_dir'], 'previous_nodes')
    
    if os.path.exists(prev_nodes_dir):
        from function_block_runtime import previous_nodes
        nodes = previous_nodes.list()
        adata = None
        for node in reversed(nodes):
            h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
            if h5ad_files:
                path = previous_nodes.get_file_path(node['index'], h5ad_files[0])
                if path and path.exists():
                    adata = sc.read_h5ad(path)
                    break
        if adata is None:
            raise FileNotFoundError("No h5ad files found")
    else:
        input_dir = Path(path_dict['input_dir'])
        h5ad_files = list(input_dir.glob('*.h5ad'))
        if h5ad_files:
            adata = sc.read_h5ad(h5ad_files[0])
        else:
            raise FileNotFoundError("No h5ad files found")
    
    adata.obs_names_make_unique()
    
    # === PREPROCESSING IF NEEDED ===
    if 'X_pca' not in adata.obsm:
        print("Running preprocessing...")
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        sc.pp.highly_variable_genes(adata, n_top_genes=2000)
        adata = adata[:, adata.var.highly_variable]
        sc.pp.scale(adata, max_value=10)
        sc.tl.pca(adata, n_comps=50)
    
    if 'neighbors' not in adata.uns:
        print("Computing neighbors...")
        sc.pp.neighbors(adata, n_neighbors=30)
    
    # === CLUSTERING (Required for PAGA) ===
    if 'leiden' not in adata.obs.columns:
        print("Computing Leiden clustering...")
        sc.tl.leiden(adata, resolution=0.5)
    
    # Make sure leiden is categorical
    if not hasattr(adata.obs['leiden'], 'cat'):
        import pandas as pd
        adata.obs['leiden'] = pd.Categorical(adata.obs['leiden'])
    
    # === RUN PAGA ===
    print("Computing PAGA...")
    sc.tl.paga(adata, groups='leiden')
    
    # === RUN DPT ===
    print("Computing DPT pseudotime...")
    
    # Find root cell (use cluster with earliest timepoint or markers)
    # Option 1 (heuristic, disclose in outputs): first cell in smallest cluster as root
    cluster_sizes = adata.obs['leiden'].value_counts()
    smallest_cluster = cluster_sizes.idxmin()
    root_mask = adata.obs['leiden'] == smallest_cluster
    root_idx = np.where(root_mask)[0][0]
    
    # Option 2: Use marker expression if available
    early_markers = ['Sox2', 'Nanog', 'Kit']
    available_markers = [m for m in early_markers if m in adata.var_names]
    if available_markers:
        marker_expr = adata[:, available_markers].X
        if hasattr(marker_expr, 'toarray'):
            marker_expr = marker_expr.toarray()
        mean_expr = marker_expr.mean(axis=1)
        root_idx = np.argmax(mean_expr)
        print(f"Selected root cell {root_idx} based on markers")
    
    # Set root and compute DPT
    adata.uns['iroot'] = root_idx
    sc.tl.dpt(adata)
    
    print("DPT analysis complete")
    
    # === VISUALIZATIONS ===
    fig_dir = os.path.join(path_dict['output_dir'], 'figures')
    os.makedirs(fig_dir, exist_ok=True)
    
    # PAGA plot
    sc.pl.paga(adata, save='_paga.pdf')
    
    # UMAP with pseudotime
    if 'X_umap' not in adata.obsm:
        sc.tl.umap(adata)
    sc.pl.umap(adata, color=['dpt_pseudotime', 'leiden'], save='_dpt.png')
    
    # === SAVE OUTPUT ===
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
    print(f"Saved to {output_file}")
    
    return adata
```

---

## Clustering Analysis

### Complete Leiden Clustering with Validation

```python
def run(path_dict, params):
    """Leiden Clustering - Complete Implementation with Validation"""
    import os
    import scanpy as sc
    import pandas as pd
    from pathlib import Path
    
    # Parameters
    resolution = params.get('resolution', 0.5)
    n_neighbors = params.get('n_neighbors', 30)
    
    # === LOAD DATA (standard pattern) ===
    prev_nodes_dir = os.path.join(path_dict['input_dir'], 'previous_nodes')
    
    if os.path.exists(prev_nodes_dir):
        from function_block_runtime import previous_nodes
        nodes = previous_nodes.list()
        adata = None
        for node in reversed(nodes):
            h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
            if h5ad_files:
                path = previous_nodes.get_file_path(node['index'], h5ad_files[0])
                if path and path.exists():
                    adata = sc.read_h5ad(path)
                    break
        if adata is None:
            raise FileNotFoundError("No h5ad files found")
    else:
        input_dir = Path(path_dict['input_dir'])
        h5ad_files = list(input_dir.glob('*.h5ad'))
        if h5ad_files:
            adata = sc.read_h5ad(h5ad_files[0])
        else:
            raise FileNotFoundError("No h5ad files found")
    
    adata.obs_names_make_unique()
    
    # === ENSURE PREPROCESSING ===
    if 'X_pca' not in adata.obsm:
        print("Running PCA...")
        # Check if data is already normalized
        if adata.X.max() > 100:  # Likely raw counts
            sc.pp.normalize_total(adata, target_sum=1e4)
            sc.pp.log1p(adata)
        sc.pp.scale(adata, max_value=10)
        sc.tl.pca(adata, n_comps=50)
    
    # === COMPUTE NEIGHBORS ===
    print(f"Computing neighbors with k={n_neighbors}...")
    sc.pp.neighbors(adata, n_neighbors=n_neighbors, use_rep='X_pca')
    
    # === RUN LEIDEN CLUSTERING ===
    print(f"Running Leiden clustering with resolution={resolution}...")
    sc.tl.leiden(adata, resolution=resolution)
    
    # Ensure it's categorical
    if not hasattr(adata.obs['leiden'], 'cat'):
        adata.obs['leiden'] = pd.Categorical(adata.obs['leiden'])
    
    # === COMPUTE UMAP FOR VISUALIZATION ===
    if 'X_umap' not in adata.obsm:
        print("Computing UMAP...")
        sc.tl.umap(adata)
    
    # === CLUSTER STATISTICS ===
    cluster_counts = adata.obs['leiden'].value_counts().sort_index()
    print("\nCluster statistics:")
    for cluster, count in cluster_counts.items():
        print(f"  Cluster {cluster}: {count} cells ({count/adata.n_obs*100:.1f}%)")
    
    # === FIND MARKER GENES ===
    print("\nFinding marker genes...")
    sc.tl.rank_genes_groups(adata, 'leiden', method='wilcoxon', n_genes=50)
    
    # Save top markers to CSV
    markers_dir = os.path.join(path_dict['output_dir'], 'markers')
    os.makedirs(markers_dir, exist_ok=True)
    
    # Extract markers for each cluster
    markers = []
    for cluster in adata.obs['leiden'].cat.categories:
        cluster_markers = sc.get.rank_genes_groups_df(adata, group=cluster, n_genes=10)
        cluster_markers['cluster'] = cluster
        markers.append(cluster_markers)
    
    markers_df = pd.concat(markers)
    markers_df.to_csv(os.path.join(markers_dir, 'cluster_markers.csv'), index=False)
    print(f"Saved marker genes to markers/cluster_markers.csv")
    
    # === VISUALIZATIONS ===
    fig_dir = os.path.join(path_dict['output_dir'], 'figures')
    os.makedirs(fig_dir, exist_ok=True)
    
    # UMAP plot
    sc.pl.umap(adata, color='leiden', legend_loc='on data', save='_leiden.png')
    
    # Marker genes heatmap
    sc.pl.rank_genes_groups_heatmap(adata, n_genes=3, save='_markers.png')
    
    # === SAVE OUTPUT ===
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
    print(f"Saved to {output_file}")
    
    return adata
```

---

## Visualization Patterns

### Complete Visualization Function Block

```python
def run(path_dict, params):
    """Generate Multiple Visualizations - Complete Implementation"""
    import os
    import scanpy as sc
    import matplotlib.pyplot as plt
    import seaborn as sns
    from pathlib import Path
    import numpy as np
    
    # === LOAD DATA ===
    prev_nodes_dir = os.path.join(path_dict['input_dir'], 'previous_nodes')
    
    if os.path.exists(prev_nodes_dir):
        from function_block_runtime import previous_nodes
        nodes = previous_nodes.list()
        adata = None
        for node in reversed(nodes):
            h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
            if h5ad_files:
                path = previous_nodes.get_file_path(node['index'], h5ad_files[0])
                if path and path.exists():
                    adata = sc.read_h5ad(path)
                    break
        if adata is None:
            raise FileNotFoundError("No h5ad files found")
    else:
        input_dir = Path(path_dict['input_dir'])
        h5ad_files = list(input_dir.glob('*.h5ad'))
        if h5ad_files:
            adata = sc.read_h5ad(h5ad_files[0])
        else:
            raise FileNotFoundError("No h5ad files found")
    
    adata.obs_names_make_unique()
    
    # === CREATE OUTPUT DIRECTORIES ===
    fig_dir = os.path.join(path_dict['output_dir'], 'figures')
    os.makedirs(fig_dir, exist_ok=True)
    
    # === ENSURE UMAP EXISTS ===
    if 'X_umap' not in adata.obsm:
        print("Computing UMAP...")
        if 'neighbors' not in adata.uns:
            if 'X_pca' not in adata.obsm:
                sc.pp.pca(adata, n_comps=50)
            sc.pp.neighbors(adata, n_neighbors=30)
        sc.tl.umap(adata)
    
    # === 1. BASIC UMAP PLOTS ===
    # Plot all categorical columns
    categorical_cols = [col for col in adata.obs.columns 
                       if adata.obs[col].dtype == 'object' or 
                       hasattr(adata.obs[col], 'cat')]
    
    for col in categorical_cols[:5]:  # Limit to first 5
        try:
            sc.pl.umap(adata, color=col, save=f'_{col}.png')
            print(f"Saved UMAP colored by {col}")
        except:
            pass
    
    # === 2. PSEUDOTIME PLOTS ===
    pseudotime_cols = [col for col in adata.obs.columns if 'pseudotime' in col.lower()]
    
    for pt_col in pseudotime_cols:
        fig, ax = plt.subplots(figsize=(8, 6))
        scatter = ax.scatter(adata.obsm['X_umap'][:, 0],
                           adata.obsm['X_umap'][:, 1],
                           c=adata.obs[pt_col],
                           cmap='viridis',
                           s=10,
                           alpha=0.7)
        plt.colorbar(scatter, ax=ax, label=pt_col)
        ax.set_xlabel('UMAP 1')
        ax.set_ylabel('UMAP 2')
        ax.set_title(f'{pt_col} Visualization')
        plt.savefig(os.path.join(fig_dir, f'{pt_col}.png'), dpi=150, bbox_inches='tight')
        plt.close()
        print(f"Saved {pt_col} plot")
    
    # === 3. GENE EXPRESSION PLOTS ===
    # Plot some highly variable genes
    if 'highly_variable' in adata.var.columns:
        hvg = adata.var_names[adata.var.highly_variable][:6]
    else:
        # Use genes with highest variance
        gene_vars = np.var(adata.X, axis=0)
        if hasattr(gene_vars, 'A1'):
            gene_vars = gene_vars.A1
        top_var_idx = np.argsort(gene_vars)[-6:]
        hvg = adata.var_names[top_var_idx]
    
    if len(hvg) > 0:
        sc.pl.umap(adata, color=list(hvg), save='_top_genes.png', ncols=3)
        print("Saved top gene expression plots")
    
    # === 4. QUALITY METRICS ===
    qc_metrics = ['n_genes_by_counts', 'total_counts', 'pct_counts_mt']
    available_qc = [m for m in qc_metrics if m in adata.obs.columns]
    
    if available_qc:
        fig, axes = plt.subplots(1, len(available_qc), figsize=(5*len(available_qc), 4))
        if len(available_qc) == 1:
            axes = [axes]
        
        for i, metric in enumerate(available_qc):
            scatter = axes[i].scatter(adata.obsm['X_umap'][:, 0],
                                     adata.obsm['X_umap'][:, 1],
                                     c=adata.obs[metric],
                                     cmap='RdYlBu_r',
                                     s=5,
                                     alpha=0.7)
            plt.colorbar(scatter, ax=axes[i])
            axes[i].set_xlabel('UMAP 1')
            axes[i].set_ylabel('UMAP 2')
            axes[i].set_title(metric)
        
        plt.tight_layout()
        plt.savefig(os.path.join(fig_dir, 'qc_metrics.png'), dpi=150, bbox_inches='tight')
        plt.close()
        print("Saved QC metrics plots")
    
    # === 5. COMPARISON PLOTS ===
    # If multiple pseudotime methods exist, compare them
    if len(pseudotime_cols) >= 2:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.scatter(adata.obs[pseudotime_cols[0]], 
                  adata.obs[pseudotime_cols[1]],
                  alpha=0.5, s=10)
        ax.set_xlabel(pseudotime_cols[0])
        ax.set_ylabel(pseudotime_cols[1])
        ax.set_title('Pseudotime Comparison')
        
        # Add correlation
        corr = adata.obs[pseudotime_cols[0]].corr(adata.obs[pseudotime_cols[1]])
        ax.text(0.05, 0.95, f'Correlation: {corr:.3f}',
               transform=ax.transAxes, verticalalignment='top')
        
        plt.savefig(os.path.join(fig_dir, 'pseudotime_comparison.png'), 
                   dpi=150, bbox_inches='tight')
        plt.close()
        print("Saved pseudotime comparison plot")
    
    # === SAVE OUTPUT ===
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
    print(f"Saved to {output_file}")
    
    # Create summary
    summary = {
        'n_cells': adata.n_obs,
        'n_genes': adata.n_vars,
        'plots_generated': len(os.listdir(fig_dir)),
        'pseudotime_methods': pseudotime_cols,
        'categorical_variables': categorical_cols[:5]
    }
    
    import json
    with open(os.path.join(path_dict['output_dir'], 'visualization_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)
    
    print(f"\nGenerated {summary['plots_generated']} plots")
    
    return adata
```

---

## Critical Reminders

### ❌ NEVER DO THESE:
1. **NEVER use node index 0**: `previous_nodes.get_file_path(0, ...)` will ALWAYS fail
2. **NEVER hardcode node indices**: Always use `node['index']` from the list
3. **NEVER label an approximation as the reference method**: e.g. the DTFLOW-inspired snippet above must not be reported as DTFLOW
4. **NEVER import from DTFLOW_original**: no such module exists
5. **NEVER forget to save outputs**: Always write to `path_dict['output_dir']`
6. **NEVER assume file names**: Always check what files actually exist

### ✅ ALWAYS DO THESE:
1. **ALWAYS check if previous_nodes directory exists** before importing the runtime
2. **ALWAYS use dynamic node discovery**: Loop through nodes to find files
3. **ALWAYS make obs names unique**: `adata.obs_names_make_unique()`
4. **ALWAYS create output directory**: `os.makedirs(path_dict['output_dir'], exist_ok=True)`
5. **ALWAYS handle both cases**: With previous nodes AND root node (no previous nodes)
6. **ALWAYS save figures to subdirectory**: Create `figures/` under output_dir

## Complete Requirements.txt Examples

### For Pseudotime Analysis:
```txt
scanpy>=1.9.0
pandas>=1.3.0
numpy>=1.20.0
matplotlib>=3.3.0
seaborn>=0.11.0
scikit-learn>=1.0.0
scipy>=1.7.0
palantir>=0.2.0
scfates>=0.8.0
```

### For Basic Analysis:
```txt
scanpy>=1.9.0
pandas>=1.3.0
numpy>=1.20.0
matplotlib>=3.3.0
leidenalg>=0.8.0
```

### For Visualization:
```txt
scanpy>=1.9.0
matplotlib>=3.3.0
seaborn>=0.11.0
plotly>=5.0.0
```

Remember: These are example implementations from an early research prototype. Review and adapt them to your data and package versions.