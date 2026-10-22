#!/usr/bin/env python3
"""Test core data loading functionality - simplified without Docker."""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis_tree_management.tree_manager import AnalysisTreeManager
from models import NodeState


def test_tree_creation_with_data_loading_root():
    """Test that tree creation includes a data loading root node."""
    tree_manager = AnalysisTreeManager()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        input_file = Path(temp_dir) / "test_data.h5ad"
        input_file.write_text("Mock data file")
        
        # Create tree
        tree = tree_manager.create_tree(
            user_request="Test data loading",
            input_data_path=str(input_file),
            max_nodes=3,
            max_children_per_node=2,
            max_debug_trials=1
        )
        
        # Validate tree structure
        assert tree.root_node_id is not None, "Tree should have a root node"
        assert tree.root_node_id in tree.nodes, "Root node should exist in nodes dict"
        
        root_node = tree.nodes[tree.root_node_id]
        
        # Check root node properties
        assert root_node.state == NodeState.PENDING, f"Root node state should be PENDING, got {root_node.state}"
        assert root_node.function_block.name == "load_input_data", f"Root node should be named 'load_input_data', got {root_node.function_block.name}"
        assert root_node.parent_id is None, "Root node should have no parent"
        
        print("✅ Tree creation with data loading root node - PASSED")
        return True


def test_data_loading_root_function_block():
    """Test that the data loading root has the correct function block."""
    tree_manager = AnalysisTreeManager()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        input_file = Path(temp_dir) / "test_data.h5ad"
        input_file.write_text("Mock data file")
        
        tree = tree_manager.create_tree(
            user_request="Test function block",
            input_data_path=str(input_file),
            max_nodes=3,
            max_children_per_node=2,
            max_debug_trials=1
        )
        
        root_node = tree.nodes[tree.root_node_id]
        function_block = root_node.function_block
        
        # Check function block properties
        assert function_block.name == "load_input_data", "Function block should be named 'load_input_data'"
        assert function_block.type == "python", "Function block should be Python"
        assert hasattr(function_block, 'code'), "Function block should have code"
        assert hasattr(function_block, 'requirements'), "Function block should have requirements"
        
        # Check that the code contains expected pass-through logic
        code = function_block.code
        assert "def run(path_dict, params)" in code, "Code should have run function signature"
        assert "shutil.copy" in code or "copy" in code, "Code should copy files"
        
        print("✅ Data loading root function block - PASSED")
        return True


def test_tree_state_management():
    """Test basic tree state management."""
    tree_manager = AnalysisTreeManager()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        input_file = Path(temp_dir) / "test_data.h5ad"
        input_file.write_text("Mock data file")
        
        tree = tree_manager.create_tree(
            user_request="Test state management",
            input_data_path=str(input_file),
            max_nodes=3,
            max_children_per_node=2,
            max_debug_trials=1
        )
        
        # Test tree structure
        assert hasattr(tree, 'id'), "Tree should have an ID"
        assert hasattr(tree, 'nodes'), "Tree should have nodes dict"
        assert hasattr(tree, 'root_node_id'), "Tree should have root_node_id"
        assert hasattr(tree, 'created_at'), "Tree should have created_at timestamp"
        
        # Test node structure
        root_node = tree.nodes[tree.root_node_id]
        
        # Check required attributes exist
        assert hasattr(root_node, 'id'), "Root node should have 'id' attribute"
        assert hasattr(root_node, 'state'), "Root node should have 'state' attribute"
        assert hasattr(root_node, 'parent_id'), "Root node should have 'parent_id' attribute"
        assert hasattr(root_node, 'children'), "Root node should have 'children' attribute"
        assert hasattr(root_node, 'function_block'), "Root node should have 'function_block' attribute"
        
        assert isinstance(root_node.children, list), "children should be a list"
        assert len(root_node.children) == 0, "Root node should start with no children"
        
        print("✅ Tree state management - PASSED")
        return True


def test_input_data_path_handling():
    """Test different input data path formats."""
    tree_manager = AnalysisTreeManager()
    
    test_cases = [
        ("single_file.h5ad", "Single file"),
        ("data_directory/file.h5ad", "File in directory"),
        ("complex_name_2024.h5ad", "Complex filename")
    ]
    
    for filename, description in test_cases:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create nested directory if needed
            input_path = Path(temp_dir) / filename
            input_path.parent.mkdir(parents=True, exist_ok=True)
            input_path.write_text(f"Mock data for {description}")
            
            tree = tree_manager.create_tree(
                user_request=f"Test {description}",
                input_data_path=str(input_path),
                max_nodes=3,
                max_children_per_node=2,
                max_debug_trials=1
            )
            
            # Should create tree successfully
            assert tree.root_node_id is not None, f"Failed to create tree for {description}"
            root_node = tree.nodes[tree.root_node_id]
            assert root_node.state == NodeState.PENDING, f"Root node state wrong for {description}"
    
    print("✅ Input data path handling - PASSED")
    return True


def test_node_id_uniqueness():
    """Test that node IDs are unique within a tree."""
    tree_manager = AnalysisTreeManager()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        input_file = Path(temp_dir) / "test_data.h5ad"
        input_file.write_text("Mock data file")
        
        tree = tree_manager.create_tree(
            user_request="Test node ID uniqueness",
            input_data_path=str(input_file),
            max_nodes=5,
            max_children_per_node=3,
            max_debug_trials=1
        )
        
        # Get all node IDs
        node_ids = list(tree.nodes.keys())
        
        # Check uniqueness
        assert len(node_ids) == len(set(node_ids)), "Node IDs should be unique"
        assert tree.root_node_id in node_ids, "Root node ID should be in nodes dict"
        
        # Check node ID format (should be UUIDs)
        import uuid
        for node_id in node_ids:
            try:
                uuid.UUID(node_id)
            except ValueError:
                assert False, f"Node ID '{node_id}' is not a valid UUID"
        
        print("✅ Node ID uniqueness - PASSED")
        return True


def run_all_tests():
    """Run all core data loading tests."""
    print("\n" + "="*80)
    print("CORE DATA LOADING INFRASTRUCTURE TESTS")
    print("="*80)
    
    tests = [
        ("Tree creation with data loading root", test_tree_creation_with_data_loading_root),
        ("Data loading root function block", test_data_loading_root_function_block),
        ("Tree state management", test_tree_state_management),
        ("Input data path handling", test_input_data_path_handling),
        ("Node ID uniqueness", test_node_id_uniqueness)
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
        print("\n🎉 ALL TESTS PASSED: Core data loading infrastructure working correctly")
        return True
    else:
        print(f"\n❌ {total - passed} tests failed")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)