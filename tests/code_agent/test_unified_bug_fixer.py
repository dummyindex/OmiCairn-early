"""Tests for unified bug fixer."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
import tempfile
import json
import os
import sys

# Add parent directory to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from agents.unified_bug_fixer import UnifiedBugFixer
from llm_service import OpenAIService, ClaudeService


class TestUnifiedBugFixer:
    """Test unified bug fixer functionality."""
    
    def test_model_selection_gpt(self):
        """Test GPT model selection."""
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            with patch('agents.unified_bug_fixer.unified_bug_fixer.OpenAIService') as mock_openai:
                mock_service = Mock()
                mock_service.model = 'gpt-4o-mini'
                mock_openai.return_value = mock_service
                
                bug_fixer = UnifiedBugFixer("gpt-4o-mini")
                assert bug_fixer.model_name == "gpt-4o-mini"
                assert isinstance(bug_fixer.llm_service, Mock)
            
    def test_model_selection_claude(self):
        """Test Claude model selection."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('agents.unified_bug_fixer.unified_bug_fixer.ClaudeService') as mock_claude:
                mock_service = Mock()
                mock_service.model = 'claude-3-5-haiku-20241022'
                mock_claude.return_value = mock_service
                
                bug_fixer = UnifiedBugFixer("claude-3-5-haiku-20241022")
                assert bug_fixer.model_name == "claude-3-5-haiku-20241022"
                assert isinstance(bug_fixer.llm_service, Mock)
            
    def test_invalid_model_name(self):
        """Test invalid model name raises error."""
        with pytest.raises(ValueError, match="Unknown model type"):
            UnifiedBugFixer("invalid-model-name")
            
    def test_fix_bug_basic(self):
        """Test basic bug fixing flow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Create a broken function block
            function_block = workspace / "function_block.py"
            function_block.write_text("""
def run(path_dict, params):
    # Missing import
    df = pd.DataFrame({'a': [1, 2, 3]})
    print("Done")
