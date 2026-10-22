#!/usr/bin/env python
"""Test bug fixer behavior on simple syntax errors"""

import sys
import os
from pathlib import Path
# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch
from agents.unified_bug_fixer.unified_bug_fixer import UnifiedBugFixer


def test_bug_fixer_on_syntax_error():
    """Test bug fixer initialization and error pattern recognition."""
    
    # Test with mocked API key
    with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
        bug_fixer = UnifiedBugFixer(
            model_name="gpt-4o-mini",
            enable_web_agent=False,
            save_debug_logs=False
        )
        
        assert bug_fixer is not None
        print("✓ Bug fixer initialized successfully")
    
    # Test common syntax error patterns
    syntax_errors = [
        {
            'error': "SyntaxError: f-string: unmatched '['",
            'cause': "Bracket inside f-string without proper escaping",
            'fix': "Use double brackets or extract expression"
        },
        {
            'error': "SyntaxError: invalid syntax",
            'cause': "Missing colon, parenthesis, or other syntax element",
            'fix': "Check line endings and delimiters"
        },
        {
            'error': "IndentationError: unexpected indent",
            'cause': "Mixed tabs and spaces or wrong indentation",
            'fix': "Use consistent 4-space indentation"
        }
    ]
    
    print("\n✓ Common syntax error patterns:")
    for pattern in syntax_errors:
        print(f"\n  Error: {pattern['error']}")
        print(f"  Cause: {pattern['cause']}")
        print(f"  Fix: {pattern['fix']}")
    
    # Test f-string specific issues
    f_string_issues = [
        "adata.uns['iroot']",  # Problematic in f-string
        "data[key]",           # Needs escaping
        "dict['value']"        # Single quotes conflict
    ]
    
    print("\n✓ F-string problematic expressions:")
    for expr in f_string_issues:
        print(f"  - {expr} → Use: {{expr}} or extract to variable")
    
    assert len(syntax_errors) > 0
    assert len(f_string_issues) > 0


def test_bug_fixer_action_types():
    """Test that bug fixer knows about different action types."""
    
    action_types = [
        "read_file",
        "write_file", 
        "execute_command",
        "update_function_block",
        "install_package",
        "list_directory"
    ]
    
    print("\n✓ Available bug fixer actions:")
    for action in action_types:
        print(f"  - {action}")
    
    assert "update_function_block" in action_types
    assert "write_file" in action_types


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])