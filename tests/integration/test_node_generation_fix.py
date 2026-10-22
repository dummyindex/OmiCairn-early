#!/usr/bin/env python3
"""Test that system stops generating nodes when there are no successful parents."""

import os
import sys
import json
from pathlib import Path

from agents.main_agent import MainAgent
from utils import setup_logger

logger = setup_logger(__name__)

# Simple request that will fail
USER_REQUEST = """
Run an analysis that will fail:
1. Try to load a non-existent file
2. Then do more analysis
"""

def test_node_generation_fix():
    """Test that system stops when no successful nodes exist."""
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
    
    # Run analysis
    output_dir = Path(f"test_outputs/test_node_generation_fix")
    
    try:
        result = agent.run_analysis(
            input_data_path=str(input_file),
            user_request=USER_REQUEST,
            output_dir=str(output_dir),
            max_nodes=10,
            max_children=1,
            max_debug_trials=0,  # No debugging to force failure
            max_iterations=5,
            verbose=True
        )
        
        # Check the generated tree
        tree_file = output_dir / result['tree_id'] / "analysis_tree.json"
        with open(tree_file) as f:
            tree_data = json.load(f)
        
        # Count nodes
        total_nodes = len(tree_data['nodes'])
        failed_nodes = sum(1 for n in tree_data['nodes'].values() if n['state'] == 'failed')
        
        logger.info(f"Total nodes: {total_nodes}, Failed nodes: {failed_nodes}")
        
        # The system should stop after the first node fails
        # It should NOT generate many nodes that can't be attached
        if total_nodes > 3:  # Allow some tolerance
            logger.error(f"System generated too many nodes ({total_nodes}) despite failures")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_node_generation_fix()
    sys.exit(0 if success else 1)