""")
            
            # Mock the LLM service
            mock_service = Mock()
            mock_service.model = "test-model"
            
            # Mock responses
            responses = [
                # First response: explore workspace
                'Let me explore the workspace first.\n```json\n{"type": "list_directory", "path": "."}\n```',
                # Action result follow-up
                'I found function_block.py. Let me read it.\n```json\n{"type": "read_file", "path": "function_block.py"}\n```',
                # Fix the import
                'I need to add the pandas import.\n```json\n{"type": "write_file", "path": "function_block.py", "content": "import pandas as pd\\n\\ndef run(path_dict, params):\\n    # Missing import\\n    df = pd.DataFrame({\'a\': [1, 2, 3]})\\n    print(\\"Done\\")"}\n```',
                # Declare success
                'The error has been fixed. I added the missing import for pandas.',
                # Confirmation
                'FIXED: The NameError was caused by missing import statement. I added "import pandas as pd" at the top of the file.'
            ]
            
            mock_service.chat_completion = Mock(side_effect=responses)
            mock_service.get_usage_summary = Mock(return_value={
                'total_cost': 0.01,
                'total_tokens': 1000
            })
            
            # Create bug fixer with mocked service
            bug_fixer = UnifiedBugFixer("test-model", llm_service=mock_service)
            
            # Run bug fix
            result = bug_fixer.fix_bug(
                node_name="test_node",
                error_message="NameError: name 'pd' is not defined",
                working_directory=workspace
            )
            
            # Verify result
            assert result['success'] is True
            assert result['turn_count'] <= 5
            assert 'function_block.py' in result['files_modified']
            
            # Verify the file was updated
            fixed_content = function_block.read_text()
            assert 'import pandas as pd' in fixed_content
            
    def test_fix_bug_failure(self):
        """Test bug fixing failure after max turns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Mock service that never succeeds
            mock_service = Mock()
            mock_service.model = "test-model"
            mock_service.chat_completion = Mock(return_value="I'm still investigating...")
            mock_service.get_usage_summary = Mock(return_value={
                'total_cost': 0.01,
                'total_tokens': 500
            })
            
            # Create bug fixer
            bug_fixer = UnifiedBugFixer("test-model", max_turns=2, llm_service=mock_service)
            
            # Run bug fix
            result = bug_fixer.fix_bug(
                node_name="test_node",
                error_message="Complex error",
                working_directory=workspace
            )
            
            # Verify failure
            assert result['success'] is False
            assert result['turn_count'] == 2
        
    def test_get_statistics(self):
        """Test statistics calculation."""
        bug_fixer = UnifiedBugFixer("test-model")
        
        # Add mock sessions
        bug_fixer.debug_sessions = [
            {
                'success': True,
                'cost': 0.01,
                'tokens': {'total': 1000},
                'turn_count': 3
            },
            {
                'success': False,
                'cost': 0.02,
                'tokens': {'total': 2000},
                'turn_count': 5
            },
            {
                'success': True,
                'cost': 0.015,
                'tokens': {'total': 1500},
                'turn_count': 4
            }
        ]
        
        stats = bug_fixer.get_statistics()
        
        assert stats['total_sessions'] == 3
        assert stats['successful_sessions'] == 2
        assert stats['success_rate'] == 2/3
        assert stats['total_cost'] == 0.045
        assert stats['total_tokens'] == 4500
        assert stats['average_turns'] == 4.0
        
    def test_with_provided_llm_service(self):
        """Test using pre-initialized LLM service."""
        # Mock LLM service
        mock_service = Mock()
        mock_service.model = 'custom-model'
        
        # Create bug fixer with provided service
        bug_fixer = UnifiedBugFixer(llm_service=mock_service)
        
        assert bug_fixer.llm_service == mock_service
        assert bug_fixer.model_name == 'custom-model'
        
    def test_error_handling_json_parsing(self):
        """Test error handling when JSON parsing fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Mock service that returns invalid JSON
            mock_service = Mock()
            mock_service.model = "test-model"
            mock_service.chat_completion = Mock(return_value="Invalid JSON response```json{broken```")
            mock_service.get_usage_summary = Mock(return_value={'total_cost': 0.01, 'total_tokens': 100})
            
            bug_fixer = UnifiedBugFixer("test-model", max_turns=2, llm_service=mock_service)
            
            result = bug_fixer.fix_bug(
                node_name="test_node",
                error_message="Test error",
                working_directory=workspace
            )
            
            # Should handle gracefully and continue
            assert result['success'] is False
            assert result['turn_count'] == 2
            
    def test_action_executor_file_operations(self):
        """Test action executor integration with file operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Create initial file
            test_file = workspace / "test.py"
            test_file.write_text("print('hello')")
            
            mock_service = Mock()
            mock_service.model = "test-model"
            
            responses = [
                # Read file
                'Let me read the file.\n```json\n{"type": "read_file", "path": "test.py"}\n```',
                # Write updated file
                'I\'ll update the file.\n```json\n{"type": "write_file", "path": "test.py", "content": "print(\'hello world\')"}\n```',
                # Success
                'FIXED: Updated the print statement.'
            ]
            
            mock_service.chat_completion = Mock(side_effect=responses)
            mock_service.get_usage_summary = Mock(return_value={'total_cost': 0.01, 'total_tokens': 500})
            
            bug_fixer = UnifiedBugFixer("test-model", llm_service=mock_service)
            
            result = bug_fixer.fix_bug(
                node_name="test_node",
                error_message="Need to update print statement",
                working_directory=workspace
            )
            
            assert result['success'] is True
            assert 'test.py' in result['files_modified']
            assert test_file.read_text() == "print('hello world')"
            
    def test_action_executor_command_execution(self):
        """Test action executor with command execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            mock_service = Mock()
            mock_service.model = "test-model"
            
            responses = [
                # List directory
                'Let me see what files are here.\n```json\n{"type": "list_directory", "path": "."}\n```',
                # Execute command
                'I\'ll create a test file.\n```json\n{"type": "execute_command", "command": "echo \'test content\' > test.txt"}\n```',
                # Check file exists
                'Let me verify the file was created.\n```json\n{"type": "check_file_exists", "path": "test.txt"}\n```',
                # Success
                'FIXED: Created the required test file.'
            ]
            
            mock_service.chat_completion = Mock(side_effect=responses)
            mock_service.get_usage_summary = Mock(return_value={'total_cost': 0.01, 'total_tokens': 600})
            
            bug_fixer = UnifiedBugFixer("test-model", llm_service=mock_service)
            
            result = bug_fixer.fix_bug(
                node_name="test_node",
                error_message="Missing test.txt file",
                working_directory=workspace
            )
            
            assert result['success'] is True
            assert len(result['actions_taken']) >= 3
            assert (workspace / "test.txt").exists()
            
    def test_multiple_turn_debugging_flow(self):
        """Test complex multi-turn debugging session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            # Create a complex broken file
            broken_file = workspace / "complex.py"
            broken_file.write_text("""
def process_data(data):
    # Missing imports
    df = pd.DataFrame(data)
    result = np.mean(df.values)
    return result
""")
            
            mock_service = Mock()
            mock_service.model = "test-model"
            
            responses = [
                # First: explore
                'Let me explore the workspace.\n```json\n{"type": "list_directory", "path": "."}\n```',
                # Read the file
                'I found complex.py. Let me read it.\n```json\n{"type": "read_file", "path": "complex.py"}\n```',
                # Fix first import
                'I see missing imports. Let me add pandas first.\n```json\n{"type": "write_file", "path": "complex.py", "content": "import pandas as pd\\n\\ndef process_data(data):\\n    # Missing imports\\n    df = pd.DataFrame(data)\\n    result = np.mean(df.values)\\n    return result"}\n```',
                # Fix second import
                'Now I need to add numpy import.\n```json\n{"type": "write_file", "path": "complex.py", "content": "import pandas as pd\\nimport numpy as np\\n\\ndef process_data(data):\\n    # Missing imports\\n    df = pd.DataFrame(data)\\n    result = np.mean(df.values)\\n    return result"}\n```',
                # Verify fix
                'Let me verify the imports are correct.\n```json\n{"type": "execute_command", "command": "python -c \'import complex\'"}\n```',
                # Success
                'FIXED: Added all missing imports (pandas and numpy).'
            ]
            
            mock_service.chat_completion = Mock(side_effect=responses)
            mock_service.get_usage_summary = Mock(return_value={'total_cost': 0.02, 'total_tokens': 1500})
            
            bug_fixer = UnifiedBugFixer("test-model", max_turns=10, llm_service=mock_service)
            
            result = bug_fixer.fix_bug(
                node_name="complex",
                error_message="NameError: name 'pd' is not defined",
                working_directory=workspace
            )
            
            assert result['success'] is True
            assert result['turn_count'] <= 6
            assert 'complex.py' in result['files_modified']
            
            # Verify final file content
            final_content = broken_file.read_text()
            assert 'import pandas as pd' in final_content
            assert 'import numpy as np' in final_content
            
    def test_package_installation_action(self):
        """Test package installation action."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            mock_service = Mock()
            mock_service.model = "test-model"
            
            responses = [
                # Try to install package
                'The error suggests missing package. Let me install it.\n```json\n{"type": "install_package", "package": "requests"}\n```',
                # Create test file using the package
                'Package installed. Let me create a test script.\n```json\n{"type": "write_file", "path": "test_requests.py", "content": "import requests\\nprint(\'requests installed\')"}\n```',
                # Success
                'FIXED: Installed missing requests package.'
            ]
            
            mock_service.chat_completion = Mock(side_effect=responses)
            mock_service.get_usage_summary = Mock(return_value={'total_cost': 0.01, 'total_tokens': 400})
            
            bug_fixer = UnifiedBugFixer("test-model", llm_service=mock_service)
            
            result = bug_fixer.fix_bug(
                node_name="test_node",
                error_message="ModuleNotFoundError: No module named 'requests'",
                working_directory=workspace
            )
            
            assert result['success'] is True
            assert any(action['action']['type'] == 'install_package' for action in result['actions_taken'])
            
    def test_debug_log_saving(self):
        """Test debug log saving functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            mock_service = Mock()
            mock_service.model = "test-model"
            mock_service.chat_completion = Mock(return_value='FIXED: Simple fix')
            mock_service.get_usage_summary = Mock(return_value={'total_cost': 0.01, 'total_tokens': 100})
            
            # Enable debug logs
            bug_fixer = UnifiedBugFixer("test-model", save_debug_logs=True, llm_service=mock_service)
            
            result = bug_fixer.fix_bug(
                node_name="test_node",
                error_message="Test error",
                working_directory=workspace,
                attempt_number=1
            )
            
            # Check debug logs were saved
            debug_dir = workspace / "agent_tasks" / "unified_bug_fixer" / "attempt_1"
            assert debug_dir.exists()
            assert (debug_dir / "session_log.json").exists()
            assert (debug_dir / "conversation.json").exists()
            
            # Verify log content
            with open(debug_dir / "session_log.json") as f:
                log_data = json.load(f)
                assert log_data['node_name'] == 'test_node'
                assert log_data['attempt_number'] == 1
                assert log_data['success'] is True
                
    def test_no_action_continues_debugging(self):
        """Test behavior when LLM doesn't request an action."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            mock_service = Mock()
            mock_service.model = "test-model"
            
            responses = [
                # First response without action
                "I'm analyzing the error...",
                # Follow-up prompt response
                'Let me check the files.\n```json\n{"type": "list_directory", "path": "."}\n```',
                # Success
                'FIXED: Found and resolved the issue.'
            ]
            
            mock_service.chat_completion = Mock(side_effect=responses)
            mock_service.get_usage_summary = Mock(return_value={'total_cost': 0.01, 'total_tokens': 300})
            
            bug_fixer = UnifiedBugFixer("test-model", llm_service=mock_service)
            
            result = bug_fixer.fix_bug(
                node_name="test_node",
                error_message="Complex error",
                working_directory=workspace
            )
            
            assert result['success'] is True
            # Should have prompted for next step
            assert any('What should we try next' in msg['content'] 
                      for msg in result['messages'] if msg['role'] == 'user')
