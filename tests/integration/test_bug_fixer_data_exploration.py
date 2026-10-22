#!/usr/bin/env python3
"""Test bug fixer's data exploration capability."""

import os
import sys
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.unified_bug_fixer import UnifiedBugFixer
from llm_service.base_llm_service import BaseLLMService


class MockLLMService(BaseLLMService):
    """Mock LLM service for testing."""
    
    def __init__(self, responses=None):
        super().__init__(api_key="mock-key", model="mock-model")
        self.responses = responses or []
        self.call_count = 0
        
    def chat_completion(self, messages, temperature=0.7, max_tokens=4000, response_format=None):
        """Return pre-configured responses."""
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            # Add mock usage data
            response['usage'] = {'total_tokens': 100, 'prompt_tokens': 50, 'completion_tokens': 50}
            response['cost'] = 0.001
            return response
        return {"content": "No more mock responses available", "usage": {'total_tokens': 0}, "cost": 0}
        
    def chat_completion_json(self, messages, json_schema, temperature=0.7, max_tokens=4000):
        """Return JSON response."""
        response = self.chat_completion(messages, temperature, max_tokens)
        return json.loads(response['content'])
        
    def calculate_cost(self, prompt_tokens, completion_tokens):
        """Mock cost calculation."""
        return 0.001
        
    def get_usage_summary(self):
        """Mock usage summary."""
        return {
            'total_tokens': self.total_tokens_used,
            'total_cost': self.total_cost
        }


