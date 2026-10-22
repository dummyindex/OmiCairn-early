#!/usr/bin/env python3
"""Simple test to verify input context functionality."""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from agents.function_creator_agent import FunctionCreatorAgent
from llm_service.openai_service import OpenAIService

def test_input_context():
    """Test that input context is passed to function creator."""
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        return False
    
    # Create LLM service and agent
    llm_service = OpenAIService(api_key=api_key, model="gpt-4o-mini")
    agent = FunctionCreatorAgent(llm_service=llm_service)
    
    # Test with root node context
    root_context = {
        'is_root_node': True,
        'available_files': ['patient_sample_001.h5ad', 'control_group.h5ad', 'metadata.csv']
    }
    
    spec = {
        "name": "load_patient_data",
        "description": "Load patient sample data from available files",
        "parent_output": None
    }
    
    print("Testing function creation with input context...")
    print(f"Available files: {root_context['available_files']}")
    
    try:
        result = agent.create_from_specification(spec, input_context=root_context)
        
        if result:
            print("\nFunction created successfully!")
            print(f"Name: {result.name}")
            print(f"Description: {result.description}")
            print("\nGenerated code:")
            print("=" * 50)
            print(result.code)
            print("=" * 50)
            
            # Check if the code mentions the available files
            if any(fname in result.code for fname in root_context['available_files']):
                print("\n✓ SUCCESS: Generated code references the available files!")
                return True
            else:
                print("\n✗ FAILED: Generated code doesn't reference the specific files")
                return False
        else:
            print("\nError: Failed to create function")
            return False
            
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_input_context()
    sys.exit(0 if success else 1)