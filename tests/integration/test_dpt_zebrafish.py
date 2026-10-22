#!/usr/bin/env python3
"""Test DPT with zebrafish data to check the exact error."""

if __name__ != "__main__":  # manual script: do not execute at pytest collection time
    import pytest
    pytest.skip("manual diagnostic script; run directly with python", allow_module_level=True)

import scanpy as sc
import os

# Load zebrafish data
print("Loading zebrafish data...")
adata = sc.read_h5ad("test_data/zebrafish.h5ad")
print(f"Loaded data: {adata.shape[0]} cells, {adata.shape[1]} genes")

# The failing code from pseudotime_analysis_dpt
print("\nRunning failing code sequence...")
try:
    # Data Preprocessing (this duplicates work already done!)
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
    adata = adata[:, adata.var["highly_variable"].values]
    sc.pp.pca(adata, n_comps=50)
    sc.pp.neighbors(adata)
    sc.tl.umap(adata)
    
    print("Preprocessing completed")
    
    # Pseudotime Analysis using DPT
    sc.tl.dpt(adata)
    
    print("DPT completed")
    print(f"dpt_pseudotime in obs? {'dpt_pseudotime' in adata.obs.columns}")
    
    # Try to plot
    sc.pl.umap(adata, color="dpt_pseudotime", save="_test.png", show=False)
    print("✓ Success! Plot created")
    
except Exception as e:
    print(f"\n✗ Error occurred: {type(e).__name__}: {e}")
    print(f"\nColumns in adata.obs: {list(adata.obs.columns)}")
    
    # Check what DPT actually creates
    if 'dpt_pseudotime' in adata.obs.columns:
        print("dpt_pseudotime EXISTS but plotting failed")
    else:
        print("\nDPT-related columns:")
        dpt_cols = [col for col in adata.obs.columns if 'dpt' in col.lower()]
        print(f"Found: {dpt_cols}")
        
        # Check uns keys
        print("\nDPT-related uns keys:")
        dpt_uns = [key for key in adata.uns.keys() if 'dpt' in key.lower()]
        print(f"Found: {dpt_uns}")