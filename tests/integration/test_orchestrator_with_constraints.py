#!/usr/bin/env python3
"""Test orchestrator with actual branch constraints."""

from agents.orchestrator_agent import OrchestratorAgent
from llm_service.openai_service import OpenAIService
import os
from dotenv import load_dotenv

load_dotenv()

# Test request asking for multiple methods
MULTI_METHOD_REQUEST = """
Run ALL of the following pseudotime methods on my dataset:
1. DPT
2. Palantir  
3. scFates
4. CellRank
5. DTFLOW
Then compare their results.
"""

def test_with_constraints():
    """Test orchestrator with different branch constraints."""
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return
    
    llm_service = OpenAIService(model="gpt-4o-mini", api_key=api_key)
    orchestrator = OrchestratorAgent(llm_service=llm_service)
    
    print("Testing Orchestrator with Branch Constraints")
    print("=" * 60)
    
    # Test with different branch limits
    for max_children in [2, 3, 5]:
        print(f"\n### Testing with max_children_per_node = {max_children} ###")
        
        tree_state = {
            "total_nodes": 1,
            "completed_nodes": 1,
            "failed_nodes": 0,
            "nodes": [{
                "id": "node_1",
                "name": "preprocess_dataset",
                "state": "completed",
                "description": "Preprocessing complete",
                "parent_id": None,
                "children": [],
                "debug_attempts": 0
            }],
            "constraints": {
                "max_nodes": 20,
                "max_children_per_node": max_children
            }
        }
        
        result = orchestrator.plan_next_steps({
            "user_request": MULTI_METHOD_REQUEST,
            "tree_state": tree_state,
            "iteration": 2
        })
        
        print(f"Reasoning excerpt: {result['reasoning'][:200]}...")
        print(f"Next action: {result['next_actions'][0]['name'] if result['next_actions'] else 'None'}")
        
        # Check if orchestrator acknowledges the constraint
        if str(max_children) in result['reasoning']:
            print(f"✓ Orchestrator acknowledged max_children_per_node = {max_children}")
        else:
            print(f"❌ Orchestrator did not mention the constraint")


if __name__ == "__main__":
    test_with_constraints()