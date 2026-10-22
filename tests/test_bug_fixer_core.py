#!/usr/bin/env python3
"""Test core bug fixer infrastructure - simplified without API calls."""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.unified_bug_fixer.code_versioning import CodeVersionManager
from agents.unified_bug_fixer.error_tracker import ErrorTracker
from agents.unified_bug_fixer import prompt_templates


def test_code_version_manager_creation():
    """Test that CodeVersionManager can be created and initialized."""
    with tempfile.TemporaryDirectory() as temp_dir:
        node_dir = Path(temp_dir) / "test_node"
        node_dir.mkdir(parents=True)
        
        # Create function_block directory
        fb_dir = node_dir / "function_block"
        fb_dir.mkdir(parents=True)
        
        # Initialize version manager
        manager = CodeVersionManager(node_dir)
        
        # Check initialization
        assert manager.node_dir == node_dir
        assert manager.function_block_dir.exists()
        assert manager.versions_dir.exists()
        assert manager.function_block_dir.name == "function_block"
        
        print("✅ CodeVersionManager creation - PASSED")
        return True


def test_version_manager_save_python_code():
    """Test saving Python code versions."""
    with tempfile.TemporaryDirectory() as temp_dir:
        node_dir = Path(temp_dir) / "test_node"
        node_dir.mkdir(parents=True)
        (node_dir / "function_block").mkdir(parents=True)
        
        manager = CodeVersionManager(node_dir)
        
        # Save first version
        code1 = "def run(path_dict, params):\n    print('Version 1')\n    return {}"
        version_path1 = manager.save_version(code1, "python", "original")
        
        assert version_path1.exists()
        assert version_path1.read_text() == code1
        assert ".py" in version_path1.suffix
        assert "original" in version_path1.name
        
        # Save second version
        code2 = "def run(path_dict, params):\n    print('Version 2 - fixed')\n    return {}"
        version_path2 = manager.save_version(code2, "python", "fixed")
        
        assert version_path2.exists()
        assert version_path2.read_text() == code2
        assert "fixed" in version_path2.name
        
        # Verify both versions exist
        versions = list(manager.versions_dir.glob("*.py"))
        assert len(versions) >= 2
        
        print("✅ Version manager save Python code - PASSED")
        return True


def test_version_manager_save_r_code():
    """Test saving R code versions."""
    with tempfile.TemporaryDirectory() as temp_dir:
        node_dir = Path(temp_dir) / "test_node"
        node_dir.mkdir(parents=True)
        (node_dir / "function_block").mkdir(parents=True)
        
        manager = CodeVersionManager(node_dir)
        
        # Save R version
        r_code = "run <- function(path_dict, params) {\n  print('R version')\n  return(list())\n}"
        version_path = manager.save_version(r_code, "r", "original")
        
        assert version_path.exists()
        assert ".R" in version_path.suffix
        assert version_path.read_text() == r_code
        assert "original" in version_path.name
        
        print("✅ Version manager save R code - PASSED")
        return True


def test_error_tracker_creation():
    """Test that ErrorTracker can be created and used."""
    with tempfile.TemporaryDirectory() as temp_dir:
        node_dir = Path(temp_dir) / "test_node"
        node_dir.mkdir(parents=True)
        
        # Create error tracker
        initial_error = "SyntaxError: invalid syntax"
        tracker = ErrorTracker(initial_error, node_dir)
        
        # Check initialization
        assert tracker.node_dir == node_dir
        assert tracker.initial_error == initial_error
        assert hasattr(tracker, 'start_turn')
        assert hasattr(tracker, 'record_action')
        assert hasattr(tracker, 'should_continue_debugging')
        
        print("✅ ErrorTracker creation - PASSED")
        return True


