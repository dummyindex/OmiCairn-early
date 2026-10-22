#!/usr/bin/env python
"""Simple test for quality control with Docker."""

import os
import sys
from pathlib import Path
import shutil

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from omicairn_agent_local.agents.main_agent import MainAgent

def test_simple_qc():
    """Test simple quality control with Docker."""
    
    # Clean old outputs
    output_dir = Path("omicairn_agent_local/test_outputs/simple_qc_test")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    
    # Setup
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ No OpenAI API key found")
        return False
    
    agent = MainAgent(openai_api_key=api_key)
    
    # Find test data
    test_data = None
    for path in [
        Path("omicairn_agent_local/test_data/zebrafish.h5ad"),
        Path("omicairn_agent_local/test_outputs/clustering_openai_20250804_010410/test_data/zebrafish.h5ad"),
        Path("omicairn_agent_local/test_outputs/clustering_mock_20250804_010410/test_data/zebrafish.h5ad"),
    ]:
        if path.exists():
            test_data = path
            break
    
    if not test_data:
        print("❌ No test data found")
        return False
    
    print(f"\nTest data: {test_data}")
    print(f"Size: {test_data.stat().st_size / 1024:.1f} KB\n")
    
    # Very simple request - just one node
    request = "Apply quality control: filter cells with min_genes=200 and genes with min_cells=3"
    
    print(f"Request: {request}\n")
    
    # Run with Docker
    result = agent.run_analysis(
        input_data_path=test_data,
        user_request=request,
        output_dir=str(output_dir),
        max_nodes=1,
        max_children=0,
        max_iterations=1,
        max_debug_trials=3,
        generation_mode="only_new",
        llm_model="gpt-4o-mini",
        verbose=True
    )
    
    print(f"\nResult: {result['completed_nodes']}/{result['total_nodes']} completed")
    
    # Find the job logs
    tree_id = result['tree_id']
    nodes_dir = output_dir / tree_id / "nodes"
    
    if nodes_dir.exists():
        for node_dir in nodes_dir.iterdir():
            if node_dir.is_dir():
                print(f"\n📁 Node: {node_dir.name}")
                
                # Check outputs
                outputs_dir = node_dir / "outputs"
                if (outputs_dir / "_node_anndata.h5ad").exists():
                    print("  ✅ Output anndata created")
                if (outputs_dir / "_data_structure.json").exists():
                    print("  ✅ Data structure file created")
                    with open(outputs_dir / "_data_structure.json") as f:
                        import json
                        data = json.load(f)
                        print(f"    Shape: {data.get('shape')}")
                
                # Check job logs
                jobs_dir = node_dir / "jobs"
                if jobs_dir.exists():
                    for job_dir in sorted(jobs_dir.iterdir()):
                        if job_dir.is_dir() and job_dir.name.startswith("job_"):
                            print(f"\n  📂 Job: {job_dir.name}")
                            
                            # Show stderr
                            stderr_file = job_dir / "logs" / "stderr.txt"
                            if stderr_file.exists():
                                stderr = stderr_file.read_text()
                                if stderr.strip():
                                    print("\n  ❌ STDERR:")
                                    for line in stderr.split('\n')[-10:]:
                                        if line.strip():
                                            print(f"    {line}")
                            
                            # Show stdout last lines
                            stdout_file = job_dir / "logs" / "stdout.txt"
                            if stdout_file.exists():
                                stdout = stdout_file.read_text()
                                if "Error" in stdout or "Traceback" in stdout:
                                    print("\n  ❌ ERROR IN STDOUT:")
                                    for line in stdout.split('\n')[-20:]:
                                        if line.strip():
                                            print(f"    {line}")
    
    return result['completed_nodes'] > 0

if __name__ == "__main__":
    test_simple_qc()