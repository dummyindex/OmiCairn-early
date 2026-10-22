#!/usr/bin/env python3
"""Test that anti-placeholder warnings are comprehensive and present in prompts."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.unified_bug_fixer.prompt_templates import SYSTEM_PROMPT
from agents.unified_bug_fixer.enhanced_debug_session import EnhancedDebugSession
from agents.function_creator_agent import FunctionCreatorAgent


def test_bug_fixer_has_comprehensive_anti_placeholder_warnings():
    """Test that bug fixer prompts contain comprehensive anti-placeholder warnings."""
    
    print("Testing bug fixer anti-placeholder warnings...")
    
    # Check for the new specific template patterns
    problematic_patterns = [
        "placeholder for actual analysis code",
        "scFates analysis steps would go here",
        "Example: scFates analysis",
        "... your analysis code ...",
        "Process data",
        "steps would go here"
    ]
    
    # Check main system prompt
    assert "NO TEMPLATE PATTERNS" in SYSTEM_PROMPT
    assert "NEVER use these template-style patterns" in SYSTEM_PROMPT
    
    print("✓ Main template pattern warnings present")
    
    # Check specific problematic patterns are mentioned
    warnings_found = 0
    for pattern in problematic_patterns:
        if pattern.lower() in SYSTEM_PROMPT.lower():
            warnings_found += 1
            print(f"✓ Warning found for pattern: '{pattern}'")
    
    print(f"Found warnings for {warnings_found}/{len(problematic_patterns)} problematic patterns")
    
    # Should have at least half of the patterns mentioned
    assert warnings_found >= len(problematic_patterns) // 2
    
    # Check NO PLACEHOLDER CODE section
    assert "NO PLACEHOLDER CODE" in SYSTEM_PROMPT
    assert "NEVER provide placeholder implementations" in SYSTEM_PROMPT
    assert "template-style comments" in SYSTEM_PROMPT
    
    print("✓ Comprehensive placeholder warnings present")


def test_final_turn_instructions_have_anti_placeholder_warnings():
    """Test that final turn instructions include anti-placeholder warnings."""
    
    print("\nTesting final turn anti-placeholder warnings...")
    
    # Check the final turn instruction template
    # We need to check the _update_conversation_for_final_turn method
    import inspect
    source = inspect.getsource(EnhancedDebugSession._update_conversation_for_final_turn)
    
    # Check for anti-placeholder warnings in final turn
    assert "NO PLACEHOLDER CODE" in source
    assert "template-style comments" in source
    assert "placeholder for actual analysis code" in source
    assert "steps would go here" in source
    assert "Process data" in source
    
    print("✓ Final turn instructions contain comprehensive anti-placeholder warnings")


def test_function_creator_cleaned_of_template_patterns():
    """Test that function creator documentation doesn't contain problematic template patterns."""
    
    print("\nTesting function creator template cleanup...")
    
    # Read the function creator source
    import inspect
    source = inspect.getsource(FunctionCreatorAgent)
    
    # These patterns should NOT be in the function creator anymore
    problematic_patterns = [
        "# ... your analysis code ...",
        "# Process data\n# ... your analysis code ..."
    ]
    
    for pattern in problematic_patterns:
        assert pattern not in source, f"Found problematic pattern in function creator: {pattern}"
        print(f"✓ Cleaned pattern: '{pattern[:30]}...'")
    
    # Should have actual implementation examples instead
    assert "normalize_data" in source or "compute_metrics" in source
    print("✓ Function creator uses actual implementation examples")


def test_all_anti_placeholder_patterns_covered():
    """Test that all the specific patterns from the bug output are covered."""
    
    print("\nTesting coverage of specific problematic patterns...")
    
    # The exact patterns from the bug report
    specific_bad_patterns = [
        "# Proceed with scFates analysis (placeholder for actual analysis code)",
        "# Example: scFates analysis steps would go here",
        "placeholder for actual analysis code",
        "analysis steps would go here"
    ]
    
    covered_patterns = 0
    for pattern in specific_bad_patterns:
        # Check if any part of the pattern is mentioned in warnings
        pattern_words = pattern.lower().split()
        matches = sum(1 for word in pattern_words if word in SYSTEM_PROMPT.lower())
        
        if matches >= 3:  # If at least 3 words from the pattern are mentioned
            covered_patterns += 1
            print(f"✓ Pattern coverage: '{pattern[:40]}...'")
        else:
            print(f"⚠️  Limited coverage: '{pattern[:40]}...'")
    
    print(f"Coverage: {covered_patterns}/{len(specific_bad_patterns)} specific patterns")
    
    # Should cover at least 75% of the specific bad patterns
    assert covered_patterns >= len(specific_bad_patterns) * 0.75


def test_positive_examples_avoid_templates():
    """Test that our positive examples don't contain template patterns."""
    
    print("\nTesting positive examples for template avoidance...")
    
    # Check domain knowledge examples if they exist
    domain_file = Path(__file__).parent.parent / "domain_knowledge" / "domain_docs" / "single_cell_genomics.md"
    if domain_file.exists():
        content = domain_file.read_text()
        
        # These patterns should NOT be in domain knowledge
        bad_patterns = [
            "placeholder for actual",
            "steps would go here",
            "... your analysis code ...",
            "Example: scFates analysis steps"
        ]
        
        found_bad = 0
        for pattern in bad_patterns:
            if pattern.lower() in content.lower():
                found_bad += 1
                print(f"⚠️  Found bad pattern in domain knowledge: '{pattern}'")
            else:
                print(f"✓ Clean of pattern: '{pattern}'")
        
        assert found_bad == 0, f"Found {found_bad} bad patterns in domain knowledge"
        print("✓ Domain knowledge examples are clean")
    else:
        print("✓ Domain knowledge file not found - skipping template pattern check")


if __name__ == "__main__":
    print("Testing anti-placeholder warnings comprehensiveness...\n")
    
    test_bug_fixer_has_comprehensive_anti_placeholder_warnings()
    test_final_turn_instructions_have_anti_placeholder_warnings()
    test_function_creator_cleaned_of_template_patterns()
    test_all_anti_placeholder_patterns_covered()
    test_positive_examples_avoid_templates()
    
    print("\n✅ All anti-placeholder warning tests passed!")
    print("\nThe system now has comprehensive warnings against:")
    print("- Template-style comments")
    print("- Placeholder analysis code")
    print("- Generic process/example patterns")
    print("- 'Steps would go here' language")
    print("- Documentation-style template examples")
    print("\nBug fixer should no longer generate placeholder code!")