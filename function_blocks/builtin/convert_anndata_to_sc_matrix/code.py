#!/usr/bin/env python3
"""
Convert AnnData to _node_sc_matrix format.

This function block converts an AnnData object to a structured format that can be
read by both Python and R. It creates a _node_sc_matrix folder with subfolders
following the AnnData structure (obs, var, obsm, varm, layers, etc.).
"""

def run(path_dict, params):
    """
    Convert AnnData to shared single-cell matrix format.
    
    Args:
        path_dict: Dictionary with 'input_dir' and 'output_dir' paths
        params: Dictionary of parameters (unused)
    
    Returns:
        Dict with conversion status and output paths
    """
    import os
    import json
    import anndata
    import pandas as pd
    import numpy as np
    from scipy.io import mmwrite
    from scipy.sparse import issparse
    from pathlib import Path
    
    input_dir = Path(path_dict['input_dir'])
    output_dir = Path(path_dict['output_dir'])
    
    # Find AnnData file
    h5ad_files = list(input_dir.glob('_node_anndata.h5ad'))
    if not h5ad_files:
        raise FileNotFoundError("No _node_anndata.h5ad file found in input directory")
    
    adata_path = h5ad_files[0]
    print(f"Loading AnnData from: {adata_path}")
    
    # Load AnnData
    adata = anndata.read_h5ad(adata_path)
    print(f"Loaded AnnData with shape: {adata.shape}")
    
    # Create output structure
    sc_matrix_dir = output_dir / '_node_sc_matrix'
    sc_matrix_dir.mkdir(exist_ok=True)
    
    # Helper function to write matrix
    def write_matrix(matrix, path, name):
        """Write matrix in appropriate format."""
        if issparse(matrix):
            # Write as MTX format for sparse matrices
            mmwrite(str(path / f"{name}.mtx"), matrix)
            return {"type": "sparse", "format": "mtx", "shape": list(matrix.shape)}
        else:
            # Write as CSV for dense matrices
            if isinstance(matrix, pd.DataFrame):
                matrix.to_csv(path / f"{name}.csv", index=False)
            else:
                np.savetxt(path / f"{name}.csv", matrix, delimiter=',')
            return {"type": "dense", "format": "csv", "shape": list(matrix.shape)}
    
    # Create metadata dictionary
    metadata = {
        "source": "anndata",
        "shape": list(adata.shape),
        "components": {}
    }
    
    # 1. Write cell and gene names
    with open(sc_matrix_dir / 'obs_names.txt', 'w') as f:
        for name in adata.obs_names:
            f.write(f"{name}\n")
    
    with open(sc_matrix_dir / 'var_names.txt', 'w') as f:
        for name in adata.var_names:
            f.write(f"{name}\n")
    
    # 2. Write main expression matrix (X)
    x_info = write_matrix(adata.X, sc_matrix_dir, 'X')
    metadata['components']['X'] = x_info
    
    # 3. Write obs (cell metadata)
    if len(adata.obs.columns) > 0:
        obs_dir = sc_matrix_dir / 'obs'
        obs_dir.mkdir(exist_ok=True)
        
        obs_info = {}
        for col in adata.obs.columns:
            series = adata.obs[col]
            series.to_csv(obs_dir / f"{col}.csv", index=False, header=[col])
            obs_info[col] = {
                "dtype": str(series.dtype),
                "shape": len(series)
            }
        metadata['components']['obs'] = obs_info
    
    # 4. Write var (gene metadata)
    if len(adata.var.columns) > 0:
        var_dir = sc_matrix_dir / 'var'
        var_dir.mkdir(exist_ok=True)
        
        var_info = {}
        for col in adata.var.columns:
            series = adata.var[col]
            series.to_csv(var_dir / f"{col}.csv", index=False, header=[col])
            var_info[col] = {
                "dtype": str(series.dtype),
                "shape": len(series)
            }
        metadata['components']['var'] = var_info
    
    # 5. Write obsm (cell embeddings)
    if len(adata.obsm.keys()) > 0:
        obsm_dir = sc_matrix_dir / 'obsm'
        obsm_dir.mkdir(exist_ok=True)
        
        obsm_info = {}
        for key in adata.obsm.keys():
            matrix = adata.obsm[key]
            info = write_matrix(matrix, obsm_dir, key)
            obsm_info[key] = info
        metadata['components']['obsm'] = obsm_info
    
    # 6. Write layers (additional expression matrices)
    if len(adata.layers.keys()) > 0:
        layers_dir = sc_matrix_dir / 'layers'
        layers_dir.mkdir(exist_ok=True)
        
        layers_info = {}
        for key in adata.layers.keys():
            matrix = adata.layers[key]
            info = write_matrix(matrix, layers_dir, key)
            layers_info[key] = info
        metadata['components']['layers'] = layers_info
    
    # 7. Write varm (gene embeddings) if present
    if hasattr(adata, 'varm') and len(adata.varm.keys()) > 0:
        varm_dir = sc_matrix_dir / 'varm'
        varm_dir.mkdir(exist_ok=True)
        
        varm_info = {}
        for key in adata.varm.keys():
            matrix = adata.varm[key]
            info = write_matrix(matrix, varm_dir, key)
            varm_info[key] = info
        metadata['components']['varm'] = varm_info
    
    # 8. Write metadata file
    with open(sc_matrix_dir / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Copy original files to output
    import shutil
    shutil.copy2(adata_path, output_dir / '_node_anndata.h5ad')
    
    # Check if Seurat object exists and copy it
    rds_files = list(input_dir.glob('_node_seuratObject.rds'))
    if rds_files:
        shutil.copy2(rds_files[0], output_dir / '_node_seuratObject.rds')
    
    print(f"Successfully converted AnnData to _node_sc_matrix format")
    print(f"Output directory: {sc_matrix_dir}")
    print(f"Components written: {list(metadata['components'].keys())}")
    
    return {
        "status": "success",
        "sc_matrix_path": str(sc_matrix_dir),
        "components": list(metadata['components'].keys()),
        "shape": metadata['shape']
    }