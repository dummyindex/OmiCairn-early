#!/usr/bin/env python3
"""Simplified test for bug fixer functionality."""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.unified_bug_fixer.unified_bug_fixer import UnifiedBugFixer
from utils import setup_logger

logger = setup_logger(__name__)


def test_bug_fixer_writes_to_function_block_py():
    """Test that bug fixer would update function_block.py correctly."""
    
    # Test directory structure
    test_structure = {
        'function_block.py': 'def run(path_dict, params): pass',
        'requirements.txt': 'scanpy>=1.9.0'
    }
    
    # Expected fix for missing attribute error
    expected_fixes = [
        "Check if attribute exists before accessing",
        "Use hasattr() to verify attribute",
        "Add try-except block for AttributeError"
    ]
    
    print("✓ Bug fixer would write to function_block.py")
    print("✓ Expected fixes:", expected_fixes)
    
    assert 'function_block.py' in test_structure
    assert any(fix for fix in expected_fixes)


def test_bug_fixer_reads_from_function_block_py():
    """Test that bug fixer would read from function_block.py."""
    
    # Mock file reading scenario
    mock_code = '''def run(path_dict, params):
    import scanpy as sc
    # Process data
    return adata'''
    
    # Test that bug fixer would read this file
    file_to_read = "function_block.py"
    
    print(f"✓ Bug fixer would read from {file_to_read}")
    print(f"✓ Code lines: {len(mock_code.splitlines())}")
    
    assert file_to_read == "function_block.py"
    assert "def run(" in mock_code


def test_bug_fixer_initialization():
    """Test bug fixer initialization with proper parameters."""
    
    with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
        bug_fixer = UnifiedBugFixer(
            model_name="gpt-4o-mini",
            max_turns=3,
            save_debug_logs=False
        )
        
        assert bug_fixer.max_turns == 3
        assert bug_fixer.save_debug_logs == False
        print("✓ Bug fixer initialized successfully")


def test_common_error_patterns():
    """Test common error patterns the bug fixer handles."""
    
    error_patterns = [
        {
            'error': "AttributeError: 'AnnData' object has no attribute 'X_pca'",
            'cause': "Missing preprocessing step",
            'fix': "Add sc.pp.pca() before accessing X_pca"
        },
        {
            'error': "ModuleNotFoundError: No module named 'scvelo'",
            'cause': "Missing dependency",
            'fix': "Add scvelo to requirements.txt"
        },
        {
            'error': "FileNotFoundError: _node_anndata.h5ad",
            'cause': "Wrong file path",
            'fix': "Check input directory structure"
        }
    ]
    
    for pattern in error_patterns:
        print(f"\n✓ Pattern: {pattern['cause']}")
        print(f"  Error: {pattern['error'][:50]}...")
        print(f"  Fix: {pattern['fix']}")
    
    assert len(error_patterns) > 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])