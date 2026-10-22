#!/usr/bin/env python
"""Simple test to verify basic pipeline functionality."""

import os
import sys
from pathlib import Path
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from omicairn_agent_local.agents.main_agent import MainAgent

def test_simple_pipeline():
    """Test a simple 3-step pipeline."""
    
    # Setup
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ No OpenAI API key found")
        return False
    
    agent = MainAgent(openai_api_key=api_key)
    
    # Simple test data
    test_data = Path("test_data/zebrafish.h5ad")
    
    print("\n" + "="*60)
    print("SIMPLE PIPELINE TEST")
    print("="*60)
    
    # Very simple request to maximize success
    simple_request = """Process this dataset step by step:
1. Quality control: filter cells with min_genes=200, filter genes with min_cells=3
2. Normalize: apply total-count normalization and log1p transformation
3. PCA: calculate 50 principal components and create variance ratio plot"""
    
    print(f"Request: {simple_request}\n")
    
    start_time = time.time()
    
    result = agent.run_analysis(
        input_data_path=test_data,
        user_request=simple_request,
        output_dir="test_outputs/simple_pipeline",
        max_nodes=3,
        max_children=1,
        max_iterations=5,
        max_debug_trials=3,
        generation_mode="only_new",
        llm_model="gpt-4o-mini",
        verbose=True
    )
    
    duration = time.time() - start_time
    
    print("\n" + "="*60)
    print("RESULTS")
    print("="*60)
    print(f"Duration: {duration:.1f}s")
    print(f"Total nodes: {result['total_nodes']}")
    print(f"Completed: {result['completed_nodes']}")
    print(f"Failed: {result['failed_nodes']}")
    
    # Success if all 3 nodes completed
    success = result['total_nodes'] == 3 and result['failed_nodes'] == 0
    
    if success:
        print("\n✅ TEST PASSED: Simple pipeline completed successfully")
    else:
        print("\n❌ TEST FAILED: Pipeline did not complete all steps")
    
    return success

if __name__ == "__main__":
    success = test_simple_pipeline()
    sys.exit(0 if success else 1)