#!/usr/bin/env python3
"""Test orchestrator adaptation to failed nodes with mock responses."""

import json
from typing import Dict, Any, List
from pathlib import Path

from agents.orchestrator_agent import OrchestratorAgent
from models import AnalysisTree, AnalysisNode, NodeState, NewFunctionBlock, FunctionBlockType, StaticConfig

# Mock LLM service for testing
class MockLLMService:
    """Mock LLM service that returns predefined responses based on tree state."""
    
    def __init__(self):
        self.call_count = 0
        self.model = "mock-model"
        
    def chat_completion_json(self, messages: List[Dict], json_schema: Dict, **kwargs) -> Dict[str, Any]:
        """Return mock responses based on the prompt content."""
        self.call_count += 1
        
        # Extract prompt content
        user_message = messages[-1]["content"]
        
        # Parse tree state from prompt
        has_failed_scfates = "scfates_pseudotime_analysis: failed" in user_message
        has_completed_dpt = "dpt_pseudotime_analysis: completed" in user_message
        has_palantir = "palantir_pseudotime_analysis: completed" in user_message
        has_evaluation = "evaluate_pseudotime_methods: completed" in user_message
        
        print(f"\n=== Mock LLM Call {self.call_count} ===")
        print(f"Failed scFates detected: {has_failed_scfates}")
        print(f"Completed DPT detected: {has_completed_dpt}")
        
        # Scenario 1: Initial state - create preprocessing
        if self.call_count == 1:
            return {
                "satisfied": False,
                "reasoning": "Need to start with preprocessing",
                "next_actions": [{
                    "type": "create_new",
                    "name": "preprocess_data",
                    "specification": {
                        "name": "preprocess_data",
                        "description": "Preprocess dataset with Scanpy",
                        "task": "Normalize and compute HVG, PCA, UMAP"
                    }
                }]
            }
        
        # Scenario 2: After preprocessing - create DPT if not present
        elif self.call_count == 2 and not has_completed_dpt:
            return {
                "satisfied": False,
                "reasoning": "Preprocessing complete, now run requested pseudotime methods",
                "next_actions": [{
                    "type": "create_new",
                    "name": "dpt_pseudotime_analysis",
                    "specification": {
                        "name": "dpt_pseudotime_analysis",
                        "description": "Run DPT with PAGA",
                        "task": "Compute DPT pseudotime"
                    }
                }]
            }
        
        # Scenario 3: After DPT success - add scFates
        elif self.call_count == 3:
            return {
                "satisfied": False,
                "reasoning": "DPT complete, add scFates analysis",
                "next_actions": [{
                    "type": "create_new",
                    "name": "scfates_pseudotime_analysis",
                    "specification": {
                        "name": "scfates_pseudotime_analysis",
                        "description": "Run scFates trajectory analysis",
                        "task": "Learn trajectory with scFates"
                    }
                }]
            }
        
        # Scenario 4: After scFates failure - skip to next method
        elif has_failed_scfates and not has_palantir:
            return {
                "satisfied": False,
                "reasoning": "scFates failed due to missing module. Skipping to Palantir which doesn't depend on scFates output.",
                "next_actions": [{
                    "type": "create_new",
                    "name": "palantir_pseudotime_analysis",
                    "specification": {
                        "name": "palantir_pseudotime_analysis",
                        "description": "Run Palantir pseudotime",
                        "task": "Compute pseudotime with Palantir"
                    }
                }]
            }
        
        # Scenario 5: After Palantir - finish with evaluation
        elif has_palantir:
            return {
                "satisfied": False,
                "reasoning": "Multiple methods complete (DPT, Palantir). scFates failed but we have other results. Creating evaluation.",
                "next_actions": [{
                    "type": "create_new",
                    "name": "evaluate_pseudotime_methods",
                    "specification": {
                        "name": "evaluate_pseudotime_methods",
                        "description": "Compare pseudotime methods",
                        "task": "Evaluate and visualize pseudotime results"
                    }
                }]
            }
        
        # Final: Mark as satisfied when evaluation is present
        elif has_evaluation:
            return {
                "satisfied": True,
                "reasoning": "Core objectives met: preprocessing done, multiple pseudotime methods attempted (DPT and Palantir succeeded, scFates failed), evaluation complete.",
                "next_actions": []
            }
        else:
            # Default response
            return {
                "satisfied": False,
                "reasoning": "Continue with analysis",
                "next_actions": []
            }


def create_mock_tree() -> AnalysisTree:
    """Create a mock analysis tree for testing."""
    tree = AnalysisTree(
        user_request="Run DPT, scFates, and Palantir pseudotime analysis",
        input_data_path="/tmp/test_data.h5ad",
        root_node_id="node_1",
        max_nodes=20,
        max_children_per_node=5,
        max_debug_trials=3
    )
    
    # Add preprocessing node (completed)
    preprocess_node = AnalysisNode(
        id="node_1",
        analysis_id="test_analysis",
        function_block=NewFunctionBlock(
            name="preprocess_data",
            type=FunctionBlockType.PYTHON,
            description="Preprocess with Scanpy",
            code="# preprocessing code",
            requirements="scanpy",
            parameters={},
            static_config=StaticConfig(
                args=[],
                description="Preprocess data",
                tag="normalization"
            )
        ),
        parent_id=None,
        state=NodeState.COMPLETED
    )
    tree.nodes["node_1"] = preprocess_node
    tree.completed_nodes = 1
    
    return tree


