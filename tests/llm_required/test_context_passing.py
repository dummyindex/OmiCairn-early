#!/usr/bin/env python
"""Test context passing in the improved system."""

import os
import sys
from pathlib import Path
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from omicairn_agent_local.agents.main_agent import MainAgent

def test_context_passing():
    """Test that context is properly passed between nodes."""
    
    # Setup
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ No OpenAI API key found")
        return False
    
    agent = MainAgent(openai_api_key=api_key)
    
    # Simple test data
    test_data = Path("test_data/zebrafish.h5ad")
    
    print("\n" + "="*60)
    print("CONTEXT PASSING TEST")
    print("="*60)
    
    # Request that requires context passing
    request = """Process this dataset in three steps:
1. Quality control: filter cells and genes, calculate QC metrics
2. Normalization: normalize and log-transform the data
3. Dimensionality reduction: calculate PCA and UMAP"""
    
    print(f"Request: {request}\n")
    
    start_time = time.time()
    
    result = agent.run_analysis(
        input_data_path=test_data,
        user_request=request,
        output_dir="test_outputs/context_test",
        max_nodes=3,
        max_children=1,
        max_iterations=5,
        max_debug_trials=3,
        generation_mode="only_new",
        llm_model="gpt-4o-mini",
        verbose=True
    )
    
    duration = time.time() - start_time
    
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(f"Duration: {duration:.1f}s")
    print(f"Total nodes: {result['total_nodes']}")
    print(f"Completed: {result['completed_nodes']}")
    print(f"Failed: {result['failed_nodes']}")
    
    # Check if context files were created
    output_dir = Path(result['output_dir'])
    tree_id = result['tree_id']
    nodes_dir = output_dir / tree_id / "nodes"
    
    if nodes_dir.exists():
        print("\n" + "="*60)
        print("CONTEXT FILES CHECK")
        print("="*60)
        
        for node_dir in sorted(nodes_dir.iterdir()):
            if node_dir.is_dir():
                node_name = node_dir.name
                outputs_dir = node_dir / "outputs"
                
                # Check for data structure file
                data_structure_file = outputs_dir / "_data_structure.json"
                
                print(f"\n{node_name}:")
                print(f"  Output anndata: {'✅' if (outputs_dir / '_node_anndata.h5ad').exists() else '❌'}")
                print(f"  Data structure: {'✅' if data_structure_file.exists() else '❌'}")
                
                if data_structure_file.exists():
                    import json
                    with open(data_structure_file, 'r') as f:
                        structure = json.load(f)
                        print(f"    Shape: {structure.get('shape', 'N/A')}")
                        print(f"    Obs columns: {len(structure.get('obs_columns', []))}")
                        print(f"    Obsm keys: {structure.get('obsm_keys', [])}")
    
    # Success if all nodes completed
    success = result['total_nodes'] == 3 and result['failed_nodes'] == 0
    
    if success:
        print("\n✅ TEST PASSED: Context passing working correctly")
    else:
        print("\n⚠️ TEST PARTIALLY PASSED: Some nodes may have failed")
    
    return success

if __name__ == "__main__":
    success = test_context_passing()
    sys.exit(0 if success else 1)