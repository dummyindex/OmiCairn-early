def run(path_dict, params):
    """Run DPT (Diffusion Pseudotime) and PAGA analysis.
    
    This function block performs:
    - Neighbor graph computation if needed
    - PAGA (partition-based graph abstraction) analysis
    - Diffusion pseudotime computation
    - Visualization of results
    """
    import scanpy as sc
    import pandas as pd
    import numpy as np
    import os
    import matplotlib.pyplot as plt
    
    # Load data
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    adata = sc.read_h5ad(input_file)
    
    # Get parameters with defaults
    n_neighbors = params.get("n_neighbors", 15)
    n_pcs = params.get("n_pcs", 50)
    use_rep = params.get("use_rep", "X_pca")
    clustering_key = params.get("clustering_key", "leiden")
    root_cluster = params.get("root_cluster", None)
    n_dcs = params.get("n_dcs", 15)
    
    # Ensure PCA is computed if using X_pca
    if use_rep == "X_pca" and "X_pca" not in adata.obsm:
        print("Computing PCA as it's required but not present...")
        sc.pp.pca(adata, n_comps=n_pcs)
    
    # Compute neighbor graph if not present
    if 'neighbors' not in adata.uns:
        print(f"Computing neighbor graph with {n_neighbors} neighbors...")
        sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs, use_rep=use_rep)
    
    # Ensure clustering is present
    if clustering_key not in adata.obs.columns:
        print(f"Computing {clustering_key} clustering...")
        if clustering_key == "leiden":
            sc.tl.leiden(adata)
        elif clustering_key == "louvain":
            sc.tl.louvain(adata)
        else:
            raise ValueError(f"Unknown clustering method: {clustering_key}")
    
    # Run PAGA
    print("Running PAGA analysis...")
    sc.tl.paga(adata, groups=clustering_key)
    
    # Compute diffusion map if not present
    if 'X_diffmap' not in adata.obsm:
        print("Computing diffusion map...")
        sc.tl.diffmap(adata, n_comps=n_dcs)
    
    # Set root for pseudotime
    if root_cluster is None:
        # No automatic root inference: default to the first cluster category.
        # Specify root_cluster explicitly for biologically meaningful pseudotime.
        print("No root cluster specified, using first cluster as root")
        root_cluster = adata.obs[clustering_key].cat.categories[0]
    
    # Set root cell as a cell from the root cluster
    root_cell_mask = adata.obs[clustering_key] == str(root_cluster)
    if not root_cell_mask.any():
        print(f"Warning: Root cluster {root_cluster} not found, using first cluster")
        root_cluster = adata.obs[clustering_key].cat.categories[0]
        root_cell_mask = adata.obs[clustering_key] == str(root_cluster)
    
    root_cell_idx = np.where(root_cell_mask)[0][0]
    adata.uns['iroot'] = root_cell_idx
    print(f"Set root to cell {root_cell_idx} from cluster {root_cluster}")
    
    # Compute DPT (Diffusion Pseudotime)
    print("Computing diffusion pseudotime...")
    sc.tl.dpt(adata)
    
    # Create output directory for figures
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    figures_dir = os.path.join(path_dict["output_dir"], "figures")
    os.makedirs(figures_dir, exist_ok=True)
    
    # Generate visualizations
    print("Generating visualizations...")
    
    # 1. PAGA graph
    plt.figure(figsize=(8, 8))
    sc.pl.paga(adata, show=False)
    plt.savefig(os.path.join(figures_dir, "paga_graph.png"), dpi=300, bbox_inches="tight")
    plt.close()
    
    # 2. PAGA with UMAP overlay
    if 'X_umap' in adata.obsm:
        plt.figure(figsize=(10, 8))
        sc.pl.paga(adata, pos=adata.uns['paga']['pos'], show=False)
        plt.savefig(os.path.join(figures_dir, "paga_umap_overlay.png"), dpi=300, bbox_inches="tight")
        plt.close()
    
    # 3. DPT pseudotime on UMAP
    if 'X_umap' in adata.obsm:
        plt.figure(figsize=(10, 8))
        sc.pl.umap(adata, color=['dpt_pseudotime', clustering_key], 
                   cmap='viridis', show=False, ncols=2)
        plt.savefig(os.path.join(figures_dir, "dpt_pseudotime_umap.png"), 
                    dpi=300, bbox_inches="tight")
        plt.close()
    
    # 4. Diffusion map colored by pseudotime
    plt.figure(figsize=(10, 8))
    sc.pl.diffmap(adata, color=['dpt_pseudotime', clustering_key], 
                  cmap='viridis', show=False, ncols=2)
    plt.savefig(os.path.join(figures_dir, "dpt_pseudotime_diffmap.png"), 
                dpi=300, bbox_inches="tight")
    plt.close()
    
    # Save pseudotime results as CSV
    pseudotime_df = pd.DataFrame({
        'cell_id': adata.obs.index,
        'dpt_pseudotime': adata.obs['dpt_pseudotime'],
        'cluster': adata.obs[clustering_key]
    })
    pseudotime_df.to_csv(os.path.join(path_dict["output_dir"], "dpt_pseudotime.csv"), 
                         index=False)
    
    # Add metadata about the analysis
    adata.uns['pseudotime_params'] = {
        'method': 'DPT+PAGA',
        'root_cluster': str(root_cluster),
        'root_cell': int(root_cell_idx),
        'n_neighbors': n_neighbors,
        'n_pcs': n_pcs,
        'n_dcs': n_dcs,
        'clustering_key': clustering_key
    }
    
    # Save output
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    adata.write(output_file)
    
    print("DPT + PAGA analysis completed successfully")
    print(f"Output saved to: {output_file}")
    print(f"Figures saved to: {figures_dir}")
    print(f"Pseudotime range: {adata.obs['dpt_pseudotime'].min():.3f} to {adata.obs['dpt_pseudotime'].max():.3f}")