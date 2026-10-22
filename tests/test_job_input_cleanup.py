#!/usr/bin/env python3
"""Test job input directory cleanup functionality.

This test ensures that job input directories (including previous_nodes) are 
properly cleaned up after node execution, regardless of success or failure.
"""

import tempfile
import shutil
from pathlib import Path
import json
import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (
    AnalysisTree, AnalysisNode, NewFunctionBlock, FunctionBlockType, 
    ExecutionResult, NodeState
)
from analysis_tree_management.interactive_node_executor import InteractiveNodeExecutor
from job_executors.executor_manager import ExecutorManager
from utils.logger import setup_logger

logger = setup_logger(__name__)


class TestJobInputCleanup(unittest.TestCase):
    """Test suite for job input directory cleanup in InteractiveNodeExecutor."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_job_input_cleanup_"))
        self.tree_dir = self.test_dir / "tree"
        self.tree_dir.mkdir()
        self.nodes_dir = self.tree_dir / "nodes"
        self.nodes_dir.mkdir()
        
        # Create test tree
        self.tree = AnalysisTree(
            name="Test Tree",
            description="Test job input cleanup",
            user_request="Test request",
            input_data_path="test_input.txt",
            max_nodes=10,
            max_children_per_node=3,
            max_debug_trials=3
        )
        
        # Create test input file
        self.input_file = self.test_dir / "test_input.txt"
        self.input_file.write_text("test data")
        
        # Create test node
        self.node = AnalysisNode(
            id="test_node_001",
            analysis_id="test_analysis",
            function_block=NewFunctionBlock(
                id="fb_001",
                name="test_function",
                description="Test function",
                type=FunctionBlockType.PYTHON,
                code='def run(path_dict, params):\n    print("test")\n    return {}',
                requirements="",
                parameters={},
                static_config={
                    "args": [],
                    "description": "Test",
                    "tag": "test"
                }
            )
        )
        self.tree.add_node(self.node)
        
        # Create node directory structure
        self.node_dir = self.nodes_dir / f"node_{self.node.id}"
        self.node_dir.mkdir(parents=True)
        
        # Mock executor manager
        self.mock_executor_manager = Mock(spec=ExecutorManager)
        self.mock_executor_manager.docker_manager = Mock()
        
    def tearDown(self):
        """Clean up test fixtures."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def _create_job_input_directory(self, job_dir: Path, size_mb: float = 10):
        """Create a job input directory with test files including previous_nodes.
        
        Args:
            job_dir: The job directory path
            size_mb: Approximate size in MB to create
        """
        job_input_dir = job_dir / "input"
        job_input_dir.mkdir(parents=True, exist_ok=True)
        
        # Create main input files
        test_file = job_input_dir / "test_input.txt"
        test_file.write_text("test" * 100)
        
        # Create previous_nodes directory with simulated data
        prev_nodes_dir = job_input_dir / "previous_nodes"
        prev_nodes_dir.mkdir(exist_ok=True)
        
        # Create multiple node directories with files
        for i in range(1, 4):
            node_dir = prev_nodes_dir / f"node_{i}"
            node_outputs = node_dir / "outputs"
            node_outputs.mkdir(parents=True)
            
            # Create a large file to simulate real data
            large_file = node_outputs / f"data_{i}.h5ad"
            # Create approximately size_mb/3 MB per node
            file_size = int((size_mb * 1024 * 1024) / 3)
            large_file.write_bytes(b"x" * file_size)
        
        # Create previous_nodes_index.json
        index_file = job_input_dir / "previous_nodes_index.json"
        index_data = {
            "1": {"node_id": "node_001", "node_name": "test1"},
            "2": {"node_id": "node_002", "node_name": "test2"},
            "3": {"node_id": "node_003", "node_name": "test3"}
        }
        index_file.write_text(json.dumps(index_data, indent=2))
        
        return job_input_dir
    
    def test_cleanup_on_successful_execution(self):
        """Test that job input directory is cleaned up after successful execution."""
        logger.info("Testing cleanup on successful execution")
        
        # Create executor with cleanup enabled
        executor = InteractiveNodeExecutor(
            executor_manager=self.mock_executor_manager,
            bug_fixer=None,
            enable_interactive_debug=False,
            cleanup_job_dirs=True  # Enable cleanup
        )
        
        # Mock successful execution result
        success_result = ExecutionResult(
            success=True,
            output_data_path=str(self.node_dir / "outputs"),
            logs="Success",
            duration=1.0
        )
        
        # Track if rmtree was called on job input directory
        cleanup_called = False
        original_rmtree = shutil.rmtree
        
        def mock_rmtree(path, *args, **kwargs):
            nonlocal cleanup_called
            if Path(path).name == "input" and Path(path).parent.name.startswith("job_"):
                cleanup_called = True
                logger.info(f"Cleanup called for: {path}")
            return original_rmtree(path, *args, **kwargs)
        
        # Patch the executor's execute method to return success and rmtree to track cleanup
        with patch.object(self.mock_executor_manager, 'execute', return_value=success_result), \
             patch('analysis_tree_management.interactive_node_executor.shutil.rmtree', side_effect=mock_rmtree):
            
            # Execute node
            state, output, result = executor.execute_node(
                node=self.node,
                tree=self.tree,
                input_path=self.input_file,
                output_base_dir=self.tree_dir,
                max_debug_attempts=0
            )
            
            # Verify execution succeeded
            self.assertEqual(state, NodeState.COMPLETED, "Node should complete successfully")
            self.assertTrue(result.success, "Result should indicate success")
            
            # Verify cleanup was called
            self.assertTrue(cleanup_called, 
                           "rmtree should be called on job input directory after successful execution")
            
            logger.info("✓ Job input directory cleanup called after successful execution")
    
    def test_cleanup_on_failed_execution(self):
        """Test that job input directory is cleaned up after failed execution."""
        logger.info("Testing cleanup on failed execution")
        
        # Create executor with cleanup enabled
        executor = InteractiveNodeExecutor(
            executor_manager=self.mock_executor_manager,
            bug_fixer=None,
            enable_interactive_debug=False,
            cleanup_job_dirs=True  # Enable cleanup
        )
        
        # Mock failed execution result
        failed_result = ExecutionResult(
            success=False,
            error="Test failure",
            logs="Error occurred",
            duration=1.0,
            exit_code=1
        )
        
        # Track if rmtree was called on job input directory
        cleanup_called = False
        original_rmtree = shutil.rmtree
        
        def mock_rmtree(path, *args, **kwargs):
            nonlocal cleanup_called
            if Path(path).name == "input" and Path(path).parent.name.startswith("job_"):
                cleanup_called = True
                logger.info(f"Cleanup called for failed node: {path}")
            return original_rmtree(path, *args, **kwargs)
        
        # Patch the executor's execute method to return failure and rmtree to track cleanup
        with patch.object(self.mock_executor_manager, 'execute', return_value=failed_result), \
             patch('analysis_tree_management.interactive_node_executor.shutil.rmtree', side_effect=mock_rmtree):
            
            # Execute node
            state, error, result = executor.execute_node(
                node=self.node,
                tree=self.tree,
                input_path=self.input_file,
                output_base_dir=self.tree_dir,
                max_debug_attempts=0
            )
            
            # Verify execution failed
            self.assertEqual(state, NodeState.FAILED, "Node should fail")
            self.assertFalse(result.success, "Result should indicate failure")
            self.assertEqual(result.error, "Test failure", "Error should be preserved")
            
            # Verify cleanup was called despite failure
            self.assertTrue(cleanup_called, 
                           "rmtree should be called on job input directory after failed execution")
            
            logger.info("✓ Job input directory cleanup called after failed execution")
    
    def test_cleanup_on_exception(self):
        """Test that job input directory is cleaned up even when exceptions occur."""
        logger.info("Testing cleanup on exception")
        
        # Create executor with cleanup enabled
        executor = InteractiveNodeExecutor(
            executor_manager=self.mock_executor_manager,
            bug_fixer=None,
            enable_interactive_debug=False,
            cleanup_job_dirs=True  # Enable cleanup
        )
        
        # Track if rmtree was called on job input directory
        cleanup_called = False
        original_rmtree = shutil.rmtree
        
        def mock_rmtree(path, *args, **kwargs):
            nonlocal cleanup_called
            if Path(path).name == "input" and Path(path).parent.name.startswith("job_"):
                cleanup_called = True
                logger.info(f"Cleanup called after exception: {path}")
            return original_rmtree(path, *args, **kwargs)
        
        # Patch the executor's execute method to raise an exception and rmtree to track cleanup
        with patch.object(self.mock_executor_manager, 'execute', 
                         side_effect=Exception("Unexpected error")), \
             patch('analysis_tree_management.interactive_node_executor.shutil.rmtree', side_effect=mock_rmtree):
            
            # Execute node (will raise exception)
            state, error, result = executor.execute_node(
                node=self.node,
                tree=self.tree,
                input_path=self.input_file,
                output_base_dir=self.tree_dir,
                max_debug_attempts=0
            )
            
            # Verify execution failed with exception
            self.assertEqual(state, NodeState.FAILED, "Node should fail on exception")
            self.assertIsNone(result, "Result should be None on exception")
            self.assertIn("Unexpected error", error, "Error message should be preserved")
            
            # Verify cleanup was called despite exception
            self.assertTrue(cleanup_called, 
                           "rmtree should be called on job input directory after exception")
            
            logger.info("✓ Job input directory cleanup called after exception")
    
    def test_no_cleanup_when_disabled(self):
        """Test that job input directory is NOT cleaned when cleanup is disabled."""
        logger.info("Testing no cleanup when disabled")
        
        # Create executor with cleanup DISABLED
        executor = InteractiveNodeExecutor(
            executor_manager=self.mock_executor_manager,
            bug_fixer=None,
            enable_interactive_debug=False,
            cleanup_job_dirs=False  # Disable cleanup
        )
        
        # Mock successful execution
        success_result = ExecutionResult(
            success=True,
            output_data_path=str(self.node_dir / "outputs"),
            logs="Success",
            duration=1.0
        )
        
        with patch.object(self.mock_executor_manager, 'execute', return_value=success_result):
            # Create job directory and input files
            job_dir = self.node_dir / "jobs" / "job_test_004"
            job_dir.mkdir(parents=True)
            job_input_dir = self._create_job_input_directory(job_dir)
            
            # Execute node
            state, output, result = executor.execute_node(
                node=self.node,
                tree=self.tree,
                input_path=self.input_file,
                output_base_dir=self.tree_dir,
                max_debug_attempts=0
            )
            
            # Verify execution succeeded
            self.assertEqual(state, NodeState.COMPLETED, "Node should complete successfully")
            
            # Verify input directory was NOT cleaned up
            self.assertTrue(job_input_dir.exists(), 
                          "Job input directory should NOT be deleted when cleanup is disabled")
            
            # Verify previous_nodes still exists
            prev_nodes_dir = job_input_dir / "previous_nodes"
            self.assertTrue(prev_nodes_dir.exists(), "previous_nodes should be preserved")
            
            logger.info("✓ Job input directory preserved when cleanup is disabled")
    
    def test_cleanup_handles_missing_directory(self):
        """Test that cleanup handles gracefully when input directory doesn't exist."""
        logger.info("Testing cleanup with missing input directory")
        
        executor = InteractiveNodeExecutor(
            executor_manager=self.mock_executor_manager,
            bug_fixer=None,
            enable_interactive_debug=False,
            cleanup_job_dirs=True
        )
        
        success_result = ExecutionResult(
            success=True,
            output_data_path=str(self.node_dir / "outputs"),
            logs="Success",
            duration=1.0
        )
        
        with patch.object(self.mock_executor_manager, 'execute', return_value=success_result):
            # Create job directory but NO input directory
            job_dir = self.node_dir / "jobs" / "job_test_005"
            job_dir.mkdir(parents=True)
            
            # Execute node (should not crash even though input dir doesn't exist)
            state, output, result = executor.execute_node(
                node=self.node,
                tree=self.tree,
                input_path=self.input_file,
                output_base_dir=self.tree_dir,
                max_debug_attempts=0
            )
            
            # Should complete successfully without errors
            self.assertEqual(state, NodeState.COMPLETED, 
                           "Node should complete even if input dir doesn't exist")
            
            logger.info("✓ Cleanup handled missing input directory gracefully")
    
    def test_cleanup_size_calculation(self):
        """Test that cleanup correctly calculates and logs freed space."""
        logger.info("Testing cleanup size calculation")
        
        # Use a mock logger to capture log messages
        with patch('analysis_tree_management.interactive_node_executor.logger') as mock_logger:
            executor = InteractiveNodeExecutor(
                executor_manager=self.mock_executor_manager,
                bug_fixer=None,
                enable_interactive_debug=False,
                cleanup_job_dirs=True
            )
            
            success_result = ExecutionResult(
                success=True,
                output_data_path=str(self.node_dir / "outputs"),
                logs="Success",
                duration=1.0
            )
            
            with patch.object(self.mock_executor_manager, 'execute', return_value=success_result):
                # Create job directory with known size
                job_dir = self.node_dir / "jobs" / "job_test_006"
                job_dir.mkdir(parents=True)
                job_input_dir = self._create_job_input_directory(job_dir, size_mb=50)
                
                # Execute node
                executor.execute_node(
                    node=self.node,
                    tree=self.tree,
                    input_path=self.input_file,
                    output_base_dir=self.tree_dir,
                    max_debug_attempts=0
                )
                
                # Check that size was logged correctly
                # Find the cleanup log message
                cleanup_logged = False
                for call in mock_logger.info.call_args_list:
                    if call[0][0] and "Cleaned up job input directory" in str(call[0][0]):
                        message = str(call[0][0])
                        # Should mention freed space
                        self.assertIn("freed", message)
                        self.assertIn("MB", message)
                        # Should mention it was after successful execution
                        self.assertIn("successful", message)
                        cleanup_logged = True
                        logger.info(f"Cleanup log message: {message}")
                        break
                
                self.assertTrue(cleanup_logged, "Cleanup should log the freed space")
                
        logger.info("✓ Cleanup size calculation and logging works correctly")


def run_tests():
    """Run all tests and return results."""
    # Set up test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestJobInputCleanup)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("TESTING JOB INPUT DIRECTORY CLEANUP")
    logger.info("=" * 80)
    
    success = run_tests()
    
    if success:
        logger.info("\n" + "=" * 80)
        logger.info("ALL TESTS PASSED ✓")
        logger.info("=" * 80)
        sys.exit(0)
    else:
        logger.error("\n" + "=" * 80)
        logger.error("SOME TESTS FAILED ✗")
        logger.error("=" * 80)
        sys.exit(1)