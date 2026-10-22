#!/usr/bin/env python3
"""Comprehensive test for bug fixer integration with main agent.

This test validates:
1. Function creator writes to function_block.py
2. Bug fixer reads from function_block.py, fixes it, and writes back
3. Main agent loads the fixed code and re-executes it
4. The fixed code actually runs successfully
"""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from models import (
    AnalysisTree, AnalysisNode, NewFunctionBlock, FunctionBlockType,
    NodeState, StaticConfig, ExecutionResult
)
from agents.main_agent import MainAgent
from agents.unified_bug_fixer import UnifiedBugFixer
from agents.function_creator_agent import FunctionCreatorAgent
from analysis_tree_management.tree_manager import AnalysisTreeManager
from job_executors.executor_manager import ExecutorManager
from utils import setup_logger

logger = setup_logger(__name__)


class MockLLMService:
    """Mock LLM service that returns predefined responses."""
    
    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0
        self.model = "mock-model"
        self.total_cost = 0.0
        self.total_tokens = 0
    
    def invoke(self, messages):
        """Return next response from list."""
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            # If it's a dict with content, return as is
            if isinstance(response, dict) and 'content' in response:
                return response
            # Otherwise wrap in content
            return {"content": response}
        return {"content": "No more responses"}
    
    def chat_completion_json(self, messages, json_schema, temperature=0.7, max_tokens=2000):
        """Return JSON response for orchestrator."""
        return {
            "satisfied": False,
            "reasoning": "Need to create function block",
            "next_actions": [{
                "type": "create_new",
                "name": "test_function",
                "specification": {
                    "name": "test_function",
                    "description": "Test function that will fail first",
                    "task": "Process data with intentional bug"
                }
            }]
        }
    
    def chat_completion_stream(self, messages, temperature=0.7, max_tokens=2000):
        """Return streaming response for bug fixer."""
        # Get next response
        response = self.invoke(messages)
        # Yield it as a stream chunk
        yield response['content']


def create_buggy_code():
    """Create initial buggy code that will fail."""
    return '''def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Read input - this will work
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)
    
    # Intentional bug: accessing non-existent attribute
    result = adata.nonexistent_attribute
    
    # Save output
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
'''


def create_fixed_code():
    """Create fixed code that will succeed."""
    return '''def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Read input
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)
    
    # Fixed: proper processing
    print(f"Processing {adata.n_obs} cells and {adata.n_vars} genes")
    
    # Create output directory
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    
    # Save output
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
    print(f"Saved output to {output_file}")
'''


