#!/usr/bin/env python3
"""Test that function creator properly extracts function block names from user requests."""

import os
import sys
import json
from pathlib import Path

from agents.main_agent import MainAgent
from utils import setup_logger

logger = setup_logger(__name__)

# Simple user request with explicit function block names
USER_REQUEST = """
Perform analysis with these steps:

1. **Data Preprocessing** (create function block named 'preprocess_data'):
   - Load the input AnnData file
   - Normalize and log transform
   - Save output

2. **DPT Analysis** (create function block named 'dpt_analysis'):
   - Load preprocessed data
   - Run DPT
   - Save output

3. **Comparison** (create function block named 'compare_methods'):
   - Load all results
   - Compare methods
   - Save output
"""

def test_function_naming():
    """Test that function blocks are named correctly."""
    # Initialize main agent
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        return False
    
    agent = MainAgent(
        openai_api_key=api_key,
        bug_fixer_type="unified",
        bug_fixer_model="gpt-4o-mini",
        llm_model="gpt-4o-mini"
    )
    
    # Create test data
    input_file = Path("test_data/zebrafish.h5ad")
    if not input_file.exists():
        logger.error(f"Test data not found: {input_file}")
        return False
    
    # Run analysis with small limits
    output_dir = Path(f"test_outputs/test_naming_{Path(__file__).stem}")
    
    try:
        result = agent.run_analysis(
            input_data_path=str(input_file),
            user_request=USER_REQUEST,
            output_dir=str(output_dir),
            max_nodes=5,  # Small limit
            max_children=1,  # Linear pipeline
            max_debug_trials=0,  # No debugging for this test
            max_iterations=5,
            verbose=True
        )
        
        # Check the generated tree
        tree_file = output_dir / result['tree_id'] / "analysis_tree.json"
        with open(tree_file) as f:
            tree_data = json.load(f)
        
        # Extract function block names
        node_names = []
        for node_id, node_data in tree_data['nodes'].items():
            node_names.append(node_data['function_block']['name'])
        
        logger.info(f"Generated nodes: {node_names}")
        
        # Check if we have the expected names
        expected_names = ['preprocess_data', 'dpt_analysis', 'compare_methods']
        success = True
        
        for expected in expected_names[:len(node_names)]:
            if expected not in node_names:
                logger.error(f"Missing expected function block: {expected}")
                success = False
        
        # Check for duplicates
        if len(node_names) != len(set(node_names)):
            logger.error(f"Duplicate function block names found: {node_names}")
            success = False
        
        return success
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_function_naming()
    sys.exit(0 if success else 1)