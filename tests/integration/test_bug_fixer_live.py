#!/usr/bin/env python3
"""Test script to verify bug fixer actually works with executors.

This creates a buggy function block and lets the system fix it.
"""

import os
import json
import tempfile
from pathlib import Path
from datetime import datetime

from models import NewFunctionBlock, FunctionBlockType
from job_executors.executor_manager import ExecutorManager
from agents.main_agent import MainAgent
from utils.logger import get_logger

logger = get_logger(__name__)

def create_buggy_function_block():
    """Create a function block with a deliberate bug."""
    
    # This code has a bug: it tries to use sc.pl.umap without importing scanpy
    # and it also has a wrong parameter name
    buggy_code = '''def run(path_dict, params):
    """Function with deliberate bugs to test bug fixer."""
    import os
    import numpy as np
    
    # Bug 1: Missing import for scanpy
    # Bug 2: Wrong file path construction
    input_file = path_dict['input_dir'] + '_node_anndata.h5ad'  # Missing os.path.join
    
    # This will fail because scanpy is not imported
    adata = sc.read_h5ad(input_file)
    
    # Bug 3: Trying to access non-existent column
    print(f"Cell types: {adata.obs['cell_type'].unique()}")
    
    # Bug 4: Wrong parameter for plotting
    sc.pl.umap(adata, colour='leiden')  # Should be 'color' not 'colour'
    
    # Create output directory
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    
    # Save output
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
'''
    
    requirements = '''scanpy>=1.9.0
pandas
numpy
matplotlib
'''
    
    return NewFunctionBlock(
        name="test_buggy_clustering",
        type=FunctionBlockType.PYTHON,
        description="A buggy clustering function to test bug fixer",
        code=buggy_code,
        requirements=requirements,
        parameters={}
    )

def test_bug_fixer_integration():
    """Test that bug fixer actually fixes bugs during execution."""
    
    print("=== Testing Bug Fixer Integration ===\n")
    
    # Create test data path
    test_data = Path(os.environ.get("TEST_DATA_DIR", "test_data")) / "pbmc3k_processed.h5ad"
    if not test_data.exists():
        print(f"Error: Test data not found at {test_data}")
        return False
    
    # Create output directory
    output_dir = Path("test_outputs") / f"bug_fixer_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create executor manager with bug fixing enabled
    executor_manager = ExecutorManager(
        enable_bug_fixer=True,
        max_debug_attempts=3,
        bug_fixer_model="gpt-4o-mini"
    )
    
    # Create buggy function block
    buggy_block = create_buggy_function_block()
    
    print(f"1. Created buggy function block: {buggy_block.name}")
    print(f"   Output directory: {output_dir}")
    print("\n2. Executing buggy code (should fail initially)...\n")
    
    # Try to execute - this should fail, trigger bug fixer, and eventually succeed
    result = executor_manager.execute(
        function_block=buggy_block,
        input_data_path=test_data,
        output_dir=output_dir,
        parameters={}
    )
    
    print("\n3. Execution Results:")
    print(f"   Success: {result.success}")
    print(f"   Duration: {result.duration:.2f}s")
    
    if result.error:
        print(f"   Final Error: {result.error[:200]}...")
    
    if result.debug_info:
        print(f"\n4. Debug Information:")
        print(f"   Debug attempts: {result.debug_info.get('attempts', 0)}")
        
        if 'bug_fixes' in result.debug_info:
            print(f"   Bug fixes applied: {len(result.debug_info['bug_fixes'])}")
            for i, fix in enumerate(result.debug_info['bug_fixes']):
                print(f"\n   Fix {i+1}:")
                print(f"   - Error: {fix.get('error', 'Unknown')[:100]}...")
                print(f"   - Success: {fix.get('success', False)}")
                if fix.get('changes'):
                    print(f"   - Changes: {fix['changes'][:100]}...")
    
    # Check if output was created
    output_file = output_dir / "_node_anndata.h5ad"
    if output_file.exists():
        print(f"\n5. Output file created successfully: {output_file}")
        print(f"   File size: {output_file.stat().st_size:,} bytes")
    else:
        print(f"\n5. Output file NOT created")
    
    # Save execution log
    log_file = output_dir / "execution_log.json"
    with open(log_file, 'w') as f:
        json.dump({
            'success': result.success,
            'duration': result.duration,
            'error': result.error,
            'stdout': result.stdout[-1000:] if result.stdout else None,  # Last 1000 chars
            'stderr': result.stderr[-1000:] if result.stderr else None,
            'debug_info': result.debug_info
        }, f, indent=2)
    
    print(f"\n6. Execution log saved to: {log_file}")
    
    return result.success

