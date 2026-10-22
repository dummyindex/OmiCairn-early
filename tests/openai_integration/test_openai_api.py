#!/usr/bin/env python3
"""Comprehensive tests for OpenAI API integration using gpt-4o-mini."""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from openai import OpenAI

# Import local modules
try:
    from llm_service.openai_service import OpenAIService
    from config import config
except ImportError:
    # Try alternative import
    from omicairn_agent_local.llm_service.openai_service import OpenAIService
    from omicairn_agent_local.config import config


# Load environment variables
load_dotenv()


class TestOpenAIAPI:
    """Test suite for OpenAI API functionality."""
    
    def __init__(self):
        """Initialize test suite."""
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = OpenAI(api_key=self.api_key)
        self.service = OpenAIService(api_key=self.api_key)
        # Update the service's model
        self.service.model = self.model
        self.results = []
    
    def test_basic_completion(self):
        """Test basic chat completion."""
        print("\n=== Test 1: Basic Chat Completion ===")
        
        try:
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is 2+2? Reply with just the number."}
            ]
            
            response = self.service.chat_completion(
                messages=messages,
                temperature=0,
                max_tokens=10
            )
            
            print(f"Response: {response}")
            success = "4" in response
            print(f"Result: {'✓ PASSED' if success else '✗ FAILED'}")
            
            self.results.append(("Basic Completion", success))
            return success
            
        except Exception as e:
            print(f"Error: {e}")
            self.results.append(("Basic Completion", False))
            return False
    
    def test_json_mode(self):
        """Test JSON mode response."""
        print("\n=== Test 2: JSON Mode ===")
        
        try:
            messages = [
                {"role": "system", "content": "You are a helpful assistant that outputs JSON."},
                {"role": "user", "content": "Create a JSON object with fields: name (string), age (number), and active (boolean). Use example values."}
            ]
            
            # For simpler JSON mode, just use regular completion with JSON instruction
            response = self.service.chat_completion(
                messages=messages,
                temperature=0,
                max_tokens=100,
                response_format={"type": "json_object"}
            )
            
            print(f"Response: {response}")
            
            # Parse JSON response
            try:
                data = json.loads(response)
                has_fields = all(field in data for field in ["name", "age", "active"])
                print(f"Parsed JSON: {data}")
                print(f"Has required fields: {has_fields}")
                success = has_fields
            except json.JSONDecodeError:
                print("Failed to parse JSON")
                success = False
            
            print(f"Result: {'✓ PASSED' if success else '✗ FAILED'}")
            self.results.append(("JSON Mode", success))
            return success
            
        except Exception as e:
            print(f"Error: {e}")
            self.results.append(("JSON Mode", False))
            return False
    
    def test_code_extraction(self):
        """Test code extraction from response."""
        print("\n=== Test 3: Code Extraction ===")
        
        try:
            messages = [
                {"role": "system", "content": "You are a helpful coding assistant."},
                {"role": "user", "content": "Write a Python function to calculate factorial. Use markdown code blocks."}
            ]
            
            response = self.service.chat_completion(
                messages=messages,
                temperature=0,
                max_tokens=200
            )
            
            print(f"Raw Response: {response[:200]}...")
            
            # Extract code block
            code = self.service.extract_code_block(response)
            
            if code:
                print(f"\nExtracted Code:\n{code}")
                # Check if it's valid Python
                try:
                    compile(code, '<string>', 'exec')
                    print("Code is valid Python")
                    success = True
                except SyntaxError:
                    print("Code has syntax errors")
                    success = False
            else:
                print("No code block found")
                success = False
            
            print(f"Result: {'✓ PASSED' if success else '✗ FAILED'}")
            self.results.append(("Code Extraction", success))
            return success
            
        except Exception as e:
            print(f"Error: {e}")
            self.results.append(("Code Extraction", False))
            return False
    
    def test_function_calling(self):
        """Test function calling capability."""
        print("\n=== Test 4: Function Calling ===")
        
        try:
            # Define a function schema
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get the weather for a location",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string",
                                    "description": "A location name, e.g. Springfield"
                                },
                                "unit": {
                                    "type": "string",
                                    "enum": ["celsius", "fahrenheit"],
                                    "description": "The unit for temperature"
                                }
                            },
                            "required": ["location"]
                        }
                    }
                }
            ]
            
            messages = [
                {"role": "user", "content": "What's the weather in Springfield?"}
            ]
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            
            # Check if function was called
            if response.choices[0].message.tool_calls:
                tool_call = response.choices[0].message.tool_calls[0]
                print(f"Function called: {tool_call.function.name}")
                print(f"Arguments: {tool_call.function.arguments}")
                
                # Parse arguments
                args = json.loads(tool_call.function.arguments)
                success = "location" in args and "Springfield" in args["location"]
            else:
                print("No function call made")
                success = False
            
            print(f"Result: {'✓ PASSED' if success else '✗ FAILED'}")
            self.results.append(("Function Calling", success))
            return success
            
        except Exception as e:
            print(f"Error: {e}")
            self.results.append(("Function Calling", False))
            return False
    
    def test_streaming(self):
        """Test streaming response."""
        print("\n=== Test 5: Streaming Response ===")
        
        try:
            messages = [
                {"role": "user", "content": "Count from 1 to 5, one number per line."}
            ]
            
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0,
                max_tokens=50
            )
            
            chunks = []
            print("Streaming chunks:")
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    chunks.append(content)
                    print(f"  Chunk: {repr(content)}")
            
            full_response = "".join(chunks)
            print(f"\nFull response: {full_response}")
            
            # Check if numbers 1-5 are in response
            has_numbers = all(str(i) in full_response for i in range(1, 6))
            success = has_numbers
            
            print(f"Result: {'✓ PASSED' if success else '✗ FAILED'}")
            self.results.append(("Streaming", success))
            return success
            
        except Exception as e:
            print(f"Error: {e}")
            self.results.append(("Streaming", False))
            return False
    
    def test_context_length(self):
        """Test handling of context length."""
        print("\n=== Test 6: Context Length Handling ===")
        
        try:
            # Create a long context
            long_text = "This is a test sentence. " * 100
            
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": f"Summarize this text in one sentence: {long_text}"}
            ]
            
            response = self.service.chat_completion(
                messages=messages,
                temperature=0,
                max_tokens=50
            )
            
            print(f"Long text length: {len(long_text)} characters")
            print(f"Response: {response}")
            
            success = len(response) > 0 and len(response) < len(long_text)
            print(f"Result: {'✓ PASSED' if success else '✗ FAILED'}")
            
            self.results.append(("Context Length", success))
            return success
            
        except Exception as e:
            print(f"Error: {e}")
            self.results.append(("Context Length", False))
            return False
    
    def test_error_handling(self):
        """Test error handling for invalid requests."""
        print("\n=== Test 7: Error Handling ===")
        
        try:
            # Test with invalid model
            try:
                response = self.client.chat.completions.create(
                    model="invalid-model-name",
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=10
                )
                print("No error raised for invalid model")
                success = False
            except Exception as e:
                print(f"Expected error caught: {type(e).__name__}")
                success = True
            
            print(f"Result: {'✓ PASSED' if success else '✗ FAILED'}")
            self.results.append(("Error Handling", success))
            return success
            
        except Exception as e:
            print(f"Unexpected error: {e}")
            self.results.append(("Error Handling", False))
            return False
    
    def test_rate_limiting(self):
        """Test rate limit handling."""
        print("\n=== Test 8: Rate Limiting ===")
        
        try:
            print("Making rapid requests to test rate limiting...")
            
            messages = [{"role": "user", "content": "Hi"}]
            
            start_time = time.time()
            request_times = []
            
            # Make 5 rapid requests
            for i in range(5):
                req_start = time.time()
                
                response = self.service.chat_completion(
                    messages=messages,
                    temperature=0,
                    max_tokens=10
                )
                
                req_time = time.time() - req_start
                request_times.append(req_time)
                print(f"  Request {i+1}: {req_time:.2f}s")
            
            total_time = time.time() - start_time
            avg_time = sum(request_times) / len(request_times)
            
            print(f"\nTotal time: {total_time:.2f}s")
            print(f"Average request time: {avg_time:.2f}s")
            
            # Success if all requests completed
            success = len(request_times) == 5
            print(f"Result: {'✓ PASSED' if success else '✗ FAILED'}")
            
            self.results.append(("Rate Limiting", success))
            return success
            
        except Exception as e:
            print(f"Error: {e}")
            self.results.append(("Rate Limiting", False))
            return False
    
    def test_model_info(self):
        """Test model information and availability."""
        print("\n=== Test 9: Model Information ===")
        
        try:
            # List available models
            models = self.client.models.list()
            
            print(f"Using model: {self.model}")
            
            # Check if our model is available
            model_ids = [model.id for model in models.data]
            
            # Check for gpt-4o-mini specifically
            has_mini = any("gpt-4o-mini" in model_id for model_id in model_ids)
            
            if has_mini:
                print(f"✓ Model {self.model} is available")
                
                # Test the model
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": "Say 'test'"}],
                    max_tokens=10
                )
                
                print(f"Model response: {response.choices[0].message.content}")
                success = True
            else:
                print(f"✗ Model {self.model} not found")
                print(f"Available GPT models: {[m for m in model_ids if 'gpt' in m][:5]}")
                success = False
            
            print(f"Result: {'✓ PASSED' if success else '✗ FAILED'}")
            self.results.append(("Model Info", success))
            return success
            
        except Exception as e:
            print(f"Error: {e}")
            self.results.append(("Model Info", False))
            return False
    
    def test_embeddings(self):
        """Test embeddings API."""
        print("\n=== Test 10: Embeddings ===")
        
        try:
            # Create embeddings
            text = "This is a test sentence for embeddings."
            
            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            
            embedding = response.data[0].embedding
            print(f"Text: {text}")
            print(f"Embedding dimensions: {len(embedding)}")
            print(f"First 5 values: {embedding[:5]}")
            
            # Check embedding properties
            success = (
                len(embedding) > 0 and
                all(isinstance(x, float) for x in embedding[:5])
            )
            
            print(f"Result: {'✓ PASSED' if success else '✗ FAILED'}")
            self.results.append(("Embeddings", success))
            return success
            
        except Exception as e:
            print(f"Error: {e}")
            self.results.append(("Embeddings", False))
            return False
    
    def run_all_tests(self):
        """Run all tests."""
        print("="*60)
        print("OpenAI API Test Suite")
        print(f"Model: {self.model}")
        print(f"API Key: {'set' if self.api_key else 'missing'}")
        print("="*60)
        
        # Run tests
        tests = [
            self.test_basic_completion,
            self.test_json_mode,
            self.test_code_extraction,
            self.test_function_calling,
            self.test_streaming,
            self.test_context_length,
            self.test_error_handling,
            self.test_rate_limiting,
            self.test_model_info,
            self.test_embeddings
        ]
        
        for test in tests:
            try:
                test()
                time.sleep(0.5)  # Small delay between tests
            except Exception as e:
                print(f"\nTest crashed: {e}")
                self.results.append((test.__name__, False))
        
        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        for test_name, success in self.results:
            status = "✓ PASSED" if success else "✗ FAILED"
            print(f"{test_name:.<50} {status}")
        
        passed = sum(1 for _, success in self.results if success)
        total = len(self.results)
        print(f"\nTotal: {passed}/{total} passed")
        
        return passed == total


