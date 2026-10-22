#!/usr/bin/env python3
"""Direct test of bug fixer with explicit web agent findings."""

import json
import tempfile
from pathlib import Path
import shutil

from agents.unified_bug_fixer import UnifiedBugFixer
from utils import setup_logger

logger = setup_logger(__name__)


def test_direct_fix():
    """Test bug fixer with direct web agent findings in error message."""
    
    # Create test directory
    test_dir = Path(tempfile.mkdtemp(prefix="direct_fix_test_"))
    
    # Create code.py with error
    code_content = '''import palantir

def run(path_dict, params):
    # This will fail with AttributeError
    result = palantir.pseudotime(data)
    return result
'''
    (test_dir / "code.py").write_text(code_content)
    (test_dir / "requirements.txt").write_text("palantir")
    
    # Create error message with web agent findings
    error_message = """AttributeError: module 'palantir' has no attribute 'pseudotime'

[Web Agent Research]:
Key Findings:
- The correct API for Palantir is: palantir.core.run_palantir()
- The pseudotime() function doesn't exist in the palantir module
- You need to use palantir.core.run_palantir() to compute pseudotime

Potential Solutions:
- Replace palantir.pseudotime(data) with palantir.core.run_palantir(data, start_cell)
- Import palantir.core module explicitly
- Set a start_cell parameter for the analysis

Code Examples:
```python
import palantir
import palantir.core

# Correct usage:
pr_result = palantir.core.run_palantir(
    adata.obsm['X_pca'][:, :30], 
    start_cell, 
    num_waypoints=1200,
    n_jobs=4
)
```

Sources:
- https://github.com/dpeerlab/Palantir (official documentation)"""
    
    try:
        # Initialize bug fixer
        bug_fixer = UnifiedBugFixer(
            model_name="gpt-4o-mini",
            max_turns=3,
            enable_web_agent=False  # Disable web agent since we provide findings
        )
        
        # Run fix
        logger.info("Running direct fix test...")
        result = bug_fixer.fix_bug(
            node_name="test_direct",
            error_message=error_message,
            working_directory=test_dir,
            stdout="",
            stderr="AttributeError: module 'palantir' has no attribute 'pseudotime'",
            attempt_number=1
        )
        
        # Check results
        logger.info(f"Success: {result['success']}")
        logger.info(f"Actions: {[a['action']['type'] for a in result['actions_taken']]}")
        
        # Check if code was modified
        if (test_dir / "code.py").exists():
            modified_code = (test_dir / "code.py").read_text()
            logger.info("Modified code:")
            logger.info(modified_code)
            
            # Check if the fix was applied
            if "palantir.core.run_palantir" in modified_code:
                logger.info("✓ Code was correctly modified with the suggested fix!")
            else:
                logger.info("✗ Code was not modified with the suggested fix")
        
    finally:
        shutil.rmtree(test_dir)
        logger.info("Cleaned up test directory")


if __name__ == "__main__":
    test_direct_fix()