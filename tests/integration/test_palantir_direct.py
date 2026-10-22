#!/usr/bin/env python
"""Test Palantir installation and usage directly"""

import subprocess
import sys

def test_palantir_import():
    """Test if palantir can be imported correctly"""
    print("Testing Palantir import...")
    
    # First, try to install palantir
    print("\n1. Installing palantir...")
    result = subprocess.run([sys.executable, "-m", "pip", "install", "palantir"], 
                          capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    # Test import
    print("\n2. Testing import...")
    try:
        import palantir
        print("✓ Successfully imported palantir")
        print(f"   Version: {palantir.__version__ if hasattr(palantir, '__version__') else 'unknown'}")
        print(f"   Attributes: {[x for x in dir(palantir) if not x.startswith('_')][:10]}")
    except Exception as e:
        print(f"✗ Failed to import: {e}")
        return False
    
    # Test actual usage
    print("\n3. Testing Palantir usage...")
    try:
        import scanpy as sc
        import numpy as np
        
        # Create dummy data
        adata = sc.datasets.pbmc3k()
        sc.pp.normalize_total(adata)
        sc.pp.log1p(adata)
        sc.pp.highly_variable_genes(adata)
        adata = adata[:, adata.var['highly_variable']]
        sc.pp.pca(adata)
        
        # Try to run Palantir
        print("   Testing Palantir run...")
        # Different ways to call Palantir
        if hasattr(palantir, 'core'):
            print("   Found palantir.core")
            # Set start cell
            start_cell = np.random.choice(adata.obs_names)
            pr_res = palantir.core.run_palantir(
                adata, 
                start_cell,
                num_waypoints=500
            )
            print("   ✓ Palantir run successful")
        else:
            print("   Available methods:", [x for x in dir(palantir) if not x.startswith('_')])
            
    except Exception as e:
        print(f"   ✗ Failed to run Palantir: {e}")
        import traceback
        traceback.print_exc()
        
if __name__ == "__main__":
    test_palantir_import()