class TestBugFixerIntegration:
    """Test bug fixer integration with main agent."""
    
    def setup_method(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.input_dir = self.test_dir / "input"
        self.output_dir = self.test_dir / "output"
        self.input_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
        
        # Create test data
        self.create_test_data()
        
    def teardown_method(self):
        """Clean up test environment."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def create_test_data(self):
        """Create a minimal test AnnData file."""
        import scanpy as sc
        import numpy as np
        
        # Create minimal AnnData
        n_obs = 100
        n_vars = 50
        X = np.random.randn(n_obs, n_vars)
        adata = sc.AnnData(X=X)
        adata.obs_names = [f"Cell_{i}" for i in range(n_obs)]
        adata.var_names = [f"Gene_{i}" for i in range(n_vars)]
        
        # Save as _node_anndata.h5ad
        test_file = self.input_dir / "_node_anndata.h5ad"
        adata.write(test_file)
        logger.info(f"Created test data: {test_file}")
    
    @patch('agents.unified_bug_fixer.unified_bug_fixer.UnifiedBugFixer._should_use_research')
    def test_bug_fixer_updates_function_block_py(self, mock_should_research):
        """Test that bug fixer reads and writes to function_block.py."""
        mock_should_research.return_value = False
        
        # Create mock LLM responses
        bug_fix_responses = [
            # Turn 1: List directory
            {"content": json.dumps({
                "type": "list_directory",
                "path": "."
            })},
            # Turn 2: Read the buggy code
            {"content": json.dumps({
                "type": "read_file",
                "path": "function_block.py"
            })},
            # Turn 3: Write fixed code
            {"content": json.dumps({
                "type": "write_file",
                "path": "function_block.py",
                "content": create_fixed_code()
            })},
            # Turn 4: Test the fix
            {"content": json.dumps({
                "type": "execute_command",
                "command": "python -m py_compile function_block.py"
            })},
            # Turn 5: Declare success
            {"content": "The code has been fixed. The AttributeError was resolved by removing the access to nonexistent_attribute."}
        ]
        
        # Create bug fixer with mocked LLM
        mock_llm = MockLLMService(bug_fix_responses)
        bug_fixer = UnifiedBugFixer(
            model_name="mock-model",
            llm_service=mock_llm,
            max_turns=5,
            enable_web_agent=False  # Disable web agent
        )
        
        # Create working directory with buggy code
        working_dir = self.test_dir / "function_block"
        working_dir.mkdir(exist_ok=True)
        
        # Write buggy code to function_block.py (NOT code.py)
        function_block_file = working_dir / "function_block.py"
        function_block_file.write_text(create_buggy_code())
        
        # Create requirements.txt
        requirements_file = working_dir / "requirements.txt"
        requirements_file.write_text("scanpy\nnumpy")
        
        # Run bug fixer
        error_message = "AttributeError: 'AnnData' object has no attribute 'nonexistent_attribute'"
        result = bug_fixer.fix_bug(
            node_name="test_function",
            error_message=error_message,
            working_directory=working_dir,
            attempt_number=1
        )
        
        # Verify results
        assert result['success'] == True, f"Bug fix failed: {result}"
        assert function_block_file.exists(), "function_block.py should exist"
        
        # Check that the code was actually fixed
        fixed_code = function_block_file.read_text()
        assert "nonexistent_attribute" not in fixed_code, "Bug should be removed"
        assert "print(f\"Processing" in fixed_code, "Fixed code should be present"
        
        logger.info("✓ Bug fixer successfully updated function_block.py")
    
    @patch('job_executors.python_executor.PythonExecutor.execute')
    def test_main_agent_executes_fixed_code(self, mock_execute):
        """Test that main agent loads fixed code and re-executes it."""
        
        # Set up execution results
        # First execution fails
        failed_result = ExecutionResult(
            success=False,
            error="AttributeError: 'AnnData' object has no attribute 'nonexistent_attribute'",
            stderr="AttributeError: 'AnnData' object has no attribute 'nonexistent_attribute'",
            stdout="",
            logs="Container completed with code 1\n\nSTDERR:\nAttributeError...",
            exit_code=1
        )
        
        # Second execution succeeds
        success_result = ExecutionResult(
            success=True,
            outputs={"_node_anndata.h5ad": str(self.output_dir / "_node_anndata.h5ad")},
            figures=[],
            logs="Container completed with code 0\n\nSTDOUT:\nProcessing 100 cells...",
            stdout="Processing 100 cells and 50 genes\nSaved output to...",
            stderr="",
            exit_code=0
        )
        
        # Mock executor to return failed then success
        mock_execute.side_effect = [failed_result, success_result]
        
        # Create mock components
        mock_orchestrator = Mock()
        mock_orchestrator.plan_next_steps.return_value = {
            "satisfied": True,
            "next_actions": []
        }
        
        # Mock function creator to write to function_block.py
        mock_function_creator = Mock(spec=FunctionCreatorAgent)
        test_block = NewFunctionBlock(
            name="test_function",
            type=FunctionBlockType.PYTHON,
            description="Test function",
            code=create_buggy_code(),  # Start with buggy code
            requirements="scanpy\nnumpy",
            parameters={},
            static_config=StaticConfig(
                description="Test function",
                tag="test",
                args=[]
            )
        )
        mock_function_creator.create_from_specification.return_value = test_block
        
        # Mock bug fixer to fix the code
        mock_bug_fixer = Mock(spec=UnifiedBugFixer)
        mock_bug_fixer.fix_bug.return_value = {
            'success': True,
            'turn_count': 3,
            'files_modified': ['function_block.py']
        }
        
        # Create main agent with mocks
        main_agent = MainAgent(openai_api_key="mock-key")
        main_agent.orchestrator = mock_orchestrator
        main_agent.function_creator = mock_function_creator
        main_agent.bug_fixer = mock_bug_fixer
        main_agent.bug_fixer_type = "unified"
        
        # Override _save_function_block_to_dir to use function_block.py
        original_save = main_agent._save_function_block_to_dir
        def save_to_function_block_py(block, function_block_dir):
            """Save to function_block.py instead of code.py."""
            # Save as function_block.py
            function_block_file = function_block_dir / "function_block.py"
            function_block_file.write_text(block.code)
            
            # Save config and requirements normally
            config_file = function_block_dir / "config.json"
            config_data = {
                "name": block.name,
                "type": block.type.value,
                "description": block.description,
                "parameters": block.parameters
            }
            with open(config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            requirements_file = function_block_dir / "requirements.txt"
            requirements_file.write_text(block.requirements or "")
        
        main_agent._save_function_block_to_dir = save_to_function_block_py
        
        # Create a mock that simulates fixing the code
        def mock_fix_and_update_file(node_name, error_message, working_directory, attempt_number):
            # Simulate bug fixer updating function_block.py
            function_block_file = working_directory / "function_block.py"
            function_block_file.write_text(create_fixed_code())
            return {
                'success': True,
                'turn_count': 3,
                'files_modified': ['function_block.py']
            }
        
        mock_bug_fixer.fix_bug.side_effect = mock_fix_and_update_file
        
        # Run analysis
        result = main_agent.run_analysis(
            input_data_path=str(self.input_dir / "_node_anndata.h5ad"),
            user_request="Test function execution",
            output_dir=str(self.output_dir),
            max_nodes=1,
            max_debug_trials=1,
            verbose=True
        )
        
        # Verify results
        assert mock_execute.call_count == 2, f"Expected 2 executions, got {mock_execute.call_count}"
        assert result['total_nodes'] == 1, "Should have created 1 node"
        assert result['completed_nodes'] == 1, "Node should complete after fix"
        assert result['failed_nodes'] == 0, "No nodes should remain failed"
        
        # Verify the fixed code was loaded
        # Check that function_block.py exists in the output
        tree_dir = Path(result['output_dir']) / result['tree_id']
        node_dirs = list((tree_dir / 'nodes').glob('node_*'))
        assert len(node_dirs) == 1, "Should have one node directory"
        
        function_block_file = node_dirs[0] / 'function_block' / 'function_block.py'
        assert function_block_file.exists(), "function_block.py should exist"
        
        final_code = function_block_file.read_text()
        assert "nonexistent_attribute" not in final_code, "Buggy code should be replaced"
        assert "Processing" in final_code, "Fixed code should be present"
        
        logger.info("✓ Main agent successfully loaded and executed fixed code")
    
    def test_end_to_end_with_real_execution(self):
        """Test end-to-end execution with real Docker containers."""
        # This test requires Docker to be running
        try:
            import docker
            client = docker.from_env()
            client.ping()
        except Exception as e:
            logger.warning(f"Skipping real execution test - Docker not available: {e}")
            return
        
        # Create main agent with minimal mocking
        mock_llm = MockLLMService([])
        
        # Mock orchestrator to create one function block
        mock_orchestrator = Mock()
        mock_orchestrator.llm_service = mock_llm
        mock_orchestrator.plan_next_steps.side_effect = [
            {
                "satisfied": False,
                "reasoning": "Creating test function",
                "next_actions": [{
                    "type": "create_new",
                    "name": "test_function",
                    "specification": {
                        "name": "test_function",
                        "description": "Test function",
                        "task": "Process data"
                    }
                }]
            },
            {
                "satisfied": True,
                "reasoning": "Task complete",
                "next_actions": []
            }
        ]
        
        # Mock function creator
        mock_function_creator = Mock(spec=FunctionCreatorAgent)
        test_block = NewFunctionBlock(
            name="test_function",
            type=FunctionBlockType.PYTHON,
            description="Test function with bug",
            code=create_buggy_code(),
            requirements="scanpy\nnumpy",
            parameters={},
            static_config=StaticConfig(
                description="Test function",
                tag="test",
                args=[]
            )
        )
        mock_function_creator.create_from_specification.return_value = test_block
        
        # Create real bug fixer with mocked LLM
        bug_fix_responses = [
            {"content": json.dumps({"type": "list_directory", "path": "."})},
            {"content": json.dumps({"type": "read_file", "path": "code.py"})},
            {"content": json.dumps({
                "type": "write_file",
                "path": "code.py",
                "content": create_fixed_code()
            })},
            {"content": json.dumps({
                "type": "execute_command",
                "command": "python -m py_compile code.py"
            })},
            {"content": "Fixed the AttributeError by removing nonexistent_attribute access."}
        ]
        
        mock_bug_llm = MockLLMService(bug_fix_responses)
        bug_fixer = UnifiedBugFixer(
            model_name="mock-model",
            llm_service=mock_bug_llm,
            max_turns=5,
            enable_web_agent=False
        )
        
        # Create main agent
        main_agent = MainAgent(openai_api_key="mock-key")
        main_agent.orchestrator = mock_orchestrator
        main_agent.function_creator = mock_function_creator
        main_agent.bug_fixer = bug_fixer
        main_agent.bug_fixer_type = "unified"
        
        # Run analysis
        result = main_agent.run_analysis(
            input_data_path=str(self.input_dir / "_node_anndata.h5ad"),
            user_request="Test function execution",
            output_dir=str(self.output_dir),
            max_nodes=1,
            max_debug_trials=2,
            verbose=True
        )
        
        # Verify the node completed successfully
        assert result['completed_nodes'] == 1, f"Node should complete, got: {result}"
        assert result['failed_nodes'] == 0, "No nodes should fail"
        
        # Verify output file exists
        tree_dir = Path(result['output_dir']) / result['tree_id']
        node_dirs = list((tree_dir / 'nodes').glob('node_*'))
        output_file = node_dirs[0] / 'outputs' / '_node_anndata.h5ad'
        assert output_file.exists(), "Output file should be created"
        
        logger.info("✓ End-to-end test passed with real execution")


def run_tests():
    """Run all tests."""
    test = TestBugFixerIntegration()
    
    try:
        # Test 1: Bug fixer updates function_block.py
        logger.info("\n=== Test 1: Bug fixer updates function_block.py ===")
        test.setup_method()
        test.test_bug_fixer_updates_function_block_py()
        test.teardown_method()
        
        # Test 2: Main agent executes fixed code
        logger.info("\n=== Test 2: Main agent loads and executes fixed code ===")
        test.setup_method()
        test.test_main_agent_executes_fixed_code()
        test.teardown_method()
        
        # Test 3: End-to-end with real execution
        logger.info("\n=== Test 3: End-to-end with real Docker execution ===")
        test.setup_method()
        test.test_end_to_end_with_real_execution()
        test.teardown_method()
        
        logger.info("\n✅ All tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)