def test_specific_bug_scenarios():
    """Test specific bug scenarios to ensure bug fixer handles them."""
    
    print("\n=== Testing Specific Bug Scenarios ===\n")
    
    scenarios = [
        {
            'name': 'Missing Import',
            'code': '''def run(path_dict, params):
    import os
    # Missing: import scanpy as sc
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)  # NameError: sc not defined
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    adata.write(os.path.join(path_dict['output_dir'], '_node_anndata.h5ad'))
'''
        },
        {
            'name': 'Wrong API Usage',
            'code': '''def run(path_dict, params):
    import os
    import scanpy as sc
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)
    # Wrong: colour instead of color
    sc.pl.umap(adata, colour='leiden', save='_umap.png')
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    adata.write(os.path.join(path_dict['output_dir'], '_node_anndata.h5ad'))
'''
        },
        {
            'name': 'Missing Preprocessing',
            'code': '''def run(path_dict, params):
    import os
    import scanpy as sc
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)
    # Missing preprocessing - no neighbors computed
    sc.tl.leiden(adata)  # Will fail without neighbors
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    adata.write(os.path.join(path_dict['output_dir'], '_node_anndata.h5ad'))
'''
        }
    ]
    
    test_data = Path(os.environ.get("TEST_DATA_DIR", "test_data")) / "pbmc3k_processed.h5ad"
    executor_manager = ExecutorManager(enable_bug_fixer=True, max_debug_attempts=2)
    
    results = []
    for scenario in scenarios:
        print(f"\nTesting: {scenario['name']}")
        
        output_dir = Path("test_outputs") / f"scenario_{scenario['name'].lower().replace(' ', '_')}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        block = NewFunctionBlock(
            name=f"test_{scenario['name'].lower().replace(' ', '_')}",
            type=FunctionBlockType.PYTHON,
            description=f"Test {scenario['name']}",
            code=scenario['code'],
            requirements="scanpy>=1.9.0\npandas\nnumpy",
            parameters={}
        )
        
        result = executor_manager.execute(
            function_block=block,
            input_data_path=test_data,
            output_dir=output_dir,
            parameters={}
        )
        
        print(f"  Result: {'✅ FIXED' if result.success else '❌ FAILED'}")
        if result.debug_info and 'attempts' in result.debug_info:
            print(f"  Debug attempts: {result.debug_info['attempts']}")
        
        results.append({
            'scenario': scenario['name'],
            'success': result.success,
            'attempts': result.debug_info.get('attempts', 0) if result.debug_info else 0
        })
    
    # Summary
    print("\n=== Summary ===")
    for r in results:
        status = "✅" if r['success'] else "❌"
        print(f"{status} {r['scenario']}: {r['attempts']} debug attempts")
    
    return all(r['success'] for r in results)

if __name__ == "__main__":
    # Test basic bug fixer integration
    success1 = test_bug_fixer_integration()
    
    # Test specific scenarios
    success2 = test_specific_bug_scenarios()
    
    if success1 and success2:
        print("\n✅ All bug fixer tests passed!")
    else:
        print("\n❌ Some bug fixer tests failed!")