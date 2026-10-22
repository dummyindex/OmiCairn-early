#!/usr/bin/env python
"""Quick test to verify context passing is fixed."""

import os
import sys
from pathlib import Path
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from omicairn_agent_local.agents.main_agent import MainAgent

def test_context_fix():
    """Test that context is properly passed."""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"omicairn_agent_local/test_outputs/context_fix_{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ No OpenAI API key found")
        return False
    
    agent = MainAgent(openai_api_key=api_key)
    
    # Find test data
    test_data = None
    for path in [
        Path("omicairn_agent_local/test_data/zebrafish.h5ad"),
        Path("omicairn_agent_local/test_outputs/clustering_openai_20250804_010410/test_data/zebrafish.h5ad"),
    ]:
        if path.exists():
            test_data = path
            break
    
    if not test_data:
        print("❌ No test data found")
        return False
    
    print(f"\n✅ Test data: {test_data}")
    print(f"📁 Output: {output_dir}\n")
    
    # Simple request to test context passing
    request = """Do these steps:
1. Quality control: filter cells with min_genes=200
2. Apply clustering using the 'Cell_type' column as ground truth for metrics"""
    
    print(f"Request: {request}\n")
    
    result = agent.run_analysis(
        input_data_path=test_data,
        user_request=request,
        output_dir=str(output_dir),
        max_nodes=2,
        max_children=1,
        max_iterations=2,
        max_debug_trials=1,
        generation_mode="only_new",
        llm_model="gpt-4o-mini",
        verbose=True
    )
    
    # Check if context was passed
    tree_id = result['tree_id']
    nodes_dir = output_dir / tree_id / "nodes"
    
    context_passed = False
    
    if nodes_dir.exists():
        for node_dir in sorted(nodes_dir.iterdir()):
            if node_dir.is_dir():
                # Check creation logs for context
                creation_files = list((node_dir / "agent_tasks" / "function_creator").glob("creation_*.json"))
                for cf in creation_files:
                    with open(cf) as f:
                        data = json.load(f)
                        
                        # Check if Cell_type was mentioned in prompt
                        if 'llm_input' in data:
                            messages = data['llm_input'].get('messages', [])
                            for msg in messages:
                                content = msg.get('content', '')
                                if 'Cell_type' in content:
                                    context_passed = True
                                    print(f"✅ Found 'Cell_type' context in {node_dir.name}")
                                    break
    
    if context_passed:
        print("\n✅ Context passing is working!")
    else:
        print("\n❌ Context not being passed")
    
    return context_passed

if __name__ == "__main__":
    test_context_fix()