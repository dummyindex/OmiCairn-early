"""Integration test for structured error logging with mock LLM.

This test demonstrates the error logging system working with MainAgent
without requiring real LLM API calls.
"""

import json
import logging
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockLLMService:
    """Mock LLM service that simulates errors."""
    
    def __init__(self, should_fail=False, fail_on_call=None):
        self.should_fail = should_fail
        self.fail_on_call = fail_on_call
        self.call_count = 0
    
    def chat_completion(self, messages, **kwargs):
        """Mock chat completion that can simulate failures."""
        self.call_count += 1
        
        # Fail on specific call number
        if self.fail_on_call and self.call_count == self.fail_on_call:
            raise ConnectionError("Mock network error")
        
        # Always fail if configured
        if self.should_fail:
            raise ValueError("Mock LLM error")
        
        # Return successful mock response
        return {
            "content": json.dumps({
                "satisfied": False,
                "next_actions": [{
                    "type": "create_function_block",
                    "name": "test_node",
                    "description": "Test node",
                    "parent_id": "root"
                }]
            })
        }


class TestErrorLoggingIntegration:
    """Integration tests for error logging system."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_json_parsing_error_logging(self, temp_dir):
        """Test that JSON parsing errors are properly logged."""
        from agents.unified_bug_fixer.json_parser import JSONParser
        from io import StringIO
        
        # Set up logging to capture errors
        test_logger = logging.getLogger("agents.unified_bug_fixer.json_parser")
        test_logger.setLevel(logging.ERROR)
        
        # Create a string stream handler to capture log messages
        log_capture = StringIO()
        stream_handler = logging.StreamHandler(log_capture)
        stream_handler.setLevel(logging.ERROR)
        test_logger.addHandler(stream_handler)
        
        try:
            # Test with invalid JSON
            invalid_json = "{'not': 'valid json'}"  # Single quotes
            result, error_msg = JSONParser.parse_action(invalid_json)
            
            assert result is None  # Should fail to parse
            assert "Expecting property name" in error_msg  # Check error message
            
            # Check that error was logged
            log_output = log_capture.getvalue()
            assert "JSON parsing failed" in log_output
            assert "Expecting property name" in log_output
            
            # Test with missing type field
            no_type_json = '{"params": {}}'
            result2, error_msg2 = JSONParser.parse_action(no_type_json)
            
            assert result2 is None  # Should fail
            assert "missing required 'type' field" in error_msg2
            
            # Test with non-object JSON
            array_json = '["test"]'
            result3, error_msg3 = JSONParser.parse_action(array_json)
            
            assert result3 is None  # Should fail
            assert "not a JSON object" in error_msg3
            
            print(f"✅ JSON parsing error logging test passed")
            
        finally:
            test_logger.removeHandler(stream_handler)
    
    @patch('agents.main_agent.OrchestratorAgent')
    @patch('agents.main_agent.FunctionCreatorAgent')
    @patch('agents.main_agent.TreeManager')
    def test_main_agent_error_logging(self, mock_tree_manager, mock_function_creator, 
                                     mock_orchestrator, temp_dir):
        """Test MainAgent with structured error logging."""
        from agents.main_agent import MainAgent
        
        # Create test input file
        input_file = temp_dir / "test_input.h5ad"
        input_file.write_text("mock data")
        
        # Mock tree manager
        mock_tree = Mock()
        mock_tree.id = "test_tree_123"
        mock_tree.root_dir = temp_dir / "test_tree"
        mock_tree.root_dir.mkdir(parents=True)
        mock_tree.user_request = "Test request"
        mock_tree.nodes = {}
        mock_tree.get_state_summary = Mock(return_value={
            "total_nodes": 0,
            "completed_nodes": 0,
            "failed_nodes": 0
        })
        
        mock_tree_manager_instance = Mock()
        mock_tree_manager_instance.create_tree = Mock(return_value=mock_tree)
        mock_tree_manager_instance.save_tree = Mock()
        mock_tree_manager.return_value = mock_tree_manager_instance
        
        # Mock orchestrator that returns satisfied
        mock_orchestrator_instance = Mock()
        mock_orchestrator_instance.plan_next_steps = Mock(return_value={
            "satisfied": True,
            "next_actions": []
        })
        mock_orchestrator.return_value = mock_orchestrator_instance
        
        # Create MainAgent with mock LLM
        mock_llm = MockLLMService()
        
        with patch('agents.main_agent.OpenAIService', return_value=mock_llm):
            agent = MainAgent(
                openai_api_key="mock_key",
                bug_fixer_type="unified",
                enable_web_agent=False
            )
            
            # Simulate job reviewer initialization failure
            with patch.object(agent, 'job_reviewer', None):
                # Log an error during initialization
                agent_logger = logging.getLogger("agents.main_agent")
                agent_logger.error("Failed to initialize job reviewer", extra={
                    'error_category': 'initialization',
                    'component': 'job_reviewer',
                    'recovery_hint': 'System will run in degraded mode'
                })
            
            # Run analysis
            result = agent.run_analysis(
                input_data_path=str(input_file),
                user_request="Test analysis",
                output_dir=temp_dir / "output",
                max_iterations=1
            )
            
            # Check error logs were created
            error_logs_dir = mock_tree.root_dir / "error_logs"
            assert error_logs_dir.exists()
            
            # Check session summary exists
            summary_file = error_logs_dir / "session_summary.json"
            assert summary_file.exists()
    
    def test_output_collector_error_logging(self, temp_dir):
        """Test output collector error logging."""
        from agents.output_collector.output_collector import OutputCollector
        from agents.utils.structured_error_handler import StructuredErrorHandler
        
        # Set up error handler
        error_handler = StructuredErrorHandler(temp_dir)
        logging.getLogger().addHandler(error_handler)
        
        try:
            # Create output collector with failing LLM
            mock_llm = MockLLMService(should_fail=True)
            collector = OutputCollector(mock_llm)
            
            # Try to get LLM response (will fail)
            response = collector._get_llm_response([{"role": "user", "content": "test"}])
            
            # Should return error response
            assert response.get("error") is True
            assert "actions" in response
            assert len(response["actions"]) == 0
            
            # Check error was logged
            error_logs = temp_dir / "error_logs"
            detailed_dir = error_logs / "detailed"
            json_files = list(detailed_dir.glob("*llm_communication*.json"))
            assert len(json_files) > 0
            
            # Check error content
            with open(json_files[0]) as f:
                error_record = json.load(f)
            
            assert error_record["error_category"] == "llm_communication"
            assert error_record["agent_type"] == "output_collector"
            assert "exception" in error_record
            
        finally:
            logging.getLogger().removeHandler(error_handler)
            error_handler.close()
    
    def test_concurrent_error_logging(self, temp_dir):
        """Test that concurrent errors are properly handled."""
        import threading
        from agents.utils.structured_error_handler import StructuredErrorHandler
        
        # Set up error handler
        error_handler = StructuredErrorHandler(temp_dir)
        test_logger = logging.getLogger("test.concurrent")
        test_logger.addHandler(error_handler)
        
        errors_logged = []
        
        def simulate_errors(thread_id):
            """Simulate errors from different components."""
            for i in range(5):
                if i % 2 == 0:
                    test_logger.error(f"JSON parsing error from thread {thread_id}", extra={
                        'error_category': 'json_parsing',
                        'node_id': f'node_{thread_id}_{i}'
                    })
                else:
                    test_logger.error(f"LLM error from thread {thread_id}", extra={
                        'error_category': 'llm_communication',
                        'node_id': f'node_{thread_id}_{i}'
                    })
                errors_logged.append((thread_id, i))
        
        # Create threads
        threads = []
        for tid in range(3):
            t = threading.Thread(target=simulate_errors, args=(tid,))
            threads.append(t)
            t.start()
        
        # Wait for completion
        for t in threads:
            t.join()
        
        # Check all errors were logged
        error_logs = temp_dir / "error_logs"
        detailed_dir = error_logs / "detailed"
        json_files = list(detailed_dir.glob("*.json"))
        assert len(json_files) == 15  # 3 threads * 5 errors each
        
        # Check summary
        summary_file = error_logs / "session_summary.json"
        with open(summary_file) as f:
            summary = json.load(f)
        
        assert summary["total_errors"] == 15
        assert summary["by_category"]["json_parsing"] == 9  # 3 threads * 3 even iterations
        assert summary["by_category"]["llm_communication"] == 6  # 3 threads * 2 odd iterations
        
        error_handler.close()
    
    def test_error_recovery_hints(self, temp_dir):
        """Test that recovery hints are properly logged."""
        from agents.utils.structured_error_handler import StructuredErrorHandler
        
        error_handler = StructuredErrorHandler(temp_dir)
        test_logger = logging.getLogger("test.recovery")
        test_logger.addHandler(error_handler)
        
        # Log errors with different recovery hints
        test_logger.error("API key invalid", extra={
            'error_category': 'authentication',
            'recovery_hint': 'Check your API key configuration in environment variables'
        })
        
        test_logger.error("Network timeout", extra={
            'error_category': 'network',
            'recovery_hint': 'This is a temporary issue. Please retry the operation.'
        })
        
        test_logger.error("JSON malformed", extra={
            'error_category': 'json_parsing',
            'recovery_hint': 'Review the LLM prompt to ensure it generates valid JSON'
        })
        
        # Check recovery hints are saved
        error_logs = temp_dir / "error_logs"
        detailed_dir = error_logs / "detailed"
        
        for json_file in detailed_dir.glob("*.json"):
            with open(json_file) as f:
                error_record = json.load(f)
            assert "recovery_hint" in error_record
            assert len(error_record["recovery_hint"]) > 0
        
        error_handler.close()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])