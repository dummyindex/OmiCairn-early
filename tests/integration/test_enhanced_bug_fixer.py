#!/usr/bin/env python3
"""Test the enhanced bug fixer with forced solution proposal."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agents.unified_bug_fixer import UnifiedBugFixer
from utils import setup_logger

logger = setup_logger(__name__)


def test_enhanced_bug_fixer():
    """Test that bug fixer always proposes a solution on final turn."""
    
    # Create a test function block with an error
    buggy_code = '''def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Read input
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)
    
    # This will fail - accessing non-existent attribute
    adata.obs['dpt_pseudotime']  # KeyError: 'dpt_pseudotime' not in adata.obs
    
    # Save output
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
'''
    
    with tempfile.TemporaryDirectory() as temp_dir:
        work_dir = Path(temp_dir)
        
        # Create code file
        code_file = work_dir / "code.py"
        code_file.write_text(buggy_code)
        
        # Also create function_block.py
        fb_file = work_dir / "function_block.py"
        fb_file.write_text(buggy_code)
        
        # Create bug fixer with limited turns
        bug_fixer = UnifiedBugFixer(
            model_name="gpt-4o-mini",
            api_key=os.getenv("OPENAI_API_KEY"),
            max_turns=3,  # Limited turns to test forced solution
            save_debug_logs=False,
            enable_web_agent=False
        )
        
        # Test error message
        error_msg = "KeyError: 'dpt_pseudotime' not found in adata.obs"
        
        logger.info("\n=== Testing Enhanced Bug Fixer ===")
        logger.info(f"Max turns: {bug_fixer.max_turns}")
        logger.info(f"Error: {error_msg}")
        
        # Run bug fixing
        result = bug_fixer.fix_bug(
            node_name="test_dpt_analysis",
            error_message=error_msg,
            working_directory=work_dir,
            stderr=error_msg,
            attempt_number=1
        )
        
        # Check results
        logger.info(f"\n=== Results ===")
        logger.info(f"Success: {result['success']}")
        logger.info(f"Turns used: {result['turn_count']}")
        logger.info(f"Files modified: {result['files_modified']}")
        
        # Check if a solution was proposed
        solution_proposed = len(result['files_modified']) > 0
        logger.info(f"Solution proposed: {solution_proposed}")
        
        # Check the conversation for final turn
        messages = result.get('messages', [])
        final_turn_found = any(
            "This is the FINAL turn" in msg.get('content', '') 
            for msg in messages if msg['role'] == 'user'
        )
        logger.info(f"Final turn prompt used: {final_turn_found}")
        
        # Read modified code if exists
        if solution_proposed:
            for file_path in result['files_modified']:
                full_path = work_dir / file_path
                if full_path.exists():
                    logger.info(f"\n=== Modified {file_path} ===")
                    content = full_path.read_text()
                    # Show first 20 lines
                    lines = content.split('\n')[:20]
                    for i, line in enumerate(lines, 1):
                        logger.info(f"{i:3d}: {line}")
                    if len(content.split('\n')) > 20:
                        logger.info("     ... (truncated)")
        
        # Summary
        logger.info("\n=== Summary ===")
        if solution_proposed and final_turn_found:
            logger.info("✅ SUCCESS: Bug fixer proposed a solution on final turn")
        else:
            logger.error("❌ FAILED: Bug fixer did not propose a solution")
            
        return solution_proposed


if __name__ == "__main__":
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        sys.exit(1)
        
    success = test_enhanced_bug_fixer()
    sys.exit(0 if success else 1)