class TestBugFixerDataExploration:
    """Test that bug fixer explores data when encountering KeyError/AttributeError."""
    
    def __init__(self):
        self.test_dir = None
        self.passed_tests = 0
        self.failed_tests = 0
        
    def setup(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp(prefix="test_bug_fixer_"))
        print(f"Test directory: {self.test_dir}")
        
        # Create mock function block with KeyError
        function_block_dir = self.test_dir / "function_block"
        function_block_dir.mkdir(parents=True, exist_ok=True)
        
        # Write problematic code
        code_content = '''import scanpy as sc
import os

def run(path_dict, params):
    """Function that will fail with KeyError."""
    # Load data
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)
    
    # This will fail - assumes 'cell_type' column exists
    progenitor_cells = adata[adata.obs['cell_type'] == 'Progenitor']
    
    # Save output
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    progenitor_cells.write(output_file)
'''
        
        (function_block_dir / "code.py").write_text(code_content)
        
        # Create requirements.txt
        (function_block_dir / "requirements.txt").write_text("scanpy==1.9.5\n")
        
    def teardown(self):
        """Clean up test environment."""
        if self.test_dir and self.test_dir.exists():
            shutil.rmtree(self.test_dir)
            
    def test_data_exploration_on_key_error(self):
        """Test that bug fixer explores data structure when encountering KeyError."""
        print("\n=== Test: Data Exploration on KeyError ===")
        
        # Create mock LLM service that simulates proper debugging behavior
        mock_responses = [
            # First response: Explore data structure
            {
                "content": '''I see a KeyError for 'cell_type'. Let me first explore the actual data structure to see what columns are available.

```json
{
    "type": "execute_command",
    "command": "python -c \\"import scanpy as sc; adata = sc.read_h5ad('/workspace/input/_node_anndata.h5ad'); print('Available columns:', sorted(list(adata.obs.columns))); print('Shape:', adata.shape)\\""
}
```

I need to check what columns actually exist in the data before making assumptions.'''
            },
            # Second response: After seeing columns, read the code
            {
                "content": '''Now let me read the actual code to understand the implementation.

```json
{
    "type": "read_file",
    "path": "code.py"
}
```'''
            },
            # Third response: Fix based on findings
            {
                "content": '''I can see the issue. The code assumes 'cell_type' exists, but from the data exploration I saw the column is actually 'Cell_type' with a capital C. Let me fix this.

```json
{
    "type": "write_file",
    "path": "code.py",
    "content": "import scanpy as sc\\nimport os\\n\\ndef run(path_dict, params):\\n    \\"\\"\\"Function that handles column names correctly.\\"\\"\\"\\n    # Load data\\n    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')\\n    adata = sc.read_h5ad(input_file)\\n    \\n    # Check actual column name\\n    if 'Cell_type' in adata.obs.columns:\\n        progenitor_cells = adata[adata.obs['Cell_type'] == 'Progenitor']\\n    elif 'cell_type' in adata.obs.columns:\\n        progenitor_cells = adata[adata.obs['cell_type'] == 'Progenitor']\\n    else:\\n        # Fallback: use all cells\\n        print('Warning: No cell type column found, using all cells')\\n        progenitor_cells = adata\\n    \\n    # Save output\\n    os.makedirs(path_dict['output_dir'], exist_ok=True)\\n    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')\\n    progenitor_cells.write(output_file)"
}
```'''
            }
        ]
        
        mock_service = MockLLMService(responses=mock_responses)
        
        # Create bug fixer without web agent
        bug_fixer = UnifiedBugFixer(
            llm_service=mock_service,
            enable_web_agent=False,
            max_turns=5
        )
        
        # Simulate KeyError
        error_message = """KeyError: 'cell_type'

Traceback (most recent call last):
  File "code.py", line 11, in run
    progenitor_cells = adata[adata.obs['cell_type'] == 'Progenitor']
  File "/opt/conda/envs/_omicairn_job/lib/python3.10/site-packages/pandas/core/frame.py", line 3505, in __getitem__
    indexer = self.columns.get_loc(key)
  File "/opt/conda/envs/_omicairn_job/lib/python3.10/site-packages/pandas/core/indexes/base.py", line 3623, in get_loc
    raise KeyError(key) from err
KeyError: 'cell_type'"""
        
        # Run bug fixer
        result = bug_fixer.fix_bug(
            node_name="select_progenitor_cells",
            error_message=error_message,
            working_directory=self.test_dir,
            stdout="",
            stderr=error_message
        )
        
        # Verify behavior
        print(f"Debug session completed: {'SUCCESS' if result['success'] else 'FAILED'}")
        print(f"Actions taken: {len(result.get('actions_taken', []))}")
        
        # Check that data exploration was performed
        actions = result.get('actions_taken', [])
        exploration_performed = False
        code_fixed = False
        
        for action in actions:
            action_type = action['action']['type']
            if action_type == 'execute_command':
                command = action['action'].get('command', '')
                if 'adata.obs.columns' in command or 'print' in command:
                    exploration_performed = True
                    print(f"✓ Data exploration command executed: {command[:100]}...")
            elif action_type == 'write_file':
                if action['action'].get('path') == 'code.py':
                    code_fixed = True
                    print("✓ Code file was modified")
        
        # Verify expectations
        if exploration_performed:
            print("✓ PASS: Bug fixer explored data structure before fixing")
            self.passed_tests += 1
        else:
            print("✗ FAIL: Bug fixer did not explore data structure")
            self.failed_tests += 1
            
        if code_fixed:
            print("✓ PASS: Bug fixer modified the code")
            self.passed_tests += 1
        else:
            print("✗ FAIL: Bug fixer did not modify the code")
            self.failed_tests += 1
            
        # Check that exploration happened BEFORE code modification
        exploration_turn = None
        modification_turn = None
        
        for i, action in enumerate(actions):
            if action['action']['type'] == 'execute_command' and 'adata.obs.columns' in action['action'].get('command', ''):
                exploration_turn = i
            elif action['action']['type'] == 'write_file' and action['action'].get('path') == 'code.py':
                modification_turn = i
                
        if exploration_turn is not None and modification_turn is not None:
            if exploration_turn < modification_turn:
                print("✓ PASS: Data exploration happened before code modification")
                self.passed_tests += 1
            else:
                print("✗ FAIL: Code was modified before exploring data")
                self.failed_tests += 1
        
        return exploration_performed and code_fixed
        
    def test_attribute_error_exploration(self):
        """Test data exploration for AttributeError."""
        print("\n=== Test: Data Exploration on AttributeError ===")
        
        # Update code to cause AttributeError
        function_block_dir = self.test_dir / "function_block"
        code_content = '''import scanpy as sc
import os

def run(path_dict, params):
    """Function that will fail with AttributeError."""
    # Load data
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)
    
    # This will fail - assumes iroot exists
    root_cell = adata.uns.iroot
    
    # Save output
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
'''
        (function_block_dir / "code.py").write_text(code_content)
        
        # Mock responses for AttributeError
        mock_responses = [
            {
                "content": '''I see an AttributeError for 'iroot'. Let me explore the uns dictionary structure.

```json
{
    "type": "execute_command", 
    "command": "python -c \\"import scanpy as sc; adata = sc.read_h5ad('/workspace/input/_node_anndata.h5ad'); print('uns keys:', list(adata.uns.keys())); print('Has iroot:', 'iroot' in adata.uns)\\""
}
```'''
            }
        ]
        
        mock_service = MockLLMService(responses=mock_responses)
        bug_fixer = UnifiedBugFixer(
            llm_service=mock_service,
            enable_web_agent=False,
            max_turns=3
        )
        
        error_message = """AttributeError: 'OverloadedDict' object has no attribute 'iroot'"""
        
        result = bug_fixer.fix_bug(
            node_name="test_node",
            error_message=error_message,
            working_directory=self.test_dir,
            stdout="",
            stderr=error_message
        )
        
        # Check for uns exploration
        actions = result.get('actions_taken', [])
        uns_explored = any(
            action['action']['type'] == 'execute_command' and 
            'adata.uns' in action['action'].get('command', '')
            for action in actions
        )
        
        if uns_explored:
            print("✓ PASS: Bug fixer explored uns dictionary for AttributeError")
            self.passed_tests += 1
        else:
            print("✗ FAIL: Bug fixer did not explore uns dictionary")
            self.failed_tests += 1
            
        return uns_explored
        
    def run_all_tests(self):
        """Run all tests."""
        print("Starting Bug Fixer Data Exploration Tests")
        print("=" * 50)
        
        self.setup()
        
        try:
            # Run tests
            self.test_data_exploration_on_key_error()
            self.test_attribute_error_exploration()
            
        finally:
            self.teardown()
            
        # Summary
        print("\n" + "=" * 50)
        print(f"Tests passed: {self.passed_tests}")
        print(f"Tests failed: {self.failed_tests}")
        print(f"Total tests: {self.passed_tests + self.failed_tests}")
        
        return self.failed_tests == 0


if __name__ == "__main__":
    tester = TestBugFixerDataExploration()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)