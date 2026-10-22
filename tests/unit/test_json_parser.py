#!/usr/bin/env python3
"""Test the clean JSON parser after cleanup."""

import json
import sys
from pathlib import Path
# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.unified_bug_fixer.json_parser import JSONParser

def test_json_parser():
    """Comprehensive test of the clean JSON parser."""
    
    print("Testing Clean JSON Parser")
    print("="*50)
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Valid JSON with all fields
    print("\n1. Testing valid JSON with all fields...")
    valid_json = json.dumps({
        "type": "read_file",
        "params": {"path": "/workspace/test.py"},
        "explanation": "Reading test file",
        "confidence": 0.9
    })
    result, error = JSONParser.parse_action(valid_json)
    if result and result['type'] == 'read_file':
        print("   ✅ PASSED: Valid JSON parsed correctly")
        tests_passed += 1
    else:
        print(f"   ❌ FAILED: {error}")
        tests_failed += 1
    
    # Test 2: Valid JSON with minimal fields
    print("\n2. Testing valid JSON with minimal fields...")
    minimal_json = json.dumps({"type": "list_directory"})
    result, error = JSONParser.parse_action(minimal_json)
    if result and result['type'] == 'list_directory':
        print("   ✅ PASSED: Minimal JSON parsed with defaults")
        tests_passed += 1
    else:
        print(f"   ❌ FAILED: {error}")
        tests_failed += 1
    
    # Test 3: Invalid JSON syntax
    print("\n3. Testing invalid JSON syntax...")
    invalid_json = "{type: 'read_file'}"  # Single quotes, no quotes on key
    result, error = JSONParser.parse_action(invalid_json)
    if result is None and "Expecting property name" in error:
        print("   ✅ PASSED: Invalid JSON rejected with clear error")
        tests_passed += 1
    else:
        print(f"   ❌ FAILED: Should have rejected invalid JSON")
        tests_failed += 1
    
    # Test 4: Missing required 'type' field
    print("\n4. Testing missing 'type' field...")
    no_type_json = json.dumps({"params": {"path": "/test"}})
    result, error = JSONParser.parse_action(no_type_json)
    if result is None and "missing required 'type' field" in error:
        print("   ✅ PASSED: Missing type field detected")
        tests_passed += 1
    else:
        print(f"   ❌ FAILED: Should have detected missing type")
        tests_failed += 1
    
    # Test 5: Non-object JSON (array)
    print("\n5. Testing non-object JSON...")
    array_json = json.dumps(["read_file", "path"])
    result, error = JSONParser.parse_action(array_json)
    if result is None and "not a JSON object" in error:
        print("   ✅ PASSED: Non-object JSON rejected")
        tests_passed += 1
    else:
        print(f"   ❌ FAILED: Should have rejected array JSON")
        tests_failed += 1
    
    # Test 6: Malformed JSON with truncation
    print("\n6. Testing malformed/truncated JSON...")
    truncated_json = '{"type": "write_file", "params": {"path": "/test", "content": "very long content...'
    result, error = JSONParser.parse_action(truncated_json)
    if result is None and "Unterminated string" in error:
        print("   ✅ PASSED: Truncated JSON detected")
        tests_passed += 1
    else:
        print(f"   ❌ FAILED: Should have detected truncation")
        tests_failed += 1
    
    # Test 7: Complex nested JSON
    print("\n7. Testing complex nested JSON...")
    complex_json = json.dumps({
        "type": "update_function_block",
        "params": {
            "code": "def run(path_dict, params):\n    pass",
            "requirements": ["pandas", "numpy"]
        },
        "explanation": "Updating function block",
        "confidence": 0.95
    })
    result, error = JSONParser.parse_action(complex_json)
    if result and result['type'] == 'update_function_block':
        print("   ✅ PASSED: Complex nested JSON parsed correctly")
        tests_passed += 1
    else:
        print(f"   ❌ FAILED: {error}")
        tests_failed += 1
    
    # Test 8: Empty string
    print("\n8. Testing empty string...")
    result, error = JSONParser.parse_action("")
    if result is None and error:
        print("   ✅ PASSED: Empty string rejected")
        tests_passed += 1
    else:
        print(f"   ❌ FAILED: Should have rejected empty string")
        tests_failed += 1
    
    # Test 9: Plain text (not JSON)
    print("\n9. Testing plain text...")
    plain_text = "I think we should read the file first"
    result, error = JSONParser.parse_action(plain_text)
    if result is None and "Expecting value" in error:
        print("   ✅ PASSED: Plain text rejected")
        tests_passed += 1
    else:
        print(f"   ❌ FAILED: Should have rejected plain text")
        tests_failed += 1
    
    # Test 10: JSON with extra whitespace
    print("\n10. Testing JSON with extra whitespace...")
    spaced_json = """
    
    {
        "type": "read_file",
        "params": {"path": "/test"}
    }
    
    """
    result, error = JSONParser.parse_action(spaced_json)
    if result and result['type'] == 'read_file':
        print("   ✅ PASSED: Whitespace handled correctly")
        tests_passed += 1
    else:
        print(f"   ❌ FAILED: {error}")
        tests_failed += 1
    
    # Summary
    print("\n" + "="*50)
    print(f"RESULTS: {tests_passed} passed, {tests_failed} failed")
    
    assert tests_failed == 0, f"{tests_failed} JSON parser checks failed"
    print("✅ All tests passed!")

if __name__ == "__main__":
    try:
        test_json_parser()
    except AssertionError as e:
        print(f"❌ {e}")
        sys.exit(1)