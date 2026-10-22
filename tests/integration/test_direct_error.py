#!/usr/bin/env python3
"""Direct test of error capture without LLM interference."""

import os
import tempfile
import shutil
from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).parent))

from models import (
    FunctionBlock, FunctionBlockType, NewFunctionBlock,
    AnalysisNode, AnalysisTree, NodeState,
    StaticConfig, Arg
)
from job_executors.executor_manager import ExecutorManager
from analysis_tree_management.node_executor import NodeExecutor


def test_direct_error():
    """Test error capture with code that definitely fails."""
    
    print("Testing error capture with failing code...")
    
    # Create a function block that will definitely fail
    code = '''def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Load data
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)
    print(f"Loaded data with shape: {adata.shape}")
    
    # This will fail - accessing non-existent column
    print("Attempting to access non-existent column...")
    value = adata.obs['this_column_does_not_exist']
    
    # This line will never execute
    print("This should not print")
'''
    
    static_config = StaticConfig(
        args=[],
        description="Test error capture",
        tag="test"
    )
    
    function_block = NewFunctionBlock(
        name="test_error",
        type=FunctionBlockType.PYTHON,
        description="Test that errors are captured",
        code=code,
        requirements="scanpy",
        parameters={},
        static_config=static_config
    )
    
    # Create temp directories
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        
        # Find and copy input data
        zebrafish_path = Path(os.environ.get("TEST_DATA_DIR", "test_data")) / "zebrafish.h5ad"
        
        if not zebrafish_path.exists():
            print("ERROR: Could not find zebrafish data")
            return False
        
        # Create analysis tree
        tree = AnalysisTree(
            id="error-test",
            user_request="Test error capture",
            input_data_path=str(zebrafish_path),
            max_nodes=1,
            max_children_per_node=1,
            max_debug_trials=0  # No debug attempts
        )
        
        # Create node
        node = AnalysisNode(
            id="test-node",
            analysis_id=tree.id,
            function_block=function_block,
            level=1
        )
        tree.add_node(node)
        
        # Execute
        executor_manager = ExecutorManager()
        node_executor = NodeExecutor(executor_manager)
        
        state, output_path = node_executor.execute_node(
            node=node,
            tree=tree,
            input_path=zebrafish_path,
            output_base_dir=output_dir
        )
        
        print(f"\nExecution state: {state}")
        
        # Check for error files
        node_dir = output_dir / tree.id / "nodes" / f"node_{node.id}"
        jobs_dir = node_dir / "jobs"
        
        # Find job directory
        job_dirs = list(jobs_dir.glob("job_*"))
        if not job_dirs:
            print("ERROR: No job directory created")
            return False
        
        job_dir = job_dirs[0]
        logs_dir = job_dir / "logs"
        
        print(f"\nChecking logs in: {logs_dir}")
        
        # Check error.json
        error_json_path = logs_dir / "error.json"
        if error_json_path.exists():
            print("\n✓ error.json exists")
            with open(error_json_path) as f:
                error_data = json.load(f)
            
            error_msg = error_data.get('error', '')
            print(f"  Error length: {len(error_msg)}")
            
            has_traceback = 'Traceback' in error_msg
            has_keyerror = 'KeyError' in error_msg
            has_column = 'this_column_does_not_exist' in error_msg
            
            print(f"  Has Traceback: {has_traceback}")
            print(f"  Has KeyError: {has_keyerror}")
            print(f"  Has column name: {has_column}")
            
            if error_msg:
                print("\n  First 10 lines of error:")
                lines = error_msg.split('\n')
                for i, line in enumerate(lines[:10]):
                    print(f"    {i+1}: {line}")
        else:
            print("\n✗ error.json NOT found")
        
        # Check full_logs.txt
        full_logs_path = logs_dir / "full_logs.txt"
        if full_logs_path.exists():
            print("\n✓ full_logs.txt exists")
            with open(full_logs_path) as f:
                content = f.read()
            print(f"  Size: {len(content)} bytes")
            print(f"  Contains EXECUTION LOG: {'EXECUTION LOG:' in content}")
            print(f"  Contains Error details: {'Error details:' in content}")
        else:
            print("\n✗ full_logs.txt NOT found")
        
        # Check stdout.txt
        stdout_path = logs_dir / "stdout.txt"
        if stdout_path.exists():
            print("\n✓ stdout.txt exists")
            with open(stdout_path) as f:
                stdout = f.read()
            print(f"  Size: {len(stdout)} bytes")
            if stdout:
                print("  Content preview:")
                for line in stdout.split('\n')[:5]:
                    print(f"    {line}")
        
        # Summary
        print("\n" + "="*60)
        print("ERROR CAPTURE TEST SUMMARY")
        print("="*60)
        
        success = (
            state == NodeState.FAILED and
            error_json_path.exists() and
            has_traceback and
            has_keyerror and
            has_column
        )
        
        print(f"Result: {'PASSED' if success else 'FAILED'}")
        
        if not success:
            print("\nDiagnostics:")
            print(f"  - State is FAILED: {state == NodeState.FAILED}")
            print(f"  - error.json exists: {error_json_path.exists()}")
            if error_json_path.exists():
                print(f"  - Has traceback: {has_traceback}")
                print(f"  - Has KeyError: {has_keyerror}")
                print(f"  - Has column name: {has_column}")
        
        return success


if __name__ == "__main__":
    success = test_direct_error()
    sys.exit(0 if success else 1)