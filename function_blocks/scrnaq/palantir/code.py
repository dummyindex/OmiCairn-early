def run(path_dict, params):
    """Run Palantir pseudotime analysis.
    
    This function block performs:
    - Proper Palantir workflow with correct API usage
    - Diffusion map computation
    - Pseudotime and entropy calculation
    - Branch probability estimation
    - Visualization of results
    """
    import scanpy as sc
    import palantir
    import pandas as pd
    import numpy as np
    import os
    import matplotlib.pyplot as plt
    
    # Load data
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    adata = sc.read_h5ad(input_file)
    
    # Ensure observation names are unique (required for Palantir)
    adata.obs_names_make_unique()
    
    # Get parameters with defaults
    n_components = params.get("n_components", 10)
    knn = params.get("knn", 30)
    start_cell = params.get("start_cell", None)
    terminal_states = params.get("terminal_states", None)
    num_waypoints = params.get("num_waypoints", 1200)
    scale_components = params.get("scale_components", True)
    use_early_cell_as_start = params.get("use_early_cell_as_start", True)
    
    # Ensure PCA is computed
    if "X_pca" not in adata.obsm:
        print("Computing PCA as it's required for Palantir...")
        sc.pp.pca(adata, n_comps=50)
    
    # Run Palantir workflow
    print("Running Palantir analysis...")
    
    # Step 1: Run diffusion maps (correct API)
    print(f"Computing diffusion maps with {n_components} components...")
    dm_res = palantir.utils.run_diffusion_maps(
        adata,
        n_components=n_components,
        knn=knn
    )
    
    # The result is stored in adata.obsm['X_diffmap']
    
    # Step 1.5: Determine multiscale space (required for Palantir)
    # Must pass the AnnData object, not dm_res dictionary
    print("Determining multiscale space...")
    palantir.utils.determine_multiscale_space(adata)
    
    # Step 2: Determine start cell if not provided
    if start_cell is None:
        if use_early_cell_as_start and 'leiden' in adata.obs.columns:
            # Find the cluster with lowest mean expression (potentially early cells)
            # This is a heuristic - in practice you'd use known markers
            cluster_means = {}
            for cluster in adata.obs['leiden'].unique():
                cluster_mask = adata.obs['leiden'] == cluster
                cluster_means[cluster] = np.mean(adata.X[cluster_mask, :].sum(axis=1))
            
            early_cluster = min(cluster_means, key=cluster_means.get)
            early_cells = adata.obs[adata.obs['leiden'] == early_cluster].index
            start_cell = early_cells[0]
            print(f"Selected start cell: {start_cell} from cluster {early_cluster}")
        else:
            # Use the first cell as default
            start_cell = adata.obs.index[0]
            print(f"No start cell specified, using first cell: {start_cell}")
    
    # Step 3: Run Palantir (correct API)
    print("Computing pseudotime and entropy...")
    pr_res = palantir.core.run_palantir(
        adata,
        start_cell,
        num_waypoints=num_waypoints,
        scale_components=scale_components,
        terminal_states=terminal_states
    )
    
    # Palantir results are stored in:
    # - adata.obs['palantir_pseudotime']
    # - adata.obs['palantir_entropy']
    # - adata.obsm['palantir_branch_probs'] (if terminal states detected)
    
    # Create output directory for figures
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    figures_dir = os.path.join(path_dict["output_dir"], "figures")
    os.makedirs(figures_dir, exist_ok=True)
    
    # Generate visualizations
    print("Generating visualizations...")
    
    # 1. Pseudotime on UMAP (if available)
    if 'X_umap' in adata.obsm:
        plt.figure(figsize=(12, 5))
        
        # Pseudotime plot
        plt.subplot(1, 2, 1)
        sc.pl.umap(adata, color='palantir_pseudotime', cmap='viridis', 
                   show=False, ax=plt.gca())
        plt.title('Palantir Pseudotime')
        
        # Entropy plot
        plt.subplot(1, 2, 2)
        sc.pl.umap(adata, color='palantir_entropy', cmap='inferno',
                   show=False, ax=plt.gca())
        plt.title('Differentiation Entropy')
        
        plt.tight_layout()
        plt.savefig(os.path.join(figures_dir, "palantir_pseudotime_umap.png"), 
                    dpi=300, bbox_inches="tight")
        plt.close()
    
    # 2. Pseudotime on diffusion map
    plt.figure(figsize=(12, 5))
    
    # Create diffusion map plots using the correct key
    plt.subplot(1, 2, 1)
    plt.scatter(adata.obsm['DM_EigenVectors'][:, 0], adata.obsm['DM_EigenVectors'][:, 1],
                c=adata.obs['palantir_pseudotime'], cmap='viridis', s=10)
    plt.colorbar(label='Pseudotime')
    plt.xlabel('DC1')
    plt.ylabel('DC2')
    plt.title('Palantir Pseudotime on Diffusion Map')
    
    plt.subplot(1, 2, 2)
    plt.scatter(adata.obsm['DM_EigenVectors'][:, 0], adata.obsm['DM_EigenVectors'][:, 1],
                c=adata.obs['palantir_entropy'], cmap='inferno', s=10)
    plt.colorbar(label='Entropy')
    plt.xlabel('DC1')
    plt.ylabel('DC2')
    plt.title('Differentiation Entropy on Diffusion Map')
    
    plt.tight_layout()
    plt.savefig(os.path.join(figures_dir, "palantir_diffusion_map.png"), 
                dpi=300, bbox_inches="tight")
    plt.close()
    
    # 3. Branch probabilities (if available)
    if 'palantir_branch_probs' in adata.obsm:
        n_branches = adata.obsm['palantir_branch_probs'].shape[1]
        fig, axes = plt.subplots(1, n_branches, figsize=(5*n_branches, 5))
        if n_branches == 1:
            axes = [axes]
        
        for i in range(n_branches):
            if 'X_umap' in adata.obsm:
                sc.pl.umap(adata, color=f'palantir_branch_{i}', 
                          cmap='RdYlBu_r', show=False, ax=axes[i])
                axes[i].set_title(f'Branch {i} Probability')
        
        plt.tight_layout()
        plt.savefig(os.path.join(figures_dir, "palantir_branch_probabilities.png"), 
                    dpi=300, bbox_inches="tight")
        plt.close()
    
    # Save pseudotime results as CSV
    pseudotime_df = pd.DataFrame({
        'cell_id': adata.obs.index,
        'palantir_pseudotime': adata.obs['palantir_pseudotime'],
        'palantir_entropy': adata.obs['palantir_entropy']
    })
    
    # Add branch probabilities if available
    if 'palantir_branch_probs' in adata.obsm:
        for i in range(adata.obsm['palantir_branch_probs'].shape[1]):
            pseudotime_df[f'branch_{i}_prob'] = adata.obsm['palantir_branch_probs'][:, i]
    
    pseudotime_df.to_csv(os.path.join(path_dict["output_dir"], "palantir_results.csv"), 
                         index=False)
    
    # Add metadata about the analysis
    adata.uns['pseudotime_params'] = {
        'method': 'Palantir',
        'start_cell': start_cell,
        'n_components': n_components,
        'knn': knn,
        'num_waypoints': num_waypoints,
        'scale_components': scale_components
    }
    
    # Save output
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    adata.write(output_file)
    
    print("Palantir analysis completed successfully")
    print(f"Output saved to: {output_file}")
    print(f"Figures saved to: {figures_dir}")
    print(f"Pseudotime range: {adata.obs['palantir_pseudotime'].min():.3f} to {adata.obs['palantir_pseudotime'].max():.3f}")
    print(f"Entropy range: {adata.obs['palantir_entropy'].min():.3f} to {adata.obs['palantir_entropy'].max():.3f}")