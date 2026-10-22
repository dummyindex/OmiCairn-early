#!/usr/bin/env python
"""Direct test of OpenAI API call."""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Set API key from environment or use placeholder
# export OPENAI_API_KEY=your-api-key before running this test
if 'OPENAI_API_KEY' not in os.environ:
    print("Warning: OPENAI_API_KEY not set. Please set it in your environment.")
    sys.exit(1)

from omicairn_agent_local.llm_service import OpenAIService

def test_direct_api():
    """Test direct API call."""
    service = OpenAIService()
    
    # Simple test schema
    schema = {
        "name": "test_response",
        "schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "flag": {"type": "boolean"},
                "number": {"type": "integer"}
            },
            "required": ["message", "flag", "number"]
        }
    }
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Return a JSON with message='Hello', flag=true, number=42"}
    ]
    
    try:
        print("Calling OpenAI API...")
        result = service.chat_completion_json(
            messages=messages,
            json_schema=schema,
            temperature=0.1,
            max_tokens=100
        )
        print(f"Success! Result: {result}")
        print(f"Result type: {type(result)}")
        print(f"Flag value: {result.get('flag')}, type: {type(result.get('flag'))}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_direct_api()