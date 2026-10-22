"""Test to validate InteractiveExecutor node_dir fix."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import tempfile
from unittest.mock import Mock, patch

from job_executors.interactive_executor import InteractiveExecutor
from models import BaseFunctionBlock, FunctionBlockType, NewFunctionBlock, StaticConfig
from utils.docker_utils import DockerManager


def test_interactive_executor_has_node_dir_attribute():
    """Test that InteractiveExecutor properly initializes node_dir attribute."""
    # Create mocks
    mock_docker_manager = Mock(spec=DockerManager)
    mock_docker_manager.client = Mock()
    
    # Create InteractiveExecutor
    executor = InteractiveExecutor(mock_docker_manager)
    
    # Verify node_dir attribute exists and is initialized to None
    assert hasattr(executor, 'node_dir'), "InteractiveExecutor missing node_dir attribute"
    assert executor.node_dir is None, "node_dir should be initialized to None"


def test_execute_with_debugging_uses_node_dir_parameter():
    """Test that execute_with_debugging properly uses node_dir parameter, not instance attribute."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create mocks
        mock_docker_manager = Mock(spec=DockerManager)
        mock_docker_manager.client = Mock()
        mock_bug_fixer = Mock()
        
        # Create InteractiveExecutor
        executor = InteractiveExecutor(mock_docker_manager, bug_fixer=mock_bug_fixer)
        
        # Create a simple function block
        from models import StaticConfig, NewFunctionBlock
        function_block = NewFunctionBlock(
            id="test",
            name="Test Block",
            description="Test function block",
            type=FunctionBlockType.PYTHON,
            code="def run(path_dict, params): pass",
            requirements=[],
            static_config=StaticConfig(
                args=[],
                description="Test function",
                tag="test"
            )
        )
        
        # Create test paths
        input_path = Path(temp_dir) / "input"
        input_path.mkdir(exist_ok=True)
        output_path = Path(temp_dir) / "output"
        node_dir = Path(temp_dir) / "node_test"
        node_dir.mkdir(exist_ok=True)
        
        # Mock the execution to simulate an error that triggers bug fixing
        with patch.object(executor, '_execute_once') as mock_execute:
            # First execution fails, triggering bug fixer
            mock_execute.return_value = Mock(
                success=False,
                error="Test error",
                outputs={},
                metadata={}
            )
            
            # Mock bug fixer to return success after fixing
            mock_bug_fixer.fix_bug.return_value = {
                'success': True,
                'updated_code': "def run(path_dict, params): print('fixed')",
                'error_resolved': True
            }
            
            # Execute with debugging - should not raise AttributeError about node_dir
            try:
                result = executor.execute_with_debugging(
                    function_block=function_block,
                    input_data_path=input_path,
                    output_dir=output_path,
                    node_dir=node_dir,  # Pass node_dir as parameter
                    max_debug_attempts=1
                )
                
                # If we get here without AttributeError, the fix worked
                print("✅ execute_with_debugging completed without node_dir AttributeError")
                
            except AttributeError as e:
                if 'node_dir' in str(e):
                    pytest.fail(f"node_dir AttributeError occurred: {e}")
                else:
                    raise


def test_bug_fixer_attempt_directory_creation():
    """Test that bug fixer attempt directories are created using the node_dir parameter."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create mocks
        mock_docker_manager = Mock(spec=DockerManager)
        mock_docker_manager.client = Mock()
        mock_bug_fixer = Mock()
        
        # Create InteractiveExecutor
        executor = InteractiveExecutor(mock_docker_manager, bug_fixer=mock_bug_fixer)
        
        # Create test paths
        node_dir = Path(temp_dir) / "node_test"
        node_dir.mkdir(exist_ok=True)
        
        # Create a simple function block
        function_block = NewFunctionBlock(
            id="test",
            name="Test Block",
            description="Test function block",
            type=FunctionBlockType.PYTHON,
            code="def run(path_dict, params): raise ValueError('test error')",
            requirements=[]
        )
        
        input_path = Path(temp_dir) / "input"
        input_path.mkdir(exist_ok=True)
        output_path = Path(temp_dir) / "output"
        
        # Mock execution to trigger bug fixing
        with patch.object(executor, '_execute_once') as mock_execute:
            mock_execute.return_value = Mock(
                success=False,
                error="Test error",
                outputs={},
                metadata={}
            )
            
            # Mock fix_bug_in_container to check if directories are created
            original_fix_bug = executor.fix_bug_in_container
            
            def check_bug_fixer_dir(*args, **kwargs):
                # Check if bug_fixer_attempt_dir is passed correctly
                if 'bug_fixer_attempt_dir' in kwargs and kwargs['bug_fixer_attempt_dir']:
                    attempt_dir = kwargs['bug_fixer_attempt_dir']
                    assert attempt_dir.exists(), f"Bug fixer attempt directory not created: {attempt_dir}"
                    assert 'agent_tasks/unified_bug_fixer/attempt_' in str(attempt_dir)
                    print(f"✅ Bug fixer attempt directory created: {attempt_dir}")
                
                # Return mock success
                return {
                    'success': True,
                    'updated_code': "def run(path_dict, params): print('fixed')",
                    'error_resolved': True
                }
            
            with patch.object(executor, 'fix_bug_in_container', side_effect=check_bug_fixer_dir):
                # Execute with debugging
                result = executor.execute_with_debugging(
                    function_block=function_block,
                    input_data_path=input_path,
                    output_dir=output_path,
                    node_dir=node_dir,
                    max_debug_attempts=1
                )
                
                # Verify bug fixer directory structure was created
                agent_tasks_dir = node_dir / "agent_tasks" / "unified_bug_fixer"
                assert agent_tasks_dir.exists(), "agent_tasks/unified_bug_fixer directory not created"


if __name__ == "__main__":
    # Run tests
    test_interactive_executor_has_node_dir_attribute()
    test_execute_with_debugging_uses_node_dir_parameter()
    test_bug_fixer_attempt_directory_creation()
    print("\n✅ All InteractiveExecutor node_dir tests passed!")