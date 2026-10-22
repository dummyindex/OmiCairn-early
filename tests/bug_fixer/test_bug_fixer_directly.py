#!/usr/bin/env python3
"""
Test the bug fixer directly with the preprocess_data error
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ != "__main__":
    # Manual diagnostic script: it calls a real LLM API at import time.
    # Do not run it during pytest collection; run it directly with python.
    import pytest
    pytest.skip("manual script requiring OPENAI_API_KEY; run directly with python", allow_module_level=True)

from pathlib import Path
from agents.unified_bug_fixer.unified_bug_fixer import UnifiedBugFixer
from llm_service.openai_service import OpenAIService

# Create test environment
test_dir = Path("test_bug_fixer_workspace")
test_dir.mkdir(exist_ok=True)

# Create the problematic code
code_content = """def run(path_dict, params):
    import scanpy as sc
    import os
    import numpy as np

    # Construct file paths
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')

    # Read input
    if os.path.exists(input_file):
        adata = sc.read_h5ad(input_file)
    else:
        raise FileNotFoundError(f'Input file not found: {input_file}')

    # Normalize and log transform the data
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)

    # Find highly variable genes
    sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
    adata = adata[:, adata.var['highly_variable']]

    # Perform PCA
    sc.pp.pca(adata, n_comps=50)

    # Compute neighbors
    sc.pp.neighbors(adata, n_neighbors=30)

    # Run UMAP
    sc.tl.umap(adata)

    # Save output
    adata.write(output_file)
    print(f'Output saved to {output_file}')

    # Create figures directory
    figures_dir = os.path.join(path_dict['output_dir'], 'figures')
    os.makedirs(figures_dir, exist_ok=True)

    # Plot UMAP - THIS IS THE PROBLEMATIC LINE
    sc.pl.umap(adata, color='highly_variable', save='_umap_hvg.png', show=False)
    print(f'UMAP plot saved to {figures_dir}/umap_hvg.png')

    return adata
"""

# Write the code
code_file = test_dir / "function_block.py"
code_file.write_text(code_content)

# Create requirements
requirements = test_dir / "requirements.txt"
requirements.write_text("scanpy\nnumpy\npandas\nmatplotlib\nseaborn")

# Create the error message
error_message = """KeyError: 'Could not find key highly_variable in .var_names or .obs.columns.'

This error occurs in line 42:
sc.pl.umap(adata, color='highly_variable', save='_umap_hvg.png', show=False)

The problem is that 'highly_variable' is a gene attribute (in adata.var), not a cell attribute (in adata.obs).
UMAP plots show cells, so the color parameter must reference cell-level attributes."""

print("Testing bug fixer with the preprocess_data error...")
print("=" * 80)

# Initialize bug fixer
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    print("ERROR: OPENAI_API_KEY not set")
    sys.exit(1)

llm_service = OpenAIService(api_key=api_key, model="gpt-4o-mini")
bug_fixer = UnifiedBugFixer(llm_service=llm_service)

# Test the bug fixer
print("Calling bug fixer...")
try:
    result = bug_fixer.fix_bug(
        node_name="preprocess_data",
        error_message=error_message,
        working_directory=test_dir,
        attempt_number=1,
        stdout="Output saved to /workspace/output/_node_anndata.h5ad",
        stderr="",
        max_turns=5
    )
    
    print("\nBug fixer result:")
    print(f"Success: {result['success']}")
    print(f"Actions taken: {result.get('actions_taken', 0)}")
    if result['success']:
        print(f"Fixed code saved to: {result.get('fixed_code_path', 'N/A')}")
    else:
        print(f"Error: {result.get('error', 'Unknown error')}")
        
except Exception as e:
    print(f"\nBug fixer failed with exception: {e}")
    import traceback
    traceback.print_exc()

# Clean up
if test_dir.exists():
    import shutil
    shutil.rmtree(test_dir)