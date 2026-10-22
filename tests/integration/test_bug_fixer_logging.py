#!/usr/bin/env python3
"""
Test bug fixer logging improvements - shows stdout/stderr properly.
"""

import os
import sys
import logging
from pathlib import Path
from agents.main_agent import MainAgent

# Enable debug logging to see our improvements
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_with_deliberate_error():
    """Run a simple test that will trigger bug fixer with errors."""
    
    # Create test output directory
    output_dir = Path("test_outputs/test_bug_fixer_logging")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Use test data
    test_data = Path("test_data/zebrafish.h5ad")
    if not test_data.exists():
        print(f"Error: Test data not found at {test_data}")
        return False
    
    # Request that will cause errors to test logging
    test_request = """
Please run this simple analysis:
1. Load the data and try to access a non-existent column 'fake_column'
2. Try to run a command that doesn't exist like 'fakecmd'
3. Save the results

This is designed to trigger errors for testing.
"""
    
    # Initialize agent
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        return False
    
    agent = MainAgent(
        openai_api_key=api_key,
        bug_fixer_type="unified",
        bug_fixer_model="gpt-4o-mini"
    )
    
    print("Running test analysis with deliberate errors...")
    print("Check the debug output for improved error messages!")
    
    result = agent.run_analysis(
        user_request=test_request,
        output_dir=str(output_dir),
        input_data_path=str(test_data),
        max_iterations=2,
        max_nodes=1,
        max_debug_trials=2,
        verbose=True
    )
    
    print(f"\nTest completed. Check logs for stdout/stderr from bug fixer commands.")
    return True

if __name__ == "__main__":
    success = test_with_deliberate_error()
    sys.exit(0 if success else 1)