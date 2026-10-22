#!/usr/bin/env python3
"""Real Slingshot test with actual package installation."""

import os
import shutil
from pathlib import Path
from datetime import datetime

from omicairn_agent_local.llm_service.openai_service import OpenAIService
from omicairn_agent_local.agents.function_creator_agent import FunctionCreatorAgent
from omicairn_agent_local.models import FunctionBlockType
from omicairn_agent_local.job_executors.r_executor import RExecutor
from omicairn_agent_local.utils.docker_utils import DockerManager
from omicairn_agent_local.config import config


def test_real_slingshot():
    """Test real Slingshot with LLM-generated code."""
    
    print("\n=== Real Slingshot Test ===")
    print(f"Start: {datetime.now()}")
    
    output_dir = Path("test_outputs/slingshot_real")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    
    try:
        # Step 1: Use LLM to create Slingshot function block
        print("\n1. Creating Slingshot function block with LLM...")
        
        llm_service = OpenAIService(model="gpt-4o")
        creator = FunctionCreatorAgent(llm_service=llm_service)
        
        context = {
            "task_description": "Run Slingshot pseudotime analysis",
            "user_request": """Create a Slingshot (R) pseudotime analysis function that:
            1. Loads a Seurat object from 'pbmc3k_seurat_object.rds' or creates test data if not found
            2. Ensures it has PCA computed (run if needed)
            3. Converts to SingleCellExperiment
            4. Runs Slingshot pseudotime analysis
            5. Saves results as CSV with columns: Cell, Lineage1, Lineage2 (if exists), Cluster
            6. Creates a summary text file with statistics
            7. Uses proper error handling and progress messages
            """
        }
        
        function_block = creator.process(context)
        
        if not function_block:
            print("✗ Failed to create function block")
            return
            
        print(f"✓ Created: {function_block.name}")
        print(f"  Type: {function_block.type}")
        assert function_block.type == FunctionBlockType.R, f"Expected R, got {function_block.type}"
        
        # Save the generated code
        code_file = output_dir / "generated_slingshot.R"
        code_file.write_text(function_block.code)
        print(f"  Saved code to: {code_file}")
        
        # Step 2: Prepare test data
        print("\n2. Preparing test data...")
        input_dir = output_dir / "input"
        input_dir.mkdir()
        
        test_data = Path("test_data/pbmc3k_seurat_object.rds")
        if test_data.exists():
            shutil.copy(test_data, input_dir / "pbmc3k_seurat_object.rds")
            print(f"✓ Copied real test data ({test_data.stat().st_size:,} bytes)")
        else:
            print("⚠️  No test data found (function will create mock data)")
            
        # Step 3: Execute with extended timeout
        print("\n3. Executing Slingshot (this may take several minutes for package installation)...")
        
        # Set longer timeout for package installation
        original_timeout = config.function_block_timeout
        config.function_block_timeout = 900  # 15 minutes
        
        docker_manager = DockerManager()
        executor = RExecutor(docker_manager=docker_manager)
        
        job_dir = output_dir / "job"
        job_dir.mkdir()
        
        print(f"   Starting execution at {datetime.now()}")
        print("   Installing R packages...")
        
        start_exec = datetime.now()
        result = executor.execute(
            function_block=function_block,
            input_data_path=input_dir,
            output_dir=job_dir,
            parameters={"n_pcs": 10, "n_clusters": 3}
        )
        exec_time = (datetime.now() - start_exec).total_seconds()
        
        config.function_block_timeout = original_timeout
        
        print(f"   Execution completed in {exec_time:.1f} seconds ({exec_time/60:.1f} minutes)")
        
        # Step 4: Analyze results
        print("\n4. Results:")
        
        if result.success:
            print("✓ EXECUTION SUCCESSFUL!")
            
            # List all outputs
            outputs = list(job_dir.glob("**/*"))
            output_files = [f for f in outputs if f.is_file()]
            print(f"\nGenerated {len(output_files)} files:")
            
            for f in sorted(output_files):
                size = f.stat().st_size
                rel_path = f.relative_to(job_dir)
                print(f"  - {rel_path} ({size:,} bytes)")
                
            # Check pseudotime CSV
            csv_files = list(job_dir.glob("*.csv"))
            if csv_files:
                csv_file = csv_files[0]
                print(f"\n✓ SLINGSHOT OUTPUT FOUND: {csv_file.name}")
                
                with open(csv_file) as f:
                    lines = f.readlines()
                    print(f"  Total cells: {len(lines)-1}")
                    
                    # Parse header
                    header = lines[0].strip().split(',')
                    print(f"  Columns: {header}")
                    
                    # Show sample data
                    if len(lines) > 5:
                        print("\n  Sample data:")
                        for i in [1, 2, 3, -2, -1]:
                            print(f"    {lines[i].strip()}")
                            
                    # Count lineages
                    lineage_cols = [col for col in header if 'lineage' in col.lower() or 'pseudotime' in col.lower()]
                    print(f"\n  Lineages detected: {len(lineage_cols)}")
                    
            # Check summary
            summary_files = list(job_dir.glob("*summary*.txt"))
            if summary_files:
                print(f"\n✓ Summary file found:")
                with open(summary_files[0]) as f:
                    print("  " + f.read().replace("\n", "\n  "))
                    
            # Check plots
            plot_files = list(job_dir.glob("*.png")) + list(job_dir.glob("*.pdf"))
            if plot_files:
                print(f"\n✓ Generated {len(plot_files)} plots:")
                for f in plot_files:
                    print(f"  - {f.name}")
                    
            # Show R console output
            if result.logs:
                r_output = [line for line in result.logs.split('\n') 
                           if line.strip() and not line.startswith('*') and '==' not in line]
                if r_output:
                    print("\nR Console Output:")
                    print("-" * 60)
                    for line in r_output[-20:]:  # Last 20 lines
                        print(line)
                    print("-" * 60)
                    
        else:
            print(f"✗ Execution failed: {result.error}")
            
            # Show error details
            if result.stderr:
                error_lines = result.stderr.split('\n')
                print("\nError output:")
                print("-" * 60)
                for line in error_lines[:50]:  # First 50 lines
                    if line.strip():
                        print(line)
                print("-" * 60)
                
    except Exception as e:
        print(f"\n✗ Test error: {e}")
        import traceback
        traceback.print_exc()
        
    print(f"\nEnd: {datetime.now()}")
    print("=== Test Complete ===")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set")
        exit(1)
        
    test_real_slingshot()