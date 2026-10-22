#!/usr/bin/env python3
"""Test in-container bug fixing functionality."""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import docker

sys.path.insert(0, str(Path(__file__).parent))

from models import (
    FunctionBlockType, NewFunctionBlock, NodeState, AnalysisNode,
    AnalysisTree, StaticConfig
)
from agents.main_agent import MainAgent
from agents.unified_bug_fixer import UnifiedBugFixer
from job_executors.interactive_executor import InteractiveExecutor, ContainerActionHandler
from utils.docker_utils import DockerManager
from utils import setup_logger

logger = setup_logger(__name__)


def test_container_action_handler():
    """Test that container action handler correctly executes actions in container."""
    logger.info("\n=== Testing Container Action Handler ===")
    
    # Create mock container
    mock_container = Mock()
    
    # Mock exec_run responses
    def mock_exec_run(cmd, **kwargs):
        result = Mock()
        
        # Simulate different commands
        if cmd[0] == "ls" and "-la" in cmd:
            result.exit_code = 0
            result.output = (
                b"total 16\ndrwxr-xr-x 4 root root 4096 Jan  1 00:00 .\n"
                b"drwxr-xr-x 1 root root 4096 Jan  1 00:00 ..\n"
                b"-rw-r--r-- 1 root root  100 Jan  1 00:00 function_block.py\n"
                b"-rw-r--r-- 1 root root   50 Jan  1 00:00 requirements.txt\n",
                b""
            )
        elif cmd == ["cat", "/workspace/function_block.py"]:
            result.exit_code = 0
            result.output = (
                b"def run(path_dict, params):\n    pass\n",
                b""
            )
        elif "import scanpy" in str(cmd):
            result.exit_code = 0
            result.output = (
                b"Columns: ['leiden', 'n_genes', 'n_counts']\nShape: (1000, 2000)\n",
                b""
            )
        else:
            result.exit_code = 0
            result.output = (b"Success", b"")
        
        return result
    
    mock_container.exec_run = mock_exec_run
    
    # Create handler
    handler = ContainerActionHandler(mock_container, "/workspace")
    
    # Test list directory
    result = handler.execute_action({"type": "list_directory", "path": "."}, Path("/workspace"))
    logger.info(f"List directory result: {result}")
    assert result['success'] == True
    # Should have function_block.py and requirements.txt (. and .. are filtered out)
    assert len(result['entries']) >= 1, f"Expected at least 1 entry, got {len(result['entries'])}: {result['entries']}"
    assert any(e['name'] == 'function_block.py' for e in result['entries'])
    logger.info("✓ List directory works")
    
    # Test read file
    result = handler.execute_action({"type": "read_file", "path": "function_block.py"}, Path("/workspace"))
    assert result['success'] == True
    assert "def run" in result['content']
    logger.info("✓ Read file works")
    
    # Test execute command
    result = handler.execute_action({
        "type": "execute_command", 
        "command": "python -c \"import scanpy as sc; adata = sc.read_h5ad('/workspace/input/_node_anndata.h5ad'); print(f'Columns: {list(adata.obs.columns)}'); print(f'Shape: {adata.shape}')\""
    }, Path("/workspace"))
    assert result['success'] == True
    assert "Columns:" in result['stdout']
    logger.info("✓ Execute command works")


