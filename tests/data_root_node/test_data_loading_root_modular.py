#!/usr/bin/env python3
"""Modular tests for data loading root node functionality."""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
import tempfile
import shutil

# Add the omicairn_agent_local directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analysis_tree_management.tree_manager import AnalysisTreeManager
from models import GenerationMode, NodeState
from agents.main_agent import MainAgent


def test_1_data_loading_root_creation():
    """Test 1: Verify data loading root node is created automatically."""
    print("\n" + "="*80)
    print("TEST 1: Data Loading Root Node Creation")
    print("="*80)
    
    # Create tree manager
    tree_manager = AnalysisTreeManager()
    
    # Create a new tree
    tree = tree_manager.create_tree(
        user_request="Test request",
        input_data_path="test_data/zebrafish.h5ad",
        max_nodes=5,
        max_children_per_node=2,
        max_debug_trials=1,
        generation_mode=GenerationMode.MIXED,
        llm_model="gpt-4o-mini"
    )
    
    # Verify tree has a root node
    assert tree.root_node_id is not None, "Tree should have a root node ID"
    
    # Get root node
    root_node = tree.nodes.get(tree.root_node_id)
    assert root_node is not None, "Root node should exist"
    
    # Verify it's the data loading node
    assert root_node.function_block.name == "load_input_data", f"Root node should be 'load_input_data', got '{root_node.function_block.name}'"
    
    # Verify initial state
    assert root_node.state == NodeState.PENDING, f"Root node should be PENDING, got {root_node.state}"
    
    print("✅ PASSED: Data loading root node is created automatically")
    print(f"  - Root node ID: {tree.root_node_id}")
    print(f"  - Root node name: {root_node.function_block.name}")
    print(f"  - Root node state: {root_node.state}")
    
    return True


def test_2_data_loading_execution():
    """Test 2: Verify data loading root node executes successfully."""
    print("\n" + "="*80)
    print("TEST 2: Data Loading Root Node Execution")
    print("="*80)
    
    # Create temporary output directory
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "test_output"
        output_dir.mkdir(exist_ok=True)
        
        # Create tree manager
        tree_manager = AnalysisTreeManager()
        
        # Create a new tree
        tree = tree_manager.create_tree(
            user_request="Test request",
            input_data_path="test_data/zebrafish.h5ad",
            max_nodes=5
        )
        
        # Get root node
        root_node = tree.nodes[tree.root_node_id]
        
        # Create node directory structure
        paths = tree_manager.create_output_structure(output_dir)
        node_paths = tree_manager.create_node_directory(root_node.id, paths['nodes_dir'])
        
        # Create a mock executor to test just the function block
        from job_executors.python_executor import PythonExecutor
        from utils.docker_utils import DockerManager
        docker_manager = DockerManager()
        executor = PythonExecutor(docker_manager)
        
        # Prepare job for execution
        job_dir = tree_manager.create_job_directory(root_node.id, node_paths['node_dir'])
        
        # Copy input data
        input_dir = job_dir / "input"
        shutil.copy("test_data/zebrafish.h5ad", input_dir / "zebrafish.h5ad")
        
        # Execute the function block
        exit_code, output_path = executor.execute(
            function_block=root_node.function_block,
            input_path=input_dir,
            output_path=job_dir / "output",
            job_dir=job_dir
        )
        
        # Verify execution succeeded
        assert exit_code == 0, f"Execution should succeed, got exit code {exit_code}"
        
        # Verify output file exists
        output_file = job_dir / "output" / "_node_anndata.h5ad"
        assert output_file.exists(), "Output file should exist"
        
        print("✅ PASSED: Data loading root node executes successfully")
        print(f"  - Exit code: {exit_code}")
        print(f"  - Output file: {output_file}")
        print(f"  - Output size: {output_file.stat().st_size} bytes")
        
    return True


