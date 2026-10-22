#!/usr/bin/env python3
"""Test GPT-5 models with structured outputs"""

import os
import json
from dotenv import load_dotenv
from llm_service.openai_service import OpenAIService

# Load environment variables
load_dotenv()

def test_simple_schema():
    """Test a simple schema that should work"""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
        },
        "required": ["answer", "confidence"]
    }
    
    messages = [
        {"role": "user", "content": "What is 2+2? Respond with your answer and confidence level."}
    ]
    
    for model in ["gpt-5-nano", "gpt-5-mini", "gpt-5"]:
        print(f"\n=== Testing {model} ===")
        try:
            service = OpenAIService(model=model)
            result = service.chat_completion_json(
                messages=messages,
                json_schema=schema,
                temperature=0.1,
                max_tokens=100
            )
            print(f"✓ {model} SUCCESS:")
            print(f"  Answer: {result.get('answer')}")
            print(f"  Confidence: {result.get('confidence')}")
            
        except Exception as e:
            print(f"✗ {model} FAILED: {e}")

def test_orchestrator_schema():
    """Test the orchestrator schema"""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "satisfied": {
                "type": "boolean",
                "description": "Whether the user request has been fully satisfied"
            },
            "reasoning": {
                "type": "string",
                "description": "Explanation of the planning decision"
            },
            "next_actions": {
                "type": "array",
                "description": "List of next function blocks to create",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "type": {"type": "string", "enum": ["create_new"]},
                        "name": {"type": "string", "description": "Function block name (snake_case)"},
                        "specification": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string", "description": "Same as parent name"},
                                "description": {"type": "string"},
                                "task": {"type": "string", "description": "Detailed task description"}
                            },
                            "required": ["name", "description", "task"]
                        }
                    },
                    "required": ["type", "name", "specification"]
                }
            }
        },
        "required": ["satisfied", "reasoning", "next_actions"]
    }
    
    messages = [
        {"role": "user", "content": "Plan a simple data preprocessing task. Are we satisfied with 0 nodes? What should we create next?"}
    ]
    
    for model in ["gpt-5-nano", "gpt-5-mini", "gpt-5"]:
        print(f"\n=== Testing {model} with Orchestrator Schema ===")
        try:
            service = OpenAIService(model=model)
            result = service.chat_completion_json(
                messages=messages,
                json_schema=schema,
                temperature=0.1,
                max_tokens=500
            )
            print(f"✓ {model} SUCCESS:")
            print(f"  Satisfied: {result.get('satisfied')}")
            print(f"  Reasoning: {result.get('reasoning', '')[:100]}...")
            print(f"  Actions: {len(result.get('next_actions', []))}")
            
        except Exception as e:
            print(f"✗ {model} FAILED: {e}")

def test_simplified_function_block_schema():
    """Test a simplified function block schema"""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "function_block": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "description": "Function block name"},
                    "description": {"type": "string", "description": "Brief description"},
                    "code": {"type": "string", "description": "Python code"},
                    "requirements": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Package requirements"
                    },
                    "parameters": {
                        "type": "string",
                        "description": "Parameters as JSON string"
                    },
                    "type": {"type": "string", "enum": ["python", "r"]}
                },
                "required": ["name", "description", "code", "requirements", "parameters", "type"]
            },
            "reasoning": {"type": "string", "description": "Implementation reasoning"}
        },
        "required": ["function_block", "reasoning"]
    }
    
    messages = [
        {"role": "user", "content": "Create a simple Python function that loads data and prints its shape."}
    ]
    
    for model in ["gpt-5-nano", "gpt-5-mini", "gpt-5"]:
        print(f"\n=== Testing {model} with Function Block Schema ===")
        try:
            service = OpenAIService(model=model)
            result = service.chat_completion_json(
                messages=messages,
                json_schema=schema,
                temperature=0.1,
                max_tokens=1000
            )
            print(f"✓ {model} SUCCESS:")
            fb = result.get('function_block', {})
            print(f"  Name: {fb.get('name')}")
            print(f"  Type: {fb.get('type')}")
            print(f"  Requirements: {fb.get('requirements')}")
            print(f"  Code length: {len(fb.get('code', ''))}")
            
        except Exception as e:
            print(f"✗ {model} FAILED: {e}")

def test_temperature_parameter():
    """Test if temperature parameter works with GPT-5 models"""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "creativity_level": {"type": "string", "enum": ["low", "medium", "high"]},
            "response": {"type": "string"}
        },
        "required": ["creativity_level", "response"]
    }
    
    messages = [
        {"role": "user", "content": "Rate your creativity level and give a creative response about cats."}
    ]
    
    for model in ["gpt-5-nano", "gpt-5-mini", "gpt-5"]:
        print(f"\n=== Testing {model} Temperature Handling ===")
        try:
            service = OpenAIService(model=model)
            
            # Test with temperature=0.1 (should work - low creativity)
            result = service.chat_completion_json(
                messages=messages,
                json_schema=schema,
                temperature=0.1,  # This should be ignored for GPT-5
                max_tokens=200
            )
            print(f"✓ {model} SUCCESS with temperature=0.1:")
            print(f"  Creativity: {result.get('creativity_level')}")
            print(f"  Response: {result.get('response', '')[:50]}...")
            
        except Exception as e:
            print(f"✗ {model} FAILED: {e}")

def main():
    """Run all tests"""
    print("Testing GPT-5 Models with Structured Outputs")
    print("=" * 60)
    
    # Check API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment")
        return
    
    print("✓ API key found")
    
    # Run tests
    test_simple_schema()
    test_temperature_parameter()
    test_orchestrator_schema()
    test_simplified_function_block_schema()
    
    print(f"\n{'=' * 60}")
    print("Testing complete!")

if __name__ == "__main__":
    main()