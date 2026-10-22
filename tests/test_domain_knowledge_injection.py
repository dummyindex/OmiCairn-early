#!/usr/bin/env python3
"""Test domain knowledge injection in function creator and bug fixer prompts."""

import os
import sys
import json
from pathlib import Path
from unittest.mock import Mock, patch, call

# Add the omicairn_agent_local directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.function_creator_agent import FunctionCreatorAgent
from agents.unified_bug_fixer import UnifiedBugFixer
from llm_service import OpenAIService
from models import NewFunctionBlock, GenerationMode, AnalysisTree


def test_function_creator_domain_knowledge():
    """Test that function creator includes domain knowledge in prompts."""
    print("\n=== Testing Function Creator Domain Knowledge ===")
    
    # Create a mock LLM service that captures messages
    captured_messages = []
    
    mock_llm = Mock(spec=OpenAIService)
    mock_llm.model = "gpt-4o-mini"
    
    def capture_chat(**kwargs):
        captured_messages.extend(kwargs.get('messages', []))
        return {"content": '''```json
{
    "name": "test_function",
    "description": "Test function",
    "type": "python",
    "requirements": ["scanpy"],
    "static_config": {},
    "code": "def run(path_dict, params):\\n    pass",
    "output_description": "Test output"
}
```'''}
    
    mock_llm.chat_completion.side_effect = capture_chat
    
    # Create function creator with domain knowledge
    creator = FunctionCreatorAgent(
        llm_service=mock_llm,
        enable_domain_knowledge=True,
        domain_knowledge_domains=["single_cell_genomics"],
        llm_seed=42
    )
    
    # Create a function block
    spec = {
        "name": "palantir_analysis",
        "description": "Run Palantir pseudotime analysis",
        "task": "Perform Palantir pseudotime analysis on preprocessed data"
    }
    
    block = creator.create_from_specification(spec)
    
    # Check captured messages
    print(f"\nCaptured {len(captured_messages)} messages")
    
    # Find system message
    system_messages = [msg for msg in captured_messages if msg.get('role') == 'system']
    print(f"Found {len(system_messages)} system messages")
    
    if system_messages:
        system_content = system_messages[0].get('content', '')
        
        # Check for domain knowledge
        has_domain_knowledge = 'SINGLE_CELL_GENOMICS KNOWLEDGE' in system_content
        has_palantir_info = 'Palantir' in system_content and 'import palantir' in system_content
        has_previous_nodes = 'previous_nodes' in system_content
        has_flexible_files = 'NEVER assume specific file types' in system_content
        
        print(f"\nDomain knowledge included: {has_domain_knowledge}")
        print(f"Palantir-specific info: {has_palantir_info}")
        print(f"Previous nodes interface: {has_previous_nodes}")
        print(f"Flexible file handling: {has_flexible_files}")
        
        # Print a snippet of the domain knowledge
        if has_domain_knowledge:
            start = system_content.find('SINGLE_CELL_GENOMICS KNOWLEDGE')
            end = start + 500
            print(f"\nDomain knowledge snippet:\n{system_content[start:end]}...")
            
        return has_domain_knowledge and has_palantir_info
    
    return False


def test_bug_fixer_domain_knowledge():
    """Test that bug fixer includes domain knowledge in prompts."""
    print("\n=== Testing Bug Fixer Domain Knowledge ===")
    
    # Create mock LLM service
    captured_init_kwargs = {}
    
    with patch('agents.unified_bug_fixer.unified_bug_fixer.EnhancedDebugSession') as mock_session_class:
        # Capture initialization kwargs
        def capture_init(**kwargs):
            captured_init_kwargs.update(kwargs)
            mock_instance = Mock()
            mock_instance.debug.return_value = {
                'success': True,
                'turn_count': 1,
                'messages': [],
                'cost': 0,
                'tokens': {'total': 0}
            }
            return mock_instance
        
        mock_session_class.side_effect = capture_init
        
        # Create bug fixer with domain knowledge
        bug_fixer = UnifiedBugFixer(
            model_name="gpt-4o-mini",
            api_key="test-key",
            enable_domain_knowledge=True,
            domain_knowledge_domains=["single_cell_genomics"],
            seed=42,
            max_turns=10
        )
        
        # Run a fix attempt
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            result = bug_fixer.fix_bug(
                node_name="palantir_analysis",
                error_message="AttributeError: module 'palantir' has no attribute 'pseudotime'",
                working_directory=Path(tmpdir),
                node_description="Run Palantir pseudotime analysis"
            )
        
        # Check if domain knowledge was passed
        print(f"\nCaptured initialization kwargs:")
        for key, value in captured_init_kwargs.items():
            if key in ['enable_domain_knowledge', 'domain_knowledge_domains', 'prompt_injector']:
                print(f"  {key}: {value}")
        
        has_domain_knowledge = captured_init_kwargs.get('enable_domain_knowledge', False)
        has_domains = 'single_cell_genomics' in captured_init_kwargs.get('domain_knowledge_domains', [])
        has_injector = captured_init_kwargs.get('prompt_injector') is not None
        
        print(f"\nDomain knowledge enabled: {has_domain_knowledge}")
        print(f"Has single_cell_genomics domain: {has_domains}")
        print(f"Has prompt injector: {has_injector}")
        
        return has_domain_knowledge and has_domains and has_injector