def test_3_data_flow_to_children():
    """Test 3: Verify data flows correctly from root to child nodes."""
    print("\n" + "="*80)
    print("TEST 3: Data Flow from Root to Children")
    print("="*80)
    
    # Create a minimal agent that won't do bug fixing
    agent = MainAgent(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        bug_fixer_type="unified",
        bug_fixer_model="gpt-4o-mini",
        llm_model="gpt-4o-mini",
        enable_interactive_debug=False,  # Disable to avoid long bug fixing
        enable_web_agent=False,
        log_llm_to_stdout=False
    )
    
    # Simple request that should create root + one child
    user_request = """
    Just load the data and print its shape. Nothing else.
    """
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "test_output"
        output_dir.mkdir(exist_ok=True)
        
        # Run analysis with minimal settings
        result = agent.run_analysis(
            input_data_path="test_data/zebrafish.h5ad",
            user_request=user_request,
            output_dir=output_dir,
            max_nodes=3,
            max_children=1,
            max_debug_trials=0,  # No debugging
            max_iterations=2,    # Quick test
            function_block_timeout=30,  # Short timeout
            verbose=False
        )
        
        # Load the analysis tree
        tree_file = output_dir / "analysis_tree.json"
        assert tree_file.exists(), f"Analysis tree file not found: {tree_file}"
        if tree_file.exists():
            with open(tree_file, 'r') as f:
                tree_data = json.load(f)
            
            # Verify we have at least the root node
            assert len(tree_data['nodes']) >= 1, "Should have at least root node"
            
            # Get root node
            root_id = tree_data['root_node_id']
            root_node = tree_data['nodes'][root_id]
            
            # Verify root is data loading node
            assert root_node['function_block']['name'] == 'load_input_data', "Root should be data loader"
            
            # Check if root completed
            if root_node['state'] == 'completed':
                print("✅ Root node completed successfully")
                
                # Check output path
                root_output = root_node.get('output_data_id')
                if root_output:
                    print(f"  - Root output: {root_output}")
                    
                    # Check if we have children
                    children = root_node.get('children', [])
                    if children:
                        print(f"  - Root has {len(children)} children")
                        for child_id in children:
                            child = tree_data['nodes'].get(child_id)
                            if child:
                                print(f"    - Child: {child['function_block']['name']} ({child['state']})")
                    else:
                        print("  - No children created (orchestrator may have decided request was satisfied)")
            else:
                print(f"❌ Root node state: {root_node['state']}")
                return False
        
        print("\n✅ PASSED: Data loading root node is properly integrated")
        print(f"  - Total nodes created: {result.get('total_nodes', 0)}")
        print(f"  - Completed nodes: {result.get('completed_nodes', 0)}")
        
    return True


def test_4_root_failure_handling():
    """Test 4: Verify system handles root node failure gracefully."""
    print("\n" + "="*80)
    print("TEST 4: Root Node Failure Handling")
    print("="*80)
    
    # Create tree with invalid input path
    tree_manager = AnalysisTreeManager()
    
    tree = tree_manager.create_tree(
        user_request="Test request",
        input_data_path="nonexistent/file.h5ad",  # Invalid path
        max_nodes=5
    )
    
    # Create minimal agent
    agent = MainAgent(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        bug_fixer_type="unified",
        enable_interactive_debug=False,
        enable_web_agent=False,
        log_llm_to_stdout=False
    )
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "test_output"
        output_dir.mkdir(exist_ok=True)
        
        try:
            # This should handle the error gracefully
            result = agent.run_analysis(
                input_data_path="nonexistent/file.h5ad",
                user_request="Test request",
                output_dir=output_dir,
                max_nodes=3,
                max_iterations=1,
                max_debug_trials=0,
                verbose=False
            )
            
            # Check that root node failed
            assert result['failed_nodes'] > 0, "Should have failed nodes"
            
            print("✅ PASSED: System handles root node failure gracefully")
            print(f"  - Failed nodes: {result['failed_nodes']}")
            print(f"  - Total nodes: {result['total_nodes']}")
            
        except (FileNotFoundError, ValueError) as e:
            print(f"✅ PASSED: System raised exception for invalid input: {type(e).__name__}")
            
    return True


def run_all_tests():
    """Run all modular tests."""
    print("\n" + "="*80)
    print("RUNNING MODULAR TESTS FOR DATA LOADING ROOT NODE")
    print("="*80)
    
    tests = [
        ("Creation Test", test_1_data_loading_root_creation),
        ("Execution Test", test_2_data_loading_execution),
        ("Data Flow Test", test_3_data_flow_to_children),
        ("Failure Handling Test", test_4_root_failure_handling)
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
            print(f"         Error: {error}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)