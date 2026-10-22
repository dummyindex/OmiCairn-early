#!/usr/bin/env python3
"""Simple test to verify action field validation is working."""

import tempfile
from pathlib import Path
from agents.unified_bug_fixer.action_executor import ActionExecutor


def test_validation():
    """Test that action field validation is working correctly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        executor = ActionExecutor(workspace=Path(temp_dir))
        
        print("Testing action field validation...")
        
        # Test 1: Missing required field
        print("\n1. Testing missing required field (path for read_file):")
        result = executor.execute_action({'type': 'read_file'})
        print(f"   Success: {result['success']}")
        print(f"   Error: {result.get('error', '')}")
        assert not result['success']
        assert 'missing required fields' in result['error']
        
        # Test 2: Empty required field
        print("\n2. Testing empty required field (empty command):")
        result = executor.execute_action({'type': 'execute_command', 'command': ''})
        print(f"   Success: {result['success']}")
        print(f"   Error: {result.get('error', '')}")
        assert not result['success']
        assert 'missing required fields' in result['error']
        
        # Test 3: Valid action
        print("\n3. Testing valid action (execute_command):")
        result = executor.execute_action({'type': 'execute_command', 'command': 'echo hello'})
        print(f"   Success: {result['success']}")
        print(f"   Output: {result.get('stdout', '').strip()}")
        assert result['success']
        assert result['stdout'].strip() == 'hello'
        
        # Test 4: Invalid language for update_function_block
        print("\n4. Testing invalid language for update_function_block:")
        result = executor.execute_action({
            'type': 'update_function_block',
            'code': 'def test(): pass',
            'language': 'java'
        })
        print(f"   Success: {result['success']}")
        print(f"   Error: {result.get('error', '')}")
        assert not result['success']
        assert 'Invalid language' in result['error']
        
        # Test 5: Valid update_function_block
        print("\n5. Testing valid update_function_block:")
        result = executor.execute_action({
            'type': 'update_function_block',
            'code': 'def run(path_dict, params):\n    pass',
            'requirements': ['pandas', 'numpy']
        })
        print(f"   Success: {result['success']}")
        print(f"   Files updated: {result.get('files_updated', [])}")
        assert result['success']
        
        print("\n✅ All validation tests passed!")


if __name__ == "__main__":
    test_validation()