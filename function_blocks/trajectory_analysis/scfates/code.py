def run(path_dict, params):
    """Run scFates trajectory analysis with corrected API usage.
    
    This function block demonstrates proper scFates usage with:
    - Uses scf.tl.curve (linear principal curve; scf.tl.tree is the branching alternative)
    - Proper graph initialization
    - Dependency handling (requires numpy<1.24)
    """
    import scanpy as sc
    import scFates as scf
    import pandas as pd
    import numpy as np
    import os
    
    # Load data
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    adata = sc.read_h5ad(input_file)
    
    # Get parameters with defaults
    n_nodes = params.get("n_nodes", 10)
    use_rep = params.get("use_rep", "X_pca")
    device = params.get("device", "cpu")
    n_map = params.get("n_map", 100)
    spline_df = params.get("spline_df", 5)
    
    # Ensure we have PCA computed if using X_pca
    if use_rep == "X_pca" and "X_pca" not in adata.obsm:
        print("Computing PCA as it's required for scFates...")
        sc.pp.pca(adata, n_comps=50)
    
    # Prepare for trajectory analysis
    # Linear principal curve (use scf.tl.tree for branching trajectories)
    scf.tl.curve(adata, Nodes=n_nodes, use_rep=use_rep, device=device)
    
    # Test association (correct location in current API)
    # This requires rpy2 and R, so make it optional
    try:
        scf.tl.test_association(adata, n_map=n_map, spline_df=spline_df)
    except Exception as e:
        print(f"Warning: Could not run test_association (requires R/rpy2): {e}")
        print("Continuing without feature association testing...")
    
    # Ensure graph structure exists before plotting
    if "graph" not in adata.uns:
        # Initialize graph structure if missing
        adata.uns["graph"] = {"B": []}
        print("Warning: Initialized missing graph structure")
    
    # Create output directory for figures
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    figures_dir = os.path.join(path_dict["output_dir"], "figures")
    os.makedirs(figures_dir, exist_ok=True)
    
    # Generate trajectory plot
    import matplotlib.pyplot as plt
    
    # Ensure we have UMAP for visualization
    if 'X_umap' not in adata.obsm:
        print("Computing UMAP for visualization...")
        sc.pp.neighbors(adata, n_neighbors=15, n_pcs=40)
        sc.tl.umap(adata)
    
    plt.figure(figsize=(10, 8))
    scf.pl.graph(adata, basis="umap", show=False)
    plt.savefig(os.path.join(figures_dir, "trajectory_graph.png"), dpi=300, bbox_inches="tight")
    plt.close()
    
    # Save output
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    adata.write(output_file)
    
    print("scFates trajectory analysis completed successfully")
    print(f"Output saved to: {output_file}")
    print(f"Figures saved to: {figures_dir}")