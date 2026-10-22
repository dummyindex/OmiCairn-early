#!/usr/bin/env python3
"""Test GPT-5 with fixed token allocation"""

import os
from dotenv import load_dotenv
from llm_service.openai_service import OpenAIService

load_dotenv()

def test_gpt5_with_fixed_tokens():
    """Test GPT-5 models with the fixed token allocation"""
    
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
            "confidence": {"type": "number"},
            "reasoning": {"type": "string"}
        },
        "required": ["answer", "confidence", "reasoning"]
    }
    
    messages = [
        {"role": "user", "content": "What is the capital of France? Provide your answer, confidence level, and brief reasoning."}
    ]
    
    for model in ["gpt-5-nano", "gpt-5-mini", "gpt-5"]:
        print(f"\n=== Testing {model} with Fixed Token Allocation ===")
        try:
            service = OpenAIService(model=model)
            result = service.chat_completion_json(
                messages=messages,
                json_schema=schema,
                temperature=1.0,  # Use default for GPT-5
                max_tokens=500   # This should become 1500 internally for GPT-5
            )
            print(f"✓ {model} SUCCESS:")
            print(f"  Answer: {result.get('answer')}")
            print(f"  Confidence: {result.get('confidence')}")
            print(f"  Reasoning: {result.get('reasoning', '')[:100]}...")
            
        except Exception as e:
            print(f"✗ {model} FAILED: {e}")

def test_orchestrator_schema_with_gpt5():
    """Test the orchestrator schema with GPT-5"""
    
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "satisfied": {"type": "boolean"},
            "reasoning": {"type": "string"},
            "next_actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "type": {"type": "string", "enum": ["create_new"]},
                        "name": {"type": "string"},
                        "specification": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "task": {"type": "string"}
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
        {"role": "user", "content": "Plan the first step of a data preprocessing pipeline. We have 0 nodes currently. What should we create?"}
    ]
    
    for model in ["gpt-5-nano", "gpt-5-mini"]:  # Skip full GPT-5 for cost
        print(f"\n=== Testing {model} with Orchestrator Schema ===")
        try:
            service = OpenAIService(model=model)
            result = service.chat_completion_json(
                messages=messages,
                json_schema=schema,
                temperature=1.0,
                max_tokens=800  # This should become 2400 internally
            )
            print(f"✓ {model} SUCCESS:")
            print(f"  Satisfied: {result.get('satisfied')}")
            print(f"  Actions: {len(result.get('next_actions', []))}")
            if result.get('next_actions'):
                action = result['next_actions'][0]
                print(f"  First action: {action.get('name')}")
            
        except Exception as e:
            print(f"✗ {model} FAILED: {e}")

def main():
    """Test GPT-5 with fixes"""
    print("Testing GPT-5 Models with Fixed Token Allocation")
    print("=" * 60)
    
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not found")
        return
    
    test_gpt5_with_fixed_tokens()
    test_orchestrator_schema_with_gpt5()
    
    print(f"\n{'=' * 60}")
    print("If tests pass, GPT-5 models should work with our system!")

if __name__ == "__main__":
    main()