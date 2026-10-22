#!/usr/bin/env python3
"""Test single pseudotime method (DPT) to debug issues."""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.main_agent import MainAgent

def test_single_method():
    """Test just DPT to see what happens."""
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        return False
    
    # Output directory
    output_dir = Path("test_outputs/single_dpt_test")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Input data
    input_data = Path("test_data/zebrafish.h5ad")
    if not input_data.exists():
        print(f"Error: Test data not found at {input_data}")
        return False
    
    # Simple request for just DPT
    user_request = """
Run DPT (Diffusion Pseudotime) analysis:
1. Preprocess the data (normalize, log transform, find variable genes, PCA, neighbors)
2. Calculate diffusion map
3. Set root cell and calculate DPT
4. Generate trajectory plot
5. Save results
"""
    
    print("Running single DPT test...")
    print(f"Output directory: {output_dir}")
    
    # Create agent without web agent
    agent = MainAgent(
        openai_api_key=api_key,
        bug_fixer_type="unified",
        bug_fixer_model="gpt-4o-mini",
        enable_web_agent=False,
        log_llm_to_stdout=False
    )
    
    # Run analysis
    result = agent.run_analysis(
        user_request=user_request,
        output_dir=str(output_dir),
        input_data_path=str(input_data),
        max_iterations=10,
        max_nodes=10,
        max_debug_trials=2,
        verbose=True
    )
    
    # Check results
    print("\n" + "="*60)
    print("RESULTS:")
    print("="*60)
    print(f"Status: {result.get('status')}")
    
    tree = result.get('tree', {})
    print(f"Total nodes: {tree.get('total_nodes', 0)}")
    print(f"Completed nodes: {tree.get('completed_nodes', 0)}")
    print(f"Failed nodes: {tree.get('failed_nodes', 0)}")
    
    # Check for specific errors
    if "tree_structure" in result:
        nodes = result["tree_structure"].get("nodes", [])
        for node in nodes:
            if node["state"] == "failed":
                print(f"\n✗ Failed: {node['name']}")
                if "error" in node:
                    print(f"  Error: {node['error'][:200]}...")
    
    return tree.get('failed_nodes', 0) == 0 and tree.get('completed_nodes', 0) > 0

if __name__ == "__main__":
    test_single_method()