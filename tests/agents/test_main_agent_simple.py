#!/usr/bin/env python3
"""Simplified test for main agent with mock scvelo pipeline."""

import os
import sys
from pathlib import Path
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models import (
    AnalysisTree, GenerationMode, NewFunctionBlock, 
    FunctionBlockType, StaticConfig, Arg, NodeState
)
from agents import FunctionCreatorAgent
from analysis_tree_management import AnalysisTreeManager
from job_executors import ExecutorManager
from analysis_tree_management.node_executor import NodeExecutor
from utils import setup_logger

logger = setup_logger("test_main_agent_simple")


def _skip_or_exit(reason):
    """Skip under pytest (missing data/Docker is not a test failure); exit when run as a script."""
    if "pytest" in sys.modules:
        import pytest
        pytest.skip(reason)
    print(f"Error: {reason}")
    sys.exit(1)


class SimpleScVeloPipeline:
    """Simple predefined scvelo pipeline."""
    
    def __init__(self):
        self.steps = {
            'root': self._create_qc_block(),
            'qc': self._create_preprocessing_block(),
            'preprocessing': [self._create_velocity_block(), self._create_plots_block()],
            'done': None
        }
        
    def get_next_blocks(self, current_node=None):
        """Get next blocks based on current node."""
        if current_node is None:
            return [self.steps['root']], False
        
        node_name = current_node.function_block.name
        if 'quality_control' in node_name:
            return [self.steps['qc']], False
        elif 'preprocessing' in node_name:
            return self.steps['preprocessing'], False
        elif 'velocity' in node_name or 'plots' in node_name:
            # Check if both velocity and plots are done
            parent = current_node
            siblings = [n for n in parent.parent.children if n.id != current_node.id] if hasattr(parent, 'parent') else []
            if any('velocity' in s.function_block.name or 'plots' in s.function_block.name for s in siblings):
                return [], True  # Both done, satisfied
            return [], False
        else:
            return [], True
    
    def _create_qc_block(self):
        """Create quality control block."""
        config = StaticConfig(
            args=[],
            description="Quality control",
            tag="qc",
            source="test"
        )
        
        code = '''
def run(path_dict, params):
    """Quality control."""
    import os
    import scanpy as sc
    import matplotlib.pyplot as plt
    
    # Load data from path_dict
    input_path = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    if not os.path.exists(input_path):
        h5ad_files = [f for f in os.listdir(path_dict["input_dir"]) if f.endswith(".h5ad")]
        if h5ad_files:
            input_path = os.path.join(path_dict["input_dir"], h5ad_files[0])
    adata = sc.read_h5ad(input_path) if "sc" in locals() or "sc" in globals() else None

    print(f"QC: Input shape {adata.shape}")
    
    # Basic filtering
    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.filter_genes(adata, min_cells=3)
    
    # Calculate QC metrics
    adata.var['mt'] = adata.var_names.str.startswith('MT-') | adata.var_names.str.startswith('mt-')
    sc.pp.calculate_qc_metrics(adata, qc_vars=['mt'], percent_top=None, log1p=False, inplace=True)
    
    # Filter by mitochondrial percentage
    adata = adata[adata.obs.pct_counts_mt < 20, :]
    
    print(f"QC: Output shape {adata.shape}")
    
    # Simple QC plot
    fig, ax = plt.subplots(1, 1, figsize=(8, 6))
    ax.scatter(adata.obs['total_counts'], adata.obs['pct_counts_mt'], alpha=0.3)
    ax.set_xlabel('Total counts')
    ax.set_ylabel('Mitochondrial %')
    plt.savefig('/workspace/output/figures/qc_scatter.png', dpi=150)
    plt.close()
    
    return adata
'''
        
        return NewFunctionBlock(
            name="quality_control",
            type=FunctionBlockType.PYTHON,
            description="Quality control",
            code=code,
            requirements="scanpy>=1.9.0\nmatplotlib>=3.6.0",
            parameters={},
            static_config=config
        )
    
    def _create_preprocessing_block(self):
        """Create preprocessing block."""
        config = StaticConfig(
            args=[],
            description="Preprocessing for velocity",
            tag="preprocessing",
            source="test"
        )
        
        code = '''
def run(path_dict, params):
    """Preprocess data."""
    import os
    import scanpy as sc
    import numpy as np
    
    # Load data from path_dict
    input_path = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    if not os.path.exists(input_path):
        h5ad_files = [f for f in os.listdir(path_dict["input_dir"]) if f.endswith(".h5ad")]
        if h5ad_files:
            input_path = os.path.join(path_dict["input_dir"], h5ad_files[0])
    adata = sc.read_h5ad(input_path) if "sc" in locals() or "sc" in globals() else None

    print("Preprocessing data...")
    
    # Normalize and log
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    
    # HVG
    sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
    adata = adata[:, adata.var.highly_variable]
    
    # Scale
    sc.pp.scale(adata, max_value=10)
    
    # PCA
    sc.tl.pca(adata, svd_solver='arpack')
    
    # Neighbors and UMAP
    sc.pp.neighbors(adata, n_neighbors=30, n_pcs=40)
    sc.tl.umap(adata)
    sc.tl.leiden(adata)
    
    # SYNTHETIC smoke-test fixture only: random spliced/unspliced layers so the
    # scVelo code path can execute. Not biologically meaningful; never used for reported results.
    rng = np.random.default_rng(0)
    print("Creating synthetic velocity layers...")
    adata.layers['spliced'] = adata.X.copy()
    adata.layers['unspliced'] = adata.X.copy() * rng.uniform(0.2, 0.4, adata.shape)
    
    print(f"Preprocessed: {adata.shape}")
    
    return adata
'''
        
        return NewFunctionBlock(
            name="preprocessing",
            type=FunctionBlockType.PYTHON,
            description="Preprocessing",
            code=code,
            requirements="scanpy>=1.9.0\nnumpy>=1.24.0\npython-igraph>=0.10.0\nleidenalg>=0.9.0",
            parameters={},
            static_config=config
        )
    
    def _create_velocity_block(self):
        """Create velocity block."""
        config = StaticConfig(
            args=[],
            description="RNA velocity",
            tag="velocity",
            source="test"
        )
        
        code = '''
def run(path_dict, params):
    """Run velocity analysis."""
    import os
    import scanpy as sc
    import scvelo as scv
    
    # Load data from path_dict
    input_path = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    if not os.path.exists(input_path):
        h5ad_files = [f for f in os.listdir(path_dict["input_dir"]) if f.endswith(".h5ad")]
        if h5ad_files:
            input_path = os.path.join(path_dict["input_dir"], h5ad_files[0])
    adata = sc.read_h5ad(input_path) if "sc" in locals() or "sc" in globals() else None

    print("Running velocity analysis...")
    
    # Velocity preprocessing
    scv.pp.filter_and_normalize(adata, min_shared_counts=20, n_top_genes=2000)
    scv.pp.moments(adata, n_pcs=30, n_neighbors=30)
    
    # Velocity
    scv.tl.velocity(adata, mode='stochastic')
    scv.tl.velocity_graph(adata)
    
    # Velocity metrics
    scv.tl.velocity_confidence(adata)
    scv.tl.velocity_pseudotime(adata)
    
    print("Velocity analysis complete")
    
    return adata
'''
        
        return NewFunctionBlock(
            name="velocity_analysis",
            type=FunctionBlockType.PYTHON,
            description="RNA velocity",
            code=code,
            requirements="scvelo>=0.2.5",
            parameters={},
            static_config=config
        )
    
    def _create_plots_block(self):
        """Create plotting block."""
        config = StaticConfig(
            args=[],
            description="Generate plots",
            tag="plots",
            source="test"
        )
        
        code = '''
def run(path_dict, params):
    """Generate plots."""
    import os
    import scanpy as sc
    import scvelo as scv
    import matplotlib.pyplot as plt
    
    # Load data from path_dict
    input_path = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    if not os.path.exists(input_path):
        h5ad_files = [f for f in os.listdir(path_dict["input_dir"]) if f.endswith(".h5ad")]
        if h5ad_files:
            input_path = os.path.join(path_dict["input_dir"], h5ad_files[0])
    adata = sc.read_h5ad(input_path) if "sc" in locals() or "sc" in globals() else None

    print("Generating plots...")
    
    # UMAP plots
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    sc.pl.umap(adata, color='leiden', ax=axes[0], show=False, title='Clusters')
    
    if 'velocity_pseudotime' in adata.obs.columns:
        scv.pl.scatter(adata, c='velocity_pseudotime', cmap='gnuplot',
                       ax=axes[1], show=False, title='Velocity Pseudotime')
    else:
        sc.pl.umap(adata, color='leiden', ax=axes[1], show=False)
    
    plt.tight_layout()
    plt.savefig('/workspace/output/figures/analysis_plots.png', dpi=150)
    plt.close()
    
    # Velocity stream plot
    if 'velocity_graph' in adata.uns:
        scv.pl.velocity_embedding_stream(adata, basis='umap', 
                                         save='_velocity_stream.png', show=False)
    
    print("Plots generated")
    
    return adata
'''
        
        return NewFunctionBlock(
            name="visualization_plots",
            type=FunctionBlockType.PYTHON,
            description="Generate plots",
            code=code,
            requirements="scanpy>=1.9.0\nscvelo>=0.2.5\nmatplotlib>=3.6.0",
            parameters={},
            static_config=config
        )


