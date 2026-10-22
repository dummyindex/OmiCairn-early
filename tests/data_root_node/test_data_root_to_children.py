#!/usr/bin/env python3
"""Test data passing from root node to multiple children."""

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
from analysis_tree_management.interactive_node_executor import InteractiveNodeExecutor
from models import GenerationMode, NodeState, NewFunctionBlock, FunctionBlockType, StaticConfig
from agents.main_agent import MainAgent
import scanpy as sc


def create_simple_analysis_node(name: str, task: str) -> NewFunctionBlock:
    """Create a simple analysis node that just prints data info."""
    code = f'''def run(path_dict, params):
    import os
    import scanpy as sc
    
    # Load input data
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    print(f"Loading data from: {{input_file}}")
    adata = sc.read_h5ad(input_file)
    
    # Print info to verify we got the data
    print(f"[{name}] Received data with shape: {{adata.shape}}")
    print(f"[{name}] First 5 obs names: {{list(adata.obs_names[:5])}}")
    print(f"[{name}] Task: {task}")
    
    # Save output (unchanged for this test)
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
    print(f"[{name}] Saved data to: {{output_file}}")
    
    return adata
'''
    
    return NewFunctionBlock(
        name=name,
        type=FunctionBlockType.PYTHON,
        description=f"Test node: {task}",
        parameters={},
        static_config=StaticConfig(
            args=[],
            description=task,
            tag="test",
            document_url="",
            source="test"
        ),
        code=code,
        requirements="scanpy\npandas\nnumpy",
        new=True,
        output_description=f"Output from {name} - passes through the input data unchanged"
    )


def test_multiple_children_data_flow():
    """Test that root node can pass data to multiple child nodes."""
    print("\n" + "="*80)
    print("TEST: Data Flow from Root to Multiple Children")
    print("="*80)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "test_output"
        output_dir.mkdir(exist_ok=True)
        
        # Step 1: Create tree with data loading root
        tree_manager = AnalysisTreeManager()
        tree = tree_manager.create_tree(
            user_request="Test multiple children",
            input_data_path="test_data/zebrafish.h5ad",
            max_nodes=10,
            max_children_per_node=5  # Allow multiple children
        )
        
        print(f"Created tree: {tree.id}")
        print(f"Root node: {tree.root_node_id}")
        
        # Step 2: Create output structure
        paths = tree_manager.create_output_structure(output_dir)
        
        # Step 3: Execute root node
        root_node = tree.nodes[tree.root_node_id]
        print(f"\nExecuting root node: {root_node.function_block.name}")
        
        # Create simple executor (no bug fixing needed for data loading)
        from job_executors.python_executor import PythonExecutor
        from utils.docker_utils import DockerManager
        docker_manager = DockerManager()
        executor = PythonExecutor(docker_manager)
        
        # Execute root
        node_paths = tree_manager.create_node_directory(root_node.id, paths['nodes_dir'])
        job_dir = tree_manager.create_job_directory(root_node.id, node_paths['node_dir'])
        
        # Copy input data
        input_dir = job_dir / "input"
        shutil.copy("test_data/zebrafish.h5ad", input_dir / "zebrafish.h5ad")
        
        exit_code, _ = executor.execute(
            function_block=root_node.function_block,
            input_path=input_dir,
            output_path=job_dir / "output",
            job_dir=job_dir
        )
        
        assert exit_code == 0, f"Root execution failed with code {exit_code}"
        
        # Update root node state
        root_output_dir = node_paths['outputs_dir']
        shutil.copy(job_dir / "output" / "_node_anndata.h5ad", root_output_dir / "_node_anndata.h5ad")
        tree.update_node_state(root_node.id, NodeState.COMPLETED)
        root_node.output_data_id = str(root_output_dir)
        
        print(f"✅ Root node executed successfully")
        print(f"   Output: {root_output_dir}")
        
        # Step 4: Add multiple child nodes
        child_specs = [
            ("quality_control", "Calculate QC metrics"),
            ("normalization", "Normalize the data"),
            ("dim_reduction", "Reduce dimensions"),
            ("clustering", "Cluster cells")
        ]
        
        child_blocks = [create_simple_analysis_node(name, task) for name, task in child_specs]
        child_nodes = tree_manager.add_child_nodes(root_node.id, child_blocks)
        
        print(f"\nAdded {len(child_nodes)} child nodes to root")
        
        # Step 5: Execute each child and verify they receive data
        results = []
        for i, child_node in enumerate(child_nodes):
            print(f"\nExecuting child {i+1}/{len(child_nodes)}: {child_node.function_block.name}")
            
            # Create directories for child
            child_paths = tree_manager.create_node_directory(child_node.id, paths['nodes_dir'])
            child_job_dir = tree_manager.create_job_directory(child_node.id, child_paths['node_dir'])
            
            # CRITICAL: Link parent output as child input
            child_input_dir = child_job_dir / "input"
            
            # Copy parent's output file to child's input
            parent_output_file = Path(root_node.output_data_id) / "_node_anndata.h5ad"
            child_input_file = child_input_dir / "_node_anndata.h5ad"
            
            print(f"   Copying data from parent: {parent_output_file}")
            print(f"   To child input: {child_input_file}")
            
            shutil.copy(parent_output_file, child_input_file)
            
            # Execute child
            exit_code, _ = executor.execute(
                function_block=child_node.function_block,
                input_path=child_input_dir,
                output_path=child_job_dir / "output",
                job_dir=child_job_dir
            )
            
            # Check results
            success = exit_code == 0
            output_exists = (child_job_dir / "output" / "_node_anndata.h5ad").exists()
            
            results.append({
                'name': child_node.function_block.name,
                'success': success,
                'exit_code': exit_code,
                'output_exists': output_exists
            })
            
            if success:
                print(f"   ✅ Child executed successfully")
            else:
                print(f"   ❌ Child failed with exit code {exit_code}")
        
        # Step 6: Verify all children received data
        print(f"\n{'='*60}")
        print("RESULTS SUMMARY")
        print(f"{'='*60}")
        
        all_success = all(r['success'] for r in results)
        
        for r in results:
            status = "✅" if r['success'] else "❌"
            print(f"{status} {r['name']}: exit_code={r['exit_code']}, output_exists={r['output_exists']}")
        
        print(f"\nRoot → Children data flow: {'✅ PASSED' if all_success else '❌ FAILED'}")
        print(f"Successfully executed: {sum(1 for r in results if r['success'])}/{len(results)} children")
        
        # Save tree for debugging
        tree_manager.save_tree(output_dir / "test_tree.json")
        
        return all_success


