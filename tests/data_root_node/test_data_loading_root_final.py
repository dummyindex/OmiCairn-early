#!/usr/bin/env python3
"""Final test of data loading root node - quick verification it works."""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# Add the omicairn_agent_local directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.main_agent import MainAgent

def test_data_loading_root_final():
    """Quick test that data loading root node allows child attachments."""
    
    # Simple request with just one task
    user_request = """
    Normalize the data using scanpy's normalize_total method.
    """
    
    # Input data path
    input_data = Path("test_data/zebrafish.h5ad")
    
    # Output directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"test_data_root_final_{timestamp}")
    output_dir.mkdir(exist_ok=True)
    
    # Set up logging
    log_file = output_dir / "test.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    print(f"\n{'='*80}")
    print("FINAL TEST: DATA LOADING ROOT NODE WITH CHILD")
    print(f"{'='*80}")
    print(f"Input data: {input_data}")
    print(f"Output directory: {output_dir}")
    print(f"Started at: {datetime.now()}")
    print(f"{'='*80}\n")
    
    try:
        # Initialize the main agent
        agent = MainAgent(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            bug_fixer_type="unified",
            bug_fixer_model="gpt-4o-mini",
            llm_model="gpt-4o-mini",
            enable_interactive_debug=True,
            enable_web_agent=False,  # Disable for speed
            log_llm_to_stdout=False  # Less verbose
        )
        
        # Run the analysis - should create root + normalize node
        result = agent.run_analysis(
            input_data_path=input_data,
            user_request=user_request,
            output_dir=output_dir,
            max_nodes=5,  # Small limit
            max_children=2,
            max_debug_trials=1,  # Minimal debugging
            max_iterations=5,  # Quick test
            function_block_timeout=300,
            verbose=True
        )
        
        print(f"\n{'='*80}")
        print("TEST RESULTS")
        print(f"{'='*80}")
        
        # Check results
        tree_id = result['tree_id']
        tree_dir = output_dir / tree_id
        
        # Load the analysis tree
        import json
        tree_file = tree_dir / "analysis_tree.json"
        if tree_file.exists():
            with open(tree_file, 'r') as f:
                tree_data = json.load(f)
            
            # Check nodes
            print(f"Total nodes: {len(tree_data['nodes'])}")
            print("\nNodes created:")
            for node_id, node in tree_data['nodes'].items():
                state = node['state']
                name = node['function_block']['name']
                parent_id = node.get('parent_id')
                state_symbol = "✅" if state == "completed" else "❌" if state == "failed" else "⏳"
                
                if parent_id:
                    parent_name = tree_data['nodes'][parent_id]['function_block']['name']
                    print(f"  - {name} [{state_symbol}] (child of {parent_name})")
                else:
                    print(f"  - {name} [{state_symbol}] (root)")
        
        # Success criteria:
        # 1. At least 2 nodes (root + child)
        # 2. Root is data loading node
        # 3. Child was attached to root
        success = result['total_nodes'] >= 2
        if success and tree_file.exists():
            root_ids = {nid for nid, n in tree_data['nodes'].items() if not n.get('parent_id')}
            root_ok = any(tree_data['nodes'][nid]['function_block']['name'] == 'load_input_data'
                          for nid in root_ids)
            child_ok = any(n.get('parent_id') in root_ids for n in tree_data['nodes'].values())
            success = root_ok and child_ok
        else:
            success = False
        
        print(f"\n{'='*80}")
        if success:
            print("✅ TEST PASSED: Data loading root node with child attachment works!")
        else:
            print("❌ TEST FAILED: Not enough nodes created")
        print(f"{'='*80}\n")
        
        return success
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_data_loading_root_final()
    sys.exit(0 if success else 1)