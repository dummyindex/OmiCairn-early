#!/usr/bin/env python3
"""Local test for pseudotime function blocks without Docker."""

import os
import sys
import shutil
from pathlib import Path
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


def test_function_block_local(block_name, block_path, test_data_path, output_base_dir):
    """Test a single pseudotime function block locally without Docker."""
    print(f"\n{'='*60}")
    print(f"Testing {block_name} function block (local)")
    print(f"{'='*60}")
    
    # Create test directory
    test_id = f"{block_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    test_dir = output_base_dir / test_id
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup paths
    input_dir = test_dir / "input"
    output_dir = test_dir / "output"
    
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    
    # Copy test data
    shutil.copy2(test_data_path, input_dir / "_node_anndata.h5ad")
    
    # Load config
    with open(block_path / "config.json", 'r') as f:
        config_data = json.load(f)
    
    # Get parameters with defaults
    params = {}
    if 'parameters' in config_data:
        for param_name, param_info in config_data['parameters'].items():
            if 'default' in param_info:
                params[param_name] = param_info['default']
    
    # Setup path_dict
    path_dict = {
        'input_dir': str(input_dir),
        'output_dir': str(output_dir)
    }
    
    try:
        # Load and execute the function block code
        code_path = block_path / "code.py"
        
        # Read the code
        with open(code_path, 'r') as f:
            code = f.read()
        
        # Execute the code to get the run function
        exec_globals = {}
        exec(code, exec_globals)
        
        # Get the run function
        if 'run' not in exec_globals:
            print(f"❌ No 'run' function found in {code_path}")
            return False
        
        run_func = exec_globals['run']
        
        # Execute the function
        print(f"\nExecuting {block_name} locally...")
        run_func(path_dict, params)
        
        print(f"✅ {block_name} completed successfully!")
        
        # Check outputs
        output_h5ad = output_dir / "_node_anndata.h5ad"
        if output_h5ad.exists():
            print(f"  - Output h5ad: {output_h5ad} ({output_h5ad.stat().st_size} bytes)")
            
            # Verify pseudotime was added
            import scanpy as sc
            adata = sc.read_h5ad(output_h5ad)
            
            # Check for expected outputs based on method
            if block_name == "dpt_paga":
                if 'dpt_pseudotime' in adata.obs:
                    print(f"  - ✅ DPT pseudotime found")
                    print(f"  - Pseudotime range: {adata.obs['dpt_pseudotime'].min():.3f} to {adata.obs['dpt_pseudotime'].max():.3f}")
                else:
                    print("  - ⚠️  DPT pseudotime not found in adata.obs")
            
            elif block_name == "palantir":
                if 'palantir_pseudotime' in adata.obs:
                    print(f"  - ✅ Palantir pseudotime found")
                    print(f"  - Pseudotime range: {adata.obs['palantir_pseudotime'].min():.3f} to {adata.obs['palantir_pseudotime'].max():.3f}")
                else:
                    print("  - ⚠️  Palantir pseudotime not found in adata.obs")
            
            elif block_name == "cellrank":
                # CellRank might not always compute pseudotime
                if 'cellrank_pseudotime' in adata.obs:
                    print(f"  - ✅ CellRank pseudotime found")
                    print(f"  - Pseudotime range: {adata.obs['cellrank_pseudotime'].min():.3f} to {adata.obs['cellrank_pseudotime'].max():.3f}")
                else:
                    print("  - ℹ️  CellRank: No pseudotime computed (may need velocity data or more cells)")
            
            elif block_name == "scfates":
                if 'graph' in adata.uns:
                    print("  - ✅ scFates trajectory graph found")
                else:
                    print("  - ⚠️  scFates graph not found in adata.uns")
        
        # Check for figures
        figures_dir = output_dir / "figures"
        if figures_dir.exists():
            figures = list(figures_dir.glob("*.png"))
            print(f"  - Generated {len(figures)} figures")
            for fig in figures[:3]:  # Show first 3
                print(f"    • {fig.name}")
        
        # Check for CSV outputs
        csv_files = list(output_dir.glob("*.csv"))
        if csv_files:
            print(f"  - Generated {len(csv_files)} CSV files")
            for csv in csv_files:
                print(f"    • {csv.name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing {block_name}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run local tests for pseudotime function blocks."""
    # Setup paths
    project_root = Path(__file__).parent.parent.parent.parent
    function_blocks_dir = project_root / "function_blocks" / "scrnaq"
    output_base_dir = project_root / "test_outputs" / "pseudotime_fb_local"
    output_base_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Project root: {project_root}")
    print(f"Function blocks dir: {function_blocks_dir}")
    print(f"Output dir: {output_base_dir}")
    
    # Use preprocessed test data
    test_data_path = project_root / "tests" / "domain_fb" / "scrnaq" / "test_data_ready.h5ad"
    
    if not test_data_path.exists():
        print(f"\n❌ Test data not found at: {test_data_path}")
        print("Please copy a preprocessed h5ad file to this location")
        return False
    
    print(f"\nUsing test data: {test_data_path}")
    
    # Verify test data
    try:
        import scanpy as sc
        adata = sc.read_h5ad(test_data_path)
        print(f"  - Shape: {adata.shape}")
        print(f"  - Has PCA: {'X_pca' in adata.obsm}")
        print(f"  - Has UMAP: {'X_umap' in adata.obsm}")
        print(f"  - Has leiden: {'leiden' in adata.obs}")
        
        # Make sure we have the required preprocessing
        if 'X_pca' not in adata.obsm or 'leiden' not in adata.obs:
            print("\n⚠️  Test data is not properly preprocessed")
            print("Required: PCA, neighbors, leiden clustering")
            return False
            
    except Exception as e:
        print(f"  - Error with test data: {e}")
        return False
    
    # Test all function blocks
    function_blocks = [
        ("dpt_paga", function_blocks_dir / "dpt_paga"),
        ("palantir", function_blocks_dir / "palantir"),
        ("cellrank", function_blocks_dir / "cellrank"),
        ("scfates", function_blocks_dir / "scfates"),
    ]
    
    # Run tests
    results = {}
    for block_name, block_path in function_blocks:
        if block_path.exists():
            success = test_function_block_local(
                block_name=block_name,
                block_path=block_path,
                test_data_path=test_data_path,
                output_base_dir=output_base_dir
            )
            results[block_name] = success
        else:
            print(f"\n⚠️  Skipping {block_name} - path not found: {block_path}")
            results[block_name] = None
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary (Local)")
    print("="*60)
    
    for block_name, success in results.items():
        if success is None:
            status = "⚠️  SKIPPED"
        elif success:
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"
        print(f"{block_name:20} {status}")
    
    return all(s is not False for s in results.values())


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)