def test_previous_nodes_runtime():
    """Test that previous_nodes runtime exists and would be available in container."""
    print("\n=== Testing Previous Nodes Runtime ===")
    
    runtime_path = Path(__file__).parent.parent / "utils" / "function_block_runtime.py"
    print(f"\nChecking runtime at: {runtime_path}")
    print(f"Runtime exists: {runtime_path.exists()}")
    
    if runtime_path.exists():
        with open(runtime_path, 'r') as f:
            content = f.read()
        
        has_previous_nodes_class = 'class PreviousNodes' in content
        has_list_method = 'def list(self)' in content
        has_get_file = 'def get_file' in content
        has_export = 'previous_nodes = PreviousNodes' in content
        
        print(f"\nHas PreviousNodes class: {has_previous_nodes_class}")
        print(f"Has list() method: {has_list_method}")
        print(f"Has get_file() method: {has_get_file}")
        print(f"Exports previous_nodes instance: {has_export}")
        
        # Check if it's copied to container
        executor_files = [
            'base_executor.py',
            'python_executor.py',
            'r_executor.py'
        ]
        
        print(f"\nExecutor directory contents:")
        executor_dir = Path(__file__).parent.parent / "job_executors"
        for file in executor_files:
            exists = (executor_dir / file).exists()
            print(f"  {file}: {'✓' if exists else '✗'}")
        
        return all([has_previous_nodes_class, has_list_method, has_get_file, has_export])
    
    return False


def test_prompt_architecture_patterns():
    """Test that function creator prompts include updated architecture patterns."""
    print("\n=== Testing Prompt Architecture Patterns ===")
    
    # Check the prompt templates
    from agents.function_creator_agent import FunctionCreatorAgent
    
    # Create an instance to check the system prompt
    mock_llm = Mock(spec=OpenAIService)
    mock_llm.model = "gpt-4o-mini"
    
    creator = FunctionCreatorAgent(
        llm_service=mock_llm,
        enable_domain_knowledge=False  # Test without domain knowledge to see base prompt
    )
    
    # The system prompt should be in creator.SYSTEM_PROMPT
    if hasattr(creator, 'SYSTEM_PROMPT'):
        prompt = creator.SYSTEM_PROMPT
    else:
        # Try to get it from the class
        prompt = FunctionCreatorAgent.SYSTEM_PROMPT if hasattr(FunctionCreatorAgent, 'SYSTEM_PROMPT') else ""
    
    if not prompt:
        # Read from the agent file directly
        agent_path = Path(__file__).parent.parent / "agents" / "function_creator_agent.py"
        with open(agent_path, 'r') as f:
            content = f.read()
            # Extract SYSTEM_PROMPT
            start = content.find('SYSTEM_PROMPT = """')
            if start != -1:
                start += len('SYSTEM_PROMPT = """')
                end = content.find('"""', start)
                prompt = content[start:end]
    
    print(f"\nPrompt length: {len(prompt)} characters")
    
    # Check for key patterns
    patterns = {
        'previous_nodes interface': 'previous_nodes' in prompt,
        'flexible file handling': 'NEVER assume specific file types' in prompt or 'adapt to whatever files' in prompt,
        'no hardcoded paths': 'DO NOT HARDCODE' in prompt or 'HARDCODE FILENAMES' in prompt,
        'previous_nodes.list()': 'previous_nodes.list()' in prompt,
        'previous_nodes.get_file': 'previous_nodes.get_file' in prompt,
        'file discovery': 'os.listdir' in prompt or 'check what files are available' in prompt.lower()
    }
    
    print("\nArchitecture patterns in prompt:")
    for pattern, found in patterns.items():
        print(f"  {pattern}: {'✓' if found else '✗'}")
    
    # Print relevant snippets
    if patterns['previous_nodes interface']:
        start = prompt.find('previous_nodes')
        end = start + 200
        print(f"\nPrevious nodes snippet:\n...{prompt[start:end]}...")
    
    return all(patterns.values())


if __name__ == "__main__":
    print("Testing Architecture Validation\n")
    
    # Run tests
    results = {
        "Function Creator Domain Knowledge": test_function_creator_domain_knowledge(),
        "Bug Fixer Domain Knowledge": test_bug_fixer_domain_knowledge(),
        "Previous Nodes Runtime": test_previous_nodes_runtime(),
        "Prompt Architecture Patterns": test_prompt_architecture_patterns()
    }
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    print(f"\nOverall: {'✓ ALL TESTS PASSED' if all_passed else '✗ SOME TESTS FAILED'}")
    
    # Exit with appropriate code
    sys.exit(0 if all_passed else 1)