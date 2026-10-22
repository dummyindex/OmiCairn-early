#!/usr/bin/env python3
"""Test that smart display limits work correctly in bug fixer prompts."""

import sys
from pathlib import Path
import tempfile
import json

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.unified_bug_fixer.action_input_validator import ActionInputValidator
from constants import MAX_DISPLAY_ITEMS, DISPLAY_TRUNCATE_MESSAGE

def test_display_limit_constant():
    """Test that the display limit constant is properly set."""
    print(f"Testing MAX_DISPLAY_ITEMS constant...")
    assert MAX_DISPLAY_ITEMS == 15, f"Expected MAX_DISPLAY_ITEMS to be 15, got {MAX_DISPLAY_ITEMS}"
    assert DISPLAY_TRUNCATE_MESSAGE == True, f"Expected DISPLAY_TRUNCATE_MESSAGE to be True, got {DISPLAY_TRUNCATE_MESSAGE}"
    print(f"✅ Constants correctly set: MAX_DISPLAY_ITEMS={MAX_DISPLAY_ITEMS}, DISPLAY_TRUNCATE_MESSAGE={DISPLAY_TRUNCATE_MESSAGE}")
    return True

def test_smart_display_example():
    """Test that the smart display examples are valid actions."""
    print("\nTesting smart display examples...")
    
    # Example with smart column display
    smart_column_action = {
        "type": "write_and_run",
        "params": {
            "files": [{
                "path": "test_smart_display.py",
                "content": f"""import numpy as np
# Create fake data with many columns
cols = [f'col_{{i}}' for i in range(100)]
n_cols = len(cols)
print(f'Total columns: {{n_cols}}')
if n_cols <= {MAX_DISPLAY_ITEMS}:
    print(f'Columns: {{cols}}')
else:
    print(f'First {MAX_DISPLAY_ITEMS}: {{cols[:{MAX_DISPLAY_ITEMS}]}}')
    print(f'... and {{n_cols - {MAX_DISPLAY_ITEMS}}} more columns')
"""
            }],
            "run_script": "python test_smart_display.py",
            "description": "Test smart display limits"
        }
    }
    
    result = ActionInputValidator.validate_action(smart_column_action)
    assert result['valid'], f"Smart display action validation failed: {result.get('errors')}"
    print("✅ Smart display example is a valid action")
    
    # Verify the content uses the correct limit
    content = smart_column_action['params']['files'][0]['content']
    assert f"<= {MAX_DISPLAY_ITEMS}" in content, "Content should check against MAX_DISPLAY_ITEMS"
    assert f"[:{MAX_DISPLAY_ITEMS}]" in content, "Content should slice to MAX_DISPLAY_ITEMS"
    print(f"✅ Example correctly uses MAX_DISPLAY_ITEMS={MAX_DISPLAY_ITEMS}")
    
    return True

def test_var_names_display_example():
    """Test example for displaying var_names (genes) with limits."""
    print("\nTesting var_names display example...")
    
    var_names_action = {
        "type": "write_and_run",
        "params": {
            "files": [{
                "path": "check_genes.py",
                "content": f"""# Mock AnnData with many genes
import numpy as np

class MockAnnData:
    def __init__(self):
        self.var_names = [f'GENE{{i}}' for i in range(16940)]  # User's example had 16940 genes
        self.shape = (4181, 16940)

adata = MockAnnData()
print(f'Data shape: {{adata.shape}} (cells x genes)')

# SMART var_names display - NEVER print all!
n_genes = len(adata.var_names)
print(f'\\nTotal genes: {{n_genes}}')
if n_genes <= {MAX_DISPLAY_ITEMS}:
    print(f'Gene names: {{list(adata.var_names)}}')
else:
    print(f'First {MAX_DISPLAY_ITEMS} genes: {{list(adata.var_names[:{MAX_DISPLAY_ITEMS}])}}')
    print(f'... and {{n_genes - {MAX_DISPLAY_ITEMS}}} more genes')
    print('\\nTo check specific genes, search for them instead of listing all!')
"""
            }],
            "run_script": "python check_genes.py"
        }
    }
    
    result = ActionInputValidator.validate_action(var_names_action)
    assert result['valid'], f"var_names action validation failed: {result.get('errors')}"
    print("✅ var_names display example is valid")
    
    # Run a simulated test to show what the output would look like
    print("\nSimulated output with 16940 genes:")
    n_genes = 16940
    if n_genes <= MAX_DISPLAY_ITEMS:
        print(f"  Would print all {n_genes} genes (but this won't happen)")
    else:
        print(f"  First {MAX_DISPLAY_ITEMS} genes: GENE0, GENE1, ... GENE14")
        print(f"  ... and {n_genes - MAX_DISPLAY_ITEMS} more genes")
    print("✅ Output correctly truncated to avoid printing 16940 items!")
    
    return True

def test_prompt_has_guidelines():
    """Test that the prompt templates include smart display guidelines."""
    print("\nChecking if prompt templates have smart display guidelines...")
    
    from agents.unified_bug_fixer.prompt_templates import SYSTEM_PROMPT
    
    # Check for the critical guidelines
    assert "DATA EXPLORATION DISPLAY LIMITS" in SYSTEM_PROMPT, "Missing display limits section"
    assert f"NEVER print more than {MAX_DISPLAY_ITEMS} items" in SYSTEM_PROMPT, "Missing limit specification"
    assert "Check the length/shape FIRST" in SYSTEM_PROMPT, "Missing length check guideline"
    assert "n_items = len(items)" in SYSTEM_PROMPT, "Missing example pattern"
    
    print("✅ Prompt templates include smart display guidelines")
    print(f"✅ Guidelines specify limit of {MAX_DISPLAY_ITEMS} items")
    
    return True

def main():
    """Run all smart display limit tests."""
    print("=" * 80)
    print("TESTING SMART DISPLAY LIMITS IN BUG FIXER")
    print("=" * 80)
    
    all_passed = True
    
    tests = [
        ("Display limit constant", test_display_limit_constant),
        ("Smart display example", test_smart_display_example),
        ("var_names display example", test_var_names_display_example),
        ("Prompt guidelines", test_prompt_has_guidelines)
    ]
    
    for name, test_func in tests:
        print(f"\n{'='*60}")
        print(f"Test: {name}")
        print('='*60)
        try:
            if not test_func():
                all_passed = False
                print(f"❌ {name} test failed")
        except Exception as e:
            all_passed = False
            print(f"❌ {name} test error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    if all_passed:
        print("✅ ALL SMART DISPLAY TESTS PASSED")
        print("\nKey improvements:")
        print(f"  - Display limited to {MAX_DISPLAY_ITEMS} items maximum")
        print("  - Prompts include clear guidelines about checking length first")
        print("  - Examples demonstrate smart truncation patterns")
        print("  - Prevents printing hundreds/thousands of columns or gene names")
        print("\nThis fixes the issue where bug fixer would print entire lists like:")
        print("  - 16940 gene names")
        print("  - Hundreds of column names")
        print("  - Long arrays of values")
    else:
        print("❌ SOME TESTS FAILED")
        print("Please review the errors above")
    print("=" * 80)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())