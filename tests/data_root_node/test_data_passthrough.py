#!/usr/bin/env python3
"""Test that data loading root node passes through files unmodified."""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime
import tempfile

# Add the omicairn_agent_local directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analysis_tree_management.tree_manager import AnalysisTreeManager
from models import NodeState
from job_executors.python_executor import PythonExecutor
from utils.docker_utils import DockerManager


def test_single_file_passthrough():
    """Test that a single file is passed through unchanged."""
    print("\n" + "="*80)
    print("TEST 1: Single File Pass-through")
    print("="*80)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test input file
        input_dir = Path(temp_dir) / "input"
        input_dir.mkdir()
        
        test_file = input_dir / "test_data.h5ad"
        test_file.write_text("Test data content")
        original_size = test_file.stat().st_size
        
        print(f"Created test file: {test_file.name} ({original_size} bytes)")
        
        # Create tree and execute root node
        tree_manager = AnalysisTreeManager()
        tree = tree_manager.create_tree(
            user_request="Test single file",
            input_data_path=str(test_file),
            max_nodes=5
        )
        
        output_dir = Path(temp_dir) / "output"
        paths = tree_manager.create_output_structure(output_dir)
        
        # Execute root node
        root_node = tree.nodes[tree.root_node_id]
        node_paths = tree_manager.create_node_directory(root_node.id, paths['nodes_dir'])
        job_dir = tree_manager.create_job_directory(root_node.id, node_paths['node_dir'])
        
        # Copy input to job input dir
        job_input_dir = job_dir / "input"
        shutil.copy(test_file, job_input_dir / test_file.name)
        
        # Execute
        docker_manager = DockerManager()
        executor = PythonExecutor(docker_manager)
        
        result = executor.execute(
            function_block=root_node.function_block,
            input_data_path=job_input_dir,
            output_dir=job_dir / "output",
            parameters={}
        )
        
        # Check results
        assert result.exit_code == 0, f"Execution failed with code {result.exit_code}"
        
        output_file = job_dir / "output" / test_file.name
        assert output_file.exists(), f"Output file {test_file.name} not found"
        assert output_file.stat().st_size == original_size, "File size changed"
        assert output_file.read_text() == "Test data content", "File content changed"
        
        print("✅ PASSED: Single file passed through unchanged")
        print(f"  - Original: {test_file.name} ({original_size} bytes)")
        print(f"  - Output: {output_file.name} ({output_file.stat().st_size} bytes)")
        
        return True


def test_multiple_files_passthrough():
    """Test that multiple files are passed through unchanged."""
    print("\n" + "="*80)
    print("TEST 2: Multiple Files Pass-through")
    print("="*80)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test input files
        input_dir = Path(temp_dir) / "input"
        input_dir.mkdir()
        
        test_files = {
            "data1.h5ad": "Content of data file 1",
            "data2.h5ad": "Content of data file 2",
            "metadata.csv": "sample,condition\nA,control\nB,treatment",
            "config.json": '{"version": "1.0", "params": {"k": 10}}'
        }
        
        for filename, content in test_files.items():
            (input_dir / filename).write_text(content)
        
        print(f"Created {len(test_files)} test files:")
        for filename in test_files:
            size = (input_dir / filename).stat().st_size
            print(f"  - {filename} ({size} bytes)")
        
        # Create tree and execute root node
        tree_manager = AnalysisTreeManager()
        tree = tree_manager.create_tree(
            user_request="Test multiple files",
            input_data_path=str(input_dir / "data1.h5ad"),  # Just point to one file
            max_nodes=5
        )
        
        output_dir = Path(temp_dir) / "output"
        paths = tree_manager.create_output_structure(output_dir)
        
        # Execute root node
        root_node = tree.nodes[tree.root_node_id]
        node_paths = tree_manager.create_node_directory(root_node.id, paths['nodes_dir'])
        job_dir = tree_manager.create_job_directory(root_node.id, node_paths['node_dir'])
        
        # Copy ALL files to job input dir
        job_input_dir = job_dir / "input"
        for filename in test_files:
            shutil.copy(input_dir / filename, job_input_dir / filename)
        
        # Execute
        docker_manager = DockerManager()
        executor = PythonExecutor(docker_manager)
        
        result = executor.execute(
            function_block=root_node.function_block,
            input_data_path=job_input_dir,
            output_dir=job_dir / "output",
            parameters={}
        )
        
        # Check results
        assert result.exit_code == 0, f"Execution failed with code {result.exit_code}"
        
        job_output_dir = job_dir / "output"
        output_files = list(job_output_dir.iterdir())
        
        print(f"\nOutput directory contains {len(output_files)} files:")
        for f in sorted(output_files):
            print(f"  - {f.name} ({f.stat().st_size} bytes)")
        
        # Verify all files were copied unchanged
        for filename, original_content in test_files.items():
            output_file = job_output_dir / filename
            assert output_file.exists(), f"File {filename} not found in output"
            assert output_file.read_text() == original_content, f"Content of {filename} changed"
        
        print("\n✅ PASSED: All files passed through unchanged")
        return True