def simulate_failed_node(tree: AnalysisTree):
    """Add a failed scFates node to the tree."""
    # Add DPT node (completed)
    dpt_node = AnalysisNode(
        id="node_2",
        analysis_id="test_analysis",
        function_block=NewFunctionBlock(
            name="dpt_pseudotime_analysis",
            type=FunctionBlockType.PYTHON,
            description="Run DPT with PAGA",
            code="# DPT code",
            requirements="scanpy",
            parameters={},
            static_config=StaticConfig(
                args=[],
                description="Run DPT analysis",
                tag="analysis"
            )
        ),
        parent_id="node_1",
        state=NodeState.COMPLETED
    )
    tree.nodes["node_2"] = dpt_node
    tree.nodes["node_1"].children.append("node_2")
    tree.completed_nodes += 1
    
    # Add scFates node (failed)
    scfates_node = AnalysisNode(
        id="node_3",
        analysis_id="test_analysis",
        function_block=NewFunctionBlock(
            name="scfates_pseudotime_analysis",
            type=FunctionBlockType.PYTHON,
            description="Run scFates trajectory analysis",
            code="import scfates",
            requirements="scfates",
            parameters={},
            static_config=StaticConfig(
                args=[],
                description="Run scFates analysis",
                tag="analysis"
            )
        ),
        parent_id="node_1",
        state=NodeState.FAILED,
        debug_attempts=3  # Mark as permanently failed
    )
    scfates_node.execution_result = {"error": "ModuleNotFoundError: No module named 'scfates'"}
    tree.nodes["node_3"] = scfates_node
    tree.nodes["node_1"].children.append("node_3")
    tree.failed_nodes += 1


def test_orchestrator_adaptation():
    """Test orchestrator's ability to adapt when nodes fail."""
    print("=" * 60)
    print("Testing Orchestrator Adaptation to Failed Nodes")
    print("=" * 60)
    
    # Create mock components
    mock_llm = MockLLMService()
    orchestrator = OrchestratorAgent(llm_service=mock_llm)
    
    # Test 1: Initial planning
    print("\n### Test 1: Initial Planning ###")
    tree = create_mock_tree()
    tree_state = {
        "total_nodes": len(tree.nodes),
        "completed_nodes": tree.completed_nodes,
        "failed_nodes": tree.failed_nodes,
        "nodes": [{
            "id": "node_1",
            "name": "preprocess_data",
            "state": "completed",
            "description": "Preprocess with Scanpy",
            "parent_id": None,
            "children": [],
            "debug_attempts": 0
        }]
    }
    
    result = orchestrator.plan_next_steps({
        "user_request": tree.user_request,
        "tree_state": tree_state,
        "iteration": 1
    })
    
    print(f"Planning result: satisfied={result['satisfied']}")
    print(f"Reasoning: {result['reasoning']}")
    print(f"Next actions: {len(result['next_actions'])}")
    
    # Test 2: After scFates failure
    print("\n### Test 2: After scFates Failure ###")
    simulate_failed_node(tree)
    
    tree_state = {
        "total_nodes": len(tree.nodes),
        "completed_nodes": tree.completed_nodes, 
        "failed_nodes": tree.failed_nodes,
        "nodes": [
            {
                "id": "node_1",
                "name": "preprocess_data",
                "state": "completed",
                "description": "Preprocess with Scanpy",
                "parent_id": None,
                "children": ["node_2", "node_3"],
                "debug_attempts": 0
            },
            {
                "id": "node_2",
                "name": "dpt_pseudotime_analysis", 
                "state": "completed",
                "description": "Run DPT with PAGA",
                "parent_id": "node_1",
                "children": [],
                "debug_attempts": 0
            },
            {
                "id": "node_3",
                "name": "scfates_pseudotime_analysis",
                "state": "failed", 
                "description": "Run scFates trajectory analysis",
                "parent_id": "node_1",
                "children": [],
                "debug_attempts": 3,
                "error": "ModuleNotFoundError: No module named 'scfates'"
            }
        ]
    }
    
    result = orchestrator.plan_next_steps({
        "user_request": tree.user_request,
        "tree_state": tree_state,
        "iteration": 4
    })
    
    print(f"Planning result: satisfied={result['satisfied']}")
    print(f"Reasoning: {result['reasoning']}")
    print(f"Next actions: {len(result['next_actions'])}")
    if result['next_actions']:
        print(f"Next action: {result['next_actions'][0]['name']}")
    
    # Verify adaptation behavior
    assert not result['satisfied'], "Should not be satisfied yet"
    assert len(result['next_actions']) > 0, "Should suggest alternative action"
    assert "palantir" in result['next_actions'][0]['name'].lower(), "Should suggest Palantir as alternative"
    
    print("\n### Test 3: Final Satisfaction Check ###")
    # Add successful Palantir and evaluation
    tree_state['nodes'].append({
        "id": "node_4",
        "name": "palantir_pseudotime_analysis",
        "state": "completed",
        "description": "Run Palantir pseudotime",
        "parent_id": "node_1",
        "children": [],
        "debug_attempts": 0
    })
    tree_state['nodes'].append({
        "id": "node_5", 
        "name": "evaluate_pseudotime_methods",
        "state": "completed",
        "description": "Compare pseudotime methods",
        "parent_id": "node_1",
        "children": [],
        "debug_attempts": 0
    })
    tree_state['completed_nodes'] = 4
    tree_state['total_nodes'] = 5
    
    result = orchestrator.plan_next_steps({
        "user_request": tree.user_request,
        "tree_state": tree_state,
        "iteration": 6
    })
    
    print(f"Planning result: satisfied={result['satisfied']}")
    print(f"Reasoning: {result['reasoning']}")
    
    assert result['satisfied'], "Should be satisfied once alternatives and evaluation completed"
    
    # Note: this is a contract test of the planning plumbing driven by a scripted
    # mock LLM; it does not measure the planning quality of a real LLM.
    print("\nAll checks passed (mock-LLM contract test).")


if __name__ == "__main__":
    test_orchestrator_adaptation()