#!/usr/bin/env python3
"""Test suite to validate architecture compliance and parameter passing."""

import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

# Add the omicairn_agent_local directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.main_agent import MainAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.function_creator_agent import FunctionCreatorAgent
from agents.unified_bug_fixer import UnifiedBugFixer
from llm_service import OpenAIService


class TestArchitectureValidation:
    """Test suite for validating architecture compliance."""
    
    @pytest.fixture
    def mock_openai_service(self):
        """Mock OpenAI service to capture LLM calls."""
        mock_service = Mock(spec=OpenAIService)
        mock_service.model = "gpt-4o-mini"
        mock_service.chat_completion.return_value = {"content": "test response"}
        mock_service.chat_completion_json.return_value = {
            "satisfied": False,
            "reasoning": "test",
            "next_actions": []
        }
        return mock_service
    
    def test_llm_seed_propagation(self, mock_openai_service):
        """Test that llm_seed is properly passed to all agents."""
        test_seed = 42
        
        with patch('agents.main_agent.OpenAIService') as mock_openai_class:
            mock_openai_class.return_value = mock_openai_service
            
            # Initialize MainAgent with seed
            agent = MainAgent(
                openai_api_key="test-key",
                llm_seed=test_seed,
                enable_domain_knowledge=True,
                domain_knowledge_domains=["single_cell_genomics"]
            )
            
            # Check orchestrator received seed
            assert hasattr(agent.orchestrator, 'llm_seed')
            assert agent.orchestrator.llm_seed == test_seed
            
            # Check function creator received seed
            assert hasattr(agent.function_creator, 'llm_seed')
            assert agent.function_creator.llm_seed == test_seed
            
            # Check bug fixer received seed
            assert hasattr(agent.bug_fixer, 'seed')
            assert agent.bug_fixer.seed == test_seed
    
    def test_domain_knowledge_in_prompts(self, mock_openai_service):
        """Test that domain knowledge is included in LLM prompts."""
        captured_messages = []
        
        def capture_chat_completion_json(**kwargs):
            captured_messages.extend(kwargs.get('messages', []))
            return {
                "satisfied": False,
                "reasoning": "test",
                "next_actions": [{
                    "type": "create_new",
                    "name": "test_function",
                    "specification": {
                        "name": "test_function",
                        "description": "Test function",
                        "task": "Test task"
                    }
                }]
            }
        
        mock_openai_service.chat_completion_json.side_effect = capture_chat_completion_json
        
        with patch('agents.main_agent.OpenAIService') as mock_openai_class:
            mock_openai_class.return_value = mock_openai_service
            
            # Initialize with domain knowledge
            agent = MainAgent(
                openai_api_key="test-key",
                enable_domain_knowledge=True,
                domain_knowledge_domains=["single_cell_genomics"]
            )
            
            # Simulate function creation
            from models import AnalysisTree, GenerationMode
            tree = AnalysisTree(
                id="test-tree",
                user_request="test request",
                generation_mode=GenerationMode.FIXED_ANALYSIS,
                max_nodes=10
            )
            
            with patch.object(agent.function_creator, 'llm_service', mock_openai_service):
                result = agent.function_creator.process_selection_or_creation({
                    'user_request': 'Create a Palantir pseudotime analysis',
                    'tree': tree,
                    'current_node': None,
                    'parent_chain': [],
                    'generation_mode': GenerationMode.FIXED_ANALYSIS,
                    'max_children': 1
                })
            
            # Check if domain knowledge was included
            system_messages = [msg for msg in captured_messages if msg.get('role') == 'system']
            assert len(system_messages) > 0
            
            # Check for domain knowledge content
            system_content = ' '.join(msg.get('content', '') for msg in system_messages)
            assert 'SINGLE_CELL_GENOMICS KNOWLEDGE' in system_content
            assert 'Palantir' in system_content
            assert 'import palantir' in system_content
    
    def test_function_creator_prompts_architecture(self, mock_openai_service):
        """Test that function creator prompts include updated architecture patterns."""
        captured_messages = []
        
        def capture_chat(**kwargs):
            captured_messages.extend(kwargs.get('messages', []))
            return {"content": '''```json
{
    "name": "test_function",
    "description": "Test function",
    "type": "python",
    "requirements": ["scanpy"],
    "static_config": {},
    "code": "def run(path_dict, params):\\n    pass"
}
```'''}
        
        mock_openai_service.chat_completion.side_effect = capture_chat
        
        with patch('agents.main_agent.OpenAIService') as mock_openai_class:
            mock_openai_class.return_value = mock_openai_service
            
            agent = MainAgent(openai_api_key="test-key")
            
            # Mock tree manager to avoid file operations
            with patch.object(agent.tree_manager, 'add_root_node'):
                with patch.object(agent.function_creator, 'llm_service', mock_openai_service):
                    # Create a function block
                    from models import NewFunctionBlock
                    block = agent.function_creator.create_new_function_block(
                        user_request="Load data",
                        task="Load input data",
                        parent_output_description="",
                        available_files=["data.h5ad"]
                    )
            
            # Check prompts for architecture patterns
            system_messages = [msg for msg in captured_messages if msg.get('role') == 'system']
            system_content = ' '.join(msg.get('content', '') for msg in system_messages)
            
            # Check for previous_nodes interface
            assert 'previous_nodes' in system_content
            assert 'previous_nodes.list()' in system_content
            assert 'previous_nodes.get_file' in system_content or 'previous_nodes.get_file_path' in system_content
            
            # Check for flexible file handling
            assert 'NEVER assume specific file types' in system_content
            assert 'adapt to whatever files' in system_content.lower()
            
            # Check against hardcoded paths
            assert 'DO NOT HARDCODE FILENAMES' in system_content
    
    def test_previous_nodes_runtime_in_container(self):
        """Test that previous_nodes runtime would be available in container."""
        # Check if function_block_runtime.py exists
        runtime_path = Path(__file__).parent.parent / "job_executors" / "function_block_runtime.py"
        assert runtime_path.exists(), "function_block_runtime.py should exist"
        
        # Read the runtime file and check for previous_nodes
        with open(runtime_path, 'r') as f:
            runtime_content = f.read()
        
        assert 'class PreviousNodes' in runtime_content
        assert 'def list(self)' in runtime_content
        assert 'def get_file' in runtime_content or 'def get_file_path' in runtime_content
        
        # Check that it's properly exposed
        assert 'previous_nodes = PreviousNodes' in runtime_content
    
    def test_bug_fixer_domain_knowledge(self, mock_openai_service):
        """Test that bug fixer receives domain knowledge in prompts."""
        captured_messages = []
        
        def capture_chat(**kwargs):
            captured_messages.extend(kwargs.get('messages', []))
            return {"content": json.dumps({
                "actions": [{
                    "type": "read_file",
                    "path": "function_block.py"
                }]
            })}
        
        mock_openai_service.chat_completion.side_effect = capture_chat
        
        # Initialize bug fixer with domain knowledge
        bug_fixer = UnifiedBugFixer(
            model_name="gpt-4o-mini",
            api_key="test-key",
            enable_domain_knowledge=True,
            domain_knowledge_domains=["single_cell_genomics"],
            llm_service=mock_openai_service
        )
        
        # Mock the action executor and debug session
        with patch('agents.unified_bug_fixer.unified_bug_fixer.ActionExecutor'):
            with patch('agents.unified_bug_fixer.unified_bug_fixer.EnhancedDebugSession') as mock_session_class:
                mock_session = Mock()
                mock_session.debug.return_value = {
                    'success': True,
                    'turn_count': 1,
                    'messages': [],
                    'cost': 0,
                    'tokens': {'total': 0}
                }
                mock_session_class.return_value = mock_session
                
                # Run bug fix with a Palantir-related error
                result = bug_fixer.fix_bug(
                    node_name="palantir_analysis",
                    error_message="AttributeError: module 'palantir' has no attribute 'pseudotime'",
                    working_directory=Path(tempfile.mkdtemp()),
                    node_description="Run Palantir pseudotime analysis"
                )
                
                # Check that domain knowledge was passed to debug session
                mock_session_class.assert_called_once()
                call_kwargs = mock_session_class.call_args[1]
                assert call_kwargs.get('enable_domain_knowledge') is True
                assert 'single_cell_genomics' in call_kwargs.get('domain_knowledge_domains', [])
    
    def test_logging_initialization(self, mock_openai_service):
        """Test that agents log their LLM model during initialization."""
        import logging
        from io import StringIO
        
        # Capture logs
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setLevel(logging.INFO)
        
        # Add handler to relevant loggers
        loggers = [
            logging.getLogger('agents.main_agent'),
            logging.getLogger('agents.orchestrator_agent'), 
            logging.getLogger('agents.function_creator_agent'),
            logging.getLogger('agents.unified_bug_fixer.unified_bug_fixer')
        ]
        
        for logger in loggers:
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        
        try:
            with patch('agents.main_agent.OpenAIService') as mock_openai_class:
                mock_openai_class.return_value = mock_openai_service
                
                # Initialize MainAgent
                agent = MainAgent(
                    openai_api_key="test-key",
                    llm_model="gpt-4o-mini"
                )
                
                # Force orchestrator initialization by accessing it
                _ = agent.orchestrator
                _ = agent.function_creator
                _ = agent.bug_fixer
            
            # Check logs
            log_content = log_capture.getvalue()
            
            # These logs should be present
            assert "MainAgent initialized with LLM model: gpt-4o-mini" in log_content
            assert "Using unified bug fixer with model: gpt-4" in log_content
            
        finally:
            # Clean up handlers
            for logger in loggers:
                logger.removeHandler(handler)


