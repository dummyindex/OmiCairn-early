# Previous Nodes Hierarchical Directory Structure

## Overview

The previous nodes file access system has been updated to use a hierarchical directory structure that clearly separates inputs and outputs for each node. This change addresses the bug fixer's path construction issues and provides clearer organization.

## Directory Structure

### Old Structure (Flat)
```
/workspace/input/previous_nodes/
├── node1_outputs_data.h5ad
├── node1_inputs_raw.csv
├── node2_outputs_processed.h5ad
└── node2_inputs_config.json
```

### New Structure (Hierarchical)
```
/workspace/input/previous_nodes/
├── node_1/
│   ├── inputs/
│   │   └── raw.csv
│   └── outputs/
│       └── data.h5ad
└── node_2/
    ├── inputs/
    │   └── config.json
    └── outputs/
        └── processed.h5ad
```

## Changes Made

### 1. File Staging (node_executor.py and interactive_node_executor.py)
- Updated `_pre_stage_previous_nodes_files` to create hierarchical directories
- Files are now staged to `node_{idx}/outputs/` and `node_{idx}/inputs/`
- Metadata includes full path information for LLM clarity

### 2. Bug Fixer Prompts (prompt_templates.py)
- Added explicit path guidance to prevent incorrect path construction
- Includes clear examples of correct file paths
- Shows both wrong and correct path patterns

### 3. Runtime Interface (function_block_runtime.py)
- Updated `get_file` method to use new hierarchical structure
- Maintains backward compatibility with legacy flat structure
- Automatically handles both `outputs/` and `inputs/` prefixes

### 4. Interactive Executor (interactive_executor.py)
- Updated `_list_previous_nodes` to provide explicit file paths
- Each file entry includes full container path for clarity
- Helps LLMs construct correct paths without guessing

### 5. Tests Updated
- Fixed import issues in test files
- Updated test assertions to check for new structure
- All tests passing with new implementation

## Usage in Function Blocks

### Accessing Files
```python
from function_block_runtime import previous_nodes

# List available nodes
nodes = previous_nodes.list()

# Access output file from node 1
adata = previous_nodes.get_file(1, 'outputs/processed.h5ad')

# Access input file from node 2
config = previous_nodes.get_file(2, 'inputs/config.json')
```

### Bug Fixer Guidance
The bug fixer now receives explicit path information:
- Files are located at: `/workspace/input/previous_nodes/node_{idx}/outputs/` or `/workspace/input/previous_nodes/node_{idx}/inputs/`
- Example: `/workspace/input/previous_nodes/node_1/outputs/processed_data.h5ad`
- Example: `/workspace/input/previous_nodes/node_2/inputs/zebrafish.h5ad`

### Using glob in Function Blocks
```python
# Correct pattern for finding files from previous nodes
import glob

# Find all h5ad files from any previous node's outputs
h5ad_files = glob.glob('/workspace/input/previous_nodes/node_*/outputs/*.h5ad')

# Find specific file type from node 1
node1_csvs = glob.glob('/workspace/input/previous_nodes/node_1/outputs/*.csv')
```

## Benefits

1. **Clear Organization**: Inputs and outputs are clearly separated
2. **Explicit Paths**: No ambiguity about file locations
3. **Bug Fixer Clarity**: LLMs receive explicit path patterns, reducing errors
4. **Backward Compatibility**: Legacy flat structure still supported
5. **Scalability**: Easy to extend with additional metadata or file types

## Migration

The system automatically handles both old and new structures, so no migration is required. New executions will use the hierarchical structure while maintaining compatibility with existing code.