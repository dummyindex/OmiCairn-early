#!/usr/bin/env python3
"""Clustering benchmark test with LLM - ensures correct output structure."""

import os
import sys
from pathlib import Path
from datetime import datetime
import json
from dotenv import load_dotenv
import scanpy as sc
import numpy as np
import pandas as pd
from typing import Dict, Any, List

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from omicairn_agent_local.agents import MainAgent
from omicairn_agent_local.utils import setup_logger

logger = setup_logger(__name__)


def create_clustering_test_data(output_path: Path, n_obs: int = 1000, n_vars: int = 2000):
    """Create synthetic test data for clustering benchmark."""
    np.random.seed(42)
    
    # Generate count matrix
    X = np.random.negative_binomial(5, 0.3, size=(n_obs, n_vars))
    
    adata = sc.AnnData(X=X.astype(np.float32))
    adata.obs_names = [f'Cell_{i:04d}' for i in range(n_obs)]
    adata.var_names = [f'Gene_{i:04d}' for i in range(n_vars)]
    
    # Add ground truth cell types for benchmarking
    n_types = 5
    adata.obs['cell_type'] = np.random.choice([f'Type_{i}' for i in range(n_types)], size=n_obs)
    adata.obs['batch'] = np.random.choice(['Batch1', 'Batch2'], size=n_obs)
    
    # Mark mitochondrial genes
    adata.var['mt'] = [i < 50 for i in range(n_vars)]
    adata.var_names = [f'MT-{i:04d}' if i < 50 else f'Gene_{i:04d}' for i in range(n_vars)]
    
    # Add some QC metrics
    adata.obs['n_genes'] = (X > 0).sum(axis=1)
    adata.obs['total_counts'] = X.sum(axis=1)
    
    adata.write(output_path)
    print(f"Created test data: {adata.shape}")
    print(f"Cell types: {adata.obs['cell_type'].value_counts().to_dict()}")
    return adata


