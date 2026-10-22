#!/usr/bin/env python3
"""Debug LLM schema validation for GPT-4o-mini."""

import json
import os
from pathlib import Path

# Add to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from omicairn_agent_local.llm_service import OpenAIService
from omicairn_agent_local.agents.schemas import (
    FunctionBlockContent, FunctionBlockRecommendation, StaticConfig
)
from omicairn_agent_local.models import Arg


def test_schema_validation():
    """Test schema validation with GPT-4o-mini."""
    
    # Get API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        return
    
    llm_service = OpenAIService(api_key=api_key)
    llm_service.model = "gpt-4o-mini"
    
    # Simple test prompt
    system_prompt = """You are a function block generator. Generate a function block for clustering analysis."""
    
    user_prompt = """Generate a function block that performs clustering on scRNA-seq data.
    
    Return a JSON with:
    - satisfied: true
    - next_level_function_blocks: array with one function block
    - reasoning: brief explanation
    
    Each function block should have:
    - name: string
    - function_block_code: string (Python code)
    - requirements_file_content: string (package names)
    - static_config_file_content: object with args, description, tag
    - parameters: object (can be empty)
    - new: true
    - rest_task: null or string
    """
    
    # Test 1: Full schema
    print("Test 1: Using full FunctionBlockRecommendation schema")
    print("-" * 60)
    
    try:
        schema = {
            "name": "function_block_recommendation",
            "schema": FunctionBlockRecommendation.model_json_schema()
        }
        
        print("Schema being sent:")
        print(json.dumps(schema, indent=2))
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        result = llm_service.chat_completion_json(
            messages=messages,
            json_schema=schema,
            temperature=0.3,
            max_tokens=2000
        )
        
        print("\nLLM Response:")
        print(json.dumps(result, indent=2))
        
        # Try to validate
        recommendation = FunctionBlockRecommendation(**result)
        print("\n✓ Validation successful!")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
    
    # Test 2: Simplified schema
    print("\n\nTest 2: Using simplified schema")
    print("-" * 60)
    
    try:
        simple_schema = {
            "name": "clustering_function",
            "schema": {
                "type": "object",
                "properties": {
                    "satisfied": {"type": "boolean"},
                    "next_level_function_blocks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "function_block_code": {"type": "string"},
                                "requirements_file_content": {"type": "string"},
                                "static_config_file_content": {
                                    "type": "object",
                                    "properties": {
                                        "args": {"type": "array"},
                                        "description": {"type": "string"},
                                        "tag": {"type": "string"}
                                    }
                                },
                                "parameters": {"type": "object"},
                                "new": {"type": "boolean"},
                                "rest_task": {"type": ["string", "null"]}
                            },
                            "required": ["name", "function_block_code", "requirements_file_content", "static_config_file_content"]
                        }
                    },
                    "reasoning": {"type": "string"}
                },
                "required": ["satisfied", "next_level_function_blocks", "reasoning"]
            }
        }
        
        print("Simplified schema being sent:")
        print(json.dumps(simple_schema, indent=2))
        
        result = llm_service.chat_completion_json(
            messages=messages,
            json_schema=simple_schema,
            temperature=0.3,
            max_tokens=2000
        )
        
        print("\nLLM Response:")
        print(json.dumps(result, indent=2))
        
        # Manual validation
        if "satisfied" in result and "next_level_function_blocks" in result:
            print("\n✓ Response has required fields!")
            
            # Check function blocks
            for fb in result["next_level_function_blocks"]:
                print(f"\nFunction block: {fb.get('name', 'unnamed')}")
                print(f"  - Has code: {'function_block_code' in fb}")
                print(f"  - Has requirements: {'requirements_file_content' in fb}")
                print(f"  - Has static_config: {'static_config_file_content' in fb}")
                
                if 'static_config_file_content' in fb:
                    config = fb['static_config_file_content']
                    print(f"  - Config type: {type(config)}")
                    if isinstance(config, dict):
                        print(f"  - Config keys: {list(config.keys())}")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_schema_validation()