#!/usr/bin/env python3
"""Test that bug fixer includes action results in subsequent LLM calls."""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add the omicairn_agent_local directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.unified_bug_fixer.enhanced_debug_session import EnhancedDebugSession
from agents.unified_bug_fixer.action_executor import ActionExecutor
from agents.unified_bug_fixer.error_tracker import ErrorTracker
from llm_service.openai_service import OpenAIService


class TestBugFixerActionResults:
    """Test that action results are properly included in LLM input for subsequent turns."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_dir = Path(self.temp_dir) / "logs"
        self.log_dir.mkdir(exist_ok=True)
        
        # Mock OpenAI service
        self.mock_llm_service = Mock(spec=OpenAIService)
        
        # Mock action executor  
        self.mock_action_executor = Mock(spec=ActionExecutor)
        
        # Create debug session
        self.debug_session = EnhancedDebugSession(
            action_executor=self.mock_action_executor,
            llm_service=self.mock_llm_service,
            max_turns=3,
            node_dir=self.log_dir
        )
        
        # The debug session will create its own error tracker
    
    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_action_results_included_in_subsequent_llm_calls(self):
        """Test that action results from turn N are included in LLM input for turn N+1."""
        
        # Mock LLM responses for multiple turns
        llm_responses = [
            # Turn 1: LLM requests read_file action
            Mock(choices=[Mock(message=Mock(content=json.dumps({
                "analysis": "I need to read the file to understand the error",
                "action": {
                    "type": "read_file",
                    "path": "function_block.py"
                }
            })))]),
            
            # Turn 2: LLM requests execute_command based on file content
            Mock(choices=[Mock(message=Mock(content=json.dumps({
                "analysis": "I can see the file content, now I need to test the function",
                "action": {
                    "type": "execute_command",
                    "command": "python -c 'print(\"testing\")'"
                }
            })))]),
            
            # Turn 3: LLM analyzes results and provides fix
            Mock(choices=[Mock(message=Mock(content=json.dumps({
                "analysis": "Based on the previous results, I can fix the issue",
                "action": {
                    "type": "update_function_block",
                    "code": "def run(path_dict, params): pass"
                }
            })))])
        ]
        self.mock_llm_service.chat_completion.side_effect = llm_responses
        
        # Mock action handler results
        action_results = [
            # read_file result
            {
                "success": True,
                "result": "def run(path_dict, params):\n    import pandas as pd\n    # Missing import causes error",
                "error": None
            },
            
            # execute_command result  
            {
                "success": True,
                "result": "testing\n",
                "error": None
            },
            
            # update_function_block result
            {
                "success": True,
                "result": "Function updated successfully",
                "error": None
            }
        ]
        self.mock_action_executor.execute_action.side_effect = action_results
        
        # The debug session will manage error tracking automatically
        
        # Run the debug session
        initial_error = "ImportError: No module named 'pandas'"
        result = self.debug_session.debug(
            error_message=initial_error,
            node_name="test_node",
            stdout="",
            stderr=initial_error,
            attempt_number=1,
            previous_attempts=None,
            node_description="Test node for pandas import"
        )
        
        # Verify that LLM was called 3 times
        assert self.mock_llm_service.chat_completion.call_count == 3
        
        # Get all LLM call arguments
        llm_calls = self.mock_llm_service.chat_completion.call_args_list
        
        # Verify Turn 1: No previous action results (first turn)
        turn1_messages = llm_calls[0][1]['messages']
        turn1_content = next(msg['content'] for msg in turn1_messages if msg['role'] == 'user')
        
        # Turn 1 should not contain action results (it's the first turn)
        assert "## Actions Performed" not in turn1_content
        assert initial_error in turn1_content
        
        # Verify Turn 2: Should include action results from Turn 1
        turn2_messages = llm_calls[1][1]['messages']
        turn2_content = next(msg['content'] for msg in turn2_messages if msg['role'] == 'user')
        
        # Turn 2 should contain action results from Turn 1
        assert "## Actions Performed" in turn2_content
        assert "read_file" in turn2_content
        assert "def run(path_dict, params)" in turn2_content  # Result from read_file
        assert "✅ SUCCESS" in turn2_content  # Success indicator
        
        # Verify Turn 3: Should include action results from Turn 1 and Turn 2
        turn3_messages = llm_calls[2][1]['messages']
        turn3_content = next(msg['content'] for msg in turn3_messages if msg['role'] == 'user')
        
        # Turn 3 should contain action results from both previous turns
        assert "## Actions Performed" in turn3_content
        assert "read_file" in turn3_content  # From Turn 1
        assert "execute_command" in turn3_content  # From Turn 2
        assert "testing" in turn3_content  # Result from execute_command
        assert turn3_content.count("✅ SUCCESS") >= 2  # At least 2 successful actions
        
        # Verify the bug was resolved
        assert result["resolved"] == True
        assert result["turns_taken"] == 3
    
    def test_action_failure_results_included_in_llm_input(self):
        """Test that failed action results are also included in subsequent LLM calls."""
        
        # Mock LLM responses
        llm_responses = [
            # Turn 1: LLM requests execute_command that will fail
            Mock(choices=[Mock(message=Mock(content=json.dumps({
                "analysis": "Let me try to run a command",
                "action": {
                    "type": "execute_command",
                    "command": "invalid_command_that_fails"
                }
            })))]),
            
            # Turn 2: LLM analyzes the failure and tries different approach
            Mock(choices=[Mock(message=Mock(content=json.dumps({
                "analysis": "The previous command failed, let me try a different approach",
                "action": {
                    "type": "read_file",
                    "path": "function_block.py"
                }
            })))])
        ]
        self.mock_llm_service.chat_completion.side_effect = llm_responses
        
        # Mock action handler results - first action fails, second succeeds
        action_results = [
            # execute_command failure
            {
                "success": False,
                "result": "",
                "error": "Command 'invalid_command_that_fails' not found"
            },
            
            # read_file success
            {
                "success": True,
                "result": "def run(path_dict, params): pass",
                "error": None
            }
        ]
        self.mock_action_executor.execute_action.side_effect = action_results
        
        # The debug session will manage error tracking automatically
        
        # Run the debug session
        initial_error = "Some error occurred"
        result = self.debug_session.debug(
            error_message=initial_error,
            node_name="test_node",
            stdout="",
            stderr=initial_error,
            attempt_number=1,
            previous_attempts=None,
            node_description="Test node"
        )
        
        # Verify that LLM was called 2 times  
        assert self.mock_llm_service.chat_completion.call_count == 2
        
        # Get all LLM call arguments
        llm_calls = self.mock_llm_service.chat_completion.call_args_list
        
        # Verify Turn 2: Should include the failed action result from Turn 1
        turn2_messages = llm_calls[1][1]['messages']
        turn2_content = next(msg['content'] for msg in turn2_messages if msg['role'] == 'user')
        
        # Turn 2 should contain the failed action result from Turn 1
        assert "## Actions Performed" in turn2_content
        assert "execute_command" in turn2_content
        assert "invalid_command_that_fails" in turn2_content
        assert "❌ FAILED" in turn2_content  # Failure indicator
        assert "Command 'invalid_command_that_fails' not found" in turn2_content  # Error message
    
    def test_message_timing_bug_scenario(self):
        """Test the specific bug scenario where messages are captured before action results are added."""
        
        # This test simulates the bug described in the issue:
        # 1. Messages are captured for LLM input (line 169 in enhanced_debug_session.py)
        # 2. LLM is called with these messages
        # 3. Action results are added to conversation AFTER the LLM call (line 239)
        # 4. Next turn should see the action results from previous turn
        
        # Mock LLM responses
        llm_responses = [
            Mock(choices=[Mock(message=Mock(content=json.dumps({
                "analysis": "I need to read the file",
                "action": {
                    "type": "read_file", 
                    "path": "test.py"
                }
            })))]),
            Mock(choices=[Mock(message=Mock(content=json.dumps({
                "analysis": "Now I can see the file contents from previous action",
                "action": {
                    "type": "execute_command",
                    "command": "echo 'done'"
                }
            })))])
        ]
        self.mock_llm_service.chat_completion.side_effect = llm_responses
        
        # Mock successful action results
        self.mock_action_executor.execute_action.side_effect = [
            {"success": True, "result": "file contents here", "error": None},
            {"success": True, "result": "done\n", "error": None}
        ]
        
        # Mock action executor to simulate success after the read_file action
        
        # Run debug session
        result = self.debug_session.debug(
            error_message="Test error",
            node_name="test_node",
            stdout="",
            stderr="Test error",
            attempt_number=1,
            previous_attempts=None,
            node_description="Test node"
        )
        
        # The key test: verify that turn 2 contains action results from turn 1
        assert self.mock_llm_service.chat_completion.call_count == 2
        
        # Check turn 2 LLM input
        turn2_call = self.mock_llm_service.chat_completion.call_args_list[1]
        turn2_messages = turn2_call[1]['messages']
        turn2_user_content = next(msg['content'] for msg in turn2_messages if msg['role'] == 'user')
        
        # This should contain the action results from turn 1
        assert "## Actions Performed" in turn2_user_content
        assert "read_file" in turn2_user_content
        assert "file contents here" in turn2_user_content
        assert "✅ SUCCESS" in turn2_user_content
        
        # Verify the conversation state was properly updated
        assert len(self.debug_session.messages) > 2  # Initial + Turn 1 action + Turn 2 setup
    
    def test_conversation_state_consistency(self):
        """Test that the conversation state remains consistent throughout the debug session."""
        
        # Mock a simple single-turn debug session
        self.mock_llm_service.chat_completion.return_value = Mock(
            choices=[Mock(message=Mock(content=json.dumps({
                "analysis": "Let me read the file",
                "action": {
                    "type": "read_file",
                    "path": "test.py"
                }
            })))]
        )
        
        self.mock_action_executor.execute_action.return_value = {
            "success": True,
            "result": "test file content",
            "error": None
        }
        
        # Mock a successful resolution
        
        # Track initial conversation state
        initial_message_count = len(self.debug_session.messages)
        
        # Run debug session
        result = self.debug_session.debug(
            error_message="Test error",
            node_name="test_node",
            stdout="",
            stderr="Test error",
            attempt_number=1,
            previous_attempts=None,
            node_description="Test node"
        )
        
        # Verify conversation was updated properly
        final_message_count = len(self.debug_session.messages)
        assert final_message_count > initial_message_count
        
        # The conversation should contain the action result
        conversation_str = str(self.debug_session.messages)
        assert "read_file" in conversation_str
        assert "test file content" in conversation_str
        
        # Verify the debug session reports success
        assert result["resolved"] == True
        assert result["turns_taken"] == 1


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])