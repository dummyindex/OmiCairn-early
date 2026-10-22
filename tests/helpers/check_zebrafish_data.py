#!/usr/bin/env python3
"""Check zebrafish data structure."""

import os
import sys
import scanpy as sc
from pathlib import Path

# Load data
data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("TEST_DATA_DIR", "test_data")) / "zebrafish.h5ad"
adata = sc.read_h5ad(data_path)

print(f"Data shape: {adata.shape}")
print(f"\nObservation columns: {list(adata.obs.columns)}")
print(f"\nVariable columns: {list(adata.var.columns)}")
print(f"\nLayers: {list(adata.layers.keys())}")
print(f"\nObsm keys: {list(adata.obsm.keys())}")
print(f"\nUns keys: {list(adata.uns.keys())}")

# Check for potential cell type columns
potential_cell_type_cols = [col for col in adata.obs.columns if 
                            'cell' in col.lower() or 
                            'type' in col.lower() or 
                            'cluster' in col.lower() or
                            'label' in col.lower()]

print(f"\nPotential cell type columns: {potential_cell_type_cols}")

if potential_cell_type_cols:
    for col in potential_cell_type_cols[:3]:  # Show first 3
        print(f"\n{col} unique values ({adata.obs[col].nunique()}): {list(adata.obs[col].unique()[:10])}")