class TestRealLLMCalls:
    """Integration tests with real LLM calls (requires API key)."""
    
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="Requires OPENAI_API_KEY")
    def test_real_function_creation_with_domain_knowledge(self):
        """Test real function creation to verify domain knowledge injection."""
        agent = MainAgent(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            llm_model="gpt-4o-mini",
            enable_domain_knowledge=True,
            domain_knowledge_domains=["single_cell_genomics"]
        )
        
        # Create a simple function block
        block = agent.function_creator.create_new_function_block(
            user_request="Create a Palantir pseudotime analysis function",
            task="Run Palantir pseudotime analysis on the input data",
            parent_output_description="Preprocessed single-cell data with PCA",
            available_files=["preprocessed_data.h5ad"]
        )
        
        # Check that the code follows proper patterns
        assert 'import palantir' in block.code
        assert 'def run(path_dict, params):' in block.code
        
        # Check for previous_nodes usage or flexible file handling
        has_previous_nodes = 'previous_nodes' in block.code
        has_flexible_loading = any(pattern in block.code for pattern in [
            'os.listdir', 'glob', '.h5ad', 'available_files'
        ])
        
        assert has_previous_nodes or has_flexible_loading, \
            "Code should use previous_nodes interface or flexible file loading"
        
        # Should NOT have hardcoded paths
        assert '/workspace/input/previous_nodes/node_' not in block.code, \
            "Code should not have hardcoded paths"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])