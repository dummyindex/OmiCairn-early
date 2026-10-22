# Data Loading Root Node Architecture

## Overview

The data loading root node is a fundamental architectural improvement that ensures analysis trees can always be expanded, even when computation nodes fail. This document describes the design, implementation, and benefits of this approach.

## Problem Statement

Previously, the system had a critical limitation:
- When the first (root) computation node failed, the entire analysis tree would fail
- The orchestrator agent couldn't attach new nodes to a failed root
- Users would need to restart the entire analysis with different parameters
- No opportunity for the system to self-correct or try alternative approaches

## Solution: Data Loading Root Node

### Design Principles

1. **Always Successful**: The root node performs a simple file copy operation that rarely fails
2. **Pass-Through Functionality**: Preserves all input files exactly as they are
3. **No Transformations**: Does not rename files or modify content (but see note below)
4. **Minimal Dependencies**: Uses only Python standard library (os, shutil)

**Important Note**: While the data loading root node itself preserves filenames, the Python executor renames single input files to `_node_anndata.h5ad` before passing them to any function block (including the data loading root). This happens in `python_executor.py` lines 52-53. For directories with multiple files, original names are preserved.

### Implementation Details

#### Tree Creation (`tree_manager.py`)

```python
def create_tree(self, ...):
    # ... create tree object ...
    
    # Always add a data loading root node that just passes through the input data
    data_loading_block = self._create_data_loading_block()
    root_node = self.add_root_node(data_loading_block)
    logger.info(f"Added data loading root node: {root_node.id}")
```

#### Data Loading Function Block

The `_create_data_loading_block()` method creates a simple function block that:
1. Lists all files in the input directory
2. Copies each file to the output directory unchanged
3. Preserves original filenames (no renaming to `_node_anndata.h5ad`)
4. Logs the operation for transparency

```python
def run(path_dict, params):
    import os
    import shutil
    
    input_dir = path_dict['input_dir']
    output_dir = path_dict['output_dir']
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Find and copy all input files
    for filename in os.listdir(input_dir):
        if os.path.isfile(os.path.join(input_dir, filename)):
            shutil.copy2(
                os.path.join(input_dir, filename),
                os.path.join(output_dir, filename)
            )
    
    return {"status": "success"}
```

### Main Agent Integration

The `MainAgent` now handles the data loading root specially:

1. **Pre-Orchestrator Execution**: Executes the data loading root before planning
2. **Tree Statistics**: Logs tree state for debugging
3. **Pending Node Detection**: Identifies and executes pending nodes before orchestration

```python
# Execute any pending nodes (like data loading root)
pending_nodes = [n for n in tree.nodes.values() if n.state == NodeState.PENDING]
if pending_nodes:
    logger.info(f"Executing {len(pending_nodes)} pending nodes before orchestrator planning")
    for node in pending_nodes:
        state, output = interactive_executor.execute_node(...)
```

## Benefits

### 1. **Resilient Tree Structure**
- Trees can always be expanded, even after failures
- Orchestrator has a stable foundation to build upon
- Multiple recovery paths possible

### 2. **Better User Experience**
- No need to restart analysis after initial failures
- System can try alternative approaches automatically
- More robust to edge cases and unexpected data

### 3. **Simplified Debugging**
- Clear separation between data loading and computation
- Easier to identify where failures occur
- Bug fixer can focus on actual computation issues

### 4. **Flexible Data Handling**
- Supports single or multiple input files
- Preserves all file metadata
- No assumptions about file naming conventions

## File Organization

### Input Structure
```
input_dir/
├── data.h5ad           # Main data file
├── metadata.csv        # Optional metadata
├── config.json         # Optional configuration
└── ...                 # Any other files
```

### Output Structure

#### Single File Input
When a single file is provided as input (e.g., `zebrafish.h5ad`):
```
output_dir/
└── _node_anndata.h5ad  # Renamed by Python executor
```

#### Multiple Files Input
When a directory with multiple files is provided:
```
output_dir/
├── data.h5ad           # Original name preserved
├── metadata.csv        # Original name preserved
├── config.json         # Original name preserved
└── ...                 # All names preserved
```

## Child Node Considerations

Child nodes of the data loading root must handle two scenarios:

### For Single File Inputs
- The file will be named `_node_anndata.h5ad` (renamed by Python executor)
- This is the standard convention for single h5ad files

### For Multiple File Inputs  
- Original filenames are preserved
- Must look for specific files by their original names
- Handle missing files gracefully

### Example Child Node

```python
def run(path_dict, params):
    import os
    import glob
    import scanpy as sc
    
    # Look for the specific data file
    input_dir = path_dict['input_dir']
    
    # Try common patterns
    for pattern in ['*.h5ad', '*.h5', '*.csv']:
        files = glob.glob(os.path.join(input_dir, pattern))
        if files:
            input_file = files[0]  # Use first matching file
            break
    
    # Load and process data
    adata = sc.read_h5ad(input_file)
    # ... processing ...
```

## Testing

### Test Categories

1. **Non-LLM Tests** (No API calls required):
   - `test_data_root_passthrough.py` - Verifies pass-through functionality
   - `test_tree_structure.py` - Tests tree creation with root node
   - `test_manual_tree.py` - Manual tree construction tests

2. **LLM-Required Tests** (Need OpenAI API):
   - `test_data_loading_root.py` - Full integration test
   - `test_data_root_to_children.py` - Tests data flow to children
   - `test_data_loading_root_comprehensive.py` - Edge cases

### Running Tests

```bash
# Run all data root tests
python -m pytest tests/data_root_node/ -v

# Run non-LLM tests only
python -m pytest tests/data_root_node/test_data_root_passthrough.py -v

# Run with specific markers
python -m pytest -m "not llm_required" tests/data_root_node/
```

## Migration Notes

### For Existing Code
- No changes needed for existing function blocks
- Child nodes should already handle various input scenarios
- Tree structure remains compatible

### For New Development
- Always expect data loading root as first node
- Don't assume `_node_anndata.h5ad` naming
- Handle multiple input files when relevant

## Future Enhancements

1. **Selective File Passing**: Allow filtering which files to pass through
2. **Metadata Extraction**: Create a manifest of available files
3. **Validation**: Basic file integrity checks
4. **Compression Support**: Handle compressed input archives

## Conclusion

The data loading root node architecture provides a robust foundation for analysis trees, ensuring they can always be expanded and recovered from failures. This simple but effective design significantly improves the system's resilience and user experience.