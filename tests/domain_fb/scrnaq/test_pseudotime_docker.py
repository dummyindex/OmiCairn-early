#!/usr/bin/env python3
"""Test pseudotime function blocks using Docker containers."""

import os
import sys
import shutil
from pathlib import Path
import json
import uuid
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from job_executors.python_executor import PythonExecutor
from models import FunctionBlock, FunctionBlockType, NewFunctionBlock, StaticConfig, Arg
from utils.docker_utils import DockerManager
from utils import setup_logger

logger = setup_logger(__name__)


def test_function_block_docker(block_name, block_path, test_data_path, output_base_dir):
    """Test a single pseudotime function block using Docker container."""
    print(f"\n{'='*60}")
    print(f"Testing {block_name} function block (Docker)")
    print(f"{'='*60}")
    
    # Create unique test directory
    test_id = f"{block_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    test_dir = output_base_dir / test_id
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup paths - mimic the job executor structure
    execution_dir = test_dir / "execution"
    execution_dir.mkdir(exist_ok=True)
    
    # Create input/output directories
    input_dir = execution_dir / "input"
    output_dir = execution_dir / "output"
    figures_dir = output_dir / "figures"
    
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(exist_ok=True)
    
    # Copy test data
    shutil.copy2(test_data_path, input_dir / "_node_anndata.h5ad")
    
    # Load config and code
    with open(block_path / "config.json", 'r') as f:
        config_data = json.load(f)
    
    with open(block_path / "code.py", 'r') as f:
        code = f.read()
    
    with open(block_path / "requirements.txt", 'r') as f:
        requirements = f.read()
    
    # Get parameters with defaults
    params = {}
    if 'parameters' in config_data:
        for param_name, param_info in config_data['parameters'].items():
            if 'default' in param_info:
                params[param_name] = param_info['default']
    
    # Create StaticConfig from config.json
    # Convert parameters to Arg objects
    args = []
    if 'parameters' in config_data:
        for param_name, param_info in config_data['parameters'].items():
            arg = Arg(
                name=param_name,
                value_type=param_info.get('type', 'string'),
                description=param_info.get('description', ''),
                optional=not param_info.get('required', False),
                default_value=param_info.get('default')
            )
            args.append(arg)
    
    static_config = StaticConfig(
        args=args,
        description=config_data.get('description', ''),
        tag=config_data.get('name', block_name),
        document_url="",
        source="generated"
    )
    
    # Create NewFunctionBlock instance
    function_block = NewFunctionBlock(
        id=str(uuid.uuid4()),
        name=config_data.get('name', block_name),
        type=FunctionBlockType.PYTHON,
        description=config_data.get('description', ''),
        code=code,
        requirements=requirements,
        parameters=params,
        static_config=static_config
    )
    
    # Initialize Docker manager and Python executor
    docker_manager = DockerManager()
    executor = PythonExecutor(docker_manager)
    
    try:
        # Execute function block in Docker
        print(f"\nExecuting {block_name} in Docker container...")
        
        result = executor.execute(
            function_block=function_block,
            input_data_path=input_dir,
            output_dir=output_dir,
            parameters=params
        )
        
        print(f"Exit code: {result.exit_code}")
        
        if result.exit_code == 0:
            print(f"✅ {block_name} completed successfully in Docker!")
            
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
            figures = list(figures_dir.glob("*.png"))
            if figures:
                print(f"  - Generated {len(figures)} figures")
                for fig in figures[:3]:  # Show first 3
                    print(f"    • {fig.name}")
            
            # Check for CSV outputs
            csv_files = list(output_dir.glob("*.csv"))
            if csv_files:
                print(f"  - Generated {len(csv_files)} CSV files")
                for csv in csv_files:
                    print(f"    • {csv.name}")
            
            # Copy outputs to test directory for preservation
            shutil.copytree(output_dir, test_dir / "outputs", dirs_exist_ok=True)
            
            return True
        else:
            print(f"❌ {block_name} failed with exit code {result.exit_code}")
            print(f"Stdout:\n{result.stdout}")
            print(f"Stderr:\n{result.stderr}")
            
            # Save logs for debugging
            with open(test_dir / "stdout.log", 'w') as f:
                f.write(result.stdout)
            with open(test_dir / "stderr.log", 'w') as f:
                f.write(result.stderr)
            
            return False
            
    except Exception as e:
        print(f"❌ Error testing {block_name}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Clean up execution directory but keep outputs
        if execution_dir.exists():
            shutil.rmtree(execution_dir)


def main():
    """Run Docker tests for all pseudotime function blocks."""
    # Setup paths
    project_root = Path(__file__).parent.parent.parent.parent
    function_blocks_dir = project_root / "function_blocks" / "scrnaq"
    output_base_dir = project_root / "test_outputs" / "pseudotime_fb_docker"
    output_base_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Project root: {project_root}")
    print(f"Function blocks dir: {function_blocks_dir}")
    print(f"Output dir: {output_base_dir}")
    
    # Use existing test data - try multiple options
    test_data_candidates = [
        project_root / "test_data" / "zebrafish.h5ad",
        project_root / "test_data" / "pbmc3k_processed.h5ad",
        project_root / "tests" / "domain_fb" / "scrnaq" / "test_data_ready.h5ad",
    ]
    
    test_data_path = None
    for candidate in test_data_candidates:
        if candidate.exists():
            test_data_path = candidate
            break
    
    if test_data_path is None:
        print(f"\n❌ No test data found. Tried:")
        for candidate in test_data_candidates:
            print(f"  - {candidate}")
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
            success = test_function_block_docker(
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
    print("Test Summary (Docker)")
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
    
    # Show where outputs are saved
    if passed > 0:
        print(f"\n📁 Test outputs saved in: {output_base_dir}")
        print("Each successful test has an 'outputs' directory with:")
        print("  - _node_anndata.h5ad (with pseudotime results)")
        print("  - CSV exports")
        print("  - figures/ directory with visualizations")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)