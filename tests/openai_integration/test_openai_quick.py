#!/usr/bin/env python3
"""Quick test to verify OpenAI API key and model."""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

def quick_test():
    """Quick test of OpenAI API."""
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found in .env file")
        return False
    
    print(f"API Key: {'set' if api_key else 'missing'}")
    print(f"Model: {model}")
    
    try:
        client = OpenAI(api_key=api_key)
        
        # Simple test
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "Say 'API test successful' if you can read this."}
            ],
            max_tokens=20,
            temperature=0
        )
        
        result = response.choices[0].message.content
        print(f"\nResponse: {result}")
        
        if "successful" in result.lower():
            print("✓ OpenAI API is working correctly!")
            return True
        else:
            print("✗ Unexpected response")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


if __name__ == "__main__":
    success = quick_test()
    sys.exit(0 if success else 1)