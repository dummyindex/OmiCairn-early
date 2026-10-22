#!/usr/bin/env python3
"""Simple test for clustering with bug fixer."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agents.main_agent import MainAgent

def test_simple_clustering():
    """Test a simple clustering request."""
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        return False
    
    print("Testing simple clustering with bug fixer...")
    
    agent = MainAgent(
        openai_api_key=api_key,
        llm_model="gpt-4o-mini",
        bug_fixer_model="gpt-4o-mini",
        bug_fixer_type="unified",
        enable_web_agent=False,  # Disable for faster testing
        enable_interactive_debug=True,
        log_llm_to_stdout=False  # Less verbose
    )
    
    # Simple request - just normalize and one clustering
    request = """
    Please perform the following analysis:
    1. Normalize the data using scanpy's normalize_total and log1p
    2. Perform Leiden clustering with resolution 0.5
    3. Generate a simple UMAP plot colored by clusters
    """
    
    output_dir = Path("test_outputs/simple_clustering_test")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    result = agent.run_analysis(
        input_data_path="test_data/zebrafish.h5ad",
        user_request=request,
        output_dir=str(output_dir),
        max_iterations=10,
        max_debug_trials=2,
        max_nodes=5
    )
    
    print(f"\nTest completed: {result['success']}")
    if result.get('message'):
        print(f"Message: {result['message']}")
    
    # Check if bug fixer was invoked
    if output_dir.exists():
        bug_fixer_dirs = list(output_dir.glob("*/nodes/*/agent_tasks/bug_fixer"))
        if bug_fixer_dirs:
            print(f"\nBug fixer was invoked for {len(bug_fixer_dirs)} nodes")
            for bf_dir in bug_fixer_dirs:
                turns = list(bf_dir.glob("attempt_*/turn_*.md"))
                print(f"  - {bf_dir.parent.parent.name}: {len(turns)} turns")
    
    return result['success']

if __name__ == "__main__":
    success = test_simple_clustering()
    sys.exit(0 if success else 1)