#!/usr/bin/env python3
"""Test that bug fixer receives proper error messages including Python exceptions."""

import tempfile
import json
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from models import (
    FunctionBlock, FunctionBlockType, NewFunctionBlock,
    AnalysisNode, AnalysisTree, NodeState,
    StaticConfig, Arg
)
from job_executors.executor_manager import ExecutorManager
from analysis_tree_management.node_executor import NodeExecutor
from agents.unified_bug_fixer.unified_bug_fixer import UnifiedBugFixer


def create_failing_function_block():
    """Create a function block that will fail with a specific Python exception."""
    code = '''def run(path_dict, params):
    import pandas as pd
    
    # This will cause a KeyError
    data = {'col1': [1, 2, 3]}
    df = pd.DataFrame(data)
    
    # Try to access non-existent column - will raise KeyError
    value = df['non_existent_column']
    
    print("This line will never be reached")
'''
    
    static_config = StaticConfig(
        args=[],
        description="Test function block that fails with KeyError",
        tag="test"
    )
    
    return NewFunctionBlock(
        name="test_error_reporting",
        type=FunctionBlockType.PYTHON,
        description="Test function block that fails with KeyError",
        code=code,
        requirements="pandas",
        parameters={},
        static_config=static_config
    )


def test_error_reporting():
    """Test that Python exceptions are properly captured and passed to bug fixer."""
    
    print("Setting up test environment...")
    
    # Create temporary directories
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_dir = temp_path / "input"
        output_dir = temp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        
        # Create dummy input file
        input_file = input_dir / "_node_anndata.h5ad"
        input_file.write_text("dummy data")
        
        # Create function block
        function_block = create_failing_function_block()
        
        # Create analysis tree and node
        tree = AnalysisTree(
            id="test-tree",
            user_request="Test error reporting",
            input_data_path=str(input_file),
            max_nodes=10,
            max_children_per_node=3,
            max_debug_trials=3
        )
        
        node = AnalysisNode(
            id="test-node",
            analysis_id=tree.id,
            function_block=function_block,
            level=1
        )
        tree.add_node(node)
        
        # Initialize executor manager and node executor
        executor_manager = ExecutorManager()
        node_executor = NodeExecutor(executor_manager)
        
        print("\nExecuting failing function block...")
        
        # Execute the node (it should fail)
        state, output_path = node_executor.execute_node(
            node=node,
            tree=tree,
            input_path=input_file,
            output_base_dir=output_dir
        )
        
        # Verify it failed
        assert state == NodeState.FAILED, f"Expected FAILED state, got {state}"
        print(f"✓ Node failed as expected")
        
        # Check error files
        node_dir = output_dir / tree.id / "nodes" / f"node_{node.id}"
        jobs_dir = node_dir / "jobs"
        
        # Find the job directory
        job_dirs = list(jobs_dir.glob("job_*"))
        assert len(job_dirs) > 0, "No job directory created"
        
        job_dir = job_dirs[0]
        logs_dir = job_dir / "logs"
        
        # Check error.json
        error_json_path = logs_dir / "error.json"
        assert error_json_path.exists(), "error.json not created"
        
        with open(error_json_path) as f:
            error_data = json.load(f)
        
        print(f"\nError data from error.json:")
        print(f"  - error field: {error_data.get('error', 'NOT FOUND')[:100]}...")
        
        # Check if we have the Python exception
        error_msg = error_data.get('error', '')
        has_traceback = 'Traceback' in error_msg
        has_key_error = 'KeyError' in error_msg
        has_column_name = 'non_existent_column' in error_msg
        
        print(f"\nError message analysis:")
        print(f"  ✓ Contains Traceback: {has_traceback}")
        print(f"  ✓ Contains KeyError: {has_key_error}")
        print(f"  ✓ Contains column name: {has_column_name}")
        
        # Check full_logs.txt
        full_logs_path = logs_dir / "full_logs.txt"
        if full_logs_path.exists():
            with open(full_logs_path) as f:
                full_logs = f.read()
            
            print(f"\nFull logs analysis:")
            print(f"  - File exists: ✓")
            print(f"  - Contains execution log: {'EXECUTION LOG:' in full_logs}")
            print(f"  - Contains Traceback: {'Traceback' in full_logs}")
        else:
            print(f"\nFull logs file not found at {full_logs_path}")
        
        # Now test that bug fixer would receive this error
        print("\n\nTesting bug fixer error reception...")
        print(f"\nBug fixer would receive error:")
        print(f"  - Error message length: {len(error_msg)}")
        print(f"  - Contains Traceback: {has_traceback}")
        print(f"  - Contains KeyError: {has_key_error}")
        print(f"  - Contains column name: {has_column_name}")
        
        # Show a sample of the error
        if error_msg:
            lines = error_msg.split('\n')
            print("\nFirst few lines of error:")
            for line in lines[:5]:
                print(f"    {line}")
        
        # Final verification
        print("\n\nTest Results:")
        print("=" * 50)
        
        if has_traceback and has_key_error and has_column_name:
            print("✅ SUCCESS: Python exceptions are properly captured!")
            print("   - Full traceback is available in error.json")
            print("   - Bug fixer would receive complete error information")
            print("   - The actual KeyError about 'non_existent_column' is captured")
        else:
            print("❌ FAILURE: Python exceptions not properly captured")
            print(f"   - Traceback found: {has_traceback}")
            print(f"   - KeyError found: {has_key_error}")  
            print(f"   - Column name found: {has_column_name}")
            
        return has_traceback and has_key_error and has_column_name


if __name__ == "__main__":
    success = test_error_reporting()
    sys.exit(0 if success else 1)