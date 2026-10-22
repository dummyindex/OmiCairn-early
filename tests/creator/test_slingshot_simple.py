#!/usr/bin/env python3
"""Simple test for Slingshot R function block creation."""

import os
from omicairn_agent_local.llm_service.openai_service import OpenAIService
from omicairn_agent_local.agents.function_creator_agent import FunctionCreatorAgent
from omicairn_agent_local.models import FunctionBlockType


def test_slingshot_creation():
    """Test that Slingshot is created as an R function block."""
    
    print("\n=== Testing Slingshot Creation ===\n")
    
    # Initialize services
    llm_service = OpenAIService(model="gpt-4o")
    creator = FunctionCreatorAgent(llm_service=llm_service)
    
    # Create context for Slingshot
    context = {
        "task_description": "Run Slingshot pseudotime analysis on Seurat object",
        "user_request": "Run Slingshot (R) pseudotime analysis. Load the Seurat object from RDS file, extract normalized expression data and dimensionality reduction (PCA), run Slingshot to compute pseudotime trajectories, and save the results as both RDS and CSV files."
    }
    
    print("Creating Slingshot function block...")
    function_block = creator.process(context)
    
    # Verify creation
    if function_block is None:
        print("✗ Failed to create function block")
        return
        
    print(f"\n✓ Created function block: {function_block.name}")
    print(f"  Type: {function_block.type}")
    print(f"  Language: {'R' if function_block.type == FunctionBlockType.R else 'Python'}")
    
    # Check if it's correctly identified as R
    if function_block.type != FunctionBlockType.R:
        print(f"\n✗ ERROR: Expected R type but got {function_block.type}")
        
    # Display requirements
    print(f"\nRequirements:")
    for req in function_block.requirements.split('\n'):
        if req.strip():
            print(f"  - {req.strip()}")
            
    # Display parameters
    if hasattr(function_block, 'parameters') and function_block.parameters:
        print(f"\nDefault Parameters:")
        for key, value in function_block.parameters.items():
            print(f"  - {key}: {value}")
            
    # Show first part of the code
    print(f"\nGenerated R Code (first 1000 chars):")
    print("=" * 60)
    print(function_block.code[:1000])
    print("=" * 60)
    
    # Analyze code structure
    print("\nCode Analysis:")
    code_patterns = [
        ("run <- function(path_dict, params)", "R function signature"),
        ("library(Seurat)", "Seurat library"),
        ("library(slingshot)", "Slingshot library"),
        ("readRDS", "RDS reading"),
        ("slingshot(", "Slingshot function"),
        ("write.csv", "CSV output"),
        ("saveRDS", "RDS output")
    ]
    
    found_count = 0
    for pattern, desc in code_patterns:
        if pattern in function_block.code:
            print(f"  ✓ {desc}")
            found_count += 1
        else:
            print(f"  ✗ Missing: {desc}")
            
    print(f"\nCode quality: {found_count}/{len(code_patterns)} patterns found")
    
    # Save the generated code for inspection
    output_file = "slingshot_generated_code.R"
    with open(output_file, 'w') as f:
        f.write(function_block.code)
    print(f"\n✓ Saved generated code to {output_file}")
    
    print("\n=== Test Complete ===\n")
    

if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set")
        exit(1)
        
    test_slingshot_creation()