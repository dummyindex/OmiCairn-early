#!/usr/bin/env python3
"""Direct test of error capture mechanism."""

import tempfile
import shutil
from pathlib import Path
import sys
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from models import FunctionBlock, FunctionBlockType, NewFunctionBlock, StaticConfig, Arg
from job_executors.executor_manager import ExecutorManager

def test_error_capture():
    """Test that errors are properly captured."""
    
    print("Testing error capture...")
    
    # Create a function block that will fail
    code = '''def run(path_dict, params):
    import scanpy as sc
    
    # This will fail - trying to use var column as obs color
    adata = sc.datasets.pbmc3k()
    sc.pp.highly_variable_genes(adata)
    
    # This will fail because 'highly_variable' is in var, not obs
    sc.pl.umap(adata, color='highly_variable')
'''
    
    static_config = StaticConfig(
        args=[],
        description="Test error capture",
        tag="test"
    )
    
    function_block = NewFunctionBlock(
        name="test_error_capture",
        type=FunctionBlockType.PYTHON,
        description="Test that errors are captured",
        code=code,
        requirements="scanpy",
        parameters={},
        static_config=static_config
    )
    
    # Create temp directories
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_dir = temp_path / "input"
        output_dir = temp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        
        # Create dummy input
        (input_dir / "_node_anndata.h5ad").write_text("dummy")
        
        # Execute
        executor_manager = ExecutorManager()
        result = executor_manager.execute(
            function_block=function_block,
            input_data_path=input_dir,
            output_dir=output_dir,
            parameters={}
        )
        
        print(f"\nExecution result:")
        print(f"  Success: {result.success}")
        print(f"  Exit code: {result.exit_code}")
        print(f"  Error length: {len(result.error or '')}")
        
        if result.error:
            print(f"\nError preview:")
            lines = result.error.split('\n')
            for i, line in enumerate(lines[:10]):
                print(f"  {i+1}: {line}")
            
            # Check error content
            has_traceback = 'Traceback' in result.error
            has_key_error = 'KeyError' in result.error or 'ValueError' in result.error
            has_color_msg = 'highly_variable' in result.error or 'color' in result.error
            
            print(f"\nError analysis:")
            print(f"  Contains Traceback: {has_traceback}")
            print(f"  Contains Error type: {has_key_error}")
            print(f"  Contains context: {has_color_msg}")
            
            # Check logs
            if result.logs:
                print(f"\nLogs contain execution.log: {'EXECUTION LOG:' in result.logs}")
                print(f"Logs contain error_details: {'Error details:' in result.logs}")
            
            return has_traceback
        else:
            print("\nNo error captured!")
            print(f"STDOUT: {result.stdout[:200] if result.stdout else 'None'}")
            print(f"STDERR: {result.stderr[:200] if result.stderr else 'None'}")
            return False


if __name__ == "__main__":
    success = test_error_capture()
    print(f"\nTest {'PASSED' if success else 'FAILED'}")
    sys.exit(0 if success else 1)