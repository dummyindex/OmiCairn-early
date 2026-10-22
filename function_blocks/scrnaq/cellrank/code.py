def run(path_dict, params):
    """Run CellRank trajectory analysis using precomputed pseudotime.
    
    CellRank requires pseudotime as input and uses it to compute:
    - Directed transition matrices
    - Terminal/initial states
    - Fate probabilities
    
    This function expects pseudotime to be present in the input data.
    """
    import scanpy as sc
    import cellrank as cr
    import pandas as pd
    import numpy as np
    import os
    import matplotlib.pyplot as plt
    
    # Load data
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    adata = sc.read_h5ad(input_file)
    
    # Get parameters with defaults
    pseudotime_key = params.get("pseudotime_key", "dpt_pseudotime")
    kernel_type = params.get("kernel_type", "pseudotime")  # "pseudotime" or "velocity"
    n_states = params.get("n_states", None)  # Auto-detect if None
    cluster_key = params.get("cluster_key", "leiden")
    basis = params.get("basis", "umap")
    
    print(f"Running CellRank with {kernel_type} kernel...")
    print(f"Using pseudotime from: {pseudotime_key}")
    
    # Check if pseudotime is available
    if pseudotime_key not in adata.obs:
        available_pseudotime_keys = [col for col in adata.obs.columns if 'pseudotime' in col.lower()]
        if available_pseudotime_keys:
            print(f"Warning: '{pseudotime_key}' not found. Available pseudotime columns: {available_pseudotime_keys}")
            pseudotime_key = available_pseudotime_keys[0]
            print(f"Using: {pseudotime_key}")
        else:
            raise ValueError(f"No pseudotime found in adata.obs. CellRank requires precomputed pseudotime. "
                           f"Available columns: {list(adata.obs.columns)}")
    
    # Ensure required preprocessing
    if 'neighbors' not in adata.uns:
        print("Computing neighbor graph...")
        sc.pp.neighbors(adata, n_neighbors=30, n_pcs=30)
    
    if f'X_{basis}' not in adata.obsm:
        print(f"Computing {basis} embedding...")
        if basis == "umap":
            sc.tl.umap(adata)
        elif basis == "tsne":
            sc.tl.tsne(adata)
    
    # Ensure we have clustering
    if cluster_key not in adata.obs:
        print(f"Computing {cluster_key} clustering...")
        if cluster_key == "leiden":
            sc.tl.leiden(adata)
    
    # Initialize CellRank kernel based on type
    if kernel_type == "pseudotime":
        # Use PseudotimeKernel with precomputed pseudotime
        from cellrank.kernels import PseudotimeKernel
        pk = PseudotimeKernel(adata, time_key=pseudotime_key)
        pk.compute_transition_matrix()
        kernel = pk
    
    elif kernel_type == "velocity":
        # Check if velocity information is available
        if 'velocity_graph' not in adata.uns:
            print("Warning: No velocity information found, falling back to pseudotime kernel")
            from cellrank.kernels import PseudotimeKernel
            pk = PseudotimeKernel(adata, time_key=pseudotime_key)
            pk.compute_transition_matrix()
            kernel = pk
        else:
            from cellrank.kernels import VelocityKernel
            vk = VelocityKernel(adata)
            vk.compute_transition_matrix()
            kernel = vk
    
    # Store transition matrix
    adata.obsp['cellrank_transition_matrix'] = kernel.transition_matrix
    
    # Compute terminal states using GPCCA
    from cellrank.estimators import GPCCA
    g = GPCCA(kernel)
    
    print("Identifying terminal and initial states...")
    
    try:
        # Fit the estimator
        g.fit(cluster_key=cluster_key, n_states=n_states)
        
        # Predict terminal states
        g.predict_terminal_states()
        if hasattr(g, 'terminal_states') and g.terminal_states is not None:
            print(f"Identified {len(g.terminal_states.cat.categories)} terminal states")
            adata.obs['cellrank_terminal_states'] = g.terminal_states
        
        # Predict initial states
        g.predict_initial_states()
        if hasattr(g, 'initial_states') and g.initial_states is not None:
            print(f"Identified {len(g.initial_states.cat.categories)} initial states")
            adata.obs['cellrank_initial_states'] = g.initial_states
        
        # Compute fate probabilities
        if hasattr(g, 'terminal_states') and g.terminal_states is not None:
            print("Computing fate probabilities...")
            g.compute_fate_probabilities()
            
            # Store fate probabilities
            if hasattr(g, 'fate_probabilities'):
                adata.obsm['cellrank_fate_probabilities'] = g.fate_probabilities.X
                
                # Also add individual columns for easy access
                for i, state in enumerate(g.fate_probabilities.names):
                    adata.obs[f'fate_prob_{state}'] = g.fate_probabilities[:, state].X.squeeze()
    
    except Exception as e:
        print(f"Warning: Could not complete full CellRank analysis: {e}")
        print("Transition matrix has been computed and saved.")
    
    # Create output directory for figures
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    figures_dir = os.path.join(path_dict["output_dir"], "figures")
    os.makedirs(figures_dir, exist_ok=True)
    
    # Generate visualizations
    print("Generating visualizations...")
    
    # 1. Pseudotime visualization
    plt.figure(figsize=(10, 8))
    sc.pl.embedding(adata, basis=basis, color=pseudotime_key, show=False, ax=plt.gca())
    plt.title(f"Input Pseudotime ({pseudotime_key})")
    plt.savefig(os.path.join(figures_dir, "cellrank_input_pseudotime.png"), dpi=300, bbox_inches="tight")
    plt.close()
    
    # 2. Terminal states if available
    if 'cellrank_terminal_states' in adata.obs:
        plt.figure(figsize=(10, 8))
        sc.pl.embedding(adata, basis=basis, color='cellrank_terminal_states', show=False, ax=plt.gca())
        plt.title("CellRank Terminal States")
        plt.savefig(os.path.join(figures_dir, "cellrank_terminal_states.png"), dpi=300, bbox_inches="tight")
        plt.close()
    
    # Save results summary
    results_df = pd.DataFrame({
        'cell_id': adata.obs.index,
        pseudotime_key: adata.obs[pseudotime_key]
    })
    
    # Add terminal/initial states if computed
    if 'cellrank_terminal_states' in adata.obs:
        results_df['terminal_state'] = adata.obs['cellrank_terminal_states']
    if 'cellrank_initial_states' in adata.obs:
        results_df['initial_state'] = adata.obs['cellrank_initial_states']
    
    # Add fate probabilities if computed
    fate_prob_cols = [col for col in adata.obs.columns if col.startswith('fate_prob_')]
    for col in fate_prob_cols:
        results_df[col] = adata.obs[col]
    
    results_df.to_csv(os.path.join(path_dict["output_dir"], "cellrank_results.csv"), index=False)
    
    # Add metadata about the analysis
    adata.uns['cellrank_params'] = {
        'method': 'CellRank',
        'kernel_type': kernel_type,
        'pseudotime_key': pseudotime_key,
        'n_terminal_states': len(g.terminal_states.cat.categories) if hasattr(g, 'terminal_states') and g.terminal_states is not None else 0,
        'n_initial_states': len(g.initial_states.cat.categories) if hasattr(g, 'initial_states') and g.initial_states is not None else 0
    }
    
    # Save output
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    adata.write(output_file)
    
    print("CellRank analysis completed successfully")
    print(f"Output saved to: {output_file}")
    print(f"Transition matrix stored in: adata.obsp['cellrank_transition_matrix']")
    
    # Summary
    print("\nAnalysis Summary:")
    print(f"- Input pseudotime: {pseudotime_key}")
    print(f"- Kernel type: {kernel_type}")
    print(f"- Transition matrix shape: {adata.obsp['cellrank_transition_matrix'].shape}")
    if 'cellrank_terminal_states' in adata.obs:
        print(f"- Terminal states identified: {len(adata.obs['cellrank_terminal_states'].cat.categories)}")
    if 'cellrank_initial_states' in adata.obs:
        print(f"- Initial states identified: {len(adata.obs['cellrank_initial_states'].cat.categories)}")