def test_specific_function_block_generation():
    """Test generating a specific function block for single-cell analysis."""
    print("\n" + "="*60)
    print("Function Block Generation Test")
    print("="*60)
    
    service = OpenAIService(api_key=os.getenv("OPENAI_API_KEY"))
    service.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    # Test generating a function block
    prompt = """
    Generate a Python function block for single-cell RNA-seq analysis with these requirements:
    1. Function name: process_single_cell_data
    2. Input: AnnData object
    3. Operations: normalize, find variable features, PCA
    4. Output: processed AnnData object
    
    Return only the Python code in a markdown code block.
    """
    
    messages = [
        {"role": "system", "content": "You are an expert in single-cell RNA-seq analysis."},
        {"role": "user", "content": prompt}
    ]
    
    response = service.chat_completion(messages, temperature=0, max_tokens=500)
    code = service.extract_code_block(response)
    
    if code:
        print("Generated Function Block:")
        print("-" * 40)
        print(code)
        print("-" * 40)
        
        # Validate the code
        try:
            compile(code, '<string>', 'exec')
            print("✓ Code is syntactically valid")
            
            # Check for required elements
            has_function = "def process_single_cell_data" in code
            has_scanpy = "scanpy" in code or "sc." in code
            has_normalize = "normalize" in code
            has_pca = "pca" in code or "PCA" in code
            
            print(f"Has function definition: {has_function}")
            print(f"Uses scanpy: {has_scanpy}")
            print(f"Has normalization: {has_normalize}")
            print(f"Has PCA: {has_pca}")
            
            success = all([has_function, has_normalize, has_pca])
            print(f"\nResult: {'✓ PASSED' if success else '✗ FAILED'}")
            return success
            
        except SyntaxError as e:
            print(f"✗ Syntax error: {e}")
            return False
    else:
        print("✗ No code block extracted")
        return False


def main():
    """Run all tests."""
    print("="*60)
    print("OpenAI API Integration Tests")
    print(f"Timestamp: {datetime.now()}")
    print("="*60)
    
    # Check environment
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not found in environment")
        print("Please ensure .env file exists with the API key")
        return False
    
    # Run main test suite
    try:
        tester = TestOpenAIAPI()
        main_success = tester.run_all_tests()
    except Exception as e:
        print(f"\nFatal error in main tests: {e}")
        main_success = False
    
    # Run function block generation test
    try:
        fb_success = test_specific_function_block_generation()
    except Exception as e:
        print(f"\nError in function block test: {e}")
        fb_success = False
    
    # Final summary
    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)
    print(f"Main Test Suite: {'✓ PASSED' if main_success else '✗ FAILED'}")
    print(f"Function Block Generation: {'✓ PASSED' if fb_success else '✗ FAILED'}")
    
    return main_success and fb_success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)