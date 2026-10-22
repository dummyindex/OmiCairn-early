# System Implementation and Status

This document consolidates implementation details and current system status of the OmiCairn Local Agent.

## Table of Contents
1. [System Overview](#system-overview)
2. [Current Capabilities](#current-capabilities)
3. [Technical Architecture](#technical-architecture)
4. [Configuration](#configuration)
5. [Usage Guide](#usage-guide)
6. [Performance Metrics](#performance-metrics)
7. [Implementation Details](#implementation-details)

## System Overview

The OmiCairn Local Agent is an AI-powered system for automated single-cell analysis that:
- Generates and executes analysis code based on natural language requests
- Supports both R and Python execution environments
- Handles complex multi-step workflows with automatic parallelization
- Provides error recovery and iterative improvement

### Key Features

1. **Multi-Language Support**: Seamless R and Python integration
2. **Parallel Execution**: Automatic parallelization of independent tasks
3. **Error Recovery**: Intelligent error handling and retry mechanisms
4. **Docker Integration**: Isolated, reproducible execution environments
5. **Tree-Based Workflow**: Hierarchical analysis organization

## Current Capabilities

### Supported Analysis Types

1. **Data Processing**
   - Quality control and filtering
   - Normalization and scaling
   - Batch effect correction
   - Data integration

2. **Dimensionality Reduction**
   - PCA, UMAP, t-SNE
   - Diffusion maps
   - Custom reductions

3. **Clustering**
   - Leiden, Louvain
   - K-means, hierarchical
   - Density-based methods

4. **Trajectory Analysis**
   - Monocle3, Slingshot
   - PAGA, Palantir, DPT
   - Velocity analysis

5. **Differential Analysis**
   - Gene expression
   - Pathway enrichment
   - Cell type annotation

### Language Support

- **Python**: Full support via Docker containers
- **R**: Full support via Docker containers
- **Automatic Conversion**: Seamless R↔Python data exchange

## Technical Architecture

### Component Structure

```
omicairn_agent_local/
├── agents/                    # Agent implementations
│   ├── main_agent.py         # Primary orchestrator
│   ├── orchestrator_agent.py # Parallel execution
│   ├── function_creator_agent.py # Code generation
│   ├── base_bug_fixer.py     # Base error recovery
│   ├── claude_code_sdk_bug_fixer.py # Claude SDK bug fixer
│   └── unified_bug_fixer/    # Unified bug fixing system
├── analysis_tree_management/  # Workflow management
│   ├── tree_manager.py       # Tree structure management
│   └── node_executor.py      # Execution engine
├── job_executors/            # Language-specific executors
│   ├── python_executor.py    # Python Docker execution
│   └── r_executor.py         # R Docker execution
├── models.py                 # Data models
├── utils/                    # Utilities
└── function_blocks/          # Built-in conversions
```

### Execution Flow

1. **Request Processing**
   ```
   User Request → Main Agent → Analysis Tree Creation
   ```

2. **Code Generation**
   ```
   Function Creator Agent → Function Block → Validation
   ```

3. **Execution**
   ```
   Node Executor → Docker Container → Results Collection
   ```

4. **Error Handling**
   ```
   Error Detection → Bug Fixer Agent → Retry Logic
   ```

## Configuration

### Environment Variables

```bash
# Required
OPENAI_API_KEY=your_api_key

# Optional
DOCKER_TIMEOUT=300
MAX_PARALLEL_NODES=4
MAX_RETRIES=3
LOG_LEVEL=INFO
```

### Configuration File (`config.py`)

```python
class Config:
    # Docker settings
    DOCKER_PYTHON_IMAGE = "omicairn-python:local"
    DOCKER_R_IMAGE = "omicairn-r:minimal"
    DOCKER_TIMEOUT = 300
    
    # Execution settings
    MAX_PARALLEL_EXECUTIONS = 4
    MAX_FUNCTION_GENERATION_ATTEMPTS = 5
    
    # Tree settings
    MAX_TREE_DEPTH = 10
    MAX_NODES_PER_TREE = 50
```

## Usage Guide

### Basic Usage

```python
from agents import MainAgent

# Initialize agent
agent = MainAgent()

# Simple request
result = agent.run_analysis(
    input_data_path="data/pbmc.h5ad",
    user_request="Perform clustering analysis on my single-cell data"
)
```

### Advanced Usage

```python
# Complex workflow
result = agent.run_analysis(
    user_request="""
    1. Quality control and filtering
    2. Normalize and find variable genes
    3. Run PCA and UMAP
    4. Perform Leiden clustering
    5. Find marker genes for each cluster
    6. Create visualization plots
    """,
    input_data_path="data/raw_counts.h5ad",
    output_dir="results/full_analysis"
)
```

### Parallel Execution

The system automatically identifies independent tasks:

```python
# These will run in parallel
result = agent.run_analysis(
    user_request="""
    Run three different clustering methods:
    1. Leiden clustering with resolution 0.5
    2. Louvain clustering 
    3. K-means with k=10
    """,
    input_data_path="data/processed.h5ad"
)
```

## Performance Metrics

> Rough, unbenchmarked indications from early development; these are not reported results.

### Execution Times

| Operation | Small (1K cells) | Medium (10K cells) | Large (100K cells) |
|-----------|-----------------|-------------------|-------------------|
| QC & Filter | 2-5s | 10-30s | 1-3 min |
| Normalize | 1-3s | 5-15s | 30s-2 min |
| PCA | 2-5s | 15-45s | 2-5 min |
| UMAP | 5-15s | 1-3 min | 10-30 min |
| Clustering | 3-10s | 30s-2 min | 5-15 min |

### Resource Usage

- **Memory**: 2-16 GB depending on dataset size
- **CPU**: 2-8 cores utilized for parallel operations
- **Disk**: 100 MB - 10 GB for outputs and intermediates

## Implementation Details

### Parallel Execution System

The orchestrator identifies parallelizable nodes:

```python
def identify_parallel_groups(self, ready_nodes):
    groups = []
    for node in ready_nodes:
        # Check if node can be added to existing group
        can_add = True
        for group in groups:
            if self._has_dependency_conflict(node, group):
                can_add = False
                break
        
        if can_add:
            # Add to first compatible group
            added = False
            for group in groups:
                if self._can_execute_together(node, group):
                    group.append(node)
                    added = True
                    break
            
            if not added:
                groups.append([node])
    
    return groups
```

### Error Recovery System

The bug fixer maintains context and history:

```python
class BugFixerAgent:
    def fix_error(self, function_block, error_info, attempt_history):
        # Build context from history
        context = self._build_error_context(attempt_history)
        
        # Generate fix with cumulative learning
        fixed_code = self._generate_fix(
            original_code=function_block.code,
            error=error_info,
            context=context,
            previous_attempts=attempt_history
        )
        
        return fixed_code
```

### Data Flow Management

Each node maintains clear data flow:

```python
class NodeExecutor:
    def execute_node(self, node, input_path):
        # Setup execution directory
        exec_dir = self._setup_execution_dir(node)
        
        # Copy inputs (from parent or initial)
        if node.parent:
            input_data = node.parent.output_path
        else:
            input_data = input_path
            
        # Execute in container
        result = self._run_container(
            function_block=node.function_block,
            input_data=input_data,
            output_dir=exec_dir
        )
        
        # Update node state
        node.execution_state = ExecutionState.COMPLETED
        node.output_path = exec_dir / "outputs"
        
        return result
```

### Docker Integration

Robust container management:

```python
class DockerManager:
    def run_container(self, image, command, volumes, timeout):
        container = self.client.containers.run(
            image=image,
            command=command,
            volumes=volumes,
            detach=True,
            mem_limit="8g",
            cpu_count=4,
            network_mode="bridge"
        )
        
        # Monitor execution
        start_time = time.time()
        while container.status == "running":
            if time.time() - start_time > timeout:
                container.kill()
                raise TimeoutError()
            time.sleep(1)
            
        # Collect results
        logs = container.logs(stdout=True, stderr=True)
        container.remove()
        
        return logs
```

## Future Enhancements

1. **GPU Support**: CUDA-enabled containers for deep learning
2. **Cloud Integration**: Remote execution capabilities
3. **Web Interface**: Browser-based interaction
4. **Plugin System**: Custom analysis method integration
5. **Result Caching**: Intelligent result reuse
6. **Workflow Templates**: Pre-built analysis pipelines