def test_simple_scvelo_pipeline():
    """Test simple scvelo pipeline execution."""
    print("\n=== Testing Simple scVelo Pipeline ===")
    
    # Setup
    input_data = Path(os.environ.get("TEST_DATA_DIR", "test_data")) / "zebrafish.h5ad"
    output_dir = Path("test_outputs/simple_scvelo_agent")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not input_data.exists():
        _skip_or_exit(f"Test data not found at {input_data} (set TEST_DATA_DIR)")
    
    # Create components
    tree_manager = AnalysisTreeManager()
    executor_manager = ExecutorManager()
    node_executor = NodeExecutor(executor_manager)
    pipeline = SimpleScVeloPipeline()
    
    # Validate environment
    print("\nValidating environment...")
    validation = executor_manager.validate_environment()
    if not validation.get('docker_available'):
        _skip_or_exit("Docker is not available")
    
    # Create tree
    tree = tree_manager.create_tree(
        user_request="Run scVelo pipeline",
        input_data_path=str(input_data),
        max_nodes=10,
        max_children_per_node=3,
        generation_mode=GenerationMode.ONLY_NEW
    )
    
    print(f"\nRunning pipeline...")
    
    current_data_path = input_data
    satisfied = False
    iteration = 0
    
    while not satisfied and iteration < 5:
        iteration += 1
        print(f"\n--- Iteration {iteration} ---")
        
        # Get nodes to expand
        if not tree.root_node_id:
            # Add root
            blocks, satisfied = pipeline.get_next_blocks(None)
            if blocks:
                tree_manager.add_root_node(blocks[0])
                print(f"Added root: {blocks[0].name}")
        else:
            # Find completed leaf nodes
            leaf_nodes = [
                node for node in tree.nodes.values()
                if node.state == NodeState.COMPLETED and not node.children
            ]
            
            for leaf in leaf_nodes:
                blocks, satisfied = pipeline.get_next_blocks(leaf)
                if blocks:
                    tree_manager.add_child_nodes(leaf.id, blocks)
                    for b in blocks:
                        print(f"Added child: {b.name}")
        
        # Execute pending nodes
        pending = tree_manager.get_execution_order()
        
        for node in pending:
            print(f"\nExecuting: {node.function_block.name}")
            
            # Update state
            tree_manager.update_node_execution(node.id, NodeState.RUNNING)
            
            # Get input path
            input_path = tree_manager.get_latest_data_path(node.id) or current_data_path
            
            # Execute
            state, output_path, result = node_executor.execute_node(
                node=node, tree=tree, input_path=input_path, output_base_dir=output_dir / tree.id
            )
            
            # Update results
            if state == NodeState.COMPLETED:
                tree_manager.update_node_execution(
                    node.id,
                    state=state,
                    output_data_id=output_path,
                    figures=result.figures if result else [],
                    logs=[result.logs] if result and result.logs else [],
                    duration=result.duration if result else 0
                )
                
                if output_path:
                    current_data_path = Path(output_path)
                
                print(f"✓ Completed in {result.duration if result else 0:.1f}s")
            else:
                tree_manager.update_node_execution(
                    node.id,
                    state=state,
                    error=result.error if result else "Unknown error"
                )
                print(f"✗ Failed: {result.error if result else 'Unknown error'}")
        
        # Save tree
        tree_manager.save_tree(output_dir / "analysis_tree.json")
    
    # Display results
    print("\n=== Pipeline Summary ===")
    summary = tree_manager.get_summary()
    print(f"Total Nodes: {summary['total_nodes']}")
    print(f"Completed: {summary['completed_nodes']}")
    print(f"Failed: {summary['failed_nodes']}")
    
    print("\n=== Analysis Tree ===")
    _print_tree(tree)
    
    print("\n=== Output Files ===")
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and not path.name.startswith('.'):
            relative = path.relative_to(output_dir)
            if len(str(relative)) < 100:  # Skip very long paths
                print(f"  {relative}")
    
    print("\n=== Test Complete ===")
    return summary['completed_nodes'] >= 3  # Success if we completed at least 3 nodes


def _print_tree(tree, node_id=None, prefix=""):
    """Print tree structure."""
    if node_id is None:
        if tree.root_node_id:
            _print_tree(tree, tree.root_node_id)
        return
    
    node = tree.get_node(node_id)
    if not node:
        return
    
    status = {
        NodeState.COMPLETED: '✓',
        NodeState.FAILED: '✗',
        NodeState.PENDING: '○',
        NodeState.RUNNING: '●'
    }.get(node.state, '?')
    
    print(f"{prefix}{status} {node.function_block.name}")
    
    for i, child_id in enumerate(node.children):
        is_last = i == len(node.children) - 1
        child_prefix = prefix + ("  " if is_last else "│ ")
        _print_tree(tree, child_id, child_prefix + "└─")


if __name__ == "__main__":
    success = test_simple_scvelo_pipeline()
    sys.exit(0 if success else 1)