def test_no_file_renaming():
    """Test that files are NOT renamed to _node_anndata.h5ad."""
    print("\n" + "="*80)
    print("TEST 3: No File Renaming")
    print("="*80)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test file with custom name
        input_dir = Path(temp_dir) / "input"
        input_dir.mkdir()
        
        custom_filename = "zebrafish_experiment_2024.h5ad"
        test_file = input_dir / custom_filename
        test_file.write_text("Zebrafish data")
        
        print(f"Created test file: {custom_filename}")
        
        # Create tree and execute
        tree_manager = AnalysisTreeManager()
        tree = tree_manager.create_tree(
            user_request="Test no renaming",
            input_data_path=str(test_file),
            max_nodes=5
        )
        
        output_dir = Path(temp_dir) / "output"
        paths = tree_manager.create_output_structure(output_dir)
        
        root_node = tree.nodes[tree.root_node_id]
        node_paths = tree_manager.create_node_directory(root_node.id, paths['nodes_dir'])
        job_dir = tree_manager.create_job_directory(root_node.id, node_paths['node_dir'])
        
        job_input_dir = job_dir / "input"
        shutil.copy(test_file, job_input_dir / custom_filename)
        
        docker_manager = DockerManager()
        executor = PythonExecutor(docker_manager)
        
        result = executor.execute(
            function_block=root_node.function_block,
            input_data_path=job_input_dir,
            output_dir=job_dir / "output",
            parameters={}
        )
        
        assert result.exit_code == 0, f"Execution failed"
        
        # Check that original filename is preserved
        job_output_dir = job_dir / "output"
        assert (job_output_dir / custom_filename).exists(), f"Original filename {custom_filename} not preserved"
        assert not (job_output_dir / "_node_anndata.h5ad").exists(), "File was renamed to _node_anndata.h5ad"
        
        print("✅ PASSED: Original filename preserved")
        print(f"  - Input: {custom_filename}")
        print(f"  - Output: {custom_filename} (not renamed)")
        
        return True


def test_empty_directory():
    """Test that empty input directory is handled gracefully."""
    print("\n" + "="*80)
    print("TEST 4: Empty Directory Handling")
    print("="*80)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create empty input directory
        input_dir = Path(temp_dir) / "input"
        input_dir.mkdir()
        
        print("Created empty input directory")
        
        # Create tree and try to execute
        tree_manager = AnalysisTreeManager()
        tree = tree_manager.create_tree(
            user_request="Test empty dir",
            input_data_path=str(input_dir / "nonexistent.h5ad"),
            max_nodes=5
        )
        
        output_dir = Path(temp_dir) / "output"
        paths = tree_manager.create_output_structure(output_dir)
        
        root_node = tree.nodes[tree.root_node_id]
        node_paths = tree_manager.create_node_directory(root_node.id, paths['nodes_dir'])
        job_dir = tree_manager.create_job_directory(root_node.id, node_paths['node_dir'])
        
        job_input_dir = job_dir / "input"
        # Don't copy anything - leave it empty
        
        docker_manager = DockerManager()
        executor = PythonExecutor(docker_manager)
        
        result = executor.execute(
            function_block=root_node.function_block,
            input_data_path=job_input_dir,
            output_dir=job_dir / "output",
            parameters={}
        )
        
        # Should fail with appropriate error
        assert result.exit_code != 0, "Should fail for empty directory"
        assert "No input files found" in result.stderr, "Should report no files found"
        
        print("✅ PASSED: Empty directory handled with appropriate error")
        print(f"  - Exit code: {result.exit_code}")
        print(f"  - Error contains: 'No input files found'")
        
        return True


def run_all_tests():
    """Run all pass-through tests."""
    print("\n" + "="*80)
    print("DATA LOADING ROOT NODE: PASS-THROUGH TESTS")
    print("="*80)
    
    tests = [
        ("Single File Pass-through", test_single_file_passthrough),
        ("Multiple Files Pass-through", test_multiple_files_passthrough),
        ("No File Renaming", test_no_file_renaming),
        ("Empty Directory Handling", test_empty_directory)
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
            import traceback
            traceback.print_exc()
    
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
            print(f"         Error: {error[:100]}...")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED: Data loading root node correctly passes through files unmodified")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)