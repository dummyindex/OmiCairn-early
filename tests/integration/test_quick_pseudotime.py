#!/usr/bin/env python3
"""Quick test of pseudotime with better error handling."""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.main_agent import MainAgent
from utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """Run a quick pseudotime test."""
    
    # Setup paths
    output_dir = Path("test_outputs") / "quick_pseudotime_test"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy test data
    import shutil
    input_file = output_dir / "input" / "_node_anndata.h5ad"
    input_file.parent.mkdir(exist_ok=True)
    shutil.copy("data/zebrafish.h5ad", input_file)
    
    # Create a simple request that will fail
    request = """
    Create a single preprocessing function block that:
    1. Load data from path_dict['input_dir']/_node_anndata.h5ad
    2. Try to color UMAP by 'cell_type' column (which doesn't exist)
    3. Save to path_dict['output_dir']/_node_anndata.h5ad
    """
    
    # Initialize agent
    agent = MainAgent(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        bug_fixer_type="unified",
        bug_fixer_model="gpt-4o-mini",
        web_agent_enabled=True,
        enable_interactive_debugging=True
    )
    
    # Run analysis
    result = agent.run_analysis(
        input_data_path=str(input_file),
        user_request=request,
        output_dir=str(output_dir),
        max_iterations=5,
        max_debug_trials=2,
        max_nodes=3
    )
    
    print(f"\nAnalysis completed: {result.success}")
    if not result.success:
        print(f"Error: {result.error}")
    
    # Check for error logs
    tree_dir = output_dir / result.tree_id
    if tree_dir.exists():
        # Find error.json files
        error_files = list(tree_dir.glob("**/error.json"))
        print(f"\nFound {len(error_files)} error files")
        
        for error_file in error_files:
            print(f"\nError file: {error_file}")
            import json
            with open(error_file) as f:
                error_data = json.load(f)
            
            error_msg = error_data.get('error', '')
            print(f"Error message preview: {error_msg[:200]}...")
            print(f"Contains traceback: {'Traceback' in error_msg}")
            print(f"Contains KeyError: {'KeyError' in error_msg}")


if __name__ == "__main__":
    main()