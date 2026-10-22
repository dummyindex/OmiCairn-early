#!/usr/bin/env python3
"""Simple integration test to verify JSON parser works with bug fixer."""

import json
import sys
from unittest.mock import Mock, patch

def test_json_parser_integration_with_bug_fixer():
    """Test that JSON parser integrates correctly with bug fixer components."""
    
    print("Testing JSON Parser Integration with Bug Fixer Components")
    print("="*60)
    
    # Import the components
    from agents.unified_bug_fixer.json_parser import JSONParser
    from agents.unified_bug_fixer.enhanced_debug_session import EnhancedDebugSession
    
    print("\n1. Testing JSON Parser directly...")
    
    # Test various JSON responses the LLM might send
    test_cases = [
        # Valid JSON
        (
            json.dumps({
                "type": "read_file",
                "params": {"path": "/workspace/test.py"},
                "explanation": "Reading file to understand error",
                "confidence": 0.9
            }),
            True,
            "read_file"
        ),
        # Invalid JSON - single quotes
        (
            "{'type': 'read_file', 'params': {'path': '/test'}}",
            False,
            None
        ),
        # Missing type field
        (
            json.dumps({"params": {"path": "/test"}}),
            False,
            None
        ),
        # Non-object JSON
        (
            '["read_file", "path"]',
            False,
            None
        ),
        # Valid minimal JSON
        (
            json.dumps({"type": "list_directory"}),
            True,
            "list_directory"
        ),
        # Complex nested JSON
        (
            json.dumps({
                "type": "update_function_block",
                "params": {
                    "code": "import pandas\ndef run():\n    pass",
                    "requirements": ["pandas", "numpy"]
                }
            }),
            True,
            "update_function_block"
        )
    ]
    
    passed = 0
    failed = 0
    
    for i, (json_text, should_parse, expected_type) in enumerate(test_cases, 1):
        result, error = JSONParser.parse_action(json_text)
        
        if should_parse:
            if result and result.get('type') == expected_type:
                print(f"  ✅ Test {i}: Valid JSON parsed correctly ({expected_type})")
                passed += 1
            else:
                print(f"  ❌ Test {i}: Failed to parse valid JSON. Error: {error}")
                failed += 1
        else:
            if result is None:
                print(f"  ✅ Test {i}: Invalid JSON correctly rejected")
                passed += 1
            else:
                print(f"  ❌ Test {i}: Invalid JSON was incorrectly parsed")
                failed += 1
    
    print(f"\nResults: {passed}/{len(test_cases)} tests passed")
    
    print("\n2. Testing _parse_action_from_text method...")
    
    # Create a minimal mock for testing the parsing method
    mock_llm_service = Mock()
    mock_action_executor = Mock()
    mock_action_executor.get_available_actions = Mock(return_value=["read_file"])
    
    # Create a debug session to test its parsing
    with patch('agents.unified_bug_fixer.enhanced_debug_session.Path'):
        debug_session = EnhancedDebugSession(
            action_executor=mock_action_executor,
            llm_service=mock_llm_service,
            max_turns=1,
            enable_domain_knowledge=False
        )
    
    # Test the _parse_action_from_text method directly
    test_responses = [
        # Valid JSON response
        json.dumps({
            "type": "read_file",
            "params": {"path": "/test.py"},
            "explanation": "Reading file",
            "confidence": 0.9
        }),
        # Invalid JSON response
        "{type: 'read_file'}",
        # Plain text response
        "I think we should read the file first"
    ]
    
    for i, response in enumerate(test_responses, 1):
        action = debug_session._parse_action_from_text(response)
        
        if i == 1:  # Valid JSON
            if action.get('type') == 'read_file':
                print(f"  ✅ Response {i}: Valid JSON parsed correctly")
            else:
                print(f"  ❌ Response {i}: Failed to parse valid JSON")
        else:  # Invalid responses
            if action.get('type') == 'PARSING_FAILED':
                print(f"  ✅ Response {i}: Invalid response handled gracefully")
                if 'error' in action:
                    print(f"      Error message: {action['error'][:50]}...")
            else:
                print(f"  ❌ Response {i}: Invalid response not handled properly")
    
    print("\n3. Verifying no hardcoded parsing workarounds...")
    
    # Check that the deprecated functions are gone
    assert not hasattr(debug_session, '_fallback_parse_strategies_DEPRECATED'), \
        "Deprecated fallback parsing still exists!"
    assert not hasattr(debug_session, '_construct_action_from_data_DEPRECATED'), \
        "Deprecated action construction still exists!"
    
    print("  ✅ No deprecated parsing functions found")
    
    # Check that complex parsing is not in json_parser.py
    import inspect
    source = inspect.getsource(JSONParser.parse_action)
    
    # These patterns should NOT be in the clean parser
    forbidden_patterns = [
        "markdown",
        "```json",
        "regex",
        "re.search",
        "re.match",
        "split('\\n')",
        "trailing_comma",
        "fix_json"
    ]
    
    found_patterns = []
    for pattern in forbidden_patterns:
        if pattern.lower() in source.lower():
            found_patterns.append(pattern)
    
    if not found_patterns:
        print("  ✅ JSON parser is clean - no hardcoded workarounds")
    else:
        print(f"  ❌ Found forbidden patterns in parser: {found_patterns}")
        return False
    
    print("\n" + "="*60)
    
    if failed == 0 and not found_patterns:
        print("✅ ALL INTEGRATION TESTS PASSED!")
        print("\nThe JSON parser is clean and integrates correctly with the bug fixer.")
        print("- No hardcoded parsing workarounds")
        print("- Clear error messages for invalid JSON")
        print("- Graceful handling of parsing failures")
        return True
    else:
        print(f"❌ Some tests failed: {failed} parsing failures, {len(found_patterns)} code issues")
        return False

if __name__ == "__main__":
    success = test_json_parser_integration_with_bug_fixer()
    sys.exit(0 if success else 1)