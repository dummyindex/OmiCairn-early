# Function Block FAQ - Common Issues and Solutions

Quick reference for common function block errors and their solutions.

## Table of Contents
1. [Function Signature Issues](#function-signature-issues)
2. [Previous Nodes Access](#previous-nodes-access)
3. [File I/O Patterns](#file-io-patterns)
4. [Import and Dependency Issues](#import-and-dependency-issues)
5. [Data Structure Issues](#data-structure-issues)
6. [Output Requirements](#output-requirements)
7. [Common Error Messages](#common-error-messages)

---

## Function Signature Issues

### ❌ WRONG: Extra parameters
```python
def run(path_dict, params, previous_nodes):  # TypeError: missing argument
# NEVER add previous_nodes as a parameter!
# previous_nodes is imported, not passed as argument
```

### ✅ CORRECT: Exactly two parameters
```python
from function_block_runtime import previous_nodes  # Import it!

def run(path_dict, params):  # Must be exactly these two parameters
    # Now you can use previous_nodes here - but discover nodes dynamically!
    nodes = previous_nodes.list()
    for node in nodes:
        h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
        if h5ad_files:
            file = previous_nodes.get_file_path(node['index'], h5ad_files[0])
            break
```

---

## Previous Nodes Access

### ❌ WRONG: Missing import
```python
def run(path_dict, params):
    # NameError: name 'previous_nodes' is not defined
    # ALSO WRONG: hardcoded node index!
    input_file = previous_nodes.get_file_path(1, 'outputs/data.h5ad')
```

### ✅ CORRECT: Import first
```python
from function_block_runtime import previous_nodes

def run(path_dict, params):
    # Find h5ad files dynamically
    nodes = previous_nodes.list()
    input_file = None
    for node in nodes:
        h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
        if h5ad_files:
            input_file = previous_nodes.get_file_path(node['index'], h5ad_files[0])
            if input_file:
                break
    
    if input_file is None:
        raise FileNotFoundError("No h5ad files found in any previous node")
    adata = sc.read_h5ad(input_file)
```

### ⚠️ CRITICAL: Node Indices are 1-based, NOT 0-based!
```python
# ❌ WRONG: Node 0 does not exist!
file_path = previous_nodes.get_file_path(0, 'outputs/data.h5ad')  # ERROR!
# This will fail with: "Node 0 not found. Available nodes: [1, 2, 3, ...]"

# ✅ CORRECT: Use dynamic discovery with node['index']
nodes = previous_nodes.list()
for node in nodes:
    if 'outputs/data.h5ad' in node['files']:
        file_path = previous_nodes.get_file_path(node['index'], 'outputs/data.h5ad')
        break

# ✅ ALSO CORRECT: If you must hardcode, start from 1
file_path = previous_nodes.get_file_path(1, 'outputs/data.h5ad')  # Node 1 exists!
```

### Common Patterns
```python
# List nodes
nodes = previous_nodes.list()

# Get file - check what's actually available
nodes = previous_nodes.list()
for node in nodes:
    # Look at actual files available
    for file in node['files']:
        if file.endswith('.h5ad'):
            path = previous_nodes.get_file_path(node['index'], file)
            if path and path.exists():
                break
```

---

## File I/O Patterns

### ❌ WRONG: Hardcoded or incomplete paths
```python
adata = sc.read_h5ad('/workspace/input/data.h5ad')  # Too specific
adata.write('output.h5ad')  # Wrong directory
adata.write(path_dict['output_dir'])  # Missing filename
```

### ✅ CORRECT: Use path_dict properly
```python
# Reading - adapt to actual files
from pathlib import Path
input_dir = Path(path_dict['input_dir'])

# Find actual h5ad files (don't assume names)
h5ad_files = list(input_dir.glob('*.h5ad'))
if h5ad_files:
    adata = sc.read_h5ad(h5ad_files[0])
else:
    # Or check for CSV, parquet, etc.
    csv_files = list(input_dir.glob('*.csv'))
    if csv_files:
        data = pd.read_csv(csv_files[0])

# Writing - use descriptive names
os.makedirs(path_dict['output_dir'], exist_ok=True)
output_file = os.path.join(path_dict['output_dir'], 'processed_data.h5ad')
adata.write(output_file)

# Figures
fig_dir = os.path.join(path_dict['output_dir'], 'figures')
os.makedirs(fig_dir, exist_ok=True)
plt.savefig(os.path.join(fig_dir, 'plot.png'))
```

---

## Import and Dependency Issues

### Requirements.txt Format

#### ❌ WRONG: Multiple packages on one line
```txt
# requirements.txt
pandas>=1.0.0, numpy>=1.20.0, scanpy>=1.9.0  # WRONG!
```

#### ✅ CORRECT: One package per line
```txt
# requirements.txt
pandas>=1.0.0
numpy>=1.20.0
scanpy>=1.9.0
```

#### ❌ WRONG: Installing multiple packages at once
```python
# In bug fixer action
{"type": "install_package", "params": {"package": "squidpy>=1.0.0, scanpy>=1.9.0"}}  # WRONG!
```

#### ✅ CORRECT: Install one package at a time
```python
# Install each package separately
{"type": "install_package", "params": {"package": "squidpy>=1.0.0"}}
{"type": "install_package", "params": {"package": "scanpy>=1.9.0"}}
```

## Import and Dependency Issues

### ❌ WRONG: Missing from requirements.txt
```python
import scanpy as sc  # ModuleNotFoundError if not in requirements.txt
```

### ✅ CORRECT: List all dependencies
```text
# requirements.txt:
scanpy>=1.9.0
pandas>=1.3.0
numpy>=1.21.0
```

### Best Practice: Import inside function
```python
def run(path_dict, params):
    import scanpy as sc  # Import after requirements installed
    import pandas as pd
```

---

## Data Structure Issues

### ❌ WRONG: Assuming columns exist
```python
clusters = adata.obs['cluster']  # KeyError if missing
```

### ✅ CORRECT: Check first
```python
if 'cluster' not in adata.obs.columns:
    sc.tl.leiden(adata, key_added='cluster')
clusters = adata.obs['cluster']
```

### Common Checks
```python
# Required components
if 'X_pca' not in adata.obsm:
    sc.pp.pca(adata, n_comps=50)

if 'neighbors' not in adata.uns:
    sc.pp.neighbors(adata)

# Always do this
adata.obs_names_make_unique()

# Validate
if adata.n_obs == 0:
    raise ValueError("Input data is empty")
```

---

## Output Requirements

### ⚠️ MANDATORY: Must save output file
```python
def run(path_dict, params):
    # ... processing ...
    
    # REQUIRED - node fails without output!
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    # Use descriptive filenames based on what you're outputting
    output_file = os.path.join(path_dict['output_dir'], 'analysis_results.h5ad')
    adata.write(output_file)
```

### Additional outputs (optional)
```python
# CSV results
results_df.to_csv(os.path.join(path_dict['output_dir'], 'results.csv'))

# Metadata
metadata = {'n_clusters': len(adata.obs['cluster'].unique())}
with open(os.path.join(path_dict['output_dir'], 'metadata.json'), 'w') as f:
    json.dump(metadata, f)
```

---

## Error Handling

### ❌ WRONG: Hiding errors with try-except
```python
try:
    result = risky_operation()
except:
    pass  # Hides the real problem!

try:
    adata = sc.read_h5ad(file)
except:
    adata = sc.AnnData()  # Masks missing file issue!
```

### ✅ CORRECT: Fail fast with clear messages
```python
# Validate first
if not os.path.exists(input_file):
    raise FileNotFoundError(f"Input not found: {input_file}")

# Log and re-raise
try:
    result = api_call()
except Exception as e:
    logger.error(f"API failed: {e}")
    raise  # Preserve error visibility

# Helpful error messages
if 'column' not in adata.obs:
    raise ValueError(f"Missing 'column'. Available: {list(adata.obs.columns)}")
```

**Remember**: Fix root causes, don't mask symptoms!

---

## Common Error Messages

| Error | Cause | Solution |
|-------|-------|----------|
| "Input file not found" | Wrong filename | Check files with `os.listdir(path_dict['input_dir'])` |
| "TypeError: run() missing 1 required positional argument" | Extra parameters | Use exactly `def run(path_dict, params):` |
| "NameError: name 'previous_nodes' is not defined" | Missing import | Add `from function_block_runtime import previous_nodes` |
| "No output files found" | No output saved | Must save at least one output file to output_dir |
| "KeyError" on AnnData | Missing column | Check with `print(list(adata.obs.columns))` |

---

## Quick Reference

### Minimal Working Function Block
```python
from function_block_runtime import previous_nodes  # If using previous nodes
import os

def run(path_dict, params):
    import scanpy as sc
    
    # Read input - find actual files
    from pathlib import Path
    input_dir = Path(path_dict['input_dir'])
    h5ad_files = list(input_dir.glob('*.h5ad'))
    if h5ad_files:
        adata = sc.read_h5ad(h5ad_files[0])
    else:
        raise FileNotFoundError(f"No h5ad files found in {input_dir}")
    
    # Process
    adata.obs_names_make_unique()
    # Your analysis here
    
    # Write output (MANDATORY!)
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    # Use descriptive filename
    output_file = os.path.join(path_dict['output_dir'], 'processed_data.h5ad')
    adata.write(output_file)
```

### Key Rules
1. **Function signature:** Always `def run(path_dict, params):`
2. **Import previous_nodes:** Use `from function_block_runtime import previous_nodes`
3. **Check before access:** Use `if 'key' in adata.obs.columns:`
4. **Always save output:** At least one output file with clear naming
5. **Use path_dict:** Never hardcode `/workspace/` paths
6. **Make names unique:** Call `adata.obs_names_make_unique()`