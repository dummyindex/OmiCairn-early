#!/usr/bin/env python
"""Test case for real clustering failure with scanpy scatter plot API misuse.

This test reproduces the exact failure from clustering_specific_20250804_030434
where the bug fixer couldn't properly fix scanpy plotting API errors.
"""

import sys
import os
from pathlib import Path
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.bug_fixer_agent import BugFixerAgent
from llm_service import OpenAIService
from models import NewFunctionBlock, FunctionBlockType

def test_real_clustering_scatter_error():
    """Test fixing the exact scanpy scatter plot error from clustering benchmark."""
    
    # Exact failing code from node_7dbb6363-719f-4935-a57f-e5540dacaa35
    failing_code = """def run(path_dict, params):
    import scanpy as sc
    import pandas as pd
    from sklearn import metrics
    from sklearn.cluster import KMeans, AgglomerativeClustering
    import os
    from pathlib import Path
    import matplotlib.pyplot as plt

    def get_param(params, key, default):
        val = params.get(key, default)
        if isinstance(val, dict) and 'default_value' in val:
            return val.get('default_value', default)
        return val if val is not None else default

    # Construct file paths
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')

    # Read input
    if not os.path.exists(input_file):
        raise FileNotFoundError(f'Input file not found: {input_file}')
    adata = sc.read_h5ad(input_file)

    # Get parameters
    n_clusters = get_param(params, 'n_clusters', 5)

    # Apply KMeans clustering
    kmeans = KMeans(n_clusters=n_clusters, random_state=42)
    adata.obs['kmeans'] = kmeans.fit_predict(adata.obsm['X_pca'])

    # Apply Agglomerative clustering
    agglo = AgglomerativeClustering(n_clusters=n_clusters)
    adata.obs['agglo'] = agglo.fit_predict(adata.obsm['X_pca'])

    # Calculate metrics
    if 'ground_truth' in adata.obs.columns:
        ari_kmeans = metrics.adjusted_rand_score(adata.obs['ground_truth'], adata.obs['kmeans'])
        ari_agglo = metrics.adjusted_rand_score(adata.obs['ground_truth'], adata.obs['agglo'])
        print(f'KMeans ARI: {ari_kmeans:.3f}')
        print(f'Agglomerative ARI: {ari_agglo:.3f}')

        # Save metrics to file
        metrics_df = pd.DataFrame({'metric': ['KMeans ARI', 'Agglomerative ARI'], 'value': [ari_kmeans, ari_agglo]})
        metrics_file = os.path.join(path_dict['output_dir'], 'clustering_metrics.csv')
        metrics_df.to_csv(metrics_file, index=False)

    # Create figures directory
    figures_dir = Path(path_dict['output_dir']) / 'figures'
    figures_dir.mkdir(parents=True, exist_ok=True)

    # Plot clustering results - THIS FAILS!
    plt.figure(figsize=(10, 5))
    sc.pl.scatter(adata, x=adata.obsm['X_pca'][:, 0], y=adata.obsm['X_pca'][:, 1], color='kmeans', title='KMeans Clustering', show=False)
    plt.savefig(figures_dir / 'kmeans_clustering.png')
    plt.close()

    plt.figure(figsize=(10, 5))
    sc.pl.scatter(adata, x=adata.obsm['X_pca'][:, 0], y=adata.obsm['X_pca'][:, 1], color='agglo', title='Agglomerative Clustering', show=False)
    plt.savefig(figures_dir / 'agglo_clustering.png')
    plt.close()

    # Save output
    adata.write(output_file)
    print(f'Output saved to {output_file}')

    return adata"""
    
    # Exact error from the real run
    error_message = """Container exited with code 1
WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv
/usr/local/lib/python3.10/dist-packages/anndata/_core/anndata.py:1818: UserWarning: Observation names are not unique. To make them unique, call `.obs_names_make_unique`.
  utils.warn_names_duplicates("obs")
"""
    
    # Exact stdout showing the real error
    stdout = """2025-08-04 07:06:54,489 - function_block_wrapper - INFO - Starting function block execution
2025-08-04 07:06:54,490 - function_block_wrapper - INFO - Loaded parameters: {'n_clusters': {'value_type': 'int', 'description': 'Number of clusters for the algorithms', 'optional': False, 'default_value': 5}}
2025-08-04 07:06:54,490 - function_block_wrapper - INFO - Path dictionary: {'input_dir': '/workspace/input', 'output_dir': '/workspace/output'}
2025-08-04 07:06:54,490 - function_block_wrapper - INFO - Parameters: {'n_clusters': {'value_type': 'int', 'description': 'Number of clusters for the algorithms', 'optional': False, 'default_value': 5}}
2025-08-04 07:06:54,491 - function_block_wrapper - INFO - Importing function block
2025-08-04 07:06:54,493 - function_block_wrapper - INFO - Executing function block with path_dict and params
2025-08-04 07:06:54,718 - numexpr.utils - INFO - NumExpr defaulting to 10 threads.
2025-08-04 07:06:55,151 - matplotlib.font_manager - INFO - generated new fontManager
2025-08-04 07:06:56,132 - function_block_wrapper - ERROR - Error during execution: `x`, `y`, and potential `color` inputs must all come from either `.obs` or `.var`
2025-08-04 07:06:56,133 - function_block_wrapper - ERROR - Traceback (most recent call last):
  File "/workspace/run.py", line 46, in main
    run(path_dict, params)  # Pass both path_dict and params
  File "/workspace/function_block.py", line 54, in run
    sc.pl.scatter(adata, x='X_pca', y='Y_pca', color='kmeans', title='KMeans Clustering', show=False)
  File "/usr/local/lib/python3.10/dist-packages/legacy_api_wrap/__init__.py", line 82, in fn_compatible
    return fn(*args_all, **kw)
  File "/usr/local/lib/python3.10/dist-packages/scanpy/plotting/_anndata.py", line 211, in scatter
    raise ValueError(msg)
ValueError: `x`, `y`, and potential `color` inputs must all come from either `.obs` or `.var`"""
    
    stderr = ""
    
    # Context from parent node (node_6442c148-5de2-4813-8034-55a38be1e372)
    parent_data_structure = {
        "shape": "4161 cells x 15496 genes",
        "obs_columns": [
            "split_id", "sample", "Size_Factor", "condition", 
            "Cluster", "Cell_type", "umap_1", "umap_2", 
            "batch", "n_genes"
        ],
        "var_columns": ["n_cells"],
        "obsm_keys": ["X_pca", "X_umap"],
        "varm_keys": ["PCs"],
        "uns_keys": ["log1p", "neighbors", "pca", "umap"],
        "layers": ["spliced", "unspliced"]
    }
    
    # Create function block
    function_block = NewFunctionBlock(
        name="clustering_comparison",
        type=FunctionBlockType.PYTHON,
        description="Apply various clustering algorithms and compare results",
        code=failing_code,
        requirements="scanpy\npandas\nscikit-learn\nmatplotlib",
        parameters={'n_clusters': {'value_type': 'int', 'default_value': 5}},
        static_config=None
    )
    
    # Initialize bug fixer with OpenAI service
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ No OpenAI API key found")
        return False
    
    # Try with GPT-4o-mini first (as used in the real run)
    llm_service = OpenAIService(api_key=api_key, model="gpt-4o-mini")
    bug_fixer = BugFixerAgent(llm_service=llm_service)
    
    # Test the bug fixer with full context
    context = {
        'function_block': function_block,
        'error_message': error_message,
        'stdout': stdout,
        'stderr': stderr,
        'parent_data_structure': parent_data_structure,  # Include parent context
        'node_id': '7dbb6363-719f-4935-a57f-e5540dacaa35',
        'previous_attempts': [
            "Changed to sc.pl.scatter(adata, x='X_pca', y='Y_pca', ...) - still failed",
            "Changed to sc.pl.scatter(adata, x='X_pca', y='X_pca', ...) - still failed"
        ]
    }
    
    print("Testing bug fixer with GPT-4o-mini...")
    result = bug_fixer.process(context)
    
    # Check if fix was successful
    if result['success'] and result['fixed_code']:
        print("✅ Bug fixer returned fixed code")
        
        fixed_code = result['fixed_code']
        
        # Verify the fix addresses the core issues:
        
        # 1. Should NOT have the problematic scatter plot calls
        if 'sc.pl.scatter(adata, x=adata.obsm' in fixed_code:
            print("❌ Still has problematic numpy array passing to scatter")
            return False
        
        if "sc.pl.scatter(adata, x='X_pca'" in fixed_code:
            print("❌ Still trying to use X_pca as obs column (it's in obsm)")
            return False
            
        # 2. Should use correct alternatives
        good_alternatives = [
            'sc.pl.umap',  # Use UMAP for visualization (available in parent)
            'sc.pl.pca',   # Use PCA visualization
            "adata.obs['PC1']",  # Or add PCA coords to obs
            "adata.obs['PC2']",
            'matplotlib',  # Or use matplotlib directly
            'plt.scatter'   # Direct matplotlib scatter
        ]
        
        has_good_alternative = any(alt in fixed_code for alt in good_alternatives)
        if has_good_alternative:
            print("✅ Uses proper visualization approach")
        else:
            print("⚠️ May not have proper visualization approach")
        
        # 3. Should use correct ground truth column
        if 'Cell_type' in fixed_code:
            print("✅ Uses correct Cell_type column for ground truth")
        elif 'ground_truth' in fixed_code:
            print("❌ Still uses wrong ground_truth column name")
            return False
        
        # Save the fixed code for inspection
        output_dir = Path(__file__).parent / "outputs"
        output_dir.mkdir(exist_ok=True)
        
        output_file = output_dir / "fixed_clustering_comparison.py"
        with open(output_file, "w") as f:
            f.write(fixed_code)
        
        print(f"💾 Fixed code saved to {output_file}")
        
        # Save bug fixer's reasoning
        reasoning_file = output_dir / "bug_fixer_reasoning.json"
        with open(reasoning_file, "w") as f:
            json.dump({
                'reasoning': result.get('reasoning', ''),
                'task_id': result.get('task_id', ''),
                'model': 'gpt-4o-mini'
            }, f, indent=2)
        
        return True
    else:
        print(f"❌ Bug fixer failed: {result.get('reasoning', 'Unknown error')}")
        
        # Try with more powerful model if first attempt fails
        print("\nTrying with GPT-4o (more powerful model)...")
        llm_service_v2 = OpenAIService(api_key=api_key, model="gpt-4o")
        bug_fixer_v2 = BugFixerAgent(llm_service=llm_service_v2)
        
        result_v2 = bug_fixer_v2.process(context)
        
        if result_v2['success'] and result_v2['fixed_code']:
            print("✅ GPT-4o successfully fixed the code!")
            
            output_dir = Path(__file__).parent / "outputs"
            output_dir.mkdir(exist_ok=True)
            
            with open(output_dir / "fixed_clustering_comparison_gpt4o.py", "w") as f:
                f.write(result_v2['fixed_code'])
            
            return True
        else:
            print(f"❌ Even GPT-4o failed: {result_v2.get('reasoning', 'Unknown error')}")
            return False


if __name__ == "__main__":
    print("="*80)
    print("REAL CLUSTERING FAILURE TEST")
    print("="*80)
    print("\n📋 Testing exact failure from clustering_specific_20250804_030434")
    print("   Node: node_7dbb6363-719f-4935-a57f-e5540dacaa35")
    print("   Error: scanpy scatter plot API misuse\n")
    print("-"*40)
    
    success = test_real_clustering_scatter_error()
    
    print("\n" + "="*80)
    print("TEST RESULT")
    print("="*80)
    
    if success:
        print("✅ TEST PASSED: Bug fixer can handle scanpy plotting errors")
        sys.exit(0)
    else:
        print("❌ TEST FAILED: Bug fixer needs improvement")
        sys.exit(1)