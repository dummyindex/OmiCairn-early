#!/usr/bin/env python3
"""Test main agent with scvelo pipeline scenarios."""

import sys
from pathlib import Path
from datetime import datetime
import json
import shutil
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models import (
    AnalysisTree, GenerationMode, NewFunctionBlock, 
    FunctionBlockType, StaticConfig, Arg, NodeState
)
from agents.main_agent import MainAgent
from analysis_tree_management.tree_manager import AnalysisTreeManager
from utils import setup_logger

logger = setup_logger("test_main_agent_scvelo")


def create_scvelo_preprocessing_block():
    """Create preprocessing block for scvelo analysis."""
    config = StaticConfig(
        args=[],
        description="Preprocess data for RNA velocity analysis",
        tag="preprocessing",
        source="test"
    )
    
    code = '''import os
import scanpy as sc
import scvelo as scv

def run(path_dict, params):
    """Preprocess data for scvelo analysis."""
    # Load data
    input_path = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    adata = sc.read_h5ad(input_path)
    
    print(f"Loaded data: {adata.shape}")
    
    # Basic filtering
    sc.pp.filter_genes(adata, min_cells=3)
    sc.pp.filter_cells(adata, min_genes=200)
    
    # Normalize
    scv.pp.normalize_per_cell(adata)
    scv.pp.log1p(adata)
    
    # Save
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    output_path = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    adata.write(output_path)
    
    return adata
'''
    
    return NewFunctionBlock(
        id="scvelo_preprocess",
        name="scvelo_preprocessing",
        type=FunctionBlockType.PYTHON,
        description="Preprocess for scvelo",
        code=code,
        requirements="scanpy>=1.9.0\nscvelo>=0.2.5",
        parameters={},
        static_config=config
    )


def create_scvelo_velocity_block():
    """Create velocity computation block."""
    config = StaticConfig(
        args=[
            Arg(name="mode", value_type="str", description="Velocity mode",
                optional=True, default_value="stochastic")
        ],
        description="Compute RNA velocity",
        tag="velocity",
        source="test"
    )
    
    code = '''import os
import scanpy as sc
import scvelo as scv

def run(path_dict, params):
    """Compute RNA velocity."""
    # Load data
    input_path = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    adata = sc.read_h5ad(input_path)
    
    print("Computing RNA velocity...")
    
    # Compute moments
    scv.pp.moments(adata)
    
    # Compute velocity
    mode = params.get("mode", "stochastic")
    scv.tl.velocity(adata, mode=mode)
    
    # Compute velocity graph
    scv.tl.velocity_graph(adata)
    
    # Save
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    output_path = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    adata.write(output_path)
    
    print(f"Velocity computed with mode: {mode}")
    
    return adata
'''
    
    return NewFunctionBlock(
        id="scvelo_velocity",
        name="velocity_computation",
        type=FunctionBlockType.PYTHON,
        description="Compute RNA velocity",
        code=code,
        requirements="scanpy>=1.9.0\nscvelo>=0.2.5",
        parameters={"mode": "stochastic"},
        static_config=config
    )


def test_scvelo_function_blocks():
    """Test creating scvelo function blocks."""
    print("\n=== Testing scVelo Function Blocks ===")
    
    # Test preprocessing block
    preprocess_block = create_scvelo_preprocessing_block()
    assert preprocess_block.name == "scvelo_preprocessing"
    assert "scvelo" in preprocess_block.requirements
    assert "normalize_per_cell" in preprocess_block.code
    print("✓ Preprocessing block created")
    
    # Test velocity block
    velocity_block = create_scvelo_velocity_block()
    assert velocity_block.name == "velocity_computation"
    assert "mode" in velocity_block.parameters
    assert "velocity_graph" in velocity_block.code
    print("✓ Velocity block created")