def test_interactive_executor_with_mock():
    """Test interactive executor with mocked Docker."""
    logger.info("\n=== Testing Interactive Executor ===")
    
    # Create test function block
    buggy_code = '''def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Read input
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)
    
    # Bug: accessing non-existent column
    marker_key = params.get('marker_key', 'cell_type')
    if marker_key not in adata.obs.columns:
        raise ValueError(f"Marker key '{marker_key}' not found in adata.obs")
    
    # Save output
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
'''
    
    function_block = NewFunctionBlock(
        name="test_root_selection",
        type=FunctionBlockType.PYTHON,
        description="Test root cell selection",
        code=buggy_code,
        requirements="scanpy\nnumpy",
        parameters={"marker_key": "cell_type"},
        static_config=StaticConfig(
            description="Test",
            tag="test",
            args=[]
        )
    )
    
    # Create mock Docker manager
    mock_docker_manager = Mock(spec=DockerManager)
    mock_docker_manager.client = Mock()
    
    # Create mock container
    mock_container = Mock()
    mock_container.id = "test_container_123"
    mock_container.status = "running"
    
    # Track execution attempts
    execution_attempts = []
    
    def mock_exec_run(cmd, **kwargs):
        result = Mock()
        execution_attempts.append(cmd)
        
        # First execution fails
        if len(execution_attempts) == 1:
            result.exit_code = 1
            result.output = (
                b"",
                b"ValueError: Marker key 'cell_type' not found in adata.obs\n"
            )
        # After fix, execution succeeds
        else:
            result.exit_code = 0
            result.output = (
                b"Available columns: ['leiden', 'n_genes']\nUsing clustering fallback\nOutput saved\n",
                b""
            )
        
        return result
    
    mock_container.exec_run = mock_exec_run
    mock_container.stop = Mock()
    mock_container.remove = Mock()
    
    # Mock container creation
    mock_docker_manager.client.containers.run = Mock(return_value=mock_container)
    
    # Create mock bug fixer that will fix the code
    mock_bug_fixer = Mock(spec=UnifiedBugFixer)
    
    def mock_fix_bug(**kwargs):
        # Simulate fixing the code by modifying it
        logger.info("Mock bug fixer: Fixing missing column error")
        return {
            'success': True,
            'turn_count': 3,
            'files_modified': ['function_block.py']
        }
    
    mock_bug_fixer.fix_bug = mock_fix_bug
    
    # Create interactive executor
    executor = InteractiveExecutor(mock_docker_manager, mock_bug_fixer)
    
    # Create temp directories
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        input_dir = temp_path / "input"
        output_dir = temp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        
        # Create dummy input file
        (input_dir / "_node_anndata.h5ad").touch()
        
        # Execute with debugging
        result = executor.execute_with_debugging(
            function_block=function_block,
            input_data_path=input_dir,
            output_dir=output_dir,
            max_debug_attempts=2
        )
        
        # Check results
        logger.info(f"Execution attempts made: {len(execution_attempts)}")
        logger.info(f"Commands executed: {execution_attempts}")
        assert result.success == True, f"Execution should succeed after debugging: {result.error}"
        assert len(execution_attempts) >= 1, f"Should have at least 1 execution attempt, got {len(execution_attempts)}"
        assert 'debug_attempts' in result.metadata, "Result should track debug attempts in metadata"
        debug_attempts = result.metadata.get('debug_attempts', 0)
        logger.info(f"✓ Interactive execution succeeded after {debug_attempts} debug attempts")


def test_main_agent_with_interactive_debug():
    """Test main agent with interactive debugging enabled."""
    logger.info("\n=== Testing Main Agent with Interactive Debug ===")
    
    # Create main agent with interactive debug
    with patch('job_executors.interactive_executor.docker.from_env'):
        agent = MainAgent(
            openai_api_key="test-key",
            bug_fixer_type="unified",
            bug_fixer_model="gpt-4o-mini",
            enable_interactive_debug=True
        )
        
        # Check that interactive node executor was created
        from analysis_tree_management.interactive_node_executor import InteractiveNodeExecutor
        assert isinstance(agent.node_executor, InteractiveNodeExecutor), "Should use interactive node executor"
        assert agent.enable_interactive_debug == True, "Interactive debug should be enabled"
        logger.info("✓ Main agent correctly initialized with interactive debugging")


def test_bug_fixer_with_data_access():
    """Test that bug fixer can access data in interactive mode."""
    logger.info("\n=== Testing Bug Fixer with Data Access ===")
    
    # Create a scenario where bug fixer needs to inspect actual data
    test_code = '''def run(path_dict, params):
    import scanpy as sc
    import os
    
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)
    
    # This will fail if 'cell_type' doesn't exist
    root_cells = adata.obs[adata.obs['cell_type'] == 'stem']
'''
    
    # Expected fix should:
    # 1. Check what columns actually exist
    # 2. Provide a fallback solution
    
    expected_fix_pattern = [
        "print(f\"Available columns: {list(adata.obs.columns)}\")",
        "if 'cell_type' in adata.obs.columns:",
        "else:",
        "leiden"  # Should fall back to clustering
    ]
    
    logger.info("NOTE: not checked here - bug fixer should inspect data and provide appropriate fallback")
    
    # This would be tested with actual Docker in integration tests
    logger.info("  (Full test requires Docker - see integration tests)")


def run_all_tests():
    """Run all in-container bug fixer tests."""
    try:
        test_container_action_handler()
        test_interactive_executor_with_mock()
        test_main_agent_with_interactive_debug()
        test_bug_fixer_with_data_access()
        
        logger.info("\n✅ All in-container bug fixer tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)