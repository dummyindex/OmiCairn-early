# Previous Nodes Interface Documentation

## Overview

The `previous_nodes` interface allows function blocks to access outputs from ancestor nodes in the analysis tree. This enables sophisticated workflows where later nodes can access results from any previous step, not just their immediate parent.

## Key Concepts

1. **Pre-staged Files**: Files from previous nodes are automatically staged in the container at `/workspace/input/previous_nodes/`
2. **Hierarchical Structure**: Files are organized as `node_{idx}/outputs/` and `node_{idx}/inputs/`
3. **File Path Access**: The interface returns file paths - you must read files yourself
4. **1-based Indexing**: Nodes are indexed starting from 1, NOT 0

## Import and Basic Usage

```python
from function_block_runtime import previous_nodes

# List all available nodes
nodes = previous_nodes.list()
for node in nodes:
    print(f"Node {node['index']}: {node['name']}")
    print(f"  Files: {node['files']}")
```

## API Reference

### `previous_nodes.list()`

Returns a list of available previous nodes with metadata.

**Returns:**
```python
[
    {
        'index': 1,                    # 1-based node index
        'name': 'load_data',          # Node name
        'level': 0,                   # Tree level (0 = root)
        'description': '...',         # Node description
        'files': ['outputs/zebrafish.h5ad'],  # List of file paths
        'is_parent': True             # Whether this is a direct parent
    },
    ...
]
```

### `previous_nodes.get_file_path(node_index, relative_path)`

Get the path to a file from a previous node. You must read the file yourself.

**Parameters:**
- `node_index` (int): 1-based index of the node (NOT 0-based!)
- `relative_path` (str): Path relative to node directory (e.g., 'outputs/data.h5ad')

**Returns:**
- Path object if file exists, None if not found

**Examples:**
```python
# Get path to h5ad file from node 1
file_path = previous_nodes.get_file_path(1, 'outputs/processed.h5ad')
if file_path:
    adata = sc.read_h5ad(file_path)

# Get path to CSV file from node 2
csv_path = previous_nodes.get_file_path(2, 'outputs/metrics.csv')
if csv_path:
    df = pd.read_csv(csv_path)
```

### `previous_nodes.get_all_files(node_index)`

Get all available files from a node as a dictionary.

**Parameters:**
- `node_index` (int): 1-based index of the node

**Returns:**
- Dictionary mapping filenames to Path objects

## File Discovery Pattern

Since filenames can vary, use flexible discovery:

```python
# Find all h5ad files from a node
nodes = previous_nodes.list()
for node in nodes:
    h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
    if h5ad_files:
        # Load the first h5ad file found
        path = previous_nodes.get_file_path(node['index'], h5ad_files[0])
        if path:
            adata = sc.read_h5ad(path)
        break
```

## Common Pitfalls

### 1. Using 0-based indexing

❌ **Wrong:**
```python
# Node indices start at 1, not 0!
path = previous_nodes.get_file_path(0, 'outputs/data.h5ad')
```

✅ **Right:**
```python
# Use 1-based indexing
path = previous_nodes.get_file_path(1, 'outputs/data.h5ad')
```

### 2. Assuming Fixed Filenames

❌ **Wrong:**
```python
# Assumes specific filename
path = previous_nodes.get_file_path(1, 'outputs/preprocessed.h5ad')
```

✅ **Right:**
```python
# Discover actual files
nodes = previous_nodes.list()
h5ad_files = [f for f in nodes[0]['files'] if f.endswith('.h5ad')]
if h5ad_files:
    path = previous_nodes.get_file_path(1, h5ad_files[0])
    if path:
        adata = sc.read_h5ad(path)
```

### 3. Not Reading the File

❌ **Wrong:**
```python
# get_file_path returns a Path object, not the data!
adata = previous_nodes.get_file_path(1, 'data.h5ad')
# adata is a Path object, not AnnData!
```

✅ **Right:**
```python
# Get path and read the file
path = previous_nodes.get_file_path(1, 'data.h5ad')
if path:
    adata = sc.read_h5ad(path)
```

### 4. Hardcoding Output Names

❌ **Wrong:**
```python
# Forces specific output name
output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
```

✅ **Right:**
```python
# Use descriptive names based on your analysis
output_file = os.path.join(path_dict['output_dir'], 'pseudotime_results.h5ad')
# or keep convention if appropriate
output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
```

## File Staging Details

Files are staged in the container with this structure:
```
/workspace/input/previous_nodes/
├── node_1/
│   ├── outputs/
│   │   ├── zebrafish.h5ad
│   │   └── metadata.json
│   └── inputs/
│       └── raw_data.csv
├── node_2/
│   ├── outputs/
│   │   └── _node_anndata.h5ad
│   └── inputs/
│       └── zebrafish.h5ad
└── previous_nodes_index.json
```

## Best Practices

1. **Always check what files exist** before assuming filenames
2. **Use file extension matching** rather than exact name matching
3. **Handle missing files gracefully** with informative error messages
4. **Remember that `get_file_path()` returns Path objects**, not data
5. **Use 1-based indexing** for nodes (node 1, not node 0)
6. **Output filenames are flexible** - use descriptive names

## Complete Example

```python
def run(path_dict, params):
    import os
    import scanpy as sc
    from function_block_runtime import previous_nodes
    
    # Check if we have previous nodes
    prev_nodes_dir = os.path.join(path_dict['input_dir'], 'previous_nodes')
    if os.path.exists(prev_nodes_dir):
        # Use previous nodes interface
        nodes = previous_nodes.list()
        print(f"Found {len(nodes)} previous nodes")
        
        # Find h5ad files from any previous node
        adata = None
        for node in nodes:
            h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
            if h5ad_files:
                print(f"Loading {h5ad_files[0]} from node {node['index']}")
                path = previous_nodes.get_file_path(node['index'], h5ad_files[0])
                if path:
                    adata = sc.read_h5ad(path)
                    break
        
        if adata is None:
            raise ValueError("No h5ad files found in previous nodes")
    else:
        # Root node - load directly from input_dir
        input_files = os.listdir(path_dict['input_dir'])
        h5ad_files = [f for f in input_files if f.endswith('.h5ad')]
        if h5ad_files:
            adata = sc.read_h5ad(os.path.join(path_dict['input_dir'], h5ad_files[0]))
        else:
            raise ValueError("No h5ad files found in input directory")
    
    # Process data...
    
    # Save with descriptive name
    output_file = os.path.join(path_dict['output_dir'], 'analysis_results.h5ad')
    adata.write(output_file)
    
    return adata
```