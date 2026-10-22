#!/usr/bin/env python3
"""Simple test to verify DPT works correctly."""

if __name__ != "__main__":  # manual script: do not execute at pytest collection time
    import pytest
    pytest.skip("manual diagnostic script; run directly with python", allow_module_level=True)

import scanpy as sc
import numpy as np
import os

# Create test data
print("Creating test data...")
adata = sc.datasets.pbmc68k_reduced()

# Preprocessing
print("Preprocessing...")
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)
sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
adata = adata[:, adata.var.highly_variable]

# PCA
print("Running PCA...")
sc.pp.pca(adata, n_comps=50)

# Neighbors
print("Computing neighbors...")
sc.pp.neighbors(adata, n_neighbors=10, n_pcs=40)

# UMAP
print("Computing UMAP...")
sc.tl.umap(adata)

# Set root cell
print("Setting root cell...")
adata.uns['iroot'] = 0

# Diffusion map
print("Computing diffusion map...")
sc.tl.diffmap(adata)

# DPT
print("Computing DPT...")
sc.tl.dpt(adata)

# Check if dpt_pseudotime exists
if 'dpt_pseudotime' in adata.obs.columns:
    print(f"✓ Success! DPT pseudotime computed. Range: {adata.obs['dpt_pseudotime'].min():.3f} - {adata.obs['dpt_pseudotime'].max():.3f}")
else:
    print("✗ Failed! dpt_pseudotime not found in adata.obs.columns")
    print(f"Available columns: {list(adata.obs.columns)}")

# Save figure
print("Saving UMAP colored by pseudotime...")
os.makedirs("figures", exist_ok=True)
sc.settings.figdir = "figures"
sc.pl.umap(adata, color='dpt_pseudotime', save='_pseudotime.png', show=False)