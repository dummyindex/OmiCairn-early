#!/usr/bin/env python3
"""Test script to verify bug fixer and validation improvements."""

import os
import sys
import json
from pathlib import Path
import tempfile
import shutil
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.function_block_validator import FunctionBlockValidator
from agents.unified_bug_fixer import UnifiedBugFixer
from models import BaseFunctionBlock, FunctionBlockType


def test_function_block_validation():
    """Test the function block validation feature."""
    print("\n=== Testing Function Block Validation ===")
    
    # Create test directories
    with tempfile.TemporaryDirectory() as tmpdir:
        input_dir = Path(tmpdir) / "input"
        output_dir = Path(tmpdir) / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        
        # Create test files (validator now only checks existence)
        (input_dir / "_node_anndata.h5ad").touch()
        
        # Test 1: Valid input specification (file exists)
        print("\nTest 1: Valid input specification")
        valid_spec = {
            "input_specification": {
                "required_files": ["_node_anndata.h5ad"]
            },
            "output_specification": {
                "required_files": ["_node_anndata.h5ad"]
            }
        }
        
        validator = FunctionBlockValidator(valid_spec)
        is_valid, errors = validator.validate_input(input_dir)
        print(f"  Input validation: {'PASSED' if is_valid else 'FAILED'}")
        if errors:
            print(f"  Errors: {errors}")
        
        # Test 2: Invalid input specification (missing file)
        print("\nTest 2: Invalid input specification (missing file)")
        invalid_spec = {
            "input_specification": {
                "required_files": ["_node_anndata.h5ad", "missing_file.csv"]
            }
        }
        
        validator2 = FunctionBlockValidator(invalid_spec)
        is_valid, errors = validator2.validate_input(input_dir)
        print(f"  Input validation: {'PASSED' if is_valid else 'FAILED'}")
        print(f"  Expected errors: {errors}")
        
        # Test 3: Output validation
        print("\nTest 3: Output validation")
        # Create output file
        (output_dir / "_node_anndata.h5ad").touch()
        
        is_valid, errors = validator.validate_output(output_dir)
        print(f"  Output validation: {'PASSED' if is_valid else 'FAILED'}")
        if errors:
            print(f"  Errors: {errors}")
        
        # Test 4: Missing output file
        print("\nTest 4: Missing output file")
        invalid_output_spec = {
            "output_specification": {
                "required_files": ["_node_anndata.h5ad", "analysis_results.csv"]
            }
        }
        
        validator3 = FunctionBlockValidator(invalid_output_spec)
        is_valid, errors = validator3.validate_output(output_dir)
        print(f"  Output validation: {'PASSED' if is_valid else 'FAILED'}")
        print(f"  Expected errors: {errors}")
    
    print("\n✓ Function block validation tests completed")


def test_enhanced_debug_session():
    """Test the enhanced debug session with mock data."""
    print("\n=== Testing Enhanced Debug Session ===")
    
    # This requires an API key to actually run
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("  Skipping enhanced debug session test (no API key)")
        return
    
    with tempfile.TemporaryDirectory() as tmpdir:
        working_dir = Path(tmpdir)
        
        # Create a simple broken function block
        function_block = Path(working_dir) / "function_block.py"
        function_block.write_text("""
def run(path_dict, params):
    import scfates  # This will fail
    print("Running analysis")
""")
        
        # Initialize bug fixer with enhanced debug
        bug_fixer = UnifiedBugFixer(
            model_name="gpt-4o-mini",
            api_key=api_key,
            max_turns=3
        )
        
        # Test error
        error = "ModuleNotFoundError: No module named 'scfates'"
        
        print("\n  Running enhanced debug session...")
        result = bug_fixer.fix_bug(
            node_name="test_node",
            error_message=error,
            working_directory=working_dir,
            stdout="",
            stderr=error,
            attempt_number=1
        )
        
        print(f"\n  Debug result:")
        print(f"    Success: {result.get('success', False)}")
        print(f"    Turns: {result.get('turns', 0)}")
        print(f"    Files modified: {result.get('files_modified', [])}")
        
        if 'error_evolution' in result:
            evolution = result['error_evolution']
            print(f"    Error types: {evolution.get('unique_error_types', [])}")
            print(f"    Total errors: {evolution.get('total_errors', 0)}")
    
    print("\n✓ Enhanced debug session tests completed")


def test_json_mode_fallback():
    """Test JSON mode with fallback parsing."""
    print("\n=== Testing JSON Mode Fallback ===")
    
    from llm_service.base_llm_service import BaseLLMService
    
    # Create a mock LLM service without JSON mode
    class MockLLMService(BaseLLMService):
        def chat_completion(self, messages, **kwargs):
            # Simulate a response with JSON in markdown
            return {
                'content': '''I'll help you fix this error. Here's the action:

```json
{
  "action_required": true,
  "action": {
    "type": "install_package",
    "parameters": {
      "package": "scfates"
    }
  },
  "explanation": "Installing the missing scfates package"
}
```

This should resolve the import error.'''
            }
        
        def calculate_cost(self, input_tokens, output_tokens):
            return 0.0
    
    # Test the JSON parsing
    service = MockLLMService(api_key="test", model="test")
    
    schema = {"type": "object", "properties": {"action_required": {"type": "boolean"}}}
    result = service.call_llm_json(
        messages=[{"role": "user", "content": "Fix the error"}],
        json_schema=schema
    )
    
    print(f"\n  Parsed result:")
    print(f"    Action required: {result.get('action_required')}")
    print(f"    Action type: {result.get('action', {}).get('type')}")
    print(f"    Success: {'action' in result}")
    
    print("\n✓ JSON mode fallback tests completed")


def run_all_tests():
    """Run all improvement tests."""
    print("=" * 60)
    print("Testing Bug Fixer and Validation Improvements")
    print("=" * 60)
    
    # Test individual components
    test_function_block_validation()
    test_json_mode_fallback()
    test_enhanced_debug_session()
    
    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()