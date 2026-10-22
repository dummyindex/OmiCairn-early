#!/usr/bin/env python3
"""Simulated clustering benchmark test without requiring OpenAI API."""

import sys
from pathlib import Path
from datetime import datetime
import tempfile
import json

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from omicairn_agent_local.analysis_tree_management import AnalysisTreeManager
from omicairn_agent_local.models import (
    NewFunctionBlock, FunctionBlockType, StaticConfig, 
    Arg, GenerationMode
)
from omicairn_agent_local.job_executors import ExecutorManager
from omicairn_agent_local.analysis_tree_management import NodeExecutor
from omicairn_agent_local.utils import setup_logger

logger = setup_logger(__name__)


def create_clustering_function_blocks():
    """Create predefined function blocks for clustering benchmark using new specs."""
    
    blocks = []
    
    # 1. Quality control
    blocks.append(NewFunctionBlock(
        name="quality_control",
        type=FunctionBlockType.PYTHON,
        description="Quality control and filtering",
        code="""
def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Construct file paths
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    # Load data
    if os.path.exists(input_file):
        adata = sc.read_h5ad(input_file)
    else:
        # Try to find any h5ad file
        import glob
        h5ad_files = glob.glob(os.path.join(path_dict["input_dir"], "*.h5ad"))
        if h5ad_files:
            adata = sc.read_h5ad(h5ad_files[0])
        else:
            raise FileNotFoundError(f"No input data found in {path_dict['input_dir']}")
    
    # Get parameters with defaults
    min_genes = params.get('min_genes', 200)
    min_cells = params.get('min_cells', 3)
    max_genes = params.get('max_genes', 2500)
    max_mt_percent = params.get('max_mt_percent', 5)
    
    # Basic QC
    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_genes(adata, min_cells=min_cells)
    
    # Calculate QC metrics
    adata.var['mt'] = adata.var_names.str.startswith('MT-')
    sc.pp.calculate_qc_metrics(adata, qc_vars=['mt'], percent_top=None, log1p=False, inplace=True)
    
    # Filter based on QC metrics
    adata = adata[adata.obs.n_genes_by_counts < max_genes, :]
    adata = adata[adata.obs.pct_counts_mt < max_mt_percent, :]
    
    print(f"After QC: {adata.n_obs} cells, {adata.n_vars} genes")
    
    # Save output
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    adata.write(output_file)
    print(f"Output saved to {output_file}")
""",
        parameters={
            "min_genes": 200,
            "min_cells": 3,
            "max_genes": 2500,
            "max_mt_percent": 5
        },
        static_config=StaticConfig(
            description="QC filtering",
            tag="qc",
            args=[
                Arg(name="min_genes", value_type="int", description="Minimum genes per cell", default_value=200),
                Arg(name="max_genes", value_type="int", description="Maximum genes per cell", default_value=2500),
                Arg(name="max_mt_percent", value_type="float", description="Maximum mitochondrial percentage", default_value=5)
            ]
        ),
        requirements="scanpy\npandas\nnumpy"
    ))
    
    # 2. Normalization
    blocks.append(NewFunctionBlock(
        name="normalization",
        type=FunctionBlockType.PYTHON,
        description="Normalize and log-transform data",
        code="""
def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Construct file paths
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    # Load data
    adata = sc.read_h5ad(input_file)
    print(f"Input shape: {adata.shape}")
    
    # Get parameters
    target_sum = params.get('target_sum', 1e4)
    min_mean = params.get('min_mean', 0.0125)
    max_mean = params.get('max_mean', 3)
    min_disp = params.get('min_disp', 0.5)
    
    # Normalize and log-transform
    sc.pp.normalize_total(adata, target_sum=target_sum)
    sc.pp.log1p(adata)
    
    # Find highly variable genes
    sc.pp.highly_variable_genes(adata, min_mean=min_mean, max_mean=max_mean, min_disp=min_disp)
    adata.raw = adata
    adata = adata[:, adata.var.highly_variable]
    
    # Scale data
    sc.pp.scale(adata, max_value=10)
    
    print(f"After HVG selection: {adata.shape}")
    
    # Save output
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    adata.write(output_file)
    print(f"Output saved to {output_file}")
""",
        parameters={
            "target_sum": 1e4,
            "min_mean": 0.0125,
            "max_mean": 3,
            "min_disp": 0.5
        },
        static_config=StaticConfig(
            description="Normalization",
            tag="norm",
            args=[]
        ),
        requirements="scanpy\nnumpy"
    ))
    
    # 3. PCA
    blocks.append(NewFunctionBlock(
        name="pca_reduction",
        type=FunctionBlockType.PYTHON,
        description="Perform PCA dimensionality reduction",
        code="""
def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Construct file paths
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    # Load data
    adata = sc.read_h5ad(input_file)
    
    # Get parameters
    n_comps = params.get('n_comps', 50)
    n_neighbors = params.get('n_neighbors', 10)
    n_pcs = params.get('n_pcs', 40)
    
    # Run PCA
    sc.tl.pca(adata, svd_solver='arpack', n_comps=n_comps)
    
    # Compute neighborhood graph
    sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs)
    
    print(f"PCA computed with {n_comps} components")
    print(f"Neighborhood graph with {n_neighbors} neighbors")
    
    # Save output
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    adata.write(output_file)
    print(f"Output saved to {output_file}")
""",
        parameters={
            "n_comps": 50,
            "n_neighbors": 10,
            "n_pcs": 40
        },
        static_config=StaticConfig(
            description="PCA",
            tag="pca",
            args=[]
        ),
        requirements="scanpy\nnumpy"
    ))
    
    # 4. UMAP with different parameters
    blocks.append(NewFunctionBlock(
        name="umap_visualization",
        type=FunctionBlockType.PYTHON,
        description="Calculate UMAP with different parameters",
        code="""
def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Construct file paths
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    # Load data
    adata = sc.read_h5ad(input_file)
    
    # Get parameters
    test_multiple = params.get('test_multiple', True)
    
    # UMAP with default parameters
    sc.tl.umap(adata)
    print("Computed default UMAP")
    
    if test_multiple:
        # UMAP with different min_dist
        sc.tl.umap(adata, min_dist=0.1, key_added='umap_mindist_0.1')
        sc.tl.umap(adata, min_dist=0.5, key_added='umap_mindist_0.5')
        
        # UMAP with different n_neighbors
        sc.tl.umap(adata, n_neighbors=30, key_added='umap_n30')
        sc.tl.umap(adata, n_neighbors=5, key_added='umap_n5')
        
        print("Computed UMAP with multiple parameter sets")
    
    # Save output
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    adata.write(output_file)
    print(f"Output saved to {output_file}")
""",
        parameters={
            "test_multiple": True
        },
        static_config=StaticConfig(
            description="UMAP visualization",
            tag="umap",
            args=[]
        ),
        requirements="scanpy\nnumpy"
    ))
    
    # 5. Clustering benchmark - multiple methods
    blocks.append(NewFunctionBlock(
        name="clustering_benchmark",
        type=FunctionBlockType.PYTHON,
        description="Run multiple clustering methods",
        code="""
def run(path_dict, params):
    import scanpy as sc
    import pandas as pd
    import os
    
    # Construct file paths
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    # Load data
    adata = sc.read_h5ad(input_file)
    
    # Get parameters
    leiden_resolutions = params.get('leiden_resolutions', [0.5, 1.0, 1.5])
    louvain_resolutions = params.get('louvain_resolutions', [0.5, 1.0])
    
    # 1. Leiden clustering with different resolutions
    for res in leiden_resolutions:
        sc.tl.leiden(adata, resolution=res, key_added=f'leiden_{res}')
        print(f"Leiden clustering with resolution {res}")
    
    # 2. Louvain clustering
    for res in louvain_resolutions:
        sc.tl.louvain(adata, resolution=res, key_added=f'louvain_{res}')
        print(f"Louvain clustering with resolution {res}")
    
    # Save clustering results summary
    clustering_cols = [col for col in adata.obs.columns if 'leiden' in col or 'louvain' in col]
    adata.uns['clustering_methods'] = clustering_cols
    
    print(f"Completed {len(clustering_cols)} clustering methods")
    
    # Save output
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    adata.write(output_file)
    print(f"Output saved to {output_file}")
""",
        parameters={
            "leiden_resolutions": [0.5, 1.0, 1.5],
            "louvain_resolutions": [0.5, 1.0]
        },
        static_config=StaticConfig(
            description="Clustering benchmark",
            tag="clustering",
            args=[]
        ),
        requirements="scanpy\npandas"
    ))
    
    # 6. Calculate metrics
    blocks.append(NewFunctionBlock(
        name="calculate_metrics",
        type=FunctionBlockType.PYTHON,
        description="Calculate clustering metrics",
        code="""
def run(path_dict, params):
    import scanpy as sc
    import pandas as pd
    import numpy as np
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score, silhouette_score
    import os
    
    # Construct file paths
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    # Load data
    adata = sc.read_h5ad(input_file)
    
    # Get ground truth if available
    ground_truth_key = None
    for key in ['cell_type', 'celltype', 'CellType', 'leiden_original']:
        if key in adata.obs.columns:
            ground_truth_key = key
            break
    
    metrics_results = []
    
    # Calculate metrics for each clustering
    clustering_cols = adata.uns.get('clustering_methods', [])
    
    for cluster_key in clustering_cols:
        metrics = {'method': cluster_key}
        
        # Number of clusters
        metrics['n_clusters'] = len(adata.obs[cluster_key].unique())
        
        # If ground truth exists, calculate ARI and NMI
        if ground_truth_key:
            metrics['ARI'] = adjusted_rand_score(adata.obs[ground_truth_key], adata.obs[cluster_key])
            metrics['NMI'] = normalized_mutual_info_score(adata.obs[ground_truth_key], adata.obs[cluster_key])
        
        # Calculate silhouette score (on PCA)
        if 'X_pca' in adata.obsm:
            try:
                sample_size = min(1000, adata.n_obs)
                metrics['silhouette'] = silhouette_score(
                    adata.obsm['X_pca'][:sample_size, :10], 
                    adata.obs[cluster_key].iloc[:sample_size]
                )
            except:
                metrics['silhouette'] = np.nan
        
        metrics_results.append(metrics)
    
    # Save metrics to anndata
    metrics_df = pd.DataFrame(metrics_results)
    adata.uns['clustering_metrics'] = metrics_df.to_dict()
    
    # Save metrics as CSV
    metrics_path = os.path.join(path_dict["output_dir"], "clustering_metrics.csv")
    metrics_df.to_csv(metrics_path, index=False)
    
    print("Clustering metrics:")
    print(metrics_df.to_string())
    
    # Save output
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    adata.write(output_file)
    print(f"Output saved to {output_file}")
""",
        parameters={},
        static_config=StaticConfig(
            description="Calculate metrics",
            tag="metrics",
            args=[]
        ),
        requirements="scanpy\npandas\nnumpy\nscikit-learn"
    ))
    
    # 7. Generate report
    blocks.append(NewFunctionBlock(
        name="generate_report",
        type=FunctionBlockType.PYTHON,
        description="Generate final report and visualizations",
        code="""
def run(path_dict, params):
    import scanpy as sc
    import pandas as pd
    import matplotlib.pyplot as plt
    import os
    
    # Construct file paths
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    # Load data
    adata = sc.read_h5ad(input_file)
    
    # Create output figures directory
    figures_dir = os.path.join(path_dict["output_dir"], "figures")
    os.makedirs(figures_dir, exist_ok=True)
    
    # Set scanpy figure directory
    sc.settings.figdir = figures_dir
    
    # Plot UMAP with different clustering results
    clustering_cols = adata.uns.get('clustering_methods', [])
    
    for cluster_key in clustering_cols[:3]:  # Plot first 3 methods
        sc.pl.umap(adata, color=cluster_key, save=f'_{cluster_key}.png', show=False)
    
    # Plot metrics comparison if available
    if 'clustering_metrics' in adata.uns:
        metrics_df = pd.DataFrame(adata.uns['clustering_metrics'])
        
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        
        # Plot number of clusters
        axes[0].bar(range(len(metrics_df)), metrics_df['n_clusters'])
        axes[0].set_xticks(range(len(metrics_df)))
        axes[0].set_xticklabels(metrics_df['method'], rotation=45)
        axes[0].set_ylabel('Number of Clusters')
        axes[0].set_title('Cluster Count by Method')
        
        # Plot ARI if available
        if 'ARI' in metrics_df.columns:
            axes[1].bar(range(len(metrics_df)), metrics_df['ARI'])
            axes[1].set_xticks(range(len(metrics_df)))
            axes[1].set_xticklabels(metrics_df['method'], rotation=45)
            axes[1].set_ylabel('ARI Score')
            axes[1].set_title('Adjusted Rand Index')
        
        # Plot silhouette score
        if 'silhouette' in metrics_df.columns:
            axes[2].bar(range(len(metrics_df)), metrics_df['silhouette'])
            axes[2].set_xticks(range(len(metrics_df)))
            axes[2].set_xticklabels(metrics_df['method'], rotation=45)
            axes[2].set_ylabel('Silhouette Score')
            axes[2].set_title('Silhouette Score')
        
        plt.tight_layout()
        plt.savefig(os.path.join(figures_dir, 'metrics_comparison.png'))
        plt.close()
    
    # Generate summary report
    report = []
    report.append("=== Clustering Benchmark Report ===")
    report.append(f"Total cells analyzed: {adata.n_obs}")
    report.append(f"Total genes: {adata.n_vars}")
    report.append(f"Clustering methods tested: {len(clustering_cols)}")
    report.append("")
    report.append("Methods tested:")
    for method in clustering_cols:
        n_clusters = len(adata.obs[method].unique())
        report.append(f"  - {method}: {n_clusters} clusters")
    report.append("")
    
    if 'clustering_metrics' in adata.uns:
        report.append("Best performing methods:")
        metrics_df = pd.DataFrame(adata.uns['clustering_metrics'])
        if 'ARI' in metrics_df.columns and not metrics_df['ARI'].isna().all():
            best_ari = metrics_df.loc[metrics_df['ARI'].idxmax()]
            report.append(f"  Highest ARI: {best_ari['method']} (ARI={best_ari['ARI']:.3f})")
        if 'silhouette' in metrics_df.columns and not metrics_df['silhouette'].isna().all():
            valid_sil = metrics_df.dropna(subset=['silhouette'])
            if not valid_sil.empty:
                best_sil = valid_sil.loc[valid_sil['silhouette'].idxmax()]
                report.append(f"  Highest Silhouette: {best_sil['method']} (score={best_sil['silhouette']:.3f})")
    
    report_text = '\n'.join(report)
    report_path = os.path.join(path_dict["output_dir"], "clustering_report.txt")
    with open(report_path, 'w') as f:
        f.write(report_text)
    
    print(report_text)
    
    # Save final results
    os.makedirs(path_dict["output_dir"], exist_ok=True)
    adata.write(output_file)
    print(f"Output saved to {output_file}")
""",
        parameters={},
        static_config=StaticConfig(
            description="Generate report",
            tag="report",
            args=[]
        ),
        requirements="scanpy\npandas\nmatplotlib"
    ))
    
    return blocks


