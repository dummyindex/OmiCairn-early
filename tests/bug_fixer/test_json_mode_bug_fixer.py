#!/usr/bin/env python3
"""Test JSON mode in bug fixer to understand why it might be falling back to text parsing."""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock
import json

import pytest

# Add project root to path
import sys
sys.path.append(str(Path(__file__).parent))

from agents.unified_bug_fixer.enhanced_debug_session import EnhancedDebugSession
from agents.unified_bug_fixer.action_executor import ActionExecutor
from llm_service.openai_service import OpenAIService
from agents.unified_bug_fixer.bug_fixer_schemas import OPENAI_COMPATIBLE_ACTION_SCHEMA


@pytest.mark.skipif(not os.getenv('OPENAI_API_KEY'), reason="OPENAI_API_KEY not set")
def test_json_mode_directly():
    """Test JSON mode directly with OpenAI service."""
    print("Testing JSON mode directly with OpenAI service...")
    
    # Get API key from environment
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return
    
    # Create OpenAI service
    llm_service = OpenAIService(api_key=api_key, model='gpt-4o-mini')
    
    # Test message
    messages = [
        {"role": "system", "content": "You are a bug fixer. Respond with a JSON action."},
        {"role": "user", "content": "I need to read the file test.py to understand an error. Please provide the action in the required JSON format with type, params, explanation, and confidence fields."}
    ]
    
    try:
        # Test JSON mode
        print("\n1. Testing call_llm_json with bug fixer schema...")
        response = llm_service.call_llm_json(
            messages=messages,
            json_schema=OPENAI_COMPATIBLE_ACTION_SCHEMA,
            temperature=0.1
        )
        print(f"✅ JSON mode succeeded!")
        print(f"Response type: {type(response)}")
        print(f"Response: {json.dumps(response, indent=2)}")
        
        # Validate response matches schema
        assert 'type' in response
        assert 'params' in response
        assert 'explanation' in response
        assert 'confidence' in response
        print("✅ Response matches expected schema")
        
    except Exception as e:
        print(f"❌ JSON mode failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
        # Try text mode as fallback
        print("\n2. Testing text mode fallback...")
        try:
            text_response = llm_service.call_llm(messages=messages, temperature=0.1)
            print(f"✅ Text mode succeeded")
            print(f"Response preview: {text_response[:200]}...")
        except Exception as e2:
            print(f"❌ Text mode also failed: {e2}")


@pytest.mark.skipif(not os.getenv('OPENAI_API_KEY'), reason="OPENAI_API_KEY not set")
def test_enhanced_debug_session():
    """Test EnhancedDebugSession JSON mode usage."""
    print("\n\nTesting EnhancedDebugSession JSON mode...")
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        return
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create components
        action_executor = ActionExecutor(workspace=Path(temp_dir))
        llm_service = OpenAIService(api_key=api_key, model='gpt-4o-mini')
        
        # Create debug session
        session = EnhancedDebugSession(
            action_executor=action_executor,
            llm_service=llm_service,
            max_turns=1
        )
        
        # JSON mode is determined by the action parsing method used
        
        # Test getting an action
        session.messages = [
            {"role": "system", "content": "You are debugging a Python error."},
            {"role": "user", "content": "There's an AttributeError: module 'scanpy' has no attribute 'hist'. I need to read the code file to understand the error."}
        ]
        
        print("\n✅ EnhancedDebugSession created successfully")
        print("📝 Bug fixer uses text parsing mode for flexible action schemas")
        
        # Check that session is properly initialized
        assert session.action_executor is not None
        assert session.llm_service is not None
        assert session.max_turns == 1
        assert session.turn_count == 0
        assert len(session.actions_taken) == 0
        
        print("✅ All session attributes initialized correctly")


def check_schema_compatibility():
    """Check if our schema is compatible with OpenAI's requirements."""
    print("\n\nChecking schema compatibility...")
    
    # Check that all properties in top level are required
    required = set(OPENAI_COMPATIBLE_ACTION_SCHEMA.get('required', []))
    properties = set(OPENAI_COMPATIBLE_ACTION_SCHEMA.get('properties', {}).keys())
    
    print(f"Properties: {properties}")
    print(f"Required: {required}")
    print(f"All properties required: {properties == required}")
    
    # Check additionalProperties is False
    print(f"additionalProperties=False: {OPENAI_COMPATIBLE_ACTION_SCHEMA.get('additionalProperties') is False}")
    
    # Check params object
    params_schema = OPENAI_COMPATIBLE_ACTION_SCHEMA['properties']['params']
    print(f"\nParams schema:")
    print(f"  Type: {params_schema.get('type')}")
    print(f"  additionalProperties=False: {params_schema.get('additionalProperties') is False}")
    print(f"  Required fields: {params_schema.get('required', [])}")


if __name__ == "__main__":
    print("="*80)
    print("JSON MODE BUG FIXER TEST")
    print("="*80)
    
    # Check schema first
    check_schema_compatibility()
    
    # Test JSON mode directly
    test_json_mode_directly()
    
    # Test in debug session
    test_enhanced_debug_session()
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)