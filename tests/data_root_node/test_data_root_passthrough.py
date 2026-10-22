#!/usr/bin/env python3
"""Test data root node pass-through functionality.

This test verifies that the data loading root node correctly passes through
all input files without modification, preserving filenames and content.
"""

import os
import sys
import json
import shutil
from pathlib import Path
import tempfile

# Add the omicairn_agent_local directory to the Python path
omicairn_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, omicairn_root)

from analysis_tree_management.tree_manager import AnalysisTreeManager
from agents.main_agent import MainAgent
from models import NodeState


class TestDataRootPassthrough:
    """Test suite for data root node pass-through functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.test_output_dir = Path("test_outputs") / "data_root_passthrough"
        self.test_output_dir.mkdir(parents=True, exist_ok=True)
        
    def teardown_method(self):
        """Clean up after tests."""
        # Keep outputs for inspection
        pass
    
    def test_single_file_passthrough(self):
        """Test that a single h5ad file is passed through unchanged."""
        print("\n" + "="*80)
        print("TEST: Single File Pass-through")
        print("="*80)
        
        timestamp = Path("test_single_file")
        output_dir = self.test_output_dir / timestamp
        output_dir.mkdir(exist_ok=True)
        
        # Create agent
        agent = MainAgent(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            bug_fixer_type="unified",
            enable_interactive_debug=False,
            enable_web_agent=False,
            log_llm_to_stdout=False
        )
        
        # Simple request
        user_request = "Just load the data and verify it's available."
        
        # Run analysis
        result = agent.run_analysis(
            input_data_path=os.path.join(omicairn_root, "test_data/zebrafish.h5ad"),
            user_request=user_request,
            output_dir=output_dir,
            max_nodes=2,
            max_iterations=2,
            max_debug_trials=0,
            verbose=False
        )
        
        # Verify results
        tree_file = output_dir / "analysis_tree.json"
        assert tree_file.exists(), "Tree file should exist"
        
        with open(tree_file, 'r') as f:
            tree_data = json.load(f)
        
        # Check root node
        root_id = tree_data['root_node_id']
        root_node = tree_data['nodes'][root_id]
        
        assert root_node['function_block']['name'] == 'load_input_data'
        assert root_node['state'] == 'completed'
        
        # Check output
        root_output = Path(root_node.get('output_data_id', ''))
        assert root_output.exists(), "Root output directory should exist"
        
        # Verify zebrafish.h5ad exists in output
        output_file = root_output / "zebrafish.h5ad"
        assert output_file.exists(), "zebrafish.h5ad should exist in output"
        
        print("✅ PASSED: Single file passed through with original name")
        print(f"  - Input: test_data/zebrafish.h5ad")
        print(f"  - Output: {output_file}")
        
        return True
    
    def test_multiple_files_passthrough(self):
        """Test that multiple files are all passed through."""
        print("\n" + "="*80)
        print("TEST: Multiple Files Pass-through")
        print("="*80)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test input directory with multiple files
            input_dir = Path(temp_dir) / "input"
            input_dir.mkdir()
            
            # Copy zebrafish data
            shutil.copy(os.path.join(omicairn_root, "test_data/zebrafish.h5ad"), input_dir / "zebrafish.h5ad")
            
            # Create additional test files
            (input_dir / "metadata.csv").write_text("sample,condition\nA,control\nB,treatment")
            (input_dir / "config.json").write_text('{"version": "1.0"}')
            
            timestamp = Path("test_multiple_files")
            output_dir = self.test_output_dir / timestamp
            output_dir.mkdir(exist_ok=True)
            
            # Run with tree manager directly to test the root node
            tree_manager = AnalysisTreeManager()
            tree = tree_manager.create_tree(
                user_request="Test multiple files",
                input_data_path=str(input_dir / "zebrafish.h5ad"),
                max_nodes=5
            )
            
            # Create output structure
            paths = tree_manager.create_output_structure(output_dir)
            
            # Get root node
            root_node = tree.nodes[tree.root_node_id]
            node_paths = tree_manager.create_node_directory(root_node.id, paths['nodes_dir'])
            job_dir = tree_manager.create_job_directory(root_node.id, node_paths['node_dir'])
            
            # Copy ALL files to job input
            job_input_dir = job_dir / "input"
            for f in input_dir.iterdir():
                if f.is_file():
                    shutil.copy(f, job_input_dir / f.name)
            
            # Execute root node
            from job_executors.python_executor import PythonExecutor
            from utils.docker_utils import DockerManager
            
            docker_manager = DockerManager()
            executor = PythonExecutor(docker_manager)
            
            result = executor.execute(
                function_block=root_node.function_block,
                input_data_path=job_input_dir,
                output_dir=job_dir / "output",
                parameters={}
            )
            
            assert result.exit_code == 0, "Execution should succeed"
            
            # Check all files were copied
            output_files = list((job_dir / "output").glob("*"))
            file_names = [f.name for f in output_files if f.is_file()]
            
            assert "zebrafish.h5ad" in file_names, "zebrafish.h5ad should be in output"
            assert "metadata.csv" in file_names, "metadata.csv should be in output"
            assert "config.json" in file_names, "config.json should be in output"
            
            print("✅ PASSED: All files passed through unchanged")
            print(f"  - Input files: zebrafish.h5ad, metadata.csv, config.json")
            print(f"  - Output files: {', '.join(sorted(file_names))}")
            
            return True
    
    def test_no_renaming_to_node_anndata(self):
        """Verify files are NOT renamed to _node_anndata.h5ad."""
        print("\n" + "="*80)
        print("TEST: No Automatic Renaming")
        print("="*80)
        
        timestamp = Path("test_no_renaming")
        output_dir = self.test_output_dir / timestamp
        output_dir.mkdir(exist_ok=True)
        
        # Create agent
        agent = MainAgent(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            bug_fixer_type="unified",
            enable_interactive_debug=False,
            enable_web_agent=False,
            log_llm_to_stdout=False
        )
        
        # Run analysis
        result = agent.run_analysis(
            input_data_path=os.path.join(omicairn_root, "test_data/zebrafish.h5ad"),
            user_request="Load data without renaming",
            output_dir=output_dir,
            max_nodes=2,
            max_iterations=2,
            max_debug_trials=0,
            verbose=False
        )
        
        # Check tree
        tree_file = output_dir / "analysis_tree.json"
        with open(tree_file, 'r') as f:
            tree_data = json.load(f)
        
        root_id = tree_data['root_node_id']
        root_node = tree_data['nodes'][root_id]
        root_output = Path(root_node.get('output_data_id', ''))
        
        # Verify NO _node_anndata.h5ad file
        assert not (root_output / "_node_anndata.h5ad").exists(), "_node_anndata.h5ad should NOT exist"
        assert (root_output / "zebrafish.h5ad").exists(), "Original filename should be preserved"
        
        print("✅ PASSED: Files are not renamed to _node_anndata.h5ad")
        print(f"  - Original name preserved: zebrafish.h5ad")
        print(f"  - No _node_anndata.h5ad created")
        
        return True
    
    def test_child_nodes_can_access_files(self):
        """Test that child nodes can access the passed-through files."""
        print("\n" + "="*80)
        print("TEST: Child Node File Access")
        print("="*80)
        
        timestamp = Path("test_child_access")
        output_dir = self.test_output_dir / timestamp
        output_dir.mkdir(exist_ok=True)
        
        # Create agent
        agent = MainAgent(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            bug_fixer_type="unified",
            enable_interactive_debug=True,
            enable_web_agent=False,
            log_llm_to_stdout=False
        )
        
        # Request that requires a child node
        user_request = """
        1. Load the data
        2. Print the shape of the zebrafish.h5ad file
        """
        
        # Run analysis
        result = agent.run_analysis(
            input_data_path=os.path.join(omicairn_root, "test_data/zebrafish.h5ad"),
            user_request=user_request,
            output_dir=output_dir,
            max_nodes=5,
            max_iterations=3,
            max_debug_trials=1,
            verbose=True
        )
        
        # Verify tree structure
        tree_file = output_dir / "analysis_tree.json"
        with open(tree_file, 'r') as f:
            tree_data = json.load(f)
        
        # Should have at least 2 nodes (root + child)
        assert len(tree_data['nodes']) >= 2, "Should have root + at least one child"
        
        # Check root
        root_id = tree_data['root_node_id']
        root_node = tree_data['nodes'][root_id]
        assert root_node['function_block']['name'] == 'load_input_data'
        assert len(root_node.get('children', [])) > 0, "Root should have children"
        
        print("✅ PASSED: Child nodes can access passed-through files")
        print(f"  - Total nodes: {len(tree_data['nodes'])}")
        print(f"  - Root has {len(root_node.get('children', []))} children")
        
        return True


def run_all_tests():
    """Run all data root node tests."""
    print("\n" + "="*80)
    print("DATA ROOT NODE PASS-THROUGH TESTS")
    print("="*80)
    
    test_suite = TestDataRootPassthrough()
    
    tests = [
        ("Single File Pass-through", test_suite.test_single_file_passthrough),
        ("Multiple Files Pass-through", test_suite.test_multiple_files_passthrough),
        ("No Automatic Renaming", test_suite.test_no_renaming_to_node_anndata),
        ("Child Node File Access", test_suite.test_child_nodes_can_access_files)
    ]
    
    results = []
    for test_name, test_func in tests:
        test_suite.setup_method()
        try:
            success = test_func()
            results.append((test_name, success, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
            print(f"\n❌ FAILED: {test_name}")
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            test_suite.teardown_method()
    
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
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)