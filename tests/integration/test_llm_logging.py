#!/usr/bin/env python3
"""Test LLM logging to stdout functionality."""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from agents.main_agent import MainAgent

def test_llm_logging():
    """Test that LLM inputs/outputs are logged to stdout."""
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        return False
    
    # Create output directory
    output_dir = Path("test_outputs/test_llm_logging")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create test data file
    test_data = Path("test_data/zebrafish.h5ad")
    if not test_data.exists():
        print(f"Error: Test data not found at {test_data}")
        return False
    
    # Simple request that will trigger both orchestrator and function creator
    test_request = """
Load the zebrafish data and perform basic quality control:
1. Calculate QC metrics
2. Filter cells with < 200 genes
3. Save the filtered data
"""
    
    print("Running analysis with LLM logging enabled...")
    print("You should see detailed LLM inputs/outputs below:")
    print("-" * 80)
    
    # Create agent with LLM logging enabled
    agent = MainAgent(
        openai_api_key=api_key,
        bug_fixer_type="unified",
        bug_fixer_model="gpt-4o-mini",
        log_llm_to_stdout=True  # Enable LLM logging!
    )
    
    # Run analysis
    result = agent.run_analysis(
        user_request=test_request,
        output_dir=str(output_dir),
        input_data_path=str(test_data),
        max_iterations=2,  # Limited iterations for testing
        max_nodes=2,       # Limited nodes for testing
        max_debug_trials=1,
        verbose=True
    )
    
    print("-" * 80)
    print("\nAnalysis completed!")
    print(f"Success: {result.get('status') == 'completed'}")
    print(f"Nodes created: {result.get('tree', {}).get('total_nodes', 0)}")
    
    # Check if we saw LLM logs
    print("\nNote: Check the output above for:")
    print("- ORCHESTRATOR LLM INPUT/OUTPUT sections")
    print("- FUNCTION CREATOR LLM INPUT/OUTPUT sections")
    
    return True

if __name__ == "__main__":
    success = test_llm_logging()
    sys.exit(0 if success else 1)