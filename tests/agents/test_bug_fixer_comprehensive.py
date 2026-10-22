#!/usr/bin/env python3
"""Comprehensive test for unified bug fixer with scFates trajectory analysis."""

import sys
import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models import (
    AnalysisTree, AnalysisNode, NodeState, GenerationMode,
    NewFunctionBlock, FunctionBlockType, StaticConfig, Arg
)
from agents import TaskManager, TaskType, TaskStatus
from agents.unified_bug_fixer.unified_bug_fixer import UnifiedBugFixer
from analysis_tree_management.tree_manager import AnalysisTreeManager
from utils import setup_logger

logger = setup_logger("test_bug_fixer_comprehensive")


def create_scfates_block_with_dependency_issue():
    """Create scFates block that will fail due to missing dependency."""
    config = StaticConfig(
        args=[
            Arg(name="n_map", value_type="int", description="Number of mapping points",
                optional=True, default_value=100),
            Arg(name="n_pcs", value_type="int", description="Number of PCs to use",
                optional=True, default_value=20)
        ],
        description="Infer trajectory using scFates",
        tag="trajectory_inference",
        source="test"
    )
    
    # This will fail because scFates is not in requirements
    code = '''import os

def run(path_dict, params):
    """Infer trajectory using scFates."""
    import scanpy as sc
    import pandas as pd
    import numpy as np
    import matplotlib.pyplot as plt
    
    # Load data
    input_path = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    adata = sc.read_h5ad(input_path)

    print("Starting scFates trajectory inference...")
    print(f"Input shape: {adata.shape}")
    
    # This will fail - scFates not imported or installed
    import scFates as scf
    
    # Ensure required preprocessing
    if 'X_pca' not in adata.obsm:
        print("Computing PCA...")
        sc.pp.pca(adata, svd_solver='arpack', n_comps=50)
    
    # Compute principal curve
    n_map = params.get('n_map', 100)
    n_pcs = params.get('n_pcs', 20)
    print(f"Learning principal curve with {n_map} mapping points...")
    scf.tl.curve(adata, Nodes=n_map, use_rep="X_pca", ndims_rep=n_pcs)
    
    # Calculate pseudotime
    print("Calculating pseudotime...")
    scf.tl.pseudotime(adata, n_jobs=4)
    
    # Save results
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    output_path = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    adata.write(output_path)
    
    print("scFates analysis complete!")
    
    return adata
'''
    
    return NewFunctionBlock(
        id="test_scfates_block",
        name="scfates_trajectory_analysis",
        type=FunctionBlockType.PYTHON,
        description="Trajectory inference with scFates",
        code=code,
        requirements="scanpy>=1.9.0\nmatplotlib>=3.6.0\npandas>=2.0.0\nnumpy>=1.24.0",  # Missing scFates!
        parameters={"n_map": 100, "n_pcs": 20},
        static_config=config
    )


def test_bug_fixer_initialization():
    """Test UnifiedBugFixer initialization."""
    print("\n=== Testing Bug Fixer Initialization ===")
    
    # Test with API key
    with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
        bug_fixer = UnifiedBugFixer(
            model_name="gpt-4o-mini",
            max_turns=3,
            seed=42
        )
        assert bug_fixer.max_turns == 3
        assert bug_fixer.save_debug_logs == True
        print("✓ Bug fixer initialized successfully")


def test_task_manager_integration():
    """Test TaskManager functionality."""
    print("\n=== Testing Task Manager Integration ===")
    
    # Setup
    output_dir = Path("test_output_task_manager")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create task manager
    task_manager = TaskManager(output_dir)
    
    # Create main task
    main_task = task_manager.create_task(
        task_type=TaskType.ORCHESTRATION,
        agent_name="orchestrator",
        description="Main analysis task",
        context={'analysis_id': 'test-001'}
    )
    
    print(f"✓ Created main task: {main_task.task_id}")
    
    # Create bug fixing subtask
    bug_fix_task = task_manager.create_task(
        task_type=TaskType.BUG_FIXING,
        agent_name="bug_fixer",
        description="Fix scFates import error",
        context={
            'node_id': 'node-001',
            'error': 'ModuleNotFoundError'
        }
    )
    
    # Link tasks
    task_manager.add_subtask(main_task.task_id, bug_fix_task.task_id)
    
    # Update status
    task_manager.update_task_status(
        bug_fix_task.task_id,
        TaskStatus.COMPLETED,
        results={'fixed': True, 'attempts': 1}
    )
    
    # Get summary
    summary = task_manager.create_task_summary(main_task.task_id)
    print(f"✓ Task hierarchy created: {len(summary.get('subtasks', []))} subtasks")
    
    # Cleanup
    shutil.rmtree(output_dir)


def test_function_block_creation():
    """Test function block creation helpers."""
    print("\n=== Testing Function Block Creation ===")
    
    # Test creating a function block
    block = create_scfates_block_with_dependency_issue()
    
    assert block.name == "scfates_trajectory_analysis"
    assert block.type == FunctionBlockType.PYTHON
    assert "scFates" not in block.requirements  # Intentionally missing
    assert "scanpy" in block.requirements
    assert "n_map" in block.parameters
    
    print("✓ Function block created successfully")
    print(f"✓ Parameters: {list(block.parameters.keys())}")
    print(f"✓ Requirements lines: {len(block.requirements.split())}")


def test_tree_manager_basics():
    """Test basic tree manager operations."""
    print("\n=== Testing Tree Manager Basics ===")
    
    tree_manager = AnalysisTreeManager()
    
    # Create a tree
    tree = tree_manager.create_tree(
        user_request="Test analysis",
        input_data_path="test.h5ad",
        max_nodes=10,
        generation_mode=GenerationMode.ONLY_NEW
    )
    
    assert tree.user_request == "Test analysis"
    assert tree.input_data_path == "test.h5ad"
    assert tree.max_nodes == 10
    assert tree.generation_mode == GenerationMode.ONLY_NEW
    
    # The tree should have a root node (data loading)
    assert tree.total_nodes == 1
    assert tree.root_node_id is not None
    
    root_node = tree.get_node(tree.root_node_id)
    assert root_node.function_block.name == "load_input_data"
    
    print("✓ Tree created with root node")
    print(f"✓ Root node: {root_node.function_block.name}")
    print(f"✓ Total nodes: {tree.total_nodes}")


def main():
    """Run all bug fixer tests."""
    print("=== Comprehensive Bug Fixer Tests ===")
    
    tests = [
        test_bug_fixer_initialization,
        test_task_manager_integration,
        test_function_block_creation,
        test_tree_manager_basics
    ]
    
    results = []
    for test in tests:
        try:
            test()
            results.append((test.__name__, True))
        except Exception as e:
            print(f"\n✗ {test.__name__} failed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test.__name__, False))
    
    print("\n=== Test Summary ===")
    for test_name, success in results:
        status = "✓ Passed" if success else "✗ Failed"
        print(f"{test_name}: {status}")
    
    all_passed = all(success for _, success in results)
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)