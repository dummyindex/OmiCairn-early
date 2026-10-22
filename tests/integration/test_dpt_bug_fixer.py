#!/usr/bin/env python3
"""Test bug fixer specifically on DPT error."""

import os
import shutil
from pathlib import Path
from agents.unified_bug_fixer.unified_bug_fixer import UnifiedBugFixer

if __name__ != "__main__":  # manual script: do not execute at pytest collection time
    import pytest
    pytest.skip("manual diagnostic script; run directly with python", allow_module_level=True)

# Create test workspace
workspace = Path("test_outputs/dpt_bug_fix_test")
workspace.mkdir(parents=True, exist_ok=True)

# Create the failing DPT code
failing_code = '''def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Read input
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    adata = sc.read_h5ad(input_file)
    
    # Run DPT without proper setup
    sc.tl.dpt(adata)
    
    # Try to plot - this will fail
    sc.pl.umap(adata, color="dpt_pseudotime", save="_pseudotime.png", show=False)
    
    # Save output
    adata.write(output_file)
'''

# Save the failing code
with open(workspace / "function_block.py", "w") as f:
    f.write(failing_code)

# Create empty requirements.txt
with open(workspace / "requirements.txt", "w") as f:
    f.write("scanpy\npandas\n")

# Create test input data
input_dir = workspace / "test_input"
output_dir = workspace / "test_output"
input_dir.mkdir(exist_ok=True)
output_dir.mkdir(exist_ok=True)

# Copy test data
shutil.copy("test_data/zebrafish.h5ad", input_dir / "_node_anndata.h5ad")

print("Test workspace created at:", workspace)
print("\nInitializing bug fixer with web agent...")

# Initialize bug fixer
bug_fixer = UnifiedBugFixer(
    model_name="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    enable_web_agent=True,
    max_turns=5
)

# The error we expect
error_message = """KeyError: 'Could not find key dpt_pseudotime in .var_names or .obs.columns.'

File "/workspace/function_block.py", line 15, in run
    sc.pl.umap(adata, color="dpt_pseudotime", save="_pseudotime.png", show=False)
"""

stderr = """WARNING: No root cell found. To compute pseudotime, pass the index or expression vector of a root cell, one of:
    adata.uns['iroot'] = root_cell_index
    adata.var['xroot'] = adata[root_cell_name, :].X
WARNING: Trying to run `tl.dpt` without prior call of `tl.diffmap`. Falling back to `tl.diffmap` with default parameters."""

print("\nRunning bug fixer on DPT error...")
result = bug_fixer.fix_bug(
    node_name="test_dpt_node",
    error_message=error_message,
    stdout="",
    stderr=stderr,
    working_directory=workspace,
    attempt_number=1
)

print("\n" + "="*80)
print("BUG FIX RESULT")
print("="*80)

print(f"Success: {result['success']}")
print(f"Turns: {result['turn_count']}")
print(f"Cost: ${result.get('cost', 0):.4f}")

if result['success']:
    print("\n✓ Bug fixed! Checking the fixed code...")
    with open(workspace / "function_block.py", "r") as f:
        fixed_code = f.read()
    
    print("\nFixed code:")
    print("-"*40)
    print(fixed_code)
    print("-"*40)
    
    # Check if key fixes were applied
    fixes_applied = []
    if "adata.uns['iroot']" in fixed_code:
        fixes_applied.append("✓ Root cell set")
    if "sc.tl.diffmap" in fixed_code:
        fixes_applied.append("✓ Diffusion map computed")
    if "obs_names_make_unique" in fixed_code:
        fixes_applied.append("✓ Observation names made unique")
    
    print("\nFixes applied:")
    for fix in fixes_applied:
        print(f"  {fix}")
else:
    print("\n✗ Bug fix failed!")
    print(f"Final state: {result.get('final_state', 'Unknown')}")

# Check if web agent was used
web_agent_used = any('web_agent_research' in str(action.get('action', {}).get('path', '')) 
                     for action in result.get('actions_taken', []))
print(f"\nWeb agent used: {web_agent_used}")