def test_error_tracker_basic_functionality():
    """Test basic error tracking functionality."""
    with tempfile.TemporaryDirectory() as temp_dir:
        node_dir = Path(temp_dir) / "test_node"
        node_dir.mkdir(parents=True)
        
        initial_error = "SyntaxError: invalid syntax"
        tracker = ErrorTracker(initial_error, node_dir)
        
        # Test initial state
        assert not tracker.is_resolved
        
        # Start a turn
        tracker.start_turn(1)
        
        # Record an action
        action = {"type": "read_file", "path": "code.py"}
        result = {"success": True, "content": "def run(): pass"}
        tracker.record_action(action, result)
        
        # Should still not be resolved
        assert not tracker.is_resolved
        
        # Check debugging should continue
        should_continue = tracker.should_continue_debugging()
        assert isinstance(should_continue, bool)
        
        print("✅ ErrorTracker basic functionality - PASSED")
        return True


def test_prompt_templates_functions():
    """Test that prompt template functions are available and callable."""
    # Test initial prompt function
    assert hasattr(prompt_templates, 'create_initial_prompt')
    
    # Test that it can be called with minimal parameters
    try:
        prompt = prompt_templates.create_initial_prompt(
            node_name="test_node",
            error_message="Test error",
            stdout="",
            stderr="Test stderr",
            attempt_number=1
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "test_node" in prompt or "Test error" in prompt
    except Exception as e:
        assert False, f"create_initial_prompt failed: {e}"
    
    # Test followup prompt function
    assert hasattr(prompt_templates, 'create_followup_prompt')
    
    try:
        followup = prompt_templates.create_followup_prompt(
            action_result={"success": True, "output": "Test output"},
            previous_explanation="Previous explanation"
        )
        assert isinstance(followup, str)
        assert len(followup) > 0
    except Exception as e:
        assert False, f"create_followup_prompt failed: {e}"
    
    print("✅ Prompt templates functions - PASSED")
    return True


def test_function_block_update_structure():
    """Test the function block update workflow structure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        node_dir = Path(temp_dir) / "test_node"
        node_dir.mkdir(parents=True)
        fb_dir = node_dir / "function_block"
        fb_dir.mkdir(parents=True)
        
        manager = CodeVersionManager(node_dir)
        
        # Create initial files
        original_code = """def run(path_dict, params):
    import os
    print('Original code')
    return {'status': 'success'}"""
        
        (fb_dir / "code.py").write_text(original_code)
        (fb_dir / "requirements.txt").write_text("numpy")
        
        # Update function block
        new_code = """def run(path_dict, params):
    import os
    import pandas as pd
    print('Updated code with pandas')
    return {'status': 'success', 'updated': True}"""
        
        new_requirements = ["numpy", "pandas"]
        
        result = manager.update_function_block(new_code, new_requirements, "python")
        
        # Check result structure
        assert isinstance(result, dict)
        assert "success" in result
        assert result["success"] is True
        
        # Check files were updated
        assert (fb_dir / "code.py").read_text() == new_code
        assert (fb_dir / "function_block.py").read_text() == new_code
        
        # Check requirements
        req_content = (fb_dir / "requirements.txt").read_text()
        assert "numpy" in req_content
        assert "pandas" in req_content
        
        print("✅ Function block update structure - PASSED")
        return True


def run_all_tests():
    """Run all core bug fixer infrastructure tests."""
    print("\n" + "="*80)
    print("CORE BUG FIXER INFRASTRUCTURE TESTS")
    print("="*80)
    
    tests = [
        ("CodeVersionManager creation", test_code_version_manager_creation),
        ("Version manager save Python code", test_version_manager_save_python_code),
        ("Version manager save R code", test_version_manager_save_r_code),
        ("ErrorTracker creation", test_error_tracker_creation),
        ("ErrorTracker basic functionality", test_error_tracker_basic_functionality),
        ("Prompt templates functions", test_prompt_templates_functions),
        ("Function block update structure", test_function_block_update_structure)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
            print(f"\n❌ FAILED: {test_name}")
            print(f"  Error: {e}")
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, error in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status}: {test_name}")
        if error:
            print(f"         Error: {error}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED: Core bug fixer infrastructure working correctly")
        return True
    else:
        print(f"\n❌ {total - passed} tests failed")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)