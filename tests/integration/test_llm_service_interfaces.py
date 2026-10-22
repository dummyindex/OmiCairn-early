#!/usr/bin/env python3
"""Test that LLM service provides consistent interfaces for all models."""

import os
from dotenv import load_dotenv
from llm_service.openai_service import OpenAIService

load_dotenv()

def test_llm_interfaces():
    """Test that all models work with the same interface."""
    
    models = ["gpt-4o-mini", "gpt-5-nano", "gpt-5-mini"]
    
    # Simple test schema
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
            "confidence": {"type": "number"}
        },
        "required": ["answer", "confidence"]
    }
    
    messages = [
        {"role": "user", "content": "What is 2+2? Respond with the answer and confidence 0-1."}
    ]
    
    print("Testing LLM Service Interfaces")
    print("=" * 60)
    
    for model in models:
        print(f"\n### Testing {model} ###")
        
        try:
            # Test 1: Basic chat completion
            service = OpenAIService(model=model)
            response = service.chat_completion(
                messages=messages,
                temperature=1.0,  # GPT-5 only supports 1.0
                max_tokens=100
            )
            
            print(f"✓ chat_completion() works")
            print(f"  Response length: {len(response['content'])} chars")
            print(f"  Tokens used: {response['usage']['total_tokens']}")
            
            # Test 2: JSON structured output
            json_response = service.chat_completion_json(
                messages=messages,
                json_schema=schema,
                temperature=1.0,
                max_tokens=100
            )
            
            print(f"✓ chat_completion_json() works")
            print(f"  Answer: {json_response.get('answer')}")
            print(f"  Confidence: {json_response.get('confidence')}")
            
            # Test 3: Convenience methods
            text_response = service.call_llm(
                messages=messages,
                temperature=1.0,
                max_tokens=100
            )
            
            print(f"✓ call_llm() works")
            print(f"  Response preview: {text_response[:50]}...")
            
            json_response2 = service.call_llm_json(
                messages=messages,
                json_schema=schema,
                temperature=1.0,
                max_tokens=100
            )
            
            print(f"✓ call_llm_json() works")
            print(f"  Has answer: {'answer' in json_response2}")
            
            # Test 4: Cost tracking
            summary = service.get_usage_summary()
            print(f"✓ Usage tracking works")
            print(f"  Total cost: ${summary['total_cost']:.4f}")
            
        except Exception as e:
            print(f"✗ FAILED: {e}")
            return False
    
    print(f"\n{'=' * 60}")
    print("✅ All models provide consistent interfaces!")
    return True


if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not found")
    else:
        test_llm_interfaces()