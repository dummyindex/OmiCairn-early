#!/usr/bin/env python3
"""Test core data models - simplified version."""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import NodeState, GenerationMode, FunctionBlockType


def test_node_states():
    """Test NodeState enum values."""
    assert NodeState.PENDING == "pending"
    assert NodeState.RUNNING == "running"
    assert NodeState.COMPLETED == "completed"
    assert NodeState.FAILED == "failed"
    assert NodeState.DEBUGGING == "debugging"
    assert NodeState.SKIPPED == "skipped"


def test_generation_modes():
    """Test GenerationMode enum values."""
    assert GenerationMode.MIXED == "mixed"
    assert GenerationMode.ONLY_NEW == "only_new"
    assert GenerationMode.ONLY_EXISTING == "only_existing"


def test_function_block_types():
    """Test FunctionBlockType enum values."""
    assert FunctionBlockType.PYTHON == "python"
    assert FunctionBlockType.R == "r"


def test_enum_membership():
    """Test that we can check enum membership."""
    assert "pending" in [state.value for state in NodeState]
    assert "completed" in [state.value for state in NodeState]
    assert "python" in [lang.value for lang in FunctionBlockType]
    assert "r" in [lang.value for lang in FunctionBlockType]


def test_enum_iteration():
    """Test that we can iterate over enums."""
    node_states = list(NodeState)
    assert len(node_states) == 6
    assert NodeState.PENDING in node_states
    
    function_types = list(FunctionBlockType)
    assert len(function_types) == 2
    assert FunctionBlockType.PYTHON in function_types


if __name__ == "__main__":
    print("Testing core models...")
    test_node_states()
    print("✓ NodeState tests passed")
    
    test_generation_modes()
    print("✓ GenerationMode tests passed")
    
    test_function_block_types()
    print("✓ FunctionBlockType tests passed")
    
    test_enum_membership()
    print("✓ Enum membership tests passed")
    
    test_enum_iteration()
    print("✓ Enum iteration tests passed")
    
    print("\n🎉 All model tests passed!")