def verify_output_structure(output_dir: Path) -> Dict[str, Any]:
    """Verify the output structure follows specifications."""
    verification = {
        'structure_valid': True,
        'issues': [],
        'statistics': {}
    }
    
    # Find tree directory
    tree_dirs = list(output_dir.glob("*/nodes"))
    if not tree_dirs:
        verification['structure_valid'] = False
        verification['issues'].append("No tree directory with nodes/ found")
        return verification
    
    tree_dir = tree_dirs[0].parent
    nodes_dir = tree_dir / "nodes"
    
    print("\n" + "="*80)
    print("OUTPUT STRUCTURE VERIFICATION")
    print("="*80)
    
    # Check tree structure
    if (tree_dir / "analysis_tree.json").exists():
        print("✅ analysis_tree.json found")
        with open(tree_dir / "analysis_tree.json") as f:
            tree_data = json.load(f)
            verification['statistics']['total_nodes'] = len(tree_data.get('nodes', {}))
    else:
        print("❌ analysis_tree.json missing")
        verification['issues'].append("analysis_tree.json missing")
    
    # Check main agent directory
    main_dirs = list(output_dir.glob("main_*"))
    if main_dirs:
        main_dir = main_dirs[0]
        print(f"✅ Main agent directory: {main_dir.name}")
        
        # Verify no agent_tasks in main
        if (main_dir / "agent_tasks").exists():
            print("❌ ERROR: agent_tasks found in main directory!")
            verification['issues'].append("agent_tasks should not be in main directory")
            verification['structure_valid'] = False
        else:
            print("✅ No agent_tasks in main directory (correct)")
            
        # Check for required files
        for required_file in ["agent_info.json", "user_request.txt"]:
            if (main_dir / required_file).exists():
                print(f"  ✅ {required_file}")
            else:
                print(f"  ❌ {required_file} missing")
                verification['issues'].append(f"{required_file} missing in main directory")
    
    # Check nodes
    print(f"\n📁 Nodes Directory: {nodes_dir.relative_to(output_dir)}")
    
    node_count = 0
    completed_nodes = 0
    nodes_with_logs = 0
    
    for node_dir in nodes_dir.glob("node_*"):
        node_count += 1
        node_name = node_dir.name
        print(f"\n  Node: {node_name}")
        
        # Check required subdirectories
        required_dirs = ["function_block", "jobs", "outputs", "agent_tasks"]
        for req_dir in required_dirs:
            if (node_dir / req_dir).exists():
                print(f"    ✅ {req_dir}/")
            else:
                print(f"    ❌ {req_dir}/ missing")
                verification['issues'].append(f"{node_name}/{req_dir} missing")
        
        # Check function block files
        fb_dir = node_dir / "function_block"
        if fb_dir.exists():
            for fb_file in ["code.py", "config.json", "requirements.txt"]:
                if (fb_dir / fb_file).exists():
                    print(f"      ✅ {fb_file}")
                else:
                    print(f"      ❌ {fb_file} missing")
        
        # Check outputs
        if (node_dir / "outputs" / "_node_anndata.h5ad").exists():
            print(f"    ✅ Output data exists")
            completed_nodes += 1
        
        # Check agent_tasks
        agent_tasks_dir = node_dir / "agent_tasks"
        if agent_tasks_dir.exists():
            agents = list(agent_tasks_dir.iterdir())
            if agents:
                nodes_with_logs += 1
                print(f"    📝 Agent logs:")
                for agent_dir in agents:
                    if agent_dir.is_dir():
                        log_count = len(list(agent_dir.glob("**/*.json")))
                        code_count = len(list(agent_dir.glob("**/*.py")))
                        print(f"      - {agent_dir.name}: {log_count} logs, {code_count} code files")
    
    verification['statistics']['node_count'] = node_count
    verification['statistics']['completed_nodes'] = completed_nodes
    verification['statistics']['nodes_with_logs'] = nodes_with_logs
    
    # Final validation
    print("\n" + "-"*80)
    print("SUMMARY")
    print("-"*80)
    print(f"Total nodes: {node_count}")
    print(f"Completed nodes: {completed_nodes}")
    print(f"Nodes with agent logs: {nodes_with_logs}")
    
    if verification['issues']:
        print(f"\n⚠️ Found {len(verification['issues'])} issues")
        verification['structure_valid'] = False
    else:
        print("\n✅ Output structure is valid!")
    
    return verification


def check_clustering_results(output_dir: Path) -> Dict[str, Any]:
    """Check the clustering analysis results."""
    results = {
        'clustering_complete': False,
        'metrics': {},
        'stages_completed': []
    }
    
    print("\n" + "="*80)
    print("CLUSTERING RESULTS")
    print("="*80)
    
    # Find the final output
    for node_dir in output_dir.glob("*/nodes/node_*/outputs"):
        output_file = node_dir / "_node_anndata.h5ad"
        if output_file.exists():
            try:
                adata = sc.read_h5ad(output_file)
                
                # Check what processing was done
                if 'highly_variable' in adata.var.columns:
                    results['stages_completed'].append('hvg_selection')
                    print("✅ Highly variable genes selected")
                
                if 'X_pca' in adata.obsm:
                    results['stages_completed'].append('pca')
                    print(f"✅ PCA computed: {adata.obsm['X_pca'].shape[1]} components")
                
                if 'X_umap' in adata.obsm:
                    results['stages_completed'].append('umap')
                    print("✅ UMAP embedding computed")
                
                if 'leiden' in adata.obs.columns:
                    results['stages_completed'].append('clustering')
                    n_clusters = adata.obs['leiden'].nunique()
                    results['metrics']['n_clusters'] = n_clusters
                    print(f"✅ Leiden clustering: {n_clusters} clusters")
                    results['clustering_complete'] = True
                    
                    # Calculate metrics if ground truth exists
                    if 'cell_type' in adata.obs.columns:
                        from sklearn.metrics import adjusted_rand_score, silhouette_score
                        
                        ari = adjusted_rand_score(adata.obs['cell_type'], adata.obs['leiden'])
                        results['metrics']['ari'] = ari
                        print(f"  ARI score: {ari:.3f}")
                        
                        if 'X_pca' in adata.obsm:
                            sil = silhouette_score(adata.obsm['X_pca'], adata.obs['leiden'])
                            results['metrics']['silhouette'] = sil
                            print(f"  Silhouette score: {sil:.3f}")
                
                # Save final shape
                results['final_shape'] = adata.shape
                print(f"\nFinal data shape: {adata.shape}")
                
            except Exception as e:
                print(f"Error reading {output_file}: {e}")
    
    return results


