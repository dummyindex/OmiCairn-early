#!/usr/bin/env python3
"""Test script for the full agent system with LLM capabilities."""

import sys
from pathlib import Path
import os

# Add the package to path
sys.path.insert(0, str(Path(__file__).parent))

from omicairn_agent_local.agents import MainAgent
from omicairn_agent_local.utils import setup_logger

# Set up logging
logger = setup_logger("test_agent_system")


def main():
    """Test the full agent system with LLM."""
    
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        print("Please set it with: export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)
    
    # Paths
    input_data = Path(os.environ.get("TEST_DATA_DIR", "test_data")) / "zebrafish.h5ad"
    user_request_file = Path(os.environ.get("TEST_DATA_DIR", "test_data")) / "user_request.txt"
    output_dir = Path("test_outputs") / "test_agent_output"
    
    # Read user request
    with open(user_request_file) as f:
        user_request = f.read().strip()
    
    print("=== OmiCairn Agent System Test ===")
    print(f"Input data: {input_data}")
    print(f"User request: {user_request}")
    print(f"Output directory: {output_dir}")
    print()
    
    # Create agent
    logger.info("Initializing agent...")
    agent = MainAgent(openai_api_key=api_key)
    
    # Validate environment first
    print("Validating environment...")
    validation = agent.validate_environment()
    for component, status in validation.items():
        status_str = "✓" if status else "✗"
        print(f"  {status_str} {component}")
    
    if not all(validation.values()):
        print("\nWarning: Some components are missing. The system may not work properly.")
        print("Please ensure Docker is running and images are built:")
        print("  cd omicairn_agent_local/docker && ./build.sh")
        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    # Run analysis
    print("\nStarting analysis...")
    try:
        result = agent.run_analysis(
            input_data_path=str(input_data),
            user_request=user_request,
            output_dir=str(output_dir),
            max_nodes=10,  # Limit for testing
            max_children=3,
            max_debug_trials=2,
            generation_mode="mixed",
            llm_model="gpt-4o-2024-08-06",
            verbose=True
        )
        
        print("\n=== Analysis Complete ===")
        print(f"Output directory: {result['output_dir']}")
        print(f"Total nodes executed: {result['completed_nodes']}")
        print(f"Failed nodes: {result['failed_nodes']}")
        print(f"Total duration: {result['total_duration_seconds']:.1f}s")
        print(f"Request satisfied: {result['satisfied']}")
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()