#!/usr/bin/env python3
"""Test fix for root cell selection issue."""

import os
import sys
import numpy as np
import scanpy as sc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import setup_logger

logger = setup_logger(__name__)


def test_root_cell_selection_fix():
    """Test the fixed root cell selection code."""
    
    # Create test data
    logger.info("Creating test data...")
    n_obs = 500
    n_vars = 100
    X = np.random.randn(n_obs, n_vars)
    adata = sc.AnnData(X=X)
    adata.obs_names = [f"Cell_{i}" for i in range(n_obs)]
    adata.var_names = [f"Gene_{i}" for i in range(n_vars)]
    
    # Add some clustering
    sc.pp.pca(adata)
    sc.pp.neighbors(adata)
    sc.tl.leiden(adata)
    
    logger.info(f"Created data with {adata.n_obs} cells and {len(adata.obs['leiden'].unique())} clusters")
    
    # Test the problematic code
    try:
        earliest_cluster = adata.obs['leiden'].value_counts().idxmin()
        logger.info(f"Earliest cluster (smallest): {earliest_cluster}")
        
        root_cells = adata[adata.obs['leiden'] == earliest_cluster]
        logger.info(f"Root cells shape: {root_cells.shape}")
        logger.info(f"Root cells .raw is None: {root_cells.raw is None}")
        
        # This will fail
        root_cell_index = root_cells[np.argmax(root_cells.raw.X.mean(axis=1))].index[0]
        logger.error("Original code should have failed but didn't!")
    except AttributeError as e:
        logger.info(f"✓ Original code failed as expected: {e}")
    
    # Fixed version 1: Use .X instead of .raw.X
    logger.info("\n--- Testing Fix 1: Use .X instead of .raw.X ---")
    try:
        root_cells = adata[adata.obs['leiden'] == earliest_cluster]
        # Use .X directly
        mean_expression = root_cells.X.mean(axis=1)
        if hasattr(mean_expression, 'A1'):  # sparse matrix
            mean_expression = mean_expression.A1
        root_cell_idx = np.argmax(mean_expression)
        root_cell_index = root_cells.obs_names[root_cell_idx]
        logger.info(f"✓ Fix 1 worked! Selected root cell: {root_cell_index}")
    except Exception as e:
        logger.error(f"✗ Fix 1 failed: {e}")
    
    # Fixed version 2: Random selection with fallback
    logger.info("\n--- Testing Fix 2: Random selection fallback ---")
    try:
        root_cells = adata[adata.obs['leiden'] == earliest_cluster]
        # Simple random selection from cluster
        root_cell_index = np.random.choice(root_cells.obs_names)
        logger.info(f"✓ Fix 2 worked! Selected root cell: {root_cell_index}")
        
        # Store as index position for DPT
        iroot = adata.obs_names.get_loc(root_cell_index)
        logger.info(f"Root cell index position (iroot): {iroot}")
    except Exception as e:
        logger.error(f"✗ Fix 2 failed: {e}")
    
    # Fixed version 3: Store iroot directly as required by DPT
    logger.info("\n--- Testing Fix 3: Store iroot for DPT ---")
    try:
        root_cells = adata[adata.obs['leiden'] == earliest_cluster]
        # Get cell indices in the cluster
        cluster_indices = np.where(adata.obs['leiden'] == earliest_cluster)[0]
        # Select random one
        iroot = np.random.choice(cluster_indices)
        adata.uns['iroot'] = int(iroot)
        logger.info(f"✓ Fix 3 worked! Set adata.uns['iroot'] = {iroot}")
        
        # Verify it's the correct cell
        logger.info(f"Cell name at iroot: {adata.obs_names[iroot]}")
    except Exception as e:
        logger.error(f"✗ Fix 3 failed: {e}")
    
    # Test the complete fixed function
    logger.info("\n--- Testing Complete Fixed Function ---")
    def fixed_root_selection(adata):
        """Fixed version of root cell selection."""
        # Perform leiden clustering if not already done
        if 'leiden' not in adata.obs.columns:
            sc.tl.leiden(adata)
        
        # Find smallest cluster (assuming it's the earliest/progenitor)
        cluster_counts = adata.obs['leiden'].value_counts()
        earliest_cluster = cluster_counts.idxmin()
        logger.info(f"Selected cluster {earliest_cluster} with {cluster_counts[earliest_cluster]} cells")
        
        # Get indices of cells in this cluster
        cluster_mask = adata.obs['leiden'] == earliest_cluster
        cluster_indices = np.where(cluster_mask)[0]
        
        if len(cluster_indices) == 0:
            # Fallback: random cell
            iroot = np.random.choice(adata.n_obs)
            logger.warning(f"No cells in cluster {earliest_cluster}, using random cell {iroot}")
        else:
            # Select random cell from cluster
            iroot = np.random.choice(cluster_indices)
            logger.info(f"Selected cell {iroot} from cluster {earliest_cluster}")
        
        # Store for DPT
        adata.uns['iroot'] = int(iroot)
        
        # Also store the cell name for reference
        adata.uns['root_cell_name'] = adata.obs_names[iroot]
        
        return adata
    
    # Test it
    adata_fixed = fixed_root_selection(adata.copy())
    logger.info(f"✓ Complete function worked!")
    logger.info(f"  iroot: {adata_fixed.uns['iroot']}")
    logger.info(f"  root cell name: {adata_fixed.uns['root_cell_name']}")


if __name__ == "__main__":
    test_root_cell_selection_fix()