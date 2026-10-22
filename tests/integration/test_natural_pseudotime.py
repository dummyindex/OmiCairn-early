#!/usr/bin/env python3
"""Test pseudotime analysis with natural user request (no explicit function block names)."""

import os
import sys
import json
from pathlib import Path

from agents.main_agent import MainAgent
from utils import setup_logger

logger = setup_logger(__name__)

# Natural user request from benchmark prompts
USER_REQUEST = """
1. Preprocess dataset if not already processed
   - Use Scanpy: normalize_total → log1p → highly_variable_genes → PCA → neighbors → UMAP

2. Run DPT + PAGA (Scanpy)
   - Compute pseudotime using sc.tl.dpt()
   - Store result in adata.obs['dpt']

3. Run Palantir
   - Use Scanpy's palantir implementation
   - Store result in adata.obs['palantir']

4. Compare methods:
   - Compare DPT and Palantir pseudotime results
   - Plot both on UMAP
"""

def test_natural_pseudotime():
    """Test that system intelligently creates function blocks from natural request."""
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
    output_dir = Path(f"test_outputs/test_natural_pseudotime")
    
    try:
        result = agent.run_analysis(
            input_data_path=str(input_file),
            user_request=USER_REQUEST,
            output_dir=str(output_dir),
            max_nodes=6,  # Reasonable limit
            max_children=1,  # Linear pipeline
            max_debug_trials=1,  # Quick test
            max_iterations=10,
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
        
        # Check that names are meaningful (not all the same)
        if len(set(node_names)) < 2:
            logger.error("All nodes have the same name - not creating meaningful names")
            return False
        
        # Check that names relate to the tasks
        expected_keywords = ['preprocess', 'dpt', 'palantir', 'compare']
        found_keywords = []
        for name in node_names:
            for keyword in expected_keywords:
                if keyword in name.lower():
                    found_keywords.append(keyword)
                    break
        
        logger.info(f"Found task-related keywords: {found_keywords}")
        
        if len(found_keywords) < 2:
            logger.error("Function names don't seem to relate to the requested tasks")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_natural_pseudotime()
    sys.exit(0 if success else 1)