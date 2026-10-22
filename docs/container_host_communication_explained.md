# Container-Host Communication in Bug Fixing

## Overview

The job executor in the container **does NOT directly communicate** with the host bug fixer. Instead, there's a clever architecture using `docker exec` commands.

## The Architecture

```
┌─────────────────────────────────┐      ┌─────────────────────────────────┐
│           HOST SYSTEM           │      │         DOCKER CONTAINER        │
├─────────────────────────────────┤      ├─────────────────────────────────┤
│                                 │      │                                 │
│  InteractiveExecutor            │      │  Function Block Code            │
│       ↓                         │      │       ↓                         │
│  Creates Container              │      │  Executes and fails             │
│       ↓                         │      │       ↓                         │
│  Detects Error                  │      │  Error: FileNotFoundError       │
│       ↓                         │      │                                 │
│  InContainerDebugSession        │      │                                 │
│       ↓                         │      │                                 │
│  ContainerActionHandler --------docker exec--→ Executes commands        │
│       ↓                         │      │       ↑                         │
│  Bug Fixer (LLM)                │      │       │                         │
│  Decides actions                │      │  Results returned               │
│       ↓                         │      │       │                         │
│  execute_action() --------------docker exec--→ Run action              │
│                                 │      │                                 │
└─────────────────────────────────┘      └─────────────────────────────────┘
```

## Key Components

### 1. **InteractiveExecutor** (Host)
Manages the container lifecycle and debugging:

```python
class InteractiveExecutor:
    def execute_with_debugging(self, function_block, ...):
        # 1. Start container
        container = self._start_interactive_container(...)
        
        # 2. Execute function block
        exit_code, stdout, stderr = self._execute_in_container(container, command)
        
        # 3. If it fails, start debugging
        if exit_code != 0:
            result = self._run_in_container_debug(container, ...)
```

### 2. **InContainerDebugSession** (Host)
Creates the bridge between bug fixer and container:

```python
class InContainerDebugSession:
    def fix_bug(self, ...):
        # Create handler that can execute commands in container
        action_handler = ContainerActionHandler(self.container, "/workspace")
        
        # Create debug session with this handler
        session = EnhancedDebugSession(
            action_executor=action_handler,  # This is the key!
            llm_service=self.bug_fixer.llm_service
        )
        
        # Run debugging
        result = session.debug(...)
```

### 3. **ContainerActionHandler** (Host, executes IN Container)
This is the key component that executes actions inside the container:

```python
class ContainerActionHandler:
    def execute_action(self, action):
        action_type = action.get('type')
        
        if action_type == 'read_file':
            # Execute IN CONTAINER via docker exec
            return self._read_file(path)
        
        elif action_type == 'execute_command':
            # Execute IN CONTAINER via docker exec
            return self._execute_command(command)
    
    def _execute_command(self, command):
        # This is the magic - docker exec!
        exec_result = self.container.exec_run(
            cmd=["bash", "-c", f"cd {self.working_dir} && {command}"],
            stdout=True,
            stderr=True
        )
        return parse_result(exec_result)
```

## How Communication Works

### Step 1: Function Block Fails
```python
# In container
def run(path_dict, params):
    # This fails
    prev_data = read_file("/workspace/input/previous_nodes/data.h5ad")
    # FileNotFoundError!
```

### Step 2: Host Detects Error
```python
# InteractiveExecutor on host
exit_code, stdout, stderr = self._execute_in_container(container, command)
if exit_code != 0:
    # Start debugging
```

### Step 3: Bug Fixer Analyzes
```python
# Bug fixer (LLM) on host decides what to do
action = {
    "type": "list_directory",
    "params": {"path": "/workspace/input"}
}
```

### Step 4: Execute Action in Container
```python
# ContainerActionHandler on host
def _list_directory(self, path):
    # Execute IN the container
    exec_result = self.container.exec_run(
        cmd=["bash", "-c", f"ls -la {path}"],
        stdout=True
    )
    # Parse and return results
```

### Step 5: Results Flow Back
The results flow back through the chain:
1. Container execution → docker exec result
2. ContainerActionHandler → parsed result
3. Bug fixer → analyzes result
4. Decides next action → repeat

## No Direct Communication

**Important**: The container CANNOT:
- Make HTTP requests to the host
- Access host filesystem directly
- Send messages to the host bug fixer

Instead:
- All actions are initiated FROM the host
- Executed IN the container via `docker exec`
- Results returned TO the host

## Security Benefits

This architecture maintains container isolation:
- Container remains sandboxed
- No network access needed
- No shared filesystem (except mounted volumes)
- All actions are logged and controlled

## The Missing Piece for Previous Nodes

For previous node file access, the `ContainerActionHandler` needs to be extended:

```python
# This should be added to ContainerActionHandler
elif action_type == 'retrieve_previous_node_file':
    # This would need to:
    # 1. Find file on HOST (outside container)
    # 2. Copy it to mounted volume
    # 3. Return success/failure
    return self._retrieve_previous_node_file(action)
```

But currently, this connection is not implemented!