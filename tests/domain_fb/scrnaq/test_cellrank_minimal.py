#!/usr/bin/env python3
"""Test minimal CellRank function block."""

import os
import sys
import shutil
from pathlib import Path
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from job_executors.python_executor import PythonExecutor
from models import FunctionBlockType, NewFunctionBlock, StaticConfig, Arg
from utils.docker_utils import DockerManager

def main():
    # Paths
    project_root = Path(__file__).parent.parent.parent.parent
    cellrank_dir = project_root / "function_blocks" / "scrnaq" / "cellrank_minimal"
    test_data_path = project_root / "test_data" / "zebrafish.h5ad"
    output_dir = project_root / "test_outputs" / "cellrank_minimal_test"
    
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
    with open(cellrank_dir / "config.json", 'r') as f:
        config_data = json.load(f)
    
    with open(cellrank_dir / "code.py", 'r') as f:
        code = f.read()
    
    with open(cellrank_dir / "requirements.txt", 'r') as f:
        requirements = f.read()
    
    # Get parameters
    params = {
        "cluster_key": "leiden",
        "basis": "umap"
    }
    
    # Create function block
    static_config = StaticConfig(
        args=[],
        description="Minimal CellRank test",
        tag="cellrank",
        document_url="",
        source="generated"
    )
    
    function_block = NewFunctionBlock(
        id="test-cellrank-minimal",
        name="cellrank_minimal",
        type=FunctionBlockType.PYTHON,
        description="Minimal CellRank test",
        code=code,
        requirements=requirements,
        parameters=params,
        static_config=static_config
    )
    
    # Execute
    docker_manager = DockerManager()
    executor = PythonExecutor(docker_manager)
    
    print("Executing minimal CellRank function block...")
    
    result = executor.execute(
        function_block=function_block,
        input_data_path=input_dir,
        output_dir=exec_output_dir,
        parameters=params
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
    
    # Check outputs
    if result.success:
        print("\n=== OUTPUTS ===")
        output_files = list(exec_output_dir.glob("*"))
        for f in output_files:
            print(f"  - {f.name}")


if __name__ == "__main__":
    main()