def main():
    """Run simulated clustering benchmark test."""
    
    print("="*80)
    print("CLUSTERING BENCHMARK SIMULATION TEST")
    print("="*80)
    print("This test simulates the clustering benchmark workflow")
    print("without requiring OpenAI API access.")
    print("="*80)
    
    # SYNTHETIC test data (random counts and random labels) - for pipeline plumbing only.
    # Clustering metrics computed on it are meaningless and must not be reported.
    test_data = Path(__file__).parent.parent.parent / "test_data" / "synthetic_clustering.h5ad"
    if not test_data.exists():
        print(f"\nCreating synthetic test data at {test_data}")
        test_data.parent.mkdir(parents=True, exist_ok=True)
        
        # Create synthetic data
        import scanpy as sc
        import numpy as np
        
        # Create a small test dataset
        n_obs = 500
        n_vars = 2000
        
        # Generate count matrix
        np.random.seed(42)
        X = np.random.negative_binomial(5, 0.3, size=(n_obs, n_vars))
        
        adata = sc.AnnData(X=X.astype(np.float32))
        adata.obs_names = [f'Cell_{i}' for i in range(n_obs)]
        adata.var_names = [f'Gene_{i}' for i in range(n_vars)]
        
        # Add some metadata
        adata.obs['cell_type'] = np.random.choice(['TypeA', 'TypeB', 'TypeC'], size=n_obs)
        adata.obs['batch'] = np.random.choice(['Batch1', 'Batch2'], size=n_obs)
        
        # Mark some genes as mitochondrial
        adata.var_names = [f'MT-{i}' if i < 20 else f'Gene_{i}' for i in range(n_vars)]
        
        adata.write(test_data)
        print(f"Created test data: {adata.shape}")
    
    # Setup output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("test_outputs") / "clustering_simulation" / f"run_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nInput data: {test_data}")
    print(f"Output directory: {output_dir}")
    
    # Create analysis tree manager
    print("\n1. Creating Analysis Tree Manager...")
    tree_manager = AnalysisTreeManager()
    
    # Create executor manager and node executor
    print("2. Setting up Executors...")
    executor_manager = ExecutorManager()
    node_executor = NodeExecutor(executor_manager)
    
    # Create analysis tree
    print("3. Creating Analysis Tree...")
    tree = tree_manager.create_tree(
        user_request="Benchmark clustering methods on synthetic test data (pipeline smoke test)",
        input_data_path=str(test_data),
        max_nodes=10,
        max_children_per_node=1,  # Single branch
        generation_mode=GenerationMode.ONLY_NEW
    )
    print(f"   Tree ID: {tree.id}")
    
    # Get predefined function blocks
    print("\n4. Creating Function Blocks for Pipeline...")
    blocks = create_clustering_function_blocks()
    
    # Build the pipeline (single branch)
    print("5. Building Single-Branch Pipeline...")
    
    # Add root node (QC)
    root_node = tree_manager.add_root_node(blocks[0])
    print(f"   ✓ Added root: {root_node.function_block.name}")
    
    current_node = root_node
    # Add remaining nodes in sequence
    for block in blocks[1:]:
        child_nodes = tree_manager.add_child_nodes(current_node.id, [block])
        if child_nodes:
            current_node = child_nodes[0]
            print(f"   ✓ Added node: {current_node.function_block.name}")
    
    print(f"\n   Total nodes in pipeline: {len(tree.nodes)}")
    
    # Execute the tree
    print("\n6. Executing Pipeline...")
    print("   (This will run all clustering and metric calculations)")
    print("-"*60)
    
    results = {}
    current_input = test_data
    
    # Execute nodes in order
    for i, (node_id, node) in enumerate(tree.nodes.items(), 1):
        print(f"\n   [{i}/{len(tree.nodes)}] Executing: {node.function_block.name}")
        print(f"       Input: {current_input}")
        
        try:
            state, output_path = node_executor.execute_node(
                node=node,
                tree=tree,
                input_path=current_input,
                output_base_dir=output_dir
            )
            
            if state.value == "completed" and output_path:
                print(f"       ✓ Success! Output: {output_path}")
                current_input = output_path
                results[node_id] = {
                    "name": node.function_block.name,
                    "state": "completed",
                    "output": output_path
                }
            else:
                print(f"       ✗ Failed: {state.value}")
                results[node_id] = {
                    "name": node.function_block.name,
                    "state": "failed",
                    "error": "Execution failed"
                }
                break
                
        except Exception as e:
            print(f"       ✗ Error: {e}")
            results[node_id] = {
                "name": node.function_block.name,
                "state": "error",
                "error": str(e)
            }
            break
    
    print("\n" + "="*80)
    print("PIPELINE EXECUTION COMPLETE")
    print("="*80)
    
    # Summary
    completed = sum(1 for r in results.values() if r['state'] == 'completed')
    failed = sum(1 for r in results.values() if r['state'] in ['failed', 'error'])
    
    print(f"\nResults Summary:")
    print(f"  Completed nodes: {completed}/{len(tree.nodes)}")
    print(f"  Failed nodes: {failed}")
    
    print(f"\nPipeline Steps:")
    for node_id, result in results.items():
        icon = "✓" if result['state'] == 'completed' else "✗"
        print(f"  {icon} {result['name']}: {result['state']}")
    
    # Check final outputs
    final_output_dir = Path(current_input) if completed > 0 else None
    
    if final_output_dir and final_output_dir.exists():
        print(f"\nFinal Outputs in: {final_output_dir}")
        
        # Check for expected files
        expected_files = ['_node_anndata.h5ad', 'clustering_metrics.csv', 'clustering_report.txt']
        for filename in expected_files:
            file_path = final_output_dir / filename
            if file_path.exists():
                print(f"  ✓ {filename}")
            else:
                print(f"  ✗ {filename} (not found)")
        
        # Check for figures
        figures_dir = final_output_dir / 'figures'
        if figures_dir.exists():
            figures = list(figures_dir.glob('*.png'))
            print(f"  ✓ Generated {len(figures)} figures")
            for fig in figures[:5]:  # Show first 5
                print(f"    - {fig.name}")
    
    # Save analysis tree
    tree_file = output_dir / "analysis_tree.json"
    tree_manager.save_tree(tree_file)
    print(f"\nAnalysis tree saved to: {tree_file}")
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)
    
    return 0 if completed == len(tree.nodes) else 1


if __name__ == "__main__":
    sys.exit(main())