def test_data_integrity_across_nodes():
    """Test that data maintains integrity when passed through nodes."""
    print("\n" + "="*80)
    print("TEST: Data Integrity Across Nodes")
    print("="*80)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "test_output"
        output_dir.mkdir(exist_ok=True)
        
        # Load original data to compare
        original_data = sc.read_h5ad("test_data/zebrafish.h5ad")
        original_shape = original_data.shape
        original_obs_names = list(original_data.obs_names[:10])
        
        print(f"Original data shape: {original_shape}")
        print(f"Original obs names (first 10): {original_obs_names}")
        
        # Create and execute tree
        tree_manager = AnalysisTreeManager()
        tree = tree_manager.create_tree(
            user_request="Test data integrity",
            input_data_path="test_data/zebrafish.h5ad",
            max_nodes=5
        )
        
        paths = tree_manager.create_output_structure(output_dir)
        
        # Execute root
        root_node = tree.nodes[tree.root_node_id]
        from job_executors.python_executor import PythonExecutor
        from utils.docker_utils import DockerManager
        docker_manager = DockerManager()
        executor = PythonExecutor(docker_manager)
        
        node_paths = tree_manager.create_node_directory(root_node.id, paths['nodes_dir'])
        job_dir = tree_manager.create_job_directory(root_node.id, node_paths['node_dir'])
        
        input_dir = job_dir / "input"
        shutil.copy("test_data/zebrafish.h5ad", input_dir / "zebrafish.h5ad")
        
        exit_code, _ = executor.execute(
            function_block=root_node.function_block,
            input_path=input_dir,
            output_path=job_dir / "output",
            job_dir=job_dir
        )
        
        # Check root output
        root_output_file = job_dir / "output" / "_node_anndata.h5ad"
        assert root_output_file.exists(), "Root output should exist"
        
        root_output_data = sc.read_h5ad(root_output_file)
        assert root_output_data.shape == original_shape, f"Root output shape {root_output_data.shape} != original {original_shape}"
        assert list(root_output_data.obs_names[:10]) == original_obs_names, "Root output obs names don't match"
        
        print("✅ Root node preserves data integrity")
        
        # Add and execute a child
        child_block = create_simple_analysis_node("integrity_check", "Check data integrity")
        root_output_dir = node_paths['outputs_dir']
        shutil.copy(root_output_file, root_output_dir / "_node_anndata.h5ad")
        tree.update_node_state(root_node.id, NodeState.COMPLETED)
        root_node.output_data_id = str(root_output_dir)
        
        child_nodes = tree_manager.add_child_nodes(root_node.id, [child_block])
        child_node = child_nodes[0]
        
        # Execute child
        child_paths = tree_manager.create_node_directory(child_node.id, paths['nodes_dir'])
        child_job_dir = tree_manager.create_job_directory(child_node.id, child_paths['node_dir'])
        
        child_input_dir = child_job_dir / "input"
        shutil.copy(root_output_dir / "_node_anndata.h5ad", child_input_dir / "_node_anndata.h5ad")
        
        exit_code, _ = executor.execute(
            function_block=child_node.function_block,
            input_path=child_input_dir,
            output_path=child_job_dir / "output",
            job_dir=child_job_dir
        )
        
        # Check child output
        child_output_file = child_job_dir / "output" / "_node_anndata.h5ad"
        assert child_output_file.exists(), "Child output should exist"
        
        child_output_data = sc.read_h5ad(child_output_file)
        assert child_output_data.shape == original_shape, f"Child output shape {child_output_data.shape} != original {original_shape}"
        assert list(child_output_data.obs_names[:10]) == original_obs_names, "Child output obs names don't match"
        
        print("✅ Child node preserves data integrity")
        print("\n✅ PASSED: Data integrity maintained across root → child")
        
        return True


