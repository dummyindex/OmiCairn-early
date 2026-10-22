#!/usr/bin/env python3
"""Test bug fixer R support fixes - no imports required."""

from pathlib import Path

PROMPT_TEMPLATES = Path(__file__).resolve().parents[2] / "agents" / "unified_bug_fixer" / "prompt_templates.py"

def test_prompt_templates_fixes():
    """Test that hardcoded filename assumptions were removed."""
    
    with open(PROMPT_TEMPLATES, 'r') as f:
        content = f.read()
    
    print("=== Testing Bug Fixer R Support Fixes ===")
    
    # Should NOT contain these hardcoded references
    bad_patterns = [
        "_node_anndata.h5ad",
        "_node_seuratObject.rds"
    ]
    
    issues_found = 0
    for pattern in bad_patterns:
        if pattern in content:
            print(f"❌ FOUND hardcoded pattern: {pattern}")
            issues_found += 1
        else:
            print(f"✅ No hardcoded pattern: {pattern}")
    
    # Should contain these correct patterns
    good_patterns = [
        "Function block decides what files to read",
        "Function block decides what files to write", 
        "requirements.txt (format: packagename, Bioconductor::packagename, user/repo)",
        "R packages cannot be installed with install_package action",
        "glob.glob('/workspace/input/*.h5ad')"  # Dynamic file discovery
    ]
    
    for pattern in good_patterns:
        if pattern in content:
            print(f"✅ Found correct guidance: {pattern}")
        else:
            print(f"❌ Missing guidance: {pattern}")
            issues_found += 1
    
    # Check language-specific distinctions
    language_checks = [
        ("def run(path_dict, params):", "Python signature"),
        ("run <- function(path_dict, params)", "R signature"),
        ("install_package", "Python install action"),
        ("update requirements.txt", "R package handling")
    ]
    
    for pattern, desc in language_checks:
        if pattern in content:
            print(f"✅ {desc}: Found")
        else:
            print(f"❌ {desc}: Missing")
            issues_found += 1
    
    if issues_found == 0:
        print("\n🎉 ALL CHECKS PASSED! Bug fixer R support is correctly implemented.")
    else:
        print(f"\n❌ {issues_found} issues found. Bug fixer needs additional fixes.")
    assert issues_found == 0, f"{issues_found} prompt-template checks failed"

def test_example_commands():
    """Test that example commands use dynamic file discovery."""
    
    with open(PROMPT_TEMPLATES, 'r') as f:
        content = f.read()
    
    print("\n=== Testing Dynamic File Discovery in Examples ===")
    
    # Check that examples use glob instead of hardcoded paths
    if "glob.glob('/workspace/input/*.h5ad')" in content:
        print("✅ Examples use dynamic file discovery")
    else:
        print("❌ Examples still use hardcoded paths")
    assert "glob.glob('/workspace/input/*.h5ad')" in content, "Examples still use hardcoded paths"

def main():
    """Run all tests."""
    print("Testing Bug Fixer R Function Block Support Fixes")
    print("=" * 60)
    
    test1_passed = test2_passed = True
    try:
        test_prompt_templates_fixes()
    except AssertionError:
        test1_passed = False
    try:
        test_example_commands()
    except AssertionError:
        test2_passed = False
    
    print("\n" + "=" * 60)
    if test1_passed and test2_passed:
        print("✅ ALL TESTS PASSED!")
        print("\nKey fixes implemented:")
        print("• Removed hardcoded filename assumptions")
        print("• Made guidance filename-agnostic") 
        print("• Preserved correct R vs Python distinctions")
        print("• Updated examples to use dynamic file discovery")
        print("• Maintained proper R package installation guidance")
        return True
    else:
        print("❌ SOME TESTS FAILED!")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)