#!/usr/bin/env python3
"""Test Slingshot R function block creation and execution with proper setup."""

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


def test_slingshot_execution():
    """Test Slingshot creation and execution with proper file naming."""
    
    print("\n=== Testing Slingshot Creation and Execution ===\n")
    
    # Create temporary directories
    test_dir = tempfile.mkdtemp()
    output_dir = Path(test_dir) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Step 1: Create the Slingshot function block with custom prompt
        print("1. Creating Slingshot function block...")
        
        llm_service = OpenAIService(model="gpt-4o")
        creator = FunctionCreatorAgent(llm_service=llm_service)
        
        # More specific context to handle our test data
        context = {
            "task_description": "Run Slingshot pseudotime analysis on Seurat object",
            "user_request": """Run Slingshot (R) pseudotime analysis. 
            The input file will be either '_node_seuratObject.rds' or 'pbmc3k_seurat_object.rds'.
            Check for both filenames. Load the Seurat object, run Slingshot pseudotime analysis,
            and save results as CSV."""
        }
        
        function_block = creator.process(context)
        
        if function_block is None:
            print("✗ Failed to create function block")
            return
            
        print(f"✓ Created function block: {function_block.name} (type: {function_block.type})")
        
        # Step 2: Prepare test data
        print("\n2. Preparing test data...")
        
        input_dir = output_dir / "input"
        input_dir.mkdir(exist_ok=True)
        
        # Copy test data with expected name
        test_data_path = Path("test_data/pbmc3k_seurat_object.rds")
        if test_data_path.exists():
            # Copy as the expected node filename
            shutil.copy(test_data_path, input_dir / "_node_seuratObject.rds")
            print(f"✓ Copied test data to {input_dir / '_node_seuratObject.rds'}")
        else:
            print("⚠️  Test data not found, creating mock data...")
            # Create a minimal mock R script that generates test data
            mock_script = '''
# Create mock Seurat object
library(Seurat)
set.seed(42)

# Create mock expression matrix
expr_matrix <- matrix(rnorm(1000 * 100), nrow = 1000, ncol = 100)
rownames(expr_matrix) <- paste0("Gene", 1:1000)
colnames(expr_matrix) <- paste0("Cell", 1:100)

# Create Seurat object
seurat_obj <- CreateSeuratObject(counts = expr_matrix)

# Run basic preprocessing
seurat_obj <- NormalizeData(seurat_obj)
seurat_obj <- FindVariableFeatures(seurat_obj)
seurat_obj <- ScaleData(seurat_obj)
seurat_obj <- RunPCA(seurat_obj, npcs = 10)

# Add mock clusters
seurat_obj$seurat_clusters <- factor(sample(1:3, 100, replace = TRUE))

# Save
saveRDS(seurat_obj, file.path("{}", "_node_seuratObject.rds"))
'''.format(input_dir)
            
            with open(input_dir / "create_mock_data.R", "w") as f:
                f.write(mock_script)
                
            # Try to create mock data
            print("  Creating mock Seurat object...")
            os.system(f"cd {input_dir} && Rscript create_mock_data.R 2>/dev/null")
            
            if not (input_dir / "_node_seuratObject.rds").exists():
                # If R script failed, create empty file
                (input_dir / "_node_seuratObject.rds").touch()
                print("  Created placeholder RDS file")
        
        # Step 3: Execute the function block
        print("\n3. Executing Slingshot function block...")
        
        docker_manager = DockerManager()
        executor = RExecutor(docker_manager=docker_manager)
        
        job_dir = output_dir / f"job_{os.getpid()}"
        job_dir.mkdir(exist_ok=True)
        
        # Execute
        result = executor.execute(
            function_block=function_block,
            input_data_path=input_dir,
            output_dir=job_dir,
            parameters={}
        )
        
        # Check results
        print("\n4. Checking execution results...")
        
        if result.success:
            print("✓ Execution completed successfully!")
            
            # List output files
            output_files = list(job_dir.glob("**/*"))
            print(f"\nGenerated files:")
            for f in output_files:
                if f.is_file():
                    print(f"  - {f.relative_to(job_dir)}")
                    
            # Check for expected outputs
            expected_outputs = [
                "pseudotime_results.csv",
                "_node_seuratObject.rds",
                "slingshot_results.rds",
                "slingshot_pseudotime.csv"
            ]
            
            found_outputs = []
            for expected in expected_outputs:
                if any(expected in str(f) for f in output_files):
                    found_outputs.append(expected)
                    print(f"  ✓ Found: {expected}")
                    
            if not found_outputs:
                print("  ⚠️  No expected output files found")
                
        else:
            print(f"✗ Execution failed: {result.error}")
            
            if result.logs:
                print("\nExecution logs:")
                print("-" * 60)
                print(result.logs[:2000])  # First 2000 chars
                print("-" * 60)
                
            if result.stderr:
                print("\nError output:")
                print("-" * 60)
                print(result.stderr[:1000])
                print("-" * 60)
        
        # Step 5: Display generated code
        print("\n5. Generated R code:")
        print("=" * 60)
        print(function_block.code)
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        if Path(test_dir).exists():
            shutil.rmtree(test_dir)
            print("\n✓ Cleaned up temporary files")
            
        # Also clean up the generated code file
        if Path("slingshot_generated_code.R").exists():
            os.remove("slingshot_generated_code.R")
            
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set")
        exit(1)
        
    test_slingshot_execution()