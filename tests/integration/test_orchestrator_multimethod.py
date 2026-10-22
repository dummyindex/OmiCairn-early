#!/usr/bin/env python3
"""Test orchestrator's handling of multi-method requests."""

from agents.orchestrator_agent import OrchestratorAgent
from llm_service.openai_service import OpenAIService
import os
from dotenv import load_dotenv

load_dotenv()

# Test multi-method request
MULTI_METHOD_REQUEST = """
1. Preprocess dataset
2. Run DPT pseudotime
3. Run Palantir pseudotime  
4. Run scFates pseudotime
5. Run CellRank pseudotime
6. Run DTFLOW pseudotime
7. Compute evaluation metrics
8. Plot pseudotime over UMAP
9. Plot metric comparisons
"""

def test_orchestrator_planning():
    """Test orchestrator planning with multi-method request."""
    
    # Initialize services
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return
    
    llm_service = OpenAIService(model="gpt-4o-mini", api_key=api_key)
    orchestrator = OrchestratorAgent(llm_service=llm_service)
    
    print("Testing Orchestrator Multi-Method Planning")
    print("=" * 60)
    print("User request has 9 tasks:")
    print(MULTI_METHOD_REQUEST)
    print("=" * 60)
    
    # Test scenarios
    scenarios = [
        {
            "name": "Initial state (no nodes)",
            "tree_state": {
                "total_nodes": 0,
                "completed_nodes": 0,
                "failed_nodes": 0,
                "nodes": []
            }
        },
        {
            "name": "After preprocessing",
            "tree_state": {
                "total_nodes": 1,
                "completed_nodes": 1,
                "failed_nodes": 0,
                "nodes": [{
                    "id": "node_1",
                    "name": "preprocess_dataset",
                    "state": "completed",
                    "description": "Preprocessing with Scanpy",
                    "parent_id": None,
                    "children": [],
                    "debug_attempts": 0
                }]
            }
        },
        {
            "name": "After DPT and failed Palantir",
            "tree_state": {
                "total_nodes": 3,
                "completed_nodes": 2,
                "failed_nodes": 1,
                "nodes": [
                    {
                        "id": "node_1",
                        "name": "preprocess_dataset",
                        "state": "completed",
                        "description": "Preprocessing with Scanpy",
                        "parent_id": None,
                        "children": ["node_2", "node_3"],
                        "debug_attempts": 0
                    },
                    {
                        "id": "node_2",
                        "name": "dpt_pseudotime",
                        "state": "completed",
                        "description": "DPT pseudotime analysis",
                        "parent_id": "node_1",
                        "children": [],
                        "debug_attempts": 0
                    },
                    {
                        "id": "node_3",
                        "name": "palantir_pseudotime",
                        "state": "failed",
                        "description": "Palantir pseudotime",
                        "parent_id": "node_1",
                        "children": [],
                        "debug_attempts": 3,
                        "error": "ModuleNotFoundError: No module named 'palantir'"
                    }
                ]
            }
        }
    ]
    
    for i, scenario in enumerate(scenarios):
        print(f"\n### Scenario {i+1}: {scenario['name']} ###")
        
        result = orchestrator.plan_next_steps({
            "user_request": MULTI_METHOD_REQUEST,
            "tree_state": scenario['tree_state'],
            "iteration": i + 1
        })
        
        print(f"Satisfied: {result['satisfied']}")
        print(f"Reasoning: {result['reasoning']}")
        print(f"Next actions: {len(result['next_actions'])}")
        
        if result['next_actions']:
            for action in result['next_actions']:
                print(f"  - {action['name']}: {action['specification']['description']}")
        
        # Key check: Should NOT be satisfied until all 9 tasks attempted
        if result['satisfied'] and scenario['tree_state']['total_nodes'] < 9:
            print(f"❌ ERROR: Marked satisfied with only {scenario['tree_state']['total_nodes']} nodes!")
        elif not result['satisfied'] and scenario['tree_state']['total_nodes'] < 9:
            print(f"✓ Correct: Not satisfied, continuing to create more nodes")
    
    print("\n" + "=" * 60)
    print("Test complete!")


if __name__ == "__main__":
    test_orchestrator_planning()