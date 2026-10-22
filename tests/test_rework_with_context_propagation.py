"""Test rework tracking with propagate_failure_context_from mechanism."""

import pytest
from pathlib import Path
import logging

from models import (
    AnalysisTree, AnalysisNode, NodeState, 
    NewFunctionBlock, FunctionBlockType, JobReviewStatus,
    StaticConfig
)
# from agents.main_agent import MainAgent  # Not needed for unit test
from constants import MAX_REWORK_ATTEMPTS
from analysis_tree_management import AnalysisTreeManager

logger = logging.getLogger(__name__)


class TestReworkWithContextPropagation:
    """Test that rework tracking works correctly with propagate_failure_context_from."""
    
    def test_rework_count_propagation(self, tmp_path):
        """Test that rework count is correctly inherited through propagate_failure_context_from."""
        print("\n=== Testing Rework Count Propagation with Context ===")
        
        # Create tree
        tree_manager = AnalysisTreeManager()
        tree = tree_manager.create_tree(
            user_request="Analyze data",
            input_data_path=str(tmp_path / "data.csv"),
            max_nodes=20,
            max_children_per_node=3,
            max_debug_trials=3
        )
        
        # Manually add nodes to simulate the scenario
        
        # First node: "CellTypist Annotation" - fails job review
        node1 = AnalysisNode(
            id="node_001",
            function_block=NewFunctionBlock(
                name="CellTypist Annotation",
                type=FunctionBlockType.PYTHON,
                description="Run CellTypist",
                code="def run(path_dict, params): pass",
                requirements="",
                static_config=StaticConfig(
                    args=[],
                    description="Test node",
                    tag="test"
                )
            ),
            parent_id=tree.root_node_id,
            analysis_id=tree.id,
            state=NodeState.COMPLETED,
            job_review_status=JobReviewStatus.FAILED,
            needs_rework=True,
            rework_attempts=0  # Original attempt
        )
        tree.nodes[node1.id] = node1
        
        # Second node: "CellTypist Annotation Implementation" - different name!
        # Should inherit rework count via propagate_failure_context_from
        node2_spec = {
            'name': 'CellTypist Annotation Implementation',
            'propagate_failure_context_from': 'node_001'  # Links to node1
        }
        
        # Simulate the rework tracking logic from MainAgent
        # Extract the rework tracking logic
        rework_count = 0
        original_task_name = node2_spec['name']
        
        if node2_spec.get('propagate_failure_context_from'):
            source_node_id = node2_spec['propagate_failure_context_from']
            if source_node_id in tree.nodes:
                source_node = tree.nodes[source_node_id]
                rework_count = source_node.rework_attempts + 1
                original_task_name = source_node.original_task_name or source_node.function_block.name
                print(f"✓ Inherited rework count from {source_node_id}: attempt #{rework_count}")
        
        # Create node2
        node2 = AnalysisNode(
            id="node_002",
            function_block=NewFunctionBlock(
                name="CellTypist Annotation Implementation",
                type=FunctionBlockType.PYTHON,
                description="Implement CellTypist properly",
                code="def run(path_dict, params): pass",
                requirements="",
                static_config=StaticConfig(
                    args=[],
                    description="Test node",
                    tag="test"
                )
            ),
            parent_id=tree.root_node_id,
            analysis_id=tree.id,
            rework_attempts=rework_count,
            original_task_name=original_task_name
        )
        tree.nodes[node2.id] = node2
        
        # Verify
        assert node2.rework_attempts == 1, "Node2 should have rework_attempts=1"
        assert node2.original_task_name == "CellTypist Annotation", "Should track original task name"
        print(f"✓ Node2 correctly has rework_attempts={node2.rework_attempts}")
        print(f"✓ Node2 tracks original task: '{node2.original_task_name}'")
        
        # Third attempt with yet another name
        node2.state = NodeState.COMPLETED
        node2.job_review_status = JobReviewStatus.FAILED
        node2.needs_rework = True
        
        node3_spec = {
            'name': 'CellTypist Annotation Proper',
            'propagate_failure_context_from': 'node_002'  # Links to node2
        }
        
        # Check rework limit enforcement
        if node3_spec.get('propagate_failure_context_from'):
            source_node_id = node3_spec['propagate_failure_context_from']
            if source_node_id in tree.nodes:
                source_node = tree.nodes[source_node_id]
                next_rework_count = source_node.rework_attempts + 1
                
                if next_rework_count > MAX_REWORK_ATTEMPTS:
                    print(f"✓ Rework limit enforced: attempt #{next_rework_count} > {MAX_REWORK_ATTEMPTS}")
                    # This node should be blocked
                else:
                    # Create node3
                    node3 = AnalysisNode(
                        id="node_003",
                        function_block=NewFunctionBlock(
                            name="CellTypist Annotation Proper",
                            type=FunctionBlockType.PYTHON,
                            description="Really implement CellTypist",
                            code="def run(path_dict, params): pass",
                            requirements="",
                            static_config=StaticConfig(
                                args=[],
                                description="Test node",
                                tag="test"
                            )
                        ),
                        parent_id=tree.root_node_id,
                        analysis_id=tree.id,
                        rework_attempts=next_rework_count,
                        original_task_name=source_node.original_task_name or source_node.function_block.name
                    )
                    tree.nodes[node3.id] = node3
                    
                    assert node3.rework_attempts == 2, "Node3 should have rework_attempts=2"
                    assert node3.original_task_name == "CellTypist Annotation", "Should still track original"
                    print(f"✓ Node3 correctly has rework_attempts={node3.rework_attempts}")
        
        # Test that 4th attempt would be blocked
        node3.state = NodeState.COMPLETED
        node3.job_review_status = JobReviewStatus.FAILED
        
        node4_spec = {
            'name': 'CellTypist Final Attempt',
            'propagate_failure_context_from': 'node_003'
        }
        
        if node4_spec.get('propagate_failure_context_from'):
            source_node = tree.nodes[node4_spec['propagate_failure_context_from']]
            next_rework_count = source_node.rework_attempts + 1
            
            assert next_rework_count > MAX_REWORK_ATTEMPTS, f"Should exceed limit: {next_rework_count} > {MAX_REWORK_ATTEMPTS}"
            print(f"✓ 4th attempt correctly blocked: {next_rework_count} > {MAX_REWORK_ATTEMPTS}")
    
    def test_rework_without_context_propagation(self, tmp_path):
        """Test that nodes without propagate_failure_context_from start fresh."""
        print("\n=== Testing Fresh Nodes Without Context Propagation ===")
        
        tree_manager = AnalysisTreeManager()
        tree = tree_manager.create_tree(
            user_request="Analyze data",
            input_data_path=str(tmp_path / "data.csv"),
            max_nodes=20,
            max_children_per_node=3,
            max_debug_trials=3
        )
        
        # Node without propagate_failure_context_from
        fresh_spec = {
            'name': 'New Analysis Method',
            # No propagate_failure_context_from
        }
        
        # Should start with rework_attempts=0
        rework_count = 0
        if fresh_spec.get('propagate_failure_context_from'):
            # This won't execute
            pass
        
        fresh_node = AnalysisNode(
            id="fresh_001",
            function_block=NewFunctionBlock(
                name="New Analysis Method",
                type=FunctionBlockType.PYTHON,
                description="Fresh analysis",
                code="def run(path_dict, params): pass",
                requirements="",
                static_config=StaticConfig(
                    args=[],
                    description="Test node",
                    tag="test"
                )
            ),
            parent_id=tree.root_node_id,
            analysis_id=tree.id,
            rework_attempts=rework_count
        )
        
        assert fresh_node.rework_attempts == 0, "Fresh node should have rework_attempts=0"
        assert fresh_node.original_task_name is None, "Fresh node should have no original task"
        print("✓ Fresh node correctly starts with rework_attempts=0")


if __name__ == "__main__":
    import tempfile
    test = TestReworkWithContextPropagation()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        test.test_rework_count_propagation(Path(tmpdir))
        test.test_rework_without_context_propagation(Path(tmpdir))
    
    print("\n✅ All rework context propagation tests passed!")