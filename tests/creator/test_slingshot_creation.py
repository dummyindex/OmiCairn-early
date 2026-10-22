#!/usr/bin/env python3
"""Test Slingshot R function block creation and execution."""

import os
import json
import shutil
import tempfile
from pathlib import Path

from omicairn_agent_local.llm_service.openai_service import OpenAIService
from omicairn_agent_local.agents.function_creator_agent import FunctionCreatorAgent
from omicairn_agent_local.models import FunctionBlockType
from omicairn_agent_local.job_executors.r_executor import RExecutor
from omicairn_agent_local.utils.docker_utils import DockerManager
from omicairn_agent_local.utils.logger import get_logger

logger = get_logger(__name__)


def test_slingshot_creation_and_execution():
    """Test that Slingshot is created as an R function block and executes correctly."""
    
    print("\n=== Testing Slingshot Creation and Execution ===\n")
    
    # Create temporary directories
    test_dir = tempfile.mkdtemp()
    output_dir = Path(test_dir) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Step 1: Test function block creation
        print("1. Creating Slingshot function block...")
        
        llm_service = OpenAIService(model="gpt-4o")
        creator = FunctionCreatorAgent(llm_service=llm_service)
        
        context = {
            "task_description": "Run Slingshot pseudotime analysis on Seurat object",
            "user_request": "Run Slingshot (R) pseudotime analysis on the Seurat object. Load the RDS file, extract the expression matrix and dimensionality reduction, run Slingshot to compute pseudotime, and save results."
        }
        
        # Create the function block
        function_block = creator.process(context)
        
        # Verify it's created correctly
        assert function_block is not None, "Function block should be created"
        assert function_block.type == FunctionBlockType.R, f"Expected R type, got {function_block.type}"
        assert "slingshot" in function_block.name.lower(), f"Expected 'slingshot' in name, got {function_block.name}"
        
        print(f"✓ Created function block: {function_block.name} (type: {function_block.type})")
        print(f"  Requirements: {function_block.requirements}")
        
        # Step 2: Prepare for execution
        print("\n2. Preparing for execution...")
        
        # Copy test data
        input_dir = output_dir / "input"
        input_dir.mkdir(exist_ok=True)
        
        test_data_path = Path("test_data/pbmc3k_seurat_object.rds")
        if test_data_path.exists():
            shutil.copy(test_data_path, input_dir / "pbmc3k_seurat_object.rds")
            print(f"✓ Copied test data to {input_dir}")
        else:
            print(f"⚠️  Test data not found at {test_data_path}")
            # Create a mock RDS file for testing
            with open(input_dir / "pbmc3k_seurat_object.rds", "w") as f:
                f.write("mock RDS file")
        
        # Step 3: Execute the function block
        print("\n3. Executing Slingshot function block...")
        
        docker_manager = DockerManager()
        executor = RExecutor(docker_manager=docker_manager)
        
        # Prepare execution parameters
        path_dict = {
            "input_dir": str(input_dir),
            "output_dir": str(output_dir)
        }
        
        params = {
            "input_file": "pbmc3k_seurat_object.rds",
            "reduction": "pca",
            "clustering": "seurat_clusters"
        }
        
        # Execute using the base executor's execute method
        job_dir = output_dir / f"job_{os.getpid()}"
        job_dir.mkdir(exist_ok=True)
        
        # Execute the function block
        result = executor.execute(
            function_block=function_block,
            input_data_path=input_dir,
            output_dir=job_dir,
            parameters=params
        )
        
        # Check execution result
        if result["success"]:
            print("✓ Execution completed successfully!")
            print(f"  Outputs: {result.get('outputs', {})}")
            
            # Check if output files were created
            output_files = list(output_dir.glob("*"))
            print(f"\n  Created files: {[f.name for f in output_files]}")
            
            # Check for expected outputs
            expected_files = ["slingshot_results.rds", "slingshot_pseudotime.csv"]
            for expected in expected_files:
                if any(expected in f.name for f in output_files):
                    print(f"  ✓ Found expected output: {expected}")
                else:
                    print(f"  ⚠️  Missing expected output: {expected}")
                    
        else:
            print(f"✗ Execution failed: {result.get('error', 'Unknown error')}")
            if 'logs' in result:
                print("\nExecution logs:")
                print(result['logs'][:1000])  # First 1000 chars
                
        # Step 4: Analyze the generated code
        print(f"\n4. Generated R code analysis:")
        print("=" * 60)
        print(function_block.code[:1500])  # First 1500 chars
        print("=" * 60)
        
        # Check for key R/Slingshot patterns
        code_checks = [
            ("library(Seurat)", "Seurat library"),
            ("library(slingshot)", "Slingshot library"),
            ("readRDS", "RDS file reading"),
            ("slingshot(", "Slingshot function call"),
            ("write.csv", "CSV output")
        ]
        
        print("\nCode quality checks:")
        for pattern, description in code_checks:
            if pattern in function_block.code:
                print(f"  ✓ Contains {description}")
            else:
                print(f"  ⚠️  Missing {description}")
                
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        if Path(test_dir).exists():
            shutil.rmtree(test_dir)
            print("\n✓ Cleaned up temporary files")
            
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    # Check if we have OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set")
        exit(1)
        
    test_slingshot_creation_and_execution()