#!/usr/bin/env python3
"""Test function creator schema with GPT-5"""

import os
from dotenv import load_dotenv
from llm_service.openai_service import OpenAIService

load_dotenv()

def test_function_creator_schema():
    """Test the complete function creator schema"""
    
    # Simplified version of the actual schema
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "function_block": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "code": {"type": "string"},
                    "requirements": {"type": "array", "items": {"type": "string"}},
                    "parameters": {"type": "string"},
                    "type": {"type": "string", "enum": ["python", "r"]},
                    "static_config": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "args": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "name": {"type": "string"},
                                        "value_type": {"type": "string", "enum": ["int", "float", "str", "bool", "list", "dict"]},
                                        "description": {"type": "string"},
                                        "optional": {"type": "boolean"},
                                        "default_value": {"type": "string", "description": "Default value as string"}
                                    },
                                    "required": ["name", "value_type", "description", "optional", "default_value"]
                                }
                            },
                            "description": {"type": "string"},
                            "tag": {"type": "string", "enum": ["quality_control", "normalization", "clustering", "visualization", "analysis", "integration"]}
                        },
                        "required": ["args", "description", "tag"]
                    }
                },
                "required": ["name", "description", "code", "requirements", "parameters", "type", "static_config"]
            },
            "reasoning": {"type": "string"}
        },
        "required": ["function_block", "reasoning"]
    }
    
    messages = [
        {"role": "user", "content": "Create a simple Python function that loads AnnData and prints its shape."}
    ]
    
    print("Testing Function Creator Schema with GPT-5-nano...")
    
    try:
        service = OpenAIService(model="gpt-5-nano")
        result = service.chat_completion_json(
            messages=messages,
            json_schema=schema,
            temperature=1.0,
            max_tokens=2000  # This becomes 6000 internally for GPT-5
        )
        print("✓ SUCCESS: Function creator schema works with GPT-5!")
        fb = result.get('function_block', {})
        print(f"  Name: {fb.get('name')}")
        print(f"  Type: {fb.get('type')}")
        print(f"  Code length: {len(fb.get('code', ''))}")
        static_config = fb.get('static_config', {})
        args = static_config.get('args', [])
        print(f"  Args count: {len(args)}")
        
        return True
        
    except Exception as e:
        print(f"✗ FAILED: {e}")
        return False

if __name__ == "__main__":
    if test_function_creator_schema():
        print("\n🎉 Function creator schema is now compatible with GPT-5!")
    else:
        print("\n❌ Function creator schema still has issues")