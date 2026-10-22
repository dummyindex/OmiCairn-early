#!/usr/bin/env python
"""Test script to verify incremental planning logic."""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from omicairn_agent_local.agents.main_agent import MainAgent

def test_incremental_planning():
    """Test that nodes are only created after parent succeeds."""
    
    # Setup
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ No OpenAI API key found")
        return False
    
    agent = MainAgent(openai_api_key=api_key)
    
    # Simple test data
    test_data = Path("test_data/zebrafish.h5ad")
    if not test_data.exists():
        print(f"❌ Test data not found: {test_data}")
        return False
    
    # Run with a request that should create multiple nodes
    print("\n" + "="*60)
    print("TESTING INCREMENTAL PLANNING LOGIC")
    print("="*60)
    
    result = agent.run_analysis(
        input_data_path=test_data,
        user_request="Perform quality control, then normalize the data",
        output_dir="test_outputs/incremental_test",
        max_nodes=3,
        max_children=1,
        max_iterations=5,
        generation_mode="only_new",
        llm_model="gpt-4o-mini",
        verbose=True
    )
    
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(f"Tree ID: {result['tree_id']}")
    print(f"Total nodes: {result['total_nodes']}")
    print(f"Completed nodes: {result['completed_nodes']}")
    print(f"Failed nodes: {result['failed_nodes']}")
    
    # Verify tree and directory markdown exist
    output_dir = Path(result['output_dir'])
    tree_file = output_dir / "analysis_tree.json"
    dir_md = output_dir / "directory_tree.md"
    
    print("\n" + "="*60)
    print("FILE VERIFICATION")
    print("="*60)
    print(f"✓ analysis_tree.json exists: {tree_file.exists()}")
    print(f"✓ directory_tree.md exists: {dir_md.exists()}")
    
    # Check that we didn't create all nodes upfront
    if result['total_nodes'] <= result['completed_nodes'] + 1:
        print("✅ PASS: Incremental planning working (nodes created as needed)")
        return True
    else:
        print("❌ FAIL: Too many nodes created upfront")
        return False

if __name__ == "__main__":
    success = test_incremental_planning()
    sys.exit(0 if success else 1)