def main():
    """Run clustering benchmark with LLM."""
    
    print("="*80)
    print("CLUSTERING BENCHMARK TEST WITH LLM")
    print("="*80)
    print("This test runs a full clustering analysis pipeline using LLM-generated code")
    print("and verifies the output structure follows specifications.")
    print("="*80)
    
    # Load environment
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded environment from {env_path}")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        return 1
    
    print("Using OpenAI API key: set")
    
    # Create test data
    test_data = Path("test_data") / "clustering_benchmark.h5ad"
    test_data.parent.mkdir(exist_ok=True)
    
    print(f"\n1. Creating test data...")
    adata = create_clustering_test_data(test_data)
    
    # Setup output directory - ALWAYS use clustering_llm
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("test_outputs") / "clustering_llm" / f"run_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n2. Output directory: {output_dir}")
    
    # Define clustering pipeline request
    user_request = """
    Perform a complete single-cell clustering analysis pipeline:
    1. Quality control: filter cells with < 200 genes and genes present in < 3 cells
    2. Normalization: normalize to 10,000 counts per cell and log-transform
    3. Feature selection: identify highly variable genes
    4. Dimensionality reduction: PCA with 50 components, then UMAP
    5. Clustering: Leiden clustering with resolution 0.8
    6. Calculate clustering metrics if cell_type column exists (ARI score)
    Save visualizations including UMAP colored by clusters.
    """
    
    print(f"\n3. Running analysis...")
    print("Request:", user_request.strip().replace('\n    ', '\n'))
    print("-"*80)
    
    # Initialize MainAgent
    agent = MainAgent(openai_api_key=api_key)
    
    # Run analysis
    try:
        results = agent.run_analysis(
            input_data_path=test_data,
            user_request=user_request,
            output_dir=output_dir,
            max_nodes=10,  # Allow enough nodes for full pipeline
            max_children=2,
            max_debug_trials=2,
            generation_mode="only_new",  # Generate new function blocks
            verbose=True
        )
        
        print("\n" + "="*80)
        print("ANALYSIS COMPLETE")
        print("="*80)
        print(f"Status: SUCCESS")
        print(f"Total nodes: {results.get('total_nodes', 0)}")
        print(f"Completed nodes: {results.get('completed_nodes', 0)}")
        print(f"Failed nodes: {results.get('failed_nodes', 0)}")
        
    except Exception as e:
        print(f"\n❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Verify output structure
    print("\n4. Verifying output structure...")
    verification = verify_output_structure(output_dir)
    
    # Check clustering results
    print("\n5. Checking clustering results...")
    clustering_results = check_clustering_results(output_dir)
    
    # Final report
    print("\n" + "="*80)
    print("FINAL REPORT")
    print("="*80)
    
    if verification['structure_valid']:
        print("✅ Output structure is valid")
    else:
        print(f"❌ Output structure has {len(verification['issues'])} issues")
        for issue in verification['issues'][:5]:
            print(f"  - {issue}")
    
    if clustering_results['clustering_complete']:
        print("✅ Clustering analysis completed successfully")
        print(f"  - Stages completed: {', '.join(clustering_results['stages_completed'])}")
        if clustering_results['metrics']:
            print(f"  - Metrics: {clustering_results['metrics']}")
    else:
        print("⚠️ Clustering analysis incomplete")
        if clustering_results['stages_completed']:
            print(f"  - Completed stages: {', '.join(clustering_results['stages_completed'])}")
    
    print(f"\n📁 Results saved to: {output_dir}")
    print("="*80)
    
    return 0 if verification['structure_valid'] else 1


if __name__ == "__main__":
    sys.exit(main())