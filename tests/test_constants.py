"""Test that constants are properly used throughout the system."""

import pytest
from constants import ROOT_NODE_NAME
from analysis_tree_management.tree_manager import AnalysisTreeManager
from models import GenerationMode


def test_root_node_uses_constant():
    """Test that root node creation uses the ROOT_NODE_NAME constant."""
    # Create tree manager
    tree_manager = AnalysisTreeManager()
    
    # Create a tree
    tree = tree_manager.create_tree(
        user_request="Test request",
        input_data_path="/tmp/test.h5ad",
        generation_mode=GenerationMode.MIXED
    )
    
    # Get root node
    root_node = tree.get_node(tree.root_node_id)
    
    # Verify it uses the constant
    assert root_node.function_block.name == ROOT_NODE_NAME
    assert ROOT_NODE_NAME == "load_input_data"  # Verify constant value
    
    # Verify description is accurate
    assert "Pass-through node" in root_node.function_block.description


def test_constants_imported_in_agents():
    """Test that agents can import and use constants."""
    from agents.main_agent import ROOT_NODE_NAME as main_agent_const
    from agents.orchestrator_agent import ROOT_NODE_NAME as orch_const
    
    # Verify imports work
    assert main_agent_const == ROOT_NODE_NAME
    assert orch_const == ROOT_NODE_NAME
    assert main_agent_const == "load_input_data"


if __name__ == "__main__":
    test_root_node_uses_constant()
    test_constants_imported_in_agents()
    print("All constant tests passed!")