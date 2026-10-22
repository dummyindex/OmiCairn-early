# Bug Fixer to Container Communication

## Overview

The bug fixer runs on the **HOST** and communicates with the **CONTAINER** to provide files from previous nodes. Here's how it works:

## The Architecture

```
┌─────────────────────────────────┐      ┌─────────────────────────────────┐
│           HOST SYSTEM           │      │         DOCKER CONTAINER        │
├─────────────────────────────────┤      ├─────────────────────────────────┤
│                                 │      │                                 │
│  Bug Fixer (UnifiedBugFixer)    │      │  Function Block Code            │
│       ↓                         │      │       ↓                         │
│  ActionExecutor                 │      │  Requests file:                 │
│       ↓                         │      │  "need node1/qc_metrics.csv"    │
│  retrieve_previous_node_file()  │      │                                 │
│       ↓                         │      │                                 │
│  1. Finds file on host          │      │                                 │
│  2. Copies to staging area      │      │                                 │
│       ↓                         │      │       ↑                         │
│  ContainerActionHandler --------docker exec---→                          │
│  3. Copies file into container  │      │  File appears at:               │
│                                 │      │  /workspace/input/              │
│                                 │      │  node1_qc_metrics.csv           │
└─────────────────────────────────┘      └─────────────────────────────────┘
```

## The Communication Flow

### 1. Bug Fixer Detects Error
When the function block fails because it can't find a file from a previous node:
```python
FileNotFoundError: /workspace/input/previous_nodes/node1_qc_metrics.csv not found
```

### 2. Bug Fixer Takes Action
The bug fixer on the host decides to retrieve the file:
```json
{
    "type": "retrieve_previous_node_file",
    "params": {
        "node_index": 1,
        "filename": "qc_metrics.csv"
    }
}
```

### 3. ActionExecutor Processes Request
The `ActionExecutor._handle_retrieve_previous_node_file()` method:
1. Uses `retrieve_func` (a callback to `NodeFileAccessor`) to find the file on the host
2. The file is located at: `tree_dir/nodes/node_001/outputs/qc_metrics.csv`

### 4. File Transfer to Container
The file is transferred in two steps:
1. **Host-side staging**: Copy to a temporary location
2. **Container injection**: Use `docker cp` or mount to get file into container

### 5. ContainerActionHandler
This runs via `docker exec` inside the container to:
1. Create `/workspace/input/previous_nodes/` if needed
2. Copy the staged file to this location
3. Return success/failure to bug fixer

## Key Components

### ContainerActionHandler (runs IN container)
```python
class ContainerActionHandler:
    def execute_action(self, action):
        # This runs INSIDE the container via docker exec
        if action['type'] == 'write_file':
            # Can write files inside container
            with open(action['path'], 'w') as f:
                f.write(action['content'])
```

### ActionExecutor (runs on HOST)
```python
class ActionExecutor:
    def _handle_retrieve_previous_node_file(self, action):
        # This runs on the HOST
        # 1. Find file on host filesystem
        file_path = self.find_previous_node_file(node_index, filename)
        
        # 2. Stage it for container access
        staging_path = self.stage_file_for_container(file_path)
        
        # 3. Tell container handler to copy it
        # (This happens via docker exec)
```

## The Missing Link

Currently, the `node_context` with `retrieve_func` is **never set** in the ActionExecutor! This needs to be fixed:

```python
# In InteractiveExecutor._run_in_container_debug():
# Need to set up node context before creating debug session

from utils.node_file_access import NodeFileAccessor

# Create file accessor
accessor = NodeFileAccessor(tree, tree_dir)
index_map = accessor.get_node_index_map(current_node_id)

# Create retrieve functions
def retrieve_func(node_index, filename):
    return accessor.retrieve_node_file(
        node_index, filename, index_map, 
        staging_dir  # Where to stage files
    )

def retrieve_batch_func(file_requests):
    return accessor.retrieve_multiple_files(
        file_requests, index_map,
        staging_dir
    )

# Set node context on action executor
action_executor.node_context = {
    'index_map': index_map,
    'retrieve_func': retrieve_func,
    'retrieve_batch_func': retrieve_batch_func,
    'node_list': accessor.get_readable_node_list(current_node_id)
}
```

## Important Notes

1. **No Direct Communication**: The container CANNOT directly access host files
2. **Bug Fixer Mediates**: All file access goes through the bug fixer's action system
3. **Docker Exec Bridge**: Commands are executed in container via `docker exec`
4. **Staged Files**: Files must be copied/mounted into container's filesystem
5. **One-Way Flow**: Container requests → Host retrieves → Host injects into container

## Security Considerations

- Container remains isolated - no host filesystem access
- All file access is mediated and logged
- Only requested files are made available
- No arbitrary host command execution from container