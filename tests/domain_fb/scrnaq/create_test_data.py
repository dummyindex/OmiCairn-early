#!/usr/bin/env python3
"""Create properly preprocessed test data for pseudotime analysis."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import scanpy as sc
import numpy as np
import pandas as pd
from pathlib import Path

def create_test_data():
    """Create a simple test dataset with proper preprocessing."""
    
    # Load the zebrafish data
    input_path = Path(__file__).parent / "zebrafish_test.h5ad"
    output_path = Path(__file__).parent / "test_data_ready.h5ad"
    
    if input_path.exists():
        print(f"Loading {input_path}")
        adata = sc.read_h5ad(input_path)
        print(f"Original shape: {adata.shape}")
        
        # Basic preprocessing if not done
        if 'X_pca' not in adata.obsm:
            print("Preprocessing data...")
            
            # Make sure we have unique obs names
            adata.obs_names_make_unique()
            
            # Basic filtering
            sc.pp.filter_cells(adata, min_genes=200)
            sc.pp.filter_genes(adata, min_cells=3)
            
            # Save raw counts
            adata.raw = adata
            
            # Normalization
            sc.pp.normalize_total(adata, target_sum=1e4)
            sc.pp.log1p(adata)
            
            # Find highly variable genes
            sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
            adata = adata[:, adata.var.highly_variable]
            
            # Scale
            sc.pp.scale(adata, max_value=10)
            
            # PCA
            print("Computing PCA...")
            sc.tl.pca(adata, svd_solver='arpack', n_comps=50)
            
            # Neighbors
            print("Computing neighbors...")
            sc.pp.neighbors(adata, n_neighbors=10, n_pcs=40)
            
            # UMAP
            print("Computing UMAP...")
            sc.tl.umap(adata)
            
            # Clustering - create synthetic clusters based on UMAP
            print("Creating clustering...")
            # Use kmeans on UMAP to create clusters
            from sklearn.cluster import KMeans
            n_clusters = 5
            kmeans = KMeans(n_clusters=n_clusters, random_state=42)
            clusters = kmeans.fit_predict(adata.obsm['X_umap'])
            adata.obs['leiden'] = pd.Categorical(clusters.astype(str))
            
            print(f"Preprocessed shape: {adata.shape}")
    else:
        # Create synthetic data
        print("Creating synthetic test data...")
        
        n_obs = 1000
        n_vars = 2000
        
        # Create count matrix
        counts = np.random.negative_binomial(5, 0.3, size=(n_obs, n_vars))
        adata = sc.AnnData(counts)
        
        # Create some structure - 3 groups
        groups = np.repeat([0, 1, 2], n_obs // 3 + 1)[:n_obs]
        
        # Add group-specific genes
        for i in range(3):
            mask = groups == i
            start_gene = i * 100
            end_gene = (i + 1) * 100
            adata.X[mask, start_gene:end_gene] *= 5
        
        adata.obs['group'] = pd.Categorical(groups)
        
        # Standard preprocessing
        print("Preprocessing synthetic data...")
        adata.obs_names = [f"Cell_{i:04d}" for i in range(n_obs)]
        adata.var_names = [f"Gene_{i:04d}" for i in range(n_vars)]
        
        # Save raw
        adata.raw = adata
        
        # Normalize and log
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        
        # HVG
        sc.pp.highly_variable_genes(adata, n_top_genes=1000)
        adata = adata[:, adata.var.highly_variable]
        
        # Scale
        sc.pp.scale(adata, max_value=10)
        
        # PCA
        sc.tl.pca(adata, svd_solver='arpack', n_comps=50)
        
        # Neighbors
        sc.pp.neighbors(adata, n_neighbors=10, n_pcs=40)
        
        # UMAP
        sc.tl.umap(adata)
        
        # Clustering - use the predefined groups
        adata.obs['leiden'] = adata.obs['group'].astype(str)
    
    # Add some additional metadata
    adata.uns['test_data'] = True
    adata.uns['preprocessing_complete'] = True
    
    # Save
    print(f"\nSaving to {output_path}")
    adata.write(output_path)
    
    # Summary
    print("\nDataset summary:")
    print(f"  Shape: {adata.shape}")
    print(f"  Has raw: {adata.raw is not None}")
    print(f"  Has PCA: {'X_pca' in adata.obsm}")
    print(f"  Has UMAP: {'X_umap' in adata.obsm}")
    print(f"  Has neighbors: {'neighbors' in adata.uns}")
    print(f"  Has leiden: {'leiden' in adata.obs}")
    print(f"  N clusters: {adata.obs['leiden'].nunique()}")
    
    return output_path


if __name__ == "__main__":
    create_test_data()