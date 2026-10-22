#!/usr/bin/env python3
"""Test bug fixer improvements with web agent integration."""

import json
import time
from pathlib import Path
import tempfile
import shutil

from agents.unified_bug_fixer import UnifiedBugFixer
from utils import setup_logger

logger = setup_logger(__name__)


def create_test_environment():
    """Create a test environment with a failing function block."""
    test_dir = tempfile.mkdtemp(prefix="bug_fixer_test_")
    test_path = Path(test_dir)
    
    # Create a code.py with palantir API error
    code_content = '''import scanpy as sc
import matplotlib.pyplot as plt
import palantir

def run(path_dict, params):
    """Run pseudotime analysis with multiple methods."""
    import os
    
    # Load data
    adata = sc.read_h5ad(os.path.join(path_dict['input_dir'], '_node_anndata.h5ad'))
    
    # Run DPT
    sc.tl.diffmap(adata)
    adata.uns['iroot'] = 0
    sc.tl.dpt(adata)
    adata.obs['dpt'] = adata.obs['dpt_pseudotime']
    
    # Run Palantir (WRONG API - this will fail)
    adata.obs['alt_pseudotime'] = palantir.pseudotime(adata)
    
    # Save results
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    adata.write_h5ad(os.path.join(path_dict['output_dir'], '_node_anndata.h5ad'))
'''
    
    (test_path / "code.py").write_text(code_content)
    
    # Create requirements.txt
    (test_path / "requirements.txt").write_text("scanpy\nmatplotlib\npalantir\n")
    
    # Create config.json
    config = {
        "name": "test_pseudotime",
        "description": "Test pseudotime with palantir error"
    }
    (test_path / "config.json").write_text(json.dumps(config))
    
    return test_path


def test_bug_fixer_with_web_agent():
    """Test that bug fixer properly uses web agent findings to fix code."""
    logger.info("=== Testing Bug Fixer with Web Agent ===")
    
    # Create test environment
    test_dir = create_test_environment()
    logger.info(f"Created test environment at: {test_dir}")
    
    try:
        # Initialize bug fixer with web agent
        bug_fixer = UnifiedBugFixer(
            model_name="gpt-4o-mini",
            max_turns=3,
            enable_web_agent=True
        )
        
        # Create a realistic error message
        error_message = """Container exited with code 1
AttributeError: module 'palantir' has no attribute 'pseudotime'
  File "/workspace/code.py", line 18, in run
    adata.obs['alt_pseudotime'] = palantir.pseudotime(adata)
AttributeError: module 'palantir' has no attribute 'pseudotime'"""
        
        stdout = "Starting preprocessing...\nDPT analysis completed.\nStarting alternative pseudotime analysis..."
        stderr = "AttributeError: module 'palantir' has no attribute 'pseudotime'"
        
        # Run bug fixer
        logger.info("Starting bug fix attempt...")
        start_time = time.time()
        
        result = bug_fixer.fix_bug(
            node_name="test_pseudotime",
            error_message=error_message,
            working_directory=test_dir,
            stdout=stdout,
            stderr=stderr,
            attempt_number=1
        )
        
        duration = time.time() - start_time
        
        # Check results
        logger.info(f"Bug fix completed in {duration:.1f}s")
        logger.info(f"Success: {result['success']}")
        logger.info(f"Turns: {result['turn_count']}")
        logger.info(f"Actions taken: {len(result['actions_taken'])}")
        
        # Analyze actions
        action_types = [a['action']['type'] for a in result['actions_taken']]
        logger.info(f"Action types: {action_types}")
        
        # Check if code was modified
        code_modified = 'write_file' in action_types
        logger.info(f"Code modified: {code_modified}")
        
        if code_modified:
            # Read the modified code
            modified_code = (test_dir / "code.py").read_text()
            logger.info("Modified code snippet:")
            logger.info(modified_code[500:800])  # Show relevant part
            
        # Print summary
        logger.info("\n=== Summary ===")
        logger.info(f"Web agent research triggered: {'web_agent_research' in str(test_dir.iterdir())}")
        logger.info(f"Code was modified: {code_modified}")
        logger.info(f"Fix successful: {result['success']}")
        
        return result
        
    finally:
        # Cleanup
        shutil.rmtree(test_dir)
        logger.info(f"Cleaned up test directory")


def test_web_agent_timeout():
    """Test that web agent respects timeout settings."""
    logger.info("\n=== Testing Web Agent Timeout ===")
    
    from agents.web_agent_langgraph.web_agent_tool import WebAgentTool
    import asyncio
    
    # Create tool with short timeout
    tool = WebAgentTool(timeout_seconds=5)
    
    # Test with a complex query that would take longer
    error_msg = "Complex error requiring extensive research " * 10
    context = {"library": "complex_lib", "function": "complex_func"}
    
    research_dir = Path(tempfile.mkdtemp(prefix="test_timeout_"))
    
    async def run_research():
        start = time.time()
        result = await tool.research_error(
            error_message=error_msg,
            context=context,
            output_folder=research_dir,
            research_type="detailed"
        )
        duration = time.time() - start
        return result, duration
    
    result, duration = asyncio.run(run_research())
    
    logger.info(f"Research duration: {duration:.1f}s")
    logger.info(f"Success: {result['success']}")
    if not result['success']:
        logger.info(f"Error: {result['error']}")
    
    # Cleanup
    import shutil
    if research_dir.exists():
        shutil.rmtree(research_dir)


if __name__ == "__main__":
    # Test 1: Bug fixer with web agent
    test_bug_fixer_with_web_agent()
    
    # Test 2: Web agent timeout
    test_web_agent_timeout()