def test_real_world_scenario():
    """Test a real-world scenario with main agent."""
    print("\n" + "="*80)
    print("TEST: Real-World Multi-Branch Analysis")
    print("="*80)
    
    # Create agent with minimal settings
    agent = MainAgent(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        bug_fixer_type="unified",
        bug_fixer_model="gpt-4o-mini",
        llm_model="gpt-4o-mini",
        enable_interactive_debug=False,  # No debugging for speed
        enable_web_agent=False,
        log_llm_to_stdout=False
    )
    
    # Request that should create multiple branches
    user_request = """
    Create separate analysis branches:
    1. Branch A: Calculate QC metrics
    2. Branch B: Normalize the data
    Both branches should work with the loaded data independently.
    """
    
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "test_output"
        output_dir.mkdir(exist_ok=True)
        
        # Run analysis
        result = agent.run_analysis(
            input_data_path="test_data/zebrafish.h5ad",
            user_request=user_request,
            output_dir=output_dir,
            max_nodes=5,
            max_children=3,  # Allow multiple children per node
            max_debug_trials=0,
            max_iterations=3,
            function_block_timeout=60,
            verbose=True
        )
        
        # Analyze results
        tree_file = output_dir / "analysis_tree.json"
        if tree_file.exists():
            with open(tree_file, 'r') as f:
                tree_data = json.load(f)
            
            print("\nTree Structure:")
            print(f"Total nodes: {len(tree_data['nodes'])}")
            
            # Find root and its children
            root_id = tree_data['root_node_id']
            root_node = tree_data['nodes'][root_id]
            
            print(f"\nRoot: {root_node['function_block']['name']} ({root_node['state']})")
            
            # Check children
            root_children = root_node.get('children', [])
            print(f"Root has {len(root_children)} direct children:")
            
            for child_id in root_children:
                child = tree_data['nodes'].get(child_id)
                if child:
                    print(f"  - {child['function_block']['name']} ({child['state']})")
            
            # Verify data loading root
            assert root_node['function_block']['name'] == 'load_input_data', "Root should be data loader"
            assert root_node['state'] == 'completed', "Root should complete successfully"
            
            print(f"\n✅ Real-world test completed")
            print(f"   Total nodes: {result['total_nodes']}")
            print(f"   Completed: {result['completed_nodes']}")
            print(f"   Failed: {result['failed_nodes']}")
            
            return True
        else:
            print("❌ No tree file generated")
            return False


def run_all_tests():
    """Run all data flow tests."""
    print("\n" + "="*80)
    print("DATA FLOW TESTS: ROOT → CHILDREN")
    print("="*80)
    
    tests = [
        ("Multiple Children Data Flow", test_multiple_children_data_flow),
        ("Data Integrity Check", test_data_integrity_across_nodes),
        ("Real-World Scenario", test_real_world_scenario)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            print(f"\nRunning: {test_name}")
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
    print("FINAL SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, error in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status}: {test_name}")
        if error:
            print(f"         Error: {error[:100]}...")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)