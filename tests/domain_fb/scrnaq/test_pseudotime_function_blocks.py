#!/usr/bin/env python3
"""Test pseudotime function blocks using containerized job executors."""

import os
import sys
import tempfile
import shutil
from pathlib import Path
import json
import uuid
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from job_executors import ExecutorManager
from models import ExistingFunctionBlock, StaticConfig, FunctionBlockType
from utils import setup_logger

logger = setup_logger(__name__)


def create_test_data():
    """Create test AnnData object with basic preprocessing."""
    import scanpy as sc
    import numpy as np
    import pandas as pd
    
    # Create synthetic data
    n_cells = 500
    n_genes = 200
    n_groups = 3
    
    # Generate expression matrix with groups - ensure positive values
    X = np.random.exponential(scale=1.0, size=(n_cells, n_genes))
    
    # Add group structure with stronger signal
    groups = np.repeat(range(n_groups), n_cells // n_groups + 1)[:n_cells]
    for i in range(n_groups):
        mask = groups == i
        # Add group-specific expression patterns
        X[mask, i*30:(i+1)*30] *= np.random.uniform(2, 5)
    
    # Add some noise
    X += np.random.exponential(scale=0.1, size=(n_cells, n_genes))
    
    # Create AnnData object
    adata = sc.AnnData(X=X)
    adata.obs['group'] = pd.Categorical(groups)
    adata.obs_names = [f'Cell_{i}' for i in range(n_cells)]
    adata.var_names = [f'Gene_{i}' for i in range(n_genes)]
    
    # Basic preprocessing
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    
    # Filter genes with some expression
    sc.pp.filter_genes(adata, min_cells=10)
    
    # Highly variable genes
    if adata.n_vars > 50:
        sc.pp.highly_variable_genes(adata, n_top_genes=min(50, adata.n_vars))
        adata = adata[:, adata.var.highly_variable]
    
    # PCA
    sc.pp.scale(adata, max_value=10)
    sc.tl.pca(adata, svd_solver='arpack', n_comps=min(30, adata.n_vars-1))
    
    # Neighbors and clustering
    try:
        sc.pp.neighbors(adata, n_neighbors=20, n_pcs=min(20, adata.obsm['X_pca'].shape[1]))
        sc.tl.umap(adata)
        sc.tl.leiden(adata, resolution=0.5)
    except Exception as e:
        # Fallback to simple clustering based on groups
        logger.warning(f"Leiden clustering failed: {e}, using group labels")
        adata.obs['leiden'] = adata.obs['group'].astype(str)
    
    return adata


def test_function_block(block_name, block_path, test_data_path, output_base_dir):
    """Test a single pseudotime function block using job executor."""
    print(f"\n{'='*60}")
    print(f"Testing {block_name} function block")
    print(f"{'='*60}")
    
    # Create unique test directory
    test_id = f"{block_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    test_dir = output_base_dir / test_id
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup paths
    function_block_dir = test_dir / "function_block"
    input_dir = test_dir / "input"
    output_dir = test_dir / "output"
    
    function_block_dir.mkdir(exist_ok=True)
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    
    # Copy function block files
    for file_name in ['code.py', 'config.json', 'requirements.txt']:
        src_file = Path(block_path) / file_name
        if src_file.exists():
            shutil.copy2(src_file, function_block_dir / file_name)
    
    # Copy test data
    shutil.copy2(test_data_path, input_dir / "_node_anndata.h5ad")
    
    # Load config
    with open(function_block_dir / "config.json", 'r') as f:
        config_data = json.load(f)
    
    # Create FunctionBlock model
    function_block = ExistingFunctionBlock(
        type=FunctionBlockType.PYTHON,
        name=config_data.get('name', block_name),
        description=config_data.get('description', ''),
        location=str(function_block_dir),
        static_config=StaticConfig(
            args=[],
            description=config_data.get('description', ''),
            tag='pseudotime'
        )
    )
    
    # Setup path_dict
    path_dict = {
        'input_dir': str(input_dir),
        'output_dir': str(output_dir),
        'function_block_dir': str(function_block_dir)
    }
    
    # Get parameters with defaults
    params = {}
    if 'parameters' in config_data:
        for param_name, param_info in config_data['parameters'].items():
            if 'default' in param_info:
                params[param_name] = param_info['default']
    
    # Initialize executor manager
    executor_manager = ExecutorManager()
    
    try:
        # Execute function block
        print(f"\nExecuting {block_name} in container...")
        result = executor_manager.execute_function_block(
            function_block=function_block,
            path_dict=path_dict,
            params=params,
            timeout=600  # 10 minutes timeout
        )
        
        if result['exit_code'] == 0:
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
                    assert 'dpt_pseudotime' in adata.obs, "DPT pseudotime not found"
                    assert 'paga' in adata.uns, "PAGA results not found"
                    print(f"  - DPT pseudotime range: {adata.obs['dpt_pseudotime'].min():.3f} to {adata.obs['dpt_pseudotime'].max():.3f}")
                
                elif block_name == "palantir":
                    assert 'palantir_pseudotime' in adata.obs, "Palantir pseudotime not found"
                    assert 'palantir_entropy' in adata.obs, "Palantir entropy not found"
                    print(f"  - Palantir pseudotime range: {adata.obs['palantir_pseudotime'].min():.3f} to {adata.obs['palantir_pseudotime'].max():.3f}")
                
                elif block_name == "cellrank":
                    # CellRank might not always compute pseudotime if it can't find terminal states
                    if 'cellrank_pseudotime' in adata.obs:
                        print(f"  - CellRank pseudotime range: {adata.obs['cellrank_pseudotime'].min():.3f} to {adata.obs['cellrank_pseudotime'].max():.3f}")
                    else:
                        print("  - CellRank: No pseudotime computed (may need velocity data)")
            
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
        else:
            print(f"❌ {block_name} failed with exit code {result['exit_code']}")
            print(f"Error output:\n{result['stderr']}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing {block_name}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run tests for all pseudotime function blocks."""
    # Setup paths
    project_root = Path(__file__).parent.parent.parent.parent
    function_blocks_dir = project_root / "function_blocks" / "scrnaq"
    output_base_dir = project_root / "test_outputs" / "pseudotime_fb_tests"
    output_base_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Project root: {project_root}")
    print(f"Function blocks dir: {function_blocks_dir}")
    print(f"Output dir: {output_base_dir}")
    
    # Create test data
    print("\nCreating test data...")
    test_data_dir = output_base_dir / "test_data"
    test_data_dir.mkdir(exist_ok=True)
    test_data_path = test_data_dir / "test_data.h5ad"
    
    if not test_data_path.exists():
        adata = create_test_data()
        adata.write(test_data_path)
        print(f"Test data saved to: {test_data_path}")
        print(f"  Shape: {adata.shape}")
        print(f"  Clusters: {adata.obs['leiden'].nunique()}")
    else:
        print(f"Using existing test data: {test_data_path}")
    
    # Define function blocks to test
    function_blocks = [
        ("dpt_paga", function_blocks_dir / "dpt_paga"),
        ("palantir", function_blocks_dir / "palantir"),
        ("cellrank", function_blocks_dir / "cellrank"),
    ]
    
    # Also test scFates if it exists
    scfates_dir = project_root / "function_blocks" / "trajectory_analysis" / "scfates"
    if scfates_dir.exists():
        function_blocks.append(("scfates", scfates_dir))
    
    # Run tests
    results = {}
    for block_name, block_path in function_blocks:
        if block_path.exists():
            success = test_function_block(
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
    print("Test Summary")
    print("="*60)
    
    for block_name, success in results.items():
        if success is None:
            status = "⚠️  SKIPPED"
        elif success:
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"
        print(f"{block_name:20} {status}")
    
    # Overall result
    passed = sum(1 for s in results.values() if s is True)
    failed = sum(1 for s in results.values() if s is False)
    skipped = sum(1 for s in results.values() if s is None)
    
    print(f"\nTotal: {passed} passed, {failed} failed, {skipped} skipped")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)