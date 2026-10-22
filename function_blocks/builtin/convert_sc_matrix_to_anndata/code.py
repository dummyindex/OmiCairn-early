def run(path_dict, params):
    """Convert shared single-cell matrix format back to AnnData."""
    import os
    import json
    import anndata
    import pandas as pd
    import numpy as np
    from scipy.io import mmread
    from pathlib import Path
    
    # Check for SC matrix
    sc_dir = Path(path_dict['input_dir']) / "_node_sc_matrix"
    if not sc_dir.exists():
        raise FileNotFoundError("No _node_sc_matrix directory found in input")
    
    # Read metadata
    with open(sc_dir / "metadata.json") as f:
        metadata = json.load(f)
    
    # Read cell and gene names
    with open(sc_dir / "obs_names.txt") as f:
        obs_names = [line.strip() for line in f if line.strip()]
    
    with open(sc_dir / "var_names.txt") as f:
        var_names = [line.strip() for line in f if line.strip()]
    
    # Read expression matrix
    if (sc_dir / "X.mtx").exists():
        X = mmread(sc_dir / "X.mtx").tocsr()
    elif (sc_dir / "X.csv").exists():
        X = pd.read_csv(sc_dir / "X.csv", index_col=0).values
    else:
        raise FileNotFoundError("No expression matrix found (X.mtx or X.csv)")
    
    # Create AnnData object
    adata = anndata.AnnData(X=X)
    adata.obs_names = obs_names
    adata.var_names = var_names
    
    # Load cell metadata
    obs_dir = sc_dir / "obs"
    if obs_dir.exists():
        for csv_file in obs_dir.glob("*.csv"):
            col_name = csv_file.stem
            df = pd.read_csv(csv_file)
            if len(df) == adata.n_obs:
                adata.obs[col_name] = df.iloc[:, 0].values
    
    # Load gene metadata
    var_dir = sc_dir / "var"
    if var_dir.exists():
        for csv_file in var_dir.glob("*.csv"):
            col_name = csv_file.stem
            df = pd.read_csv(csv_file)
            if len(df) == adata.n_vars:
                adata.var[col_name] = df.iloc[:, 0].values
    
    # Load layers if available
    layers_dir = sc_dir / "layers"
    if layers_dir.exists():
        for mtx_file in layers_dir.glob("*.mtx"):
            layer_name = mtx_file.stem
            layer_matrix = mmread(mtx_file).tocsr()
            if layer_matrix.shape == adata.shape:
                adata.layers[layer_name] = layer_matrix
    
    # Add conversion metadata
    adata.uns['conversion_from'] = 'sc_matrix'
    adata.uns['original_source'] = metadata.get('source_format', 'unknown')
    
    # Save AnnData
    output_path = Path(path_dict['output_dir']) / "_node_anndata.h5ad"
    adata.write_h5ad(output_path)
    
    # Also preserve the SC matrix
    import shutil
    shutil.copytree(sc_dir, Path(path_dict['output_dir']) / "_node_sc_matrix")
    
    print(f"Created AnnData object: {adata.n_obs} cells x {adata.n_vars} genes")
    print(f"Observations: {list(adata.obs.columns)}")
    print(f"Variables: {list(adata.var.columns)}")
    print(f"Layers: {list(adata.layers.keys())}")
    
    return {
        "success": True,
        "message": f"Successfully converted to AnnData: {adata.n_obs} cells, {adata.n_vars} genes"
    }