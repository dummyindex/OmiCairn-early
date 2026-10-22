# Previous Nodes File Access System

## Overview

The previous nodes file access feature allows function blocks to access both output and input files from ancestor nodes in the analysis tree. This enables data sharing and result aggregation across the analysis pipeline without breaking the isolation between nodes.

## Architecture

### Components

1. **NodeFileAccessor** (`utils/node_file_access.py`)
   - Core utility for identifying accessible ancestor nodes
   - Creates LLM-friendly 1-based indexing (node 1, node 2, etc.)
   - Handles tree traversal to find accessible nodes

2. **File Pre-staging** (`analysis_tree_management/node_executor.py` and `interactive_node_executor.py`)
   - Pre-stages files before container execution starts
   - Copies both outputs and inputs from previous nodes
   - Uses modular file staging interface for future extensibility

3. **Runtime Interface** (`utils/function_block_runtime.py`)
   - Python module automatically available in containers
   - Provides `previous_nodes` object for file access
   - Handles file path resolution and auto-parsing

4. **File Staging Interface** (`utils/file_staging_interface.py`)
   - Modular abstraction for file staging methods
   - Current implementation: CopyFileStaging (file copying)
   - Future implementation: HTTPFileStaging (HTTP server access)

### File Naming Convention

Files are staged with descriptive prefixes to indicate their source:
- Outputs: `node{index}_outputs_{filename}` (e.g., `node1_outputs_processed.h5ad`)
- Inputs: `node{index}_inputs_{filename}` (e.g., `node2_inputs_data.csv`)

## Usage in Function Blocks

```python
def run(path_dict, params):
    from function_block_runtime import previous_nodes
    
    # List available previous nodes
    nodes = previous_nodes.list()
    for node in nodes:
        print(f"Node {node['index']}: {node['name']}")
        print(f"  Files: {node['files']}")
    
    # Access output file from a previous node
    df = previous_nodes.get_file(1, 'outputs/results.csv')
    
    # Access input file from a previous node
    adata = previous_nodes.get_file(2, 'inputs/raw_data.h5ad')
    
    # Access without auto-parsing (returns Path object)
    file_path = previous_nodes.get_file(1, 'outputs/data.h5ad', auto_parse=False)
    
    # Check if a file exists
    if previous_nodes.has_file(1, 'outputs/metadata.json'):
        metadata = previous_nodes.get_file(1, 'outputs/metadata.json')
```

## API Reference

### `previous_nodes.list()`
Returns a list of accessible previous nodes with their metadata:
```python
[
    {
        'index': 1,
        'node_id': 'node-abc123',
        'name': 'Preprocessing',
        'level': 1,
        'files': ['outputs/processed.h5ad', 'outputs/metrics.csv', 'inputs/raw.h5ad']
    }
]
```

### `previous_nodes.get_file(node_index, relative_path, auto_parse=True)`
Retrieves a file from a previous node:
- `node_index`: 1-based index of the node
- `relative_path`: Path relative to node directory (e.g., 'outputs/file.csv' or 'inputs/data.h5ad')
- `auto_parse`: If True, automatically parses CSV/JSON/H5AD files

Returns:
- Parsed data (DataFrame, dict, AnnData) if auto_parse=True
- Path object if auto_parse=False
- None if file doesn't exist

### `previous_nodes.has_file(node_index, relative_path)`
Checks if a file exists in a previous node.

## Implementation Details

### Pre-staging Process

1. When a node is about to execute, the system:
   - Identifies all accessible ancestor nodes
   - Creates a `previous_nodes` directory in the container's input folder
   - Copies all output files from ancestor nodes' `outputs/` directories
   - Copies all input files from ancestor nodes' latest job `input/` directories
   - Creates an index map (`previous_nodes_index.json`) for runtime lookup

2. Files are excluded from input staging:
   - `function_block_runtime.py` (runtime interface itself)
   - `previous_nodes_index.json` (index map)
   - Files in `previous_nodes/` directory (to avoid recursion)

### Accessibility Rules

- Only ancestor nodes (parents, grandparents, etc.) in the same branch are accessible
- Sibling nodes or nodes in different branches cannot be accessed
- Node indices are assigned based on tree traversal order

### File Path Resolution

