#!/usr/bin/env python3
"""Quick CellRank test to check the issue."""

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
    cellrank_dir = project_root / "function_blocks" / "scrnaq" / "cellrank"
    test_data_path = project_root / "test_data" / "zebrafish.h5ad"
    output_dir = project_root / "test_outputs" / "cellrank_quick"
    
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
    
    # Get parameters - minimal setup
    params = {
        "mode": "connectivity",  # Skip velocity mode
        "n_states": 3,  # Fixed number of states
        "cluster_key": "leiden",
        "basis": "umap",
        "compute_absorption_probabilities": False,  # Skip this step
        "n_lineage_drivers": 0  # Skip lineage drivers
    }
    
    # Create function block
    static_config = StaticConfig(
        args=[],
        description="CellRank test",
        tag="cellrank",
        document_url="",
        source="generated"
    )
    
    function_block = NewFunctionBlock(
        id="test-cellrank",
        name="cellrank_trajectory",
        type=FunctionBlockType.PYTHON,
        description="CellRank test",
        code=code,
        requirements=requirements,
        parameters=params,
        static_config=static_config
    )
    
    # Execute with timeout
    docker_manager = DockerManager()
    executor = PythonExecutor(docker_manager)
    
    print("Executing CellRank function block...")
    print(f"Parameters: {params}")
    
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
        print(result.stdout[:2000])  # First 2000 chars
        if len(result.stdout) > 2000:
            print("\n... (truncated)")
    
    if result.stderr:
        print("\n=== STDERR ===")
        print(result.stderr[:2000])  # First 2000 chars
        if len(result.stderr) > 2000:
            print("\n... (truncated)")
    
    if result.error:
        print(f"\nError: {result.error}")


if __name__ == "__main__":
    main()