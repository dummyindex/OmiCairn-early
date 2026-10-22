# Correct Previous Nodes Usage Pattern

## MANDATORY CODE PATTERN

This is the correct pattern for accessing files from previous nodes:

```python
def run(path_dict, params):
    import os
    import scanpy as sc
    
    # 1. CHECK FOR PREVIOUS NODES
    prev_nodes_dir = os.path.join(path_dict['input_dir'], 'previous_nodes')
    if os.path.exists(prev_nodes_dir):
        # Import the runtime module
        from function_block_runtime import previous_nodes
        
        # List available nodes
        nodes = previous_nodes.list()
        print(f"Available previous nodes: {len(nodes)}")
        
        # Find h5ad files from any node
        adata = None
        for node in nodes:
            # Get list of files from this node
            node_files = node['files']
            print(f"Node {node['index']}: {node['name']} has files: {node_files}")
            
            # Find h5ad files
            h5ad_files = [f for f in node_files if f.endswith('.h5ad')]
            if h5ad_files:
                # Load the first h5ad file
                h5ad_file = h5ad_files[0]
                print(f"Loading {h5ad_file} from node {node['index']}")
                
                # CRITICAL: get_file_path returns a Path object - you must read it!
                file_path = previous_nodes.get_file_path(node['index'], h5ad_file)
                if file_path:
                    adata = sc.read_h5ad(file_path)
                    break
        
        if adata is None:
            raise FileNotFoundError("No .h5ad files found in any previous node")
            
    else:
        # Root node - files directly in input_dir
        input_files = os.listdir(path_dict['input_dir'])
        print(f'Available files: {input_files}')
        
        # Find h5ad files by extension
        h5ad_files = [f for f in input_files if f.endswith('.h5ad')]
        if h5ad_files:
            # For root nodes, we need to use sc.read_h5ad
            input_file = os.path.join(path_dict['input_dir'], h5ad_files[0])
            adata = sc.read_h5ad(input_file)
        else:
            raise FileNotFoundError("No .h5ad files found")
    
    # 2. PROCESS DATA
    # Your analysis here...
    
    # 3. SAVE OUTPUT
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    
    # Use descriptive name or convention
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
    
    return adata
```

## Common Mistakes to Avoid

### 1. Using the wrong method name
```python
# ❌ WRONG - get_file doesn't exist!
adata = previous_nodes.get_file(1, 'data.h5ad')

# ✅ CORRECT - use get_file_path and read the file
file_path = previous_nodes.get_file_path(1, 'data.h5ad')
if file_path:
    adata = sc.read_h5ad(file_path)
```

### 2. Using 0-based indexing
```python
# ❌ WRONG - node indices are 1-based, not 0-based!
file_path = previous_nodes.get_file_path(0, 'outputs/data.h5ad')

# ✅ CORRECT - use 1-based indexing
file_path = previous_nodes.get_file_path(1, 'outputs/data.h5ad')
```

### 3. Assuming specific filenames
```python
# ❌ WRONG - don't assume specific names
file_path = previous_nodes.get_file_path(1, 'outputs/preprocessed.h5ad')

# ✅ CORRECT - check what files actually exist
nodes = previous_nodes.list()
h5ad_files = [f for f in nodes[0]['files'] if f.endswith('.h5ad')]
if h5ad_files:
    file_path = previous_nodes.get_file_path(1, h5ad_files[0])
    if file_path:
        adata = sc.read_h5ad(file_path)
```

## File Path Access

The `get_file_path` method always returns a Path object:

```python
# Get path to any file type
path = previous_nodes.get_file_path(1, 'outputs/data.csv')
if path:
    # Read the file yourself based on type
    import pandas as pd
    df = pd.read_csv(path)
```

## Complete Example with Multiple File Types

```python
def run(path_dict, params):
    from function_block_runtime import previous_nodes
    import pandas as pd
    import json
    
    # List nodes (returns list with 1-based indices)
    nodes = previous_nodes.list()
    
    # Get different file types
    for node in nodes:
        # CSV files
        csv_files = [f for f in node['files'] if f.endswith('.csv')]
        if csv_files:
            csv_path = previous_nodes.get_file_path(node['index'], csv_files[0])
            if csv_path:
                df = pd.read_csv(csv_path)
            
        # JSON files
        json_files = [f for f in node['files'] if f.endswith('.json')]
        if json_files:
            json_path = previous_nodes.get_file_path(node['index'], json_files[0])
            if json_path:
                with open(json_path) as f:
                    data = json.load(f)
            
        # Text files
        if 'special.txt' in node['files']:
            txt_path = previous_nodes.get_file_path(node['index'], 'special.txt')
            if txt_path:
                with open(txt_path) as f:
                    content = f.read()
```