The runtime interface handles multiple file naming conventions:
1. New convention with prefixes: `node1_outputs_file.csv`
2. Legacy convention: `node1_file.csv`
3. Automatic prefix detection based on path ('outputs/' or 'inputs/')

## Agent Integration

The following agents have been updated to mention the previous nodes feature:

1. **Orchestrator Agent** - Mentions in planning prompt that function blocks can use previous_nodes interface
2. **Bug Fixer Agent** - Includes documentation about previous_nodes in debugging prompts
3. **Function Creator Agent** - Already included in function block documentation

## Future Extensibility

The file staging system is designed to be modular. The current implementation copies all files, but future implementations could:

1. **HTTP File Server**: 
   - Host files on an HTTP server accessible from containers
   - Containers request files on-demand instead of pre-copying
   - Reduces disk usage and startup time for large files

2. **Lazy Loading**:
   - Only stage files when explicitly requested
   - Use file references instead of actual copies

3. **Compression**:
   - Compress large files during staging
   - Decompress on access in container

To change the staging method, modify `DEFAULT_STAGING_METHOD` in `utils/file_staging_interface.py`.

## Testing

Run the integration tests to verify the feature:
```bash
# Full integration test
python tests/test_previous_nodes_integration_fixed.py

# Simple demonstration
python tests/test_previous_nodes_demo.py
```

## Example: Multi-Stage Analysis Pipeline

```python
# Node 1: Data Loading and QC
def run(path_dict, params):
    import scanpy as sc
    import pandas as pd
    
    # Load raw data
    adata = sc.read_h5ad(os.path.join(path_dict['input_dir'], 'raw.h5ad'))
    
    # Calculate QC metrics
    sc.pp.calculate_qc_metrics(adata, inplace=True)
    
    # Save processed data
    adata.write(os.path.join(path_dict['output_dir'], 'qc_passed.h5ad'))
    
    # Save QC summary
    qc_summary = pd.DataFrame({
        'metric': ['total_cells', 'mean_genes', 'mean_counts'],
        'value': [adata.n_obs, adata.obs['n_genes'].mean(), adata.obs['total_counts'].mean()]
    })
    qc_summary.to_csv(os.path.join(path_dict['output_dir'], 'qc_summary.csv'))

# Node 2: Normalization
def run(path_dict, params):
    import scanpy as sc
    from function_block_runtime import previous_nodes
    
    # Load QC-passed data
    adata = sc.read_h5ad(os.path.join(path_dict['input_dir'], 'qc_passed.h5ad'))
    
    # Access QC metrics from node 1
    qc_summary = previous_nodes.get_file(1, 'outputs/qc_summary.csv')
    original_cells = qc_summary.loc[qc_summary['metric'] == 'total_cells', 'value'].iloc[0]
    print(f"Started with {original_cells} cells before QC")
    
    # Normalize
    sc.pp.normalize_total(adata)
    sc.pp.log1p(adata)
    
    # Save
    adata.write(os.path.join(path_dict['output_dir'], 'normalized.h5ad'))

# Node 3: Clustering
def run(path_dict, params):
    import scanpy as sc
    from function_block_runtime import previous_nodes
    
    # Load normalized data
    adata = sc.read_h5ad(os.path.join(path_dict['input_dir'], 'normalized.h5ad'))
    
    # Access QC summary from node 1 (grandparent)
    qc_summary = previous_nodes.get_file(1, 'outputs/qc_summary.csv')
    
    # Access raw input from node 1 to compare
    if previous_nodes.has_file(1, 'inputs/raw.h5ad'):
        print("Can access original raw data if needed")
    
    # Perform clustering
    sc.pp.pca(adata)
    sc.pp.neighbors(adata)
    sc.tl.leiden(adata)
    
    # Save results
    adata.write(os.path.join(path_dict['output_dir'], 'clustered.h5ad'))
```

## Limitations and Considerations

1. **File Size**: All files are currently copied, which may be slow for large datasets
2. **Memory Usage**: Pre-staging doubles disk usage temporarily
3. **Performance**: Future HTTP-based implementation will improve performance
4. **Security**: Files are only accessible within the same analysis tree

## Migration Guide

If you have existing function blocks that need to access previous results:

1. Add import: `from function_block_runtime import previous_nodes`
2. Replace complex file path construction with `previous_nodes.get_file()`
3. Use node indices instead of node IDs for simpler reference
4. Test thoroughly as file access patterns may change