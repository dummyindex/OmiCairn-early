# OmiCairn Agent Framework Implementation

## Overview

This document consolidates all framework implementations including the function block framework, task management system, and enhanced execution capabilities.

## Function Block Framework

### Standard Interface

All function blocks must implement the standard signature:

```python
def run(path_dict, params):
    """
    Standard function block interface.
    
    Args:
        path_dict: Dict with 'input_dir' and 'output_dir' paths
        params: Dict of analysis parameters
    
    Returns:
        Processed data object
    """
```

**IMPORTANT**: All imports must be included inside the function. Do not assume any imports are available globally. Always import required modules (os, scanpy, numpy, etc.) at the beginning of the run() function.

### File Conventions

| Language | Input File | Output File | Figure Directory |
|----------|-----------|-------------|------------------|
| Python | `_node_anndata.h5ad` | `_node_anndata.h5ad` | `figures/` |
| R | `_node_seuratObject.rds` | `_node_seuratObject.rds` | `figures/` |

### Example Implementation

```python
import scanpy as sc
import os

def run(path_dict, params):
    # Load input data
    input_path = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    adata = sc.read_h5ad(input_path)
    
    # Process data
    if params.get("normalize", True):
        sc.pp.normalize_total(adata)
    
    # Save output data
    output_path = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    adata.write(output_path)
    
    # Save figures
    figures_dir = os.path.join(path_dict["output_dir"], "figures")
    os.makedirs(figures_dir, exist_ok=True)
    
    return adata
```

## Task Management System

### Core Components

1. **AgentTask Class** (`agents/task_manager.py`)
   - Represents individual agent tasks
   - Tracks context, status, and history
   - Manages LLM interactions
   - Stores task artifacts

2. **TaskManager Class**
   - Manages task folder hierarchy
   - Provides task querying capabilities
   - Generates task summaries
   - Tracks entity relationships

### Task Structure

```
agent_tasks/
├── main_agent/
│   └── task_TIMESTAMP_ID/
│       ├── task_info.json
│       ├── context.json
│       ├── llm_interactions/
│       │   └── interaction_TIMESTAMP.json
│       └── artifacts/
├── orchestrator_agent/
│   └── task_TIMESTAMP_ID/
│       └── ...
├── function_creator/
│   └── task_TIMESTAMP_ID/
│       ├── generated_code.py
│       └── ...
└── bug_fixer/
    └── task_TIMESTAMP_ID/
        ├── error_info.json
        ├── fixed_code.py
        └── ...
```

### Task Lifecycle

1. **Creation**: Agent creates task with context
2. **Processing**: Task status updated during execution
3. **LLM Logging**: All LLM interactions recorded
4. **Artifacts**: Generated files stored
5. **Completion**: Final status and summary

### Integration Example

```python
class BugFixerAgent(BaseAgent):
    def fix_error(self, context):
        # Create task
        task = self.create_task(
            task_type="bug_fix",
            context=context,
            entity_refs={
                "node_id": context["node_id"],
                "function_block_id": context["function_block"]["id"]
            }
        )
        
        # Process and log
        if use_llm:
            self.log_llm_interaction(
                task=task,
                interaction_type="debug",
                prompt=debug_prompt,
                response=llm_response
            )
        
        # Save artifacts
        task.save_artifact("fixed_code.py", fixed_code)
        
        # Update status
        self.update_task_status(task, "completed")
```

## Enhanced Execution Framework

### Extended Data Models

1. **FileType Enum**: Supports multiple file types
   - anndata, csv, json, image, rds, etc.

2. **FileInfo**: Detailed file metadata
   - path, type, size, description

3. **ExecutionContext**: Comprehensive execution information
   - node info, parent outputs, parameters
   - execution metadata

4. **Input/Output Specifications**: Define expected I/O
   - file patterns, types, requirements

### Enhanced Executor Features

1. **General File Support**: Not limited to anndata
2. **Automatic File Collection**: Categorizes outputs
3. **Execution Context JSON**: Provides metadata to blocks
4. **Figure Management**: Automatic figure collection

### Execution Flow

```
1. Prepare execution directory
2. Copy input files based on specifications
3. Create execution_context.json
4. Execute function block
5. Collect outputs by type
6. Update node results
```

### Output Structure

```
execution/<node_id>/
├── input/                    # Input files
│   ├── _node_anndata.h5ad
│   └── metadata.json
├── output/                   # Function outputs
│   ├── _node_anndata.h5ad
│   ├── figures/
│   │   ├── plot1.png
│   │   └── plot2.png
│   └── results.csv
└── execution_context.json    # Execution metadata
```

## Framework Benefits

1. **Standardization**: Consistent interface across all blocks
2. **Flexibility**: Supports multiple file types and languages
3. **Traceability**: Complete task and execution history
4. **Debugging**: Comprehensive logging and artifacts
5. **Scalability**: Parallel execution support
6. **Extensibility**: Easy to add new capabilities

## Best Practices

### Function Block Development
- Always use standard signature
- Handle missing inputs gracefully
- Create output directories as needed
- Include comprehensive error handling
- Document parameters clearly

### Task Management
- Create tasks for significant operations
- Log all LLM interactions
- Save important artifacts
- Update task status promptly
- Include entity references

### Execution Management
- Define clear I/O specifications
- Use appropriate file types
- Collect all relevant outputs
- Maintain execution context
- Clean up temporary files

## Future Enhancements

1. **Streaming Support**: For large files
2. **Caching**: Reuse previous executions
3. **Versioning**: Track function block versions
4. **Validation**: Pre/post execution checks
5. **Monitoring**: Real-time execution tracking