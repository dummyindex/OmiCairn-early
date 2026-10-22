#!/usr/bin/env python3
"""Test DPT with proper setup."""

if __name__ != "__main__":  # manual script: do not execute at pytest collection time
    import pytest
    pytest.skip("manual diagnostic script; run directly with python", allow_module_level=True)

import scanpy as sc
import numpy as np

# Load zebrafish data
print("Loading zebrafish data...")
adata = sc.read_h5ad("test_data/zebrafish.h5ad")
print(f"Loaded data: {adata.shape[0]} cells, {adata.shape[1]} genes")

# Check if data is already processed
print("\nChecking data state...")
print(f"X max value: {adata.X.max()}")
print(f"Has PCA: {'X_pca' in adata.obsm}")
print(f"Has neighbors: {'connectivities' in adata.obsp}")

# Prepare data properly
print("\nPreparing data for DPT...")

# Make observation names unique
adata.obs_names_make_unique()

# Skip normalization if already done (X max < 20 suggests log-normalized)
if adata.X.max() > 20:
    print("Normalizing...")
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
else:
    print("Data appears already normalized")

# Filter for highly variable genes
print("Finding highly variable genes...")
sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
adata = adata[:, adata.var.highly_variable]
print(f"Reduced to {adata.shape[1]} highly variable genes")

# PCA
print("Running PCA...")
sc.pp.pca(adata, n_comps=50)

# Neighbors
print("Computing neighbors...")
sc.pp.neighbors(adata, n_neighbors=10, n_pcs=40)

# UMAP
print("Computing UMAP...")
sc.tl.umap(adata)

# CRITICAL: Set root cell BEFORE running dpt
print("\nSetting root cell...")
# Option 1: Use first cell as root
adata.uns['iroot'] = 0

# Option 2: Find a cell in a specific cluster/condition
# root_cluster = 'early_stage'  # example
# root_idx = np.where(adata.obs['condition'] == root_cluster)[0][0]
# adata.uns['iroot'] = root_idx

print(f"Root cell set to index: {adata.uns['iroot']}")

# Compute diffusion map first
print("\nComputing diffusion map...")
sc.tl.diffmap(adata)

# Now compute DPT
print("Computing DPT...")
sc.tl.dpt(adata)

# Check results
print("\nChecking results...")
print(f"dpt_pseudotime in obs? {'dpt_pseudotime' in adata.obs.columns}")

if 'dpt_pseudotime' in adata.obs.columns:
    print(f"✓ Success! Pseudotime range: {adata.obs['dpt_pseudotime'].min():.3f} - {adata.obs['dpt_pseudotime'].max():.3f}")
    
    # Save plot
    import os
    os.makedirs("figures", exist_ok=True)
    sc.settings.figdir = "figures"
    sc.pl.umap(adata, color='dpt_pseudotime', save='_test_pseudotime.png', show=False)
    print("✓ Plot saved to figures/umap_test_pseudotime.png")
else:
    print("✗ dpt_pseudotime not found!")
    print(f"Available columns: {list(adata.obs.columns)}")
    print(f"Available uns keys: {list(adata.uns.keys())}")