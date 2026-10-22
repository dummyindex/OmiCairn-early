#!/usr/bin/env python
"""Test context passing with real Docker execution."""

import os
import sys
from pathlib import Path
import time
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from omicairn_agent_local.agents.main_agent import MainAgent

def test_docker_context():
    """Test that context is properly passed between nodes with Docker execution."""
    
    # Setup
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ No OpenAI API key found")
        return False
    
    agent = MainAgent(openai_api_key=api_key)
    
    # Use clustering benchmark data
    test_data = Path(__file__).parent / "test_data" / "zebrafish.h5ad"
    if not test_data.exists():
        # Try to find it in test outputs
        test_outputs = Path(__file__).parent / "test_outputs"
        for test_dir in test_outputs.glob("*/test_data/zebrafish.h5ad"):
            test_data = test_dir
            break
    
    if not test_data.exists():
        print(f"❌ Test data not found: {test_data}")
        return False
    
    print("\n" + "="*60)
    print("DOCKER CONTEXT PASSING TEST")
    print("="*60)
    
    # Simple 2-step request to test context passing
    request = """Process this dataset in two steps:
1. Quality control: filter cells with min_genes=200 and genes with min_cells=3
2. Normalization: normalize and log-transform the data"""
    
    print(f"Request: {request}\n")
    print(f"Test data: {test_data}")
    print(f"Size: {test_data.stat().st_size / 1024:.1f} KB\n")
    
    start_time = time.time()
    
    # Run with Docker execution (no mocking)
    result = agent.run_analysis(
        input_data_path=test_data,
        user_request=request,
        output_dir="test_outputs/docker_context_test",
        max_nodes=2,
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
    
    context_passing_success = False
    
    if nodes_dir.exists():
        print("\n" + "="*60)
        print("CONTEXT FILES CHECK")
        print("="*60)
        
        node_dirs = sorted([d for d in nodes_dir.iterdir() if d.is_dir()])
        
        for i, node_dir in enumerate(node_dirs):
            node_name = node_dir.name
            outputs_dir = node_dir / "outputs"
            
            # Check for data structure file
            data_structure_file = outputs_dir / "_data_structure.json"
            
            print(f"\nNode {i+1} ({node_name}):")
            
            # Check output files
            output_anndata = outputs_dir / "_node_anndata.h5ad"
            has_output = output_anndata.exists()
            print(f"  Output anndata: {'✅' if has_output else '❌'}")
            
            has_structure = data_structure_file.exists()
            print(f"  Data structure: {'✅' if has_structure else '❌'}")
            
            if has_structure:
                with open(data_structure_file, 'r') as f:
                    structure = json.load(f)
                    print(f"    Shape: {structure.get('shape', 'N/A')}")
                    print(f"    Obs columns: {len(structure.get('obs_columns', []))}")
                    print(f"    Obsm keys: {structure.get('obsm_keys', [])}") 
                    context_passing_success = True
            
            # Check if second node received context
            if i == 1:  # Second node
                creator_logs = node_dir / "agent_tasks" / "function_creator"
                if creator_logs.exists():
                    creation_files = list(creator_logs.glob("creation_*.json"))
                    if creation_files:
                        with open(creation_files[0], 'r') as f:
                            creation_data = json.load(f)
                            # Check if parent context was passed
                            if 'llm_input' in creation_data:
                                llm_input = creation_data['llm_input']
                                messages = llm_input.get('messages', [])
                                for msg in messages:
                                    if 'Input Data Structure' in msg.get('content', ''):
                                        print(f"  ✅ Parent context passed to node creator")
                                        break
    
    # Success if both nodes completed and context was passed
    success = result['total_nodes'] == 2 and result['failed_nodes'] == 0 and context_passing_success
    
    if success:
        print("\n✅ TEST PASSED: Context passing working correctly with Docker")
    else:
        print("\n⚠️ TEST FAILED: Check context passing implementation")
    
    return success

if __name__ == "__main__":
    success = test_docker_context()
    sys.exit(0 if success else 1)