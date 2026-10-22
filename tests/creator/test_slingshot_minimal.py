#!/usr/bin/env python3
"""Minimal test for Slingshot R function block execution."""

import os
import json
import shutil
import tempfile
from pathlib import Path

from omicairn_agent_local.analysis_tree_management.tree_manager import AnalysisTree
from omicairn_agent_local.agents.main_agent import MainAgent
from omicairn_agent_local.llm_service.openai_service import OpenAIService
from omicairn_agent_local.utils.logger import get_logger

logger = get_logger(__name__)


def test_slingshot_minimal():
    """Test Slingshot using the main agent infrastructure."""
    
    print("\n=== Testing Slingshot with Main Agent ===\n")
    
    # Create output directory
    output_base = Path("test_outputs/slingshot_test")
    output_base.mkdir(parents=True, exist_ok=True)
    
    try:
        # Initialize main agent with model
        main_agent = MainAgent(llm_model="gpt-4o")
        
        # Create simple request for Slingshot
        user_request = """
        Load the test data file pbmc3k_seurat_object.rds.
        Run Slingshot (R) pseudotime analysis on the Seurat object.
        Save results as CSV file.
        """
        
        # Run analysis
        print("Starting analysis...")
        result = main_agent.run(
            user_request=user_request,
            input_data_path="test_data/pbmc3k_seurat_object.rds",
            output_dir=str(output_base),
            max_nodes=5
        )
        
        # Check results
        if result and result.get("tree_id"):
            print(f"\n✓ Analysis completed successfully!")
            print(f"  Tree ID: {result['tree_id']}")
            print(f"  Status: {result.get('status', 'Unknown')}")
            
            # Find output files
            tree_dir = output_base / result['tree_id']
            if tree_dir.exists():
                output_files = list(tree_dir.glob("**/*.csv"))
                print(f"\nCSV files generated: {len(output_files)}")
                for f in output_files[:5]:  # Show first 5
                    print(f"  - {f.name}")
                    
                # Check for Slingshot-specific outputs
                slingshot_files = [f for f in output_files if 'slingshot' in f.name.lower() or 'pseudotime' in f.name.lower()]
                if slingshot_files:
                    print(f"\n✓ Found Slingshot output files:")
                    for f in slingshot_files:
                        print(f"  - {f.name}")
                else:
                    print("\n⚠️  No Slingshot-specific output files found")
                    
        else:
            print("\n✗ Analysis failed")
            print(f"Result: {result}")
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set")
        exit(1)
        
    test_slingshot_minimal()