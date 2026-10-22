#!/usr/bin/env python3
"""Test R-Python interoperability with automatic conversion nodes."""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from omicairn_agent_local.agents.main_agent import MainAgent
from omicairn_agent_local.llm_service import OpenAIService


def test_python_to_r_workflow():
    """Test workflow that starts with Python and switches to R."""
    print("\n=== Test Python → R Workflow ===")
    
    # User request that would benefit from R analysis
    user_request = """
    Please analyze this single-cell dataset. First, perform quality control 
    and normalization using scanpy. Then, use Seurat's FindMarkers function 
    to identify differentially expressed genes between clusters.
    """
    
    # Test data
    test_data = Path(__file__).parent.parent.parent / "test_data" / "zebrafish.h5ad"
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "python_to_r_test"
        
        # Initialize agent
        agent = MainAgent(llm_service=OpenAIService())
        
        # Run analysis
        result = agent.analyze(
            user_request=user_request,
            input_path=test_data,
            output_dir=output_dir,
            llm_model="gpt-4o-mini",
            generation_mode="mixed",
            max_iterations=5,
            verbose=True
        )
        
        print(f"\nAnalysis completed!")
        print(f"Tree ID: {result['tree_id']}")
        print(f"Total nodes: {result['total_nodes']}")
        print(f"Completed nodes: {result['completed_nodes']}")
        
        # Check for conversion node
        tree_file = Path(result['tree_file'])
        if tree_file.exists():
            import json
            with open(tree_file) as f:
                tree_data = json.load(f)
            
            # Look for conversion nodes
            conversion_nodes = [
                node for node in tree_data['nodes'].values()
                if 'convert' in node['function_block']['name'] and 'sc_matrix' in node['function_block']['name']
            ]
            
            if conversion_nodes:
                print(f"\n✓ Found {len(conversion_nodes)} conversion node(s):")
                for node in conversion_nodes:
                    print(f"  - {node['function_block']['name']}: {node['function_block']['description']}")
            else:
                print("\n✗ No conversion nodes found")
        
        return result


def test_r_to_python_workflow():
    """Test workflow that starts with R and switches to Python."""
    print("\n=== Test R → Python Workflow ===")
    
    # User request that would benefit from Python analysis
    user_request = """
    Please analyze this Seurat object. First, use Seurat to perform 
    basic QC and normalization. Then, switch to Python and use scVelo 
    to perform RNA velocity analysis on the processed data.
    """
    
    # Test data
    test_data = Path(__file__).parent.parent.parent / "test_data" / "pbmc3k_seurat_object.rds"
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "r_to_python_test"
        
        # Initialize agent
        agent = MainAgent(llm_service=OpenAIService())
        
        # Run analysis
        result = agent.analyze(
            user_request=user_request,
            input_path=test_data,
            output_dir=output_dir,
            llm_model="gpt-4o-mini",
            generation_mode="mixed",
            max_iterations=5,
            verbose=True
        )
        
        print(f"\nAnalysis completed!")
        print(f"Tree ID: {result['tree_id']}")
        print(f"Total nodes: {result['total_nodes']}")
        print(f"Completed nodes: {result['completed_nodes']}")
        
        # Check for conversion node
        tree_file = Path(result['tree_file'])
        if tree_file.exists():
            import json
            with open(tree_file) as f:
                tree_data = json.load(f)
            
            # Look for conversion nodes
            conversion_nodes = [
                node for node in tree_data['nodes'].values()
                if 'convert' in node['function_block']['name'] and 'sc_matrix' in node['function_block']['name']
            ]
            
            if conversion_nodes:
                print(f"\n✓ Found {len(conversion_nodes)} conversion node(s):")
                for node in conversion_nodes:
                    print(f"  - {node['function_block']['name']}: {node['function_block']['description']}")
            else:
                print("\n✗ No conversion nodes found")
        
        return result


def main():
    """Run all R-Python interoperability tests."""
    print("Testing R-Python Interoperability")
    print("=" * 50)
    
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set")
        return 1
    
    try:
        # Test 1: Python to R
        result1 = test_python_to_r_workflow()
        
        # Test 2: R to Python  
        result2 = test_r_to_python_workflow()
        
        print("\n" + "=" * 50)
        print("Test Summary:")
        print(f"Python → R test: {'✓ Passed' if result1['completed_nodes'] > 0 else '✗ Failed'}")
        print(f"R → Python test: {'✓ Passed' if result2['completed_nodes'] > 0 else '✗ Failed'}")
        
        return 0
        
    except Exception as e:
        print(f"\nError during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())