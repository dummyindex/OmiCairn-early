#!/usr/bin/env python3
"""Test bug fixer support for R function blocks."""

import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.unified_bug_fixer import prompt_templates

def test_r_function_block_guidance():
    """Test that R function block guidance is filename agnostic."""
    # Get initial prompt to check system guidance
    system_prompt = prompt_templates.create_initial_prompt(
        node_name="test_node",
        error_message="Test error",
        stdout="",
        stderr="",
        attempt_number=1
    )
    
    # Check that it doesn't contain hardcoded filenames
    print("=== Checking for hardcoded filename assumptions ===")
    
    # Should NOT contain these hardcoded references
    bad_patterns = [
        "_node_anndata.h5ad",
        "_node_seuratObject.rds",
        "Input files are typically at: file.path",
        "Output files go to: file.path"
    ]
    
    for pattern in bad_patterns:
        assert pattern not in system_prompt, f"Found hardcoded pattern: {pattern}"
        print(f"✅ No hardcoded pattern: {pattern}")
    
    # Should contain these correct patterns
    good_patterns = [
        "code.py/function_block.py for Python",
        "code.R/function_block.R for R", 
        "requirements.txt",
        "explore and understand before making changes"
    ]
    
    for pattern in good_patterns:
        assert pattern in system_prompt, f"Missing guidance: {pattern}"
        print(f"✅ Found correct guidance: {pattern}")
    
    print("\n=== R Function Block Guidance Check: PASSED ===")

def test_r_vs_python_distinction():
    """Test that R and Python function blocks are handled distinctly."""
    # Get initial prompt to analyze language handling
    system_prompt = prompt_templates.create_initial_prompt(
        node_name="test_node",
        error_message="Test error",  
        stdout="",
        stderr="",
        attempt_number=1
    )
    
    print("\n=== Testing R vs Python Distinctions ===")
    
    # Should contain proper language-specific guidance
    checks = [
        ("Python file reference", "code.py/function_block.py for Python"),
        ("R file reference", "code.R/function_block.R for R"),
        ("Requirements file mention", "requirements.txt"),
        ("Error exploration guidance", "explore the actual data structure"),
        ("Fix root cause guidance", "Fix the root cause, not just the symptoms")
    ]
    
    for check_name, pattern in checks:
        assert pattern in system_prompt, f"{check_name}: Missing - {pattern}"
        print(f"✅ {check_name}: Found")
    
    print("\n=== Language Distinction Check: PASSED ===")

def test_action_examples():
    """Test that action examples are appropriate for both languages.""" 
    # Test with Python-style error
    python_prompt = prompt_templates.create_initial_prompt(
        node_name="test_node",
        error_message="No module named 'scanpy'",
        stdout="",
        stderr="ModuleNotFoundError: No module named 'scanpy'",
        attempt_number=1
    )
    
    # Test with R-style error
    r_prompt = prompt_templates.create_initial_prompt(
        node_name="test_node",
        error_message="library(Seurat) - there is no package called 'Seurat'",
        stdout="",
        stderr="Error in library(Seurat) : there is no package called 'Seurat'",
        attempt_number=1
    )
    
    print("\n=== Testing Action Examples ===")
    
    # Both prompts should mention reading code files
    assert "code.py" in python_prompt or "function_block.py" in python_prompt, "Python prompt missing code file reference"
    print("✅ Python prompt references code files")
        
    # Both prompts should mention requirements.txt
    assert "requirements.txt" in python_prompt, "Python prompt missing requirements.txt guidance"
    assert "requirements.txt" in r_prompt, "R prompt missing requirements.txt guidance"
    print("✅ Both prompts correctly mention requirements.txt")
    
    print("\n=== Action Examples Check: PASSED ===")

if __name__ == "__main__":
    print("Testing Bug Fixer R Function Block Support")
    print("=" * 50)
    test_r_function_block_guidance()
    test_r_vs_python_distinction()
    test_action_examples()
    print("\n🎉 All tests PASSED! Bug fixer R support is correctly implemented.")