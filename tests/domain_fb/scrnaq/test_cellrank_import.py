#!/usr/bin/env python3
"""Test CellRank import issue."""

import os
import sys
import shutil
from pathlib import Path
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from job_executors.python_executor import PythonExecutor
from models import FunctionBlockType, NewFunctionBlock, StaticConfig
from utils.docker_utils import DockerManager

def main():
    # Paths
    project_root = Path(__file__).parent.parent.parent.parent
    cellrank_dir = project_root / "function_blocks" / "scrnaq" / "cellrank_simple"
    test_data_path = project_root / "test_data" / "zebrafish.h5ad"
    output_dir = project_root / "test_outputs" / "cellrank_import"
    
    # Clean and create output directory
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    
    # Create execution directories
    input_dir = output_dir / "input"
    exec_output_dir = output_dir / "output"
    input_dir.mkdir()
    exec_output_dir.mkdir()
    
    # Copy test data
    shutil.copy2(test_data_path, input_dir / "_node_anndata.h5ad")
    
    # Load function block
    with open(cellrank_dir / "code.py", 'r') as f:
        code = f.read()
    
    with open(cellrank_dir / "requirements.txt", 'r') as f:
        requirements = f.read()
    
    # Create function block
    static_config = StaticConfig(
        args=[],
        description="CellRank import test",
        tag="cellrank",
        document_url="",
        source="generated"
    )
    
    function_block = NewFunctionBlock(
        id="test-cellrank-import",
        name="cellrank_import",
        type=FunctionBlockType.PYTHON,
        description="CellRank import test",
        code=code,
        requirements=requirements,
        parameters={},
        static_config=static_config
    )
    
    # Execute
    docker_manager = DockerManager()
    executor = PythonExecutor(docker_manager)
    
    print("Testing CellRank import...")
    
    result = executor.execute(
        function_block=function_block,
        input_data_path=input_dir,
        output_dir=exec_output_dir,
        parameters={}
    )
    
    print(f"\nExit code: {result.exit_code}")
    print(f"Success: {result.success}")
    
    if result.stdout:
        print("\n=== STDOUT ===")
        print(result.stdout)
    
    if result.stderr:
        print("\n=== STDERR ===")
        print(result.stderr)
    
    if result.error:
        print(f"\nError: {result.error}")


if __name__ == "__main__":
    main()