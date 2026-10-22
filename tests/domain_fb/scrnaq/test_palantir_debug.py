#!/usr/bin/env python3
"""Debug Palantir function block execution."""

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
    palantir_dir = project_root / "function_blocks" / "scrnaq" / "palantir"
    test_data_path = project_root / "test_data" / "zebrafish.h5ad"
    output_dir = project_root / "test_outputs" / "palantir_debug"
    
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
    with open(palantir_dir / "config.json", 'r') as f:
        config_data = json.load(f)
    
    with open(palantir_dir / "code.py", 'r') as f:
        code = f.read()
    
    with open(palantir_dir / "requirements.txt", 'r') as f:
        requirements = f.read()
    
    # Get parameters
    params = {}
    args = []
    if 'parameters' in config_data:
        for param_name, param_info in config_data['parameters'].items():
            if 'default' in param_info:
                params[param_name] = param_info['default']
            
            arg = Arg(
                name=param_name,
                value_type=param_info.get('type', 'string'),
                description=param_info.get('description', ''),
                optional=not param_info.get('required', False),
                default_value=param_info.get('default')
            )
            args.append(arg)
    
    # Create function block
    static_config = StaticConfig(
        args=args,
        description=config_data.get('description', ''),
        tag="palantir",
        document_url="",
        source="generated"
    )
    
    function_block = NewFunctionBlock(
        id="test-palantir",
        name="palantir_pseudotime",
        type=FunctionBlockType.PYTHON,
        description="Palantir pseudotime test",
        code=code,
        requirements=requirements,
        parameters=params,
        static_config=static_config
    )
    
    # Execute
    docker_manager = DockerManager()
    executor = PythonExecutor(docker_manager)
    
    print("Executing Palantir function block...")
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
    
    # Save logs
    with open(output_dir / "stdout.log", 'w') as f:
        f.write(result.stdout)
    
    with open(output_dir / "stderr.log", 'w') as f:
        f.write(result.stderr)
    
    print(f"\nLogs saved to: {output_dir}")


if __name__ == "__main__":
    main()