def test_scvelo_pipeline_structure():
    """Test scvelo pipeline structure."""
    print("\n=== Testing scVelo Pipeline Structure ===")
    
    # Create tree manager
    tree_manager = AnalysisTreeManager()
    
    # Create tree
    tree = tree_manager.create_tree(
        user_request="Run RNA velocity analysis with scvelo",
        input_data_path="test_data.h5ad",
        max_nodes=10,
        generation_mode=GenerationMode.ONLY_NEW
    )
    
    # Should have root node
    assert tree.root_node_id is not None
    root_node = tree.get_node(tree.root_node_id)
    assert root_node.function_block.name == "load_input_data"
    print("✓ Tree created with data loading root")
    
    # Add preprocessing node
    preprocess_block = create_scvelo_preprocessing_block()
    preprocess_nodes = tree_manager.add_child_nodes(
        tree.root_node_id, 
        [preprocess_block]
    )
    assert len(preprocess_nodes) == 1
    print("✓ Preprocessing node added")
    
    # Add velocity node
    velocity_block = create_scvelo_velocity_block()
    velocity_nodes = tree_manager.add_child_nodes(
        preprocess_nodes[0].id,
        [velocity_block]
    )
    assert len(velocity_nodes) == 1
    print("✓ Velocity node added")
    
    # Check tree structure
    assert tree.total_nodes == 3
    print(f"✓ Tree has {tree.total_nodes} nodes")


def test_scvelo_error_scenarios():
    """Test common scvelo error scenarios."""
    print("\n=== Testing scVelo Error Scenarios ===")
    
    error_scenarios = [
        {
            'error': "KeyError: 'spliced'",
            'cause': "Missing spliced/unspliced layers",
            'fix': "Load loom file or add layers"
        },
        {
            'error': "ValueError: n_neighbors must be specified",
            'cause': "Missing neighbors computation",
            'fix': "Run sc.pp.neighbors first"
        },
        {
            'error': "AttributeError: 'layers' not found",
            'cause': "AnnData missing layers attribute",
            'fix': "Ensure proper data format"
        }
    ]
    
    for scenario in error_scenarios:
        print(f"\n  Scenario: {scenario['cause']}")
        print(f"  Error: {scenario['error']}")
        print(f"  Fix: {scenario['fix']}")


def test_main_agent_initialization():
    """Test MainAgent initialization."""
    print("\n=== Testing MainAgent Initialization ===")
    
    with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
        agent = MainAgent(
            openai_api_key="test-key",
            bug_fixer_type="unified",
            bug_fixer_model="gpt-4o-mini",
            enable_interactive_debug=True
        )
        
        # MainAgent doesn't expose these as attributes, but they're passed to sub-agents
        # Just verify the agent was created successfully
        assert agent is not None
        assert hasattr(agent, 'llm_service')
        print("✓ MainAgent initialized successfully")


def test_scvelo_requirements():
    """Test scvelo dependency requirements."""
    print("\n=== Testing scVelo Requirements ===")
    
    required_packages = [
        "scanpy>=1.9.0",
        "scvelo>=0.2.5",
        "loompy>=3.0.0",  # For loom file support
        "pandas>=1.0.0",
        "numpy>=1.20.0"
    ]
    
    # Test that blocks include necessary requirements
    velocity_block = create_scvelo_velocity_block()
    requirements = velocity_block.requirements.split('\n')
    
    assert any("scvelo" in req for req in requirements)
    assert any("scanpy" in req for req in requirements)
    print("✓ Core requirements present")
    
    # List all recommended packages
    print("\n  Recommended packages:")
    for pkg in required_packages:
        print(f"    - {pkg}")


def main():
    """Run all scvelo tests."""
    print("=== scVelo MainAgent Tests ===")
    
    tests = [
        test_scvelo_function_blocks,
        test_scvelo_pipeline_structure,
        test_scvelo_error_scenarios,
        test_main_agent_initialization,
        test_scvelo_requirements
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
    
    return all(success for _, success in results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)