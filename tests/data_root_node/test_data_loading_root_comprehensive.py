#!/usr/bin/env python3
"""Comprehensive test of data loading root node - ensures orchestrator can attach new nodes."""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime

# Add the omicairn_agent_local directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.main_agent import MainAgent

def test_data_loading_root_comprehensive():
    """Test that data loading root node allows orchestrator to add children."""
    
    # Request that requires child nodes to complete
    user_request = """
    Perform a complete single-cell analysis:
    1. Normalize the data using scanpy's normalize_total and log1p
    2. Find highly variable genes
    3. Perform PCA
    4. Generate QC plots
    """
    
    # Input data path
    input_data = Path("test_data/zebrafish.h5ad")
    
    # Output directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"test_data_root_comprehensive_{timestamp}")
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
    print("COMPREHENSIVE TEST: DATA LOADING ROOT NODE")
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
            enable_web_agent=True,
            log_llm_to_stdout=True
        )
        
        # Run the analysis - should create multiple nodes
        result = agent.run_analysis(
            input_data_path=input_data,
            user_request=user_request,
            output_dir=output_dir,
            max_nodes=10,  # Allow more nodes
            max_children=3,
            max_debug_trials=2,
            max_iterations=10,  # More iterations
            function_block_timeout=300,
            verbose=True
        )
        
        print(f"\n{'='*80}")
        print("TEST RESULTS")
        print(f"{'='*80}")
        
        # Check that data loading root was created
        tree_id = result['tree_id']
        tree_dir = output_dir / tree_id
        
        # Load the analysis tree
        import json
        tree_file = tree_dir / "analysis_tree.json"
        if tree_file.exists():
            with open(tree_file, 'r') as f:
                tree_data = json.load(f)
            
            # Check root node
            root_node_id = tree_data.get('root_node_id')
            if root_node_id:
                root_node = tree_data['nodes'].get(root_node_id)
                if root_node:
                    root_name = root_node['function_block']['name']
                    root_state = root_node['state']
                    print(f"✓ Root node exists: {root_name}")
                    print(f"  State: {root_state}")
                    print(f"  ID: {root_node_id}")
                    
                    # Check if it's our data loading node
                    if root_name == "load_input_data":
                        print("✓ Root node is data loading node as expected!")
                    else:
                        print(f"✗ Root node is '{root_name}', expected 'load_input_data'")
                    
                    # Check children - CRITICAL TEST
                    children = root_node.get('children', [])
                    print(f"\n  Children: {len(children)}")
                    
                    if len(children) > 0:
                        print("✓ CRITICAL: Orchestrator successfully attached children to data loading root!")
                        for child_id in children:
                            child_node = tree_data['nodes'].get(child_id)
                            if child_node:
                                child_name = child_node['function_block']['name']
                                child_state = child_node['state']
                                print(f"    - {child_name} ({child_state})")
                    else:
                        print("✗ CRITICAL: No children attached to root node")
                    
                    # Show full tree structure
                    print("\nFull Tree Structure:")
                    def print_tree(node_id, indent=0):
                        node = tree_data['nodes'].get(node_id)
                        if node:
                            state_symbol = "✅" if node['state'] == "completed" else "❌" if node['state'] == "failed" else "⏳"
                            print(f"{'  ' * indent}└─ {node['function_block']['name']} [{state_symbol}]")
                            for child_id in node.get('children', []):
                                print_tree(child_id, indent + 1)
                    
                    print_tree(root_node_id)
                    
                else:
                    print("✗ Root node not found in tree")
            else:
                print("✗ No root node ID in tree")
        else:
            print("✗ Analysis tree file not found")
        
        # Summary
        print(f"\nTotal nodes: {result['total_nodes']}")
        print(f"Completed nodes: {result['completed_nodes']}")
        print(f"Failed nodes: {result['failed_nodes']}")
        
        # Success criteria:
        # 1. Root node exists and is data loading node
        # 2. Root node completed successfully
        # 3. At least one child node was attached
        # 4. Total nodes > 1 (not just root)
        success = (
            root_node_id and 
            root_node.get('function_block', {}).get('name') == 'load_input_data' and
            root_node.get('state') == 'completed' and
            len(children) > 0 and
            result['total_nodes'] > 1
        )
        
        print(f"\n{'='*80}")
        if success:
            print("✓ TEST PASSED: Data loading root node allows child attachments!")
        else:
            print("✗ TEST FAILED: Issues with data loading root node or child attachments")
        print(f"{'='*80}\n")
        
        return success
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_data_loading_root_comprehensive()
    sys.exit(0 if success else 1)