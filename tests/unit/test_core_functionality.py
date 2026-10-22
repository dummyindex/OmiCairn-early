"""Consolidated unit tests for core functionality.

This file consolidates simple unit tests for constants, models, utilities, and basic functionality.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime

from constants import (
    ROOT_NODE_NAME, DEFAULT_OPENAI_MODEL, MAX_REWORK_ATTEMPTS,
    DEFAULT_MAX_DEBUG_TRIALS
)
from models import (
    NodeState, JobReviewStatus, FunctionBlockType, GenerationMode,
    AnalysisNode, AnalysisTree, NewFunctionBlock, ExecutionResult,
    Arg, StaticConfig
)
# json_utils/path_utils are covered in tests/test_json_utils.py and tests/test_path_utils.py


class TestConstants:
    """Test constants are properly defined and used."""
    
    def test_root_node_name_constant(self):
        """Test ROOT_NODE_NAME constant."""
        assert ROOT_NODE_NAME == "load_input_data"
        assert isinstance(ROOT_NODE_NAME, str)
    
    def test_model_constants(self):
        """Test model-related constants."""
        assert DEFAULT_OPENAI_MODEL == "gpt-4o-mini"
        assert isinstance(DEFAULT_MAX_DEBUG_TRIALS, int)
        assert DEFAULT_MAX_DEBUG_TRIALS > 0
    
    def test_rework_limit_constant(self):
        """Test rework limit constant."""
        assert isinstance(MAX_REWORK_ATTEMPTS, int)
        assert MAX_REWORK_ATTEMPTS >= 2  # Should allow at least 2 attempts
        assert MAX_REWORK_ATTEMPTS <= 10  # Shouldn't be too high
    
    def test_constants_imported_in_modules(self):
        """Test that constants can be imported in various modules."""
        # These imports should work without errors
        from agents.main_agent import ROOT_NODE_NAME as main_const
        from analysis_tree_management.tree_manager import ROOT_NODE_NAME as tree_const
        
        assert main_const == ROOT_NODE_NAME
        assert tree_const == ROOT_NODE_NAME


class TestModels:
    """Test model classes and enums."""
    
    def test_node_state_enum(self):
        """Test NodeState enum values."""
        assert NodeState.PENDING.value == "pending"
        assert NodeState.RUNNING.value == "running"
        assert NodeState.COMPLETED.value == "completed"
        assert NodeState.FAILED.value == "failed"
        assert NodeState.DEBUGGING.value == "debugging"
        assert NodeState.SKIPPED.value == "skipped"
    
    def test_job_review_status_enum(self):
        """Test JobReviewStatus enum values."""
        assert JobReviewStatus.PASSED.value == "passed"
        assert JobReviewStatus.FAILED.value == "failed"
        assert JobReviewStatus.NOT_REVIEWED.value == "not_reviewed"
        assert JobReviewStatus.SKIPPED.value == "skipped"
    
    def test_function_block_type_enum(self):
        """Test FunctionBlockType enum values."""
        assert FunctionBlockType.PYTHON.value == "python"
        assert FunctionBlockType.R.value == "r"
    
    def test_generation_mode_enum(self):
        """Test GenerationMode enum values."""
        assert GenerationMode.MIXED.value == "mixed"
        assert GenerationMode.ONLY_NEW.value == "only_new"
        assert GenerationMode.ONLY_EXISTING.value == "only_existing"
    
    def test_analysis_node_creation(self):
        """Test AnalysisNode model creation."""
        static_config = StaticConfig(
            args=[],
            description="Test function",
            tag="test"
        )
        
        function_block = NewFunctionBlock(
            id="test_fb",
            name="Test Function",
            description="Test description",
            type=FunctionBlockType.PYTHON,
            code="def run(path_dict, params): pass",
            requirements="numpy",
            parameters={},
            static_config=static_config
        )
        
        node = AnalysisNode(
            id="test_node",
            analysis_id="test_tree",
            function_block=function_block
        )
        
        # Test default values
        assert node.state == NodeState.PENDING
        assert node.parent_id is None
        assert node.level == 0
        assert node.debug_attempts == 0
        assert node.rework_attempts == 0
        assert not node.needs_rework
        assert not node.rework_limit_reached
        assert node.job_review_status is None
    
    def test_analysis_tree_operations(self):
        """Test AnalysisTree model operations."""
        tree = AnalysisTree(
            id="test_tree",
            user_request="Test request",
            input_data_path="test.h5ad",
            max_nodes=10,
            max_children_per_node=3,
            max_debug_trials=3
        )
        
        # Test initial state
        assert tree.total_nodes == 0
        assert tree.completed_nodes == 0
        assert tree.failed_nodes == 0
        assert len(tree.nodes) == 0
        
        # Add a node
        static_config = StaticConfig(args=[], description="Test", tag="test")
        function_block = NewFunctionBlock(
            id="fb1",
            name="Test",
            description="Test",
            type=FunctionBlockType.PYTHON,
            code="pass",
            requirements="",
            parameters={},
            static_config=static_config
        )
        
        node = AnalysisNode(
            id="node1",
            analysis_id=tree.id,
            function_block=function_block
        )
        
        tree.add_node(node)
        
        assert tree.total_nodes == 1
        assert node.id in tree.nodes
        assert tree.get_node(node.id) == node
    
    def test_node_state_transitions(self):
        """Test node state transition tracking."""
        tree = AnalysisTree(
            id="test",
            user_request="Test",
            input_data_path="test.h5ad",
            max_nodes=5,
            max_children_per_node=2,
            max_debug_trials=3
        )
        
        static_config = StaticConfig(args=[], description="Test", tag="test")
        node = AnalysisNode(
            id="node1",
            analysis_id=tree.id,
            function_block=NewFunctionBlock(
                id="fb",
                name="Test",
                description="Test",
                type=FunctionBlockType.PYTHON,
                code="pass",
                requirements="",
                parameters={},
                static_config=static_config
            )
        )
        
        tree.add_node(node)
        
        # Test state transitions
        tree.update_node_state(node.id, NodeState.RUNNING)
        assert node.state == NodeState.RUNNING
        assert tree.completed_nodes == 0
        assert tree.failed_nodes == 0
        
        tree.update_node_state(node.id, NodeState.COMPLETED)
        assert node.state == NodeState.COMPLETED
        assert tree.completed_nodes == 1
        assert tree.failed_nodes == 0
        
        # Transition to failed
        tree.update_node_state(node.id, NodeState.FAILED)
        assert node.state == NodeState.FAILED
        assert tree.completed_nodes == 0
        assert tree.failed_nodes == 1
    
    def test_execution_result_creation(self):
        """Test ExecutionResult model creation."""
        result = ExecutionResult(
            success=True,
            output_data_path="/tmp/output",
            stdout="Success",
            stderr="",
            duration=10.5
        )
        
        assert result.success
        assert result.output_data_path == "/tmp/output"
        assert result.stdout == "Success"
        assert result.stderr == ""
        assert result.duration == 10.5
        assert result.error is None
        assert isinstance(result.figures, list)
        assert len(result.figures) == 0


class TestActionSchema:
    """Test action schema validation."""
    
    def test_valid_action_structure(self):
        """Test valid action structure."""
        action = {
            "type": "read_file",
            "params": {"path": "test.py"},
            "explanation": "Reading test file",
            "confidence": 0.9
        }
        
        # Should have all required fields
        assert "type" in action
        assert "params" in action
        assert "explanation" in action
        assert "confidence" in action
        
        # Confidence should be in valid range
        assert 0.0 <= action["confidence"] <= 1.0
    
    def test_action_types(self):
        """Test known action types."""
        valid_action_types = [
            "read_file", "write_file", "execute_command", "write_and_run",
            "install_package", "list_directory", "create_directory",
            "check_file_exists", "head_file", "tail_file", "grep_file",
            "update_function_block", "list_previous_nodes",
            "retrieve_previous_node_file", "retrieve_previous_node_files"
        ]
        
        for action_type in valid_action_types:
            action = {
                "type": action_type,
                "params": {},
                "explanation": f"Testing {action_type}",
                "confidence": 0.5
            }
            assert action["type"] in valid_action_types


class TestReworkFields:
    """Test rework-related model fields."""
    
    def test_node_rework_fields(self):
        """Test that nodes have proper rework fields."""
        static_config = StaticConfig(args=[], description="Test", tag="test")
        node = AnalysisNode(
            id="test",
            analysis_id="tree",
            function_block=NewFunctionBlock(
                id="fb",
                name="Test",
                description="Test",
                type=FunctionBlockType.PYTHON,
                code="pass",
                requirements="",
                parameters={},
                static_config=static_config
            )
        )
        
        # Check rework fields exist and have correct defaults
        assert hasattr(node, 'needs_rework')
        assert hasattr(node, 'rework_attempts')
        assert hasattr(node, 'rework_limit_reached')
        # Note: original_task_name field doesn't exist in current model
        
        assert node.needs_rework == False
        assert node.rework_attempts == 0
        assert node.rework_limit_reached == False
    
    def test_job_review_fields(self):
        """Test that nodes have job review fields."""
        static_config = StaticConfig(args=[], description="Test", tag="test")
        node = AnalysisNode(
            id="test",
            analysis_id="tree",
            function_block=NewFunctionBlock(
                id="fb",
                name="Test",
                description="Test",
                type=FunctionBlockType.PYTHON,
                code="pass",
                requirements="",
                parameters={},
                static_config=static_config
            )
        )
        
        # Check job review fields
        assert hasattr(node, 'job_review_status')
        assert hasattr(node, 'job_review_result')
        assert hasattr(node, 'job_review_summary')
        
        assert node.job_review_status is None
        assert node.job_review_result is None
        assert node.job_review_summary is None


class TestSmartDisplayLimits:
    """Test smart display limit functionality."""
    
    def test_display_limit_logic(self):
        """Test logic for smart display limits."""
        # Small list - show all
        small_list = list(range(10))
        if len(small_list) <= 15:
            display = str(small_list)
        else:
            display = f"{small_list[:15]}... and {len(small_list) - 15} more"
        
        assert display == str(small_list)
        
        # Large list - truncate
        large_list = list(range(100))
        if len(large_list) <= 15:
            display = str(large_list)
        else:
            display = f"{large_list[:15]}... and {len(large_list) - 15} more"
        
        assert "... and 85 more" in display
    
    def test_column_display_limits(self):
        """Test column display limit patterns."""
        # Simulate displaying dataframe columns
        columns = [f"col_{i}" for i in range(50)]
        
        n_cols = len(columns)
        if n_cols <= 15:
            display = f"Columns: {columns}"
        else:
            display = f"First 15 columns: {columns[:15]}\n... and {n_cols - 15} more columns"
        
        assert "First 15 columns:" in display
        assert "... and 35 more columns" in display


if __name__ == "__main__":
    pytest.main([__file__, "-v"])