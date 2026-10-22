#!/usr/bin/env python3
"""Test GPT-5 reasoning token behavior"""

import os
from dotenv import load_dotenv
from llm_service.openai_service import OpenAIService

load_dotenv()

def test_reasoning_token_behavior():
    """Test different max_tokens values to understand reasoning behavior"""
    
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
        {"role": "user", "content": "What is 2+2? Answer briefly."}
    ]
    
    # Test different max_tokens values
    token_limits = [50, 100, 500, 1000, 2000, 4000]
    
    for model in ["gpt-5-nano", "gpt-5-mini", "gpt-5"]:
        print(f"\n=== Testing {model} Token Behavior ===")
        
        for max_tokens in token_limits:
            try:
                service = OpenAIService(model=model)
                result = service.chat_completion_json(
                    messages=messages,
                    json_schema=schema,
                    temperature=1.0,  # Use default temperature
                    max_tokens=max_tokens
                )
                print(f"✓ {model} SUCCESS with {max_tokens} tokens:")
                print(f"  Answer: {result.get('answer', 'EMPTY')}")
                break  # Success - move on to the next model
                
            except Exception as e:
                if "Empty content" in str(e):
                    print(f"  {max_tokens} tokens: Empty content (reasoning consumed all tokens)")
                elif "max_tokens" in str(e):
                    print(f"  {max_tokens} tokens: Hit token limit")
                else:
                    print(f"  {max_tokens} tokens: Error - {str(e)[:100]}")

def test_without_structured_outputs():
    """Test GPT-5 without structured outputs to see if it works"""
    
    messages = [
        {"role": "user", "content": "What is 2+2? Respond with just the number."}
    ]
    
    for model in ["gpt-5-nano", "gpt-5-mini", "gpt-5"]:
        print(f"\n=== Testing {model} WITHOUT Structured Outputs ===")
        
        for max_tokens in [100, 500, 1000]:
            try:
                service = OpenAIService(model=model)
                result = service.chat_completion(
                    messages=messages,
                    temperature=1.0,  # Use default temperature
                    max_tokens=max_tokens
                )
                content = result.get('content', '')
                if content.strip():
                    print(f"✓ {model} SUCCESS with {max_tokens} tokens:")
                    print(f"  Content: {content.strip()}")
                    break  # Success - move on to the next model
                else:
                    print(f"  {max_tokens} tokens: Empty content")
                    
            except Exception as e:
                print(f"  {max_tokens} tokens: Error - {str(e)[:100]}")

def test_gpt4_comparison():
    """Test with GPT-4o-mini for comparison"""
    
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
        {"role": "user", "content": "What is 2+2? Answer briefly."}
    ]
    
    print(f"\n=== Testing GPT-4o-mini for Comparison ===")
    
    try:
        service = OpenAIService(model="gpt-4o-mini")
        result = service.chat_completion_json(
            messages=messages,
            json_schema=schema,
            temperature=0.1,
            max_tokens=100
        )
        print(f"✓ GPT-4o-mini SUCCESS:")
        print(f"  Answer: {result.get('answer')}")
        print(f"  Confidence: {result.get('confidence')}")
        
    except Exception as e:
        print(f"✗ GPT-4o-mini FAILED: {e}")

def main():
    """Run reasoning token tests"""
    print("Testing GPT-5 Reasoning Token Behavior")
    print("=" * 50)
    
    # Check API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not found")
        return
    
    test_reasoning_token_behavior()
    test_without_structured_outputs()
    test_gpt4_comparison()
    
    print(f"\n{'=' * 50}")
    print("Done. See the per-model output above for results.")

if __name__ == "__main__":
    main()