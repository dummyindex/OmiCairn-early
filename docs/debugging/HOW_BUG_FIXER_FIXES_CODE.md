# How Bug Fixer Fixes Code

This document explains how the bug fixer component automatically detects and resolves errors in function blocks by operating INSIDE the Docker container.

## Overview

The bug fixer is an AI-powered debugging system that:
1. Runs within the same Docker container as the failing job (via InteractiveExecutor)
2. Analyzes error messages and stack traces in the actual runtime environment
3. Modifies `/workspace/function_block.py` directly in the container
4. Re-executes the function block immediately after fixes

**Note**: The system uses InteractiveExecutor by default. The legacy external bug fixing approach (where code is fixed outside containers) is deprecated and will be removed in future versions.

## Process Flow

### 1. Error Detection
When a function block fails execution inside the Docker container:
- Python wrapper catches the exception
- Error type, message, and stack trace are captured
- Container remains running (doesn't exit)
- Bug fixer is invoked within the same Python process

### 2. In-Container Bug Fixing (Default with InteractiveExecutor)
The bug fixer executes through the InteractiveExecutor system:

```python
# InteractiveExecutor maintains a running container
container = client.containers.run(
    image=docker_image,
    command=["tail", "-f", "/dev/null"],  # Keep alive
    detach=True,
    volumes={execution_dir: {"bind": "/workspace", "mode": "rw"}}
)

# On execution failure, bug fixer runs via exec commands
if exit_code != 0:
    debug_session = InContainerDebugSession(
        container=container,
        working_dir="/workspace",
        bug_fixer=unified_bug_fixer
    )
    
    # Bug fixer actions are translated to container commands
    # e.g., write_file action becomes:
    container.exec_run(["bash", "-c", f"cat > /workspace/function_block.py"], 
                      stdin=True, input=fixed_code.encode())
    
    # Re-execute in the same container
    container.exec_run(["python", "/workspace/run.py"])
```

This approach:
- Keeps the container running between attempts
- Preserves installed packages and state
- Allows real-time code modification
- Enables immediate re-execution

### 3. Multi-Turn Debugging Session

The bug fixer operates in turns (default: 5 turns) within the container:

#### Turn 1: Exploration
- Lists `/workspace` contents
- Checks installed packages with `pip list`
- Identifies main code file (`function_block.py`)

#### Turn 2: Code Analysis
- Reads `/workspace/function_block.py`
- Analyzes the error with full stack trace
- Has access to all imported modules

#### Turn 3-4: Fix Implementation
- Writes corrected code to `/workspace/function_block.py`
- Can run `pip install` for missing packages
- Can test imports immediately: `python -c "import module"`
- Creates missing directories if needed

#### Turn 5: Validation
- Tests the fix in the actual environment
- Can execute small code snippets to verify
- All changes persist in the container

### 4. Web Agent Integration

For complex errors, the bug fixer can invoke a web agent that:
- Searches documentation, Stack Overflow, and GitHub
- Finds relevant solutions and code examples
- Provides research findings to guide the fix

Web agent is triggered for:
- AttributeError (API usage issues)
- ModuleNotFoundError/ImportError
- KeyError (especially for scanpy operations)

## Container Environment

The bug fixer has full access to the container environment:
- **Working directory**: `/workspace`
- **Main code file**: 
  - Python: `/workspace/function_block.py`
  - R: `/workspace/function_block.R`
- **Requirements**: `/workspace/requirements.txt`
  - Python: Used directly by pip
  - R: Used to generate `install_packages.R`
- **Input data**: `/workspace/input/`
- **Output directory**: `/workspace/output/`

Key advantages of in-container execution:
1. Can see all installed packages
2. Can test imports immediately
3. Changes persist between attempts
4. Same Python environment as execution

## Common Fix Patterns

### 1. Missing Imports
```python
# Before
adata = sc.read_h5ad(input_file)

# After  
import scanpy as sc
adata = sc.read_h5ad(input_file)
```

### 2. API Usage Errors
```python
# Before (incorrect API)
result = module.wrong_function()

# After (correct API)
result = module.submodule.correct_function()
```

### 3. Missing Preprocessing Steps
```python
# Before
sc.tl.dpt(adata)  # Fails: missing diffmap

# After
sc.tl.diffmap(adata)  # Add required preprocessing
sc.tl.dpt(adata)
```

### 4. Missing Root Cell (DPT)
The root cell choice changes the scientific result, so the bug fixer is instructed not to pick one arbitrarily.
It should use a root given by the user (params) or a documented marker-based rule, and otherwise fail with a clear
error. If a heuristic root is used, it must be recorded in the node outputs.

> Limitation: automatic fixes can alter analysis choices; review fixed function blocks before relying on results.

## Success Criteria

A bug fix is considered successful when:
1. The code modification addresses the root cause
2. The fix compiles without syntax errors
3. No new errors are introduced
4. The function can proceed with execution

## Available Actions

The bug fixer can execute these actions inside the container:

### File Operations
- **read_file**: Read any file in `/workspace`
- **write_file**: Modify files (typically function_block.py/R)
- **list_directory**: Explore directory structure
- **check_file_exists**: Verify file presence
- **head_file/tail_file**: Read portions of large files
- **grep_file**: Search for patterns in files

### Code Execution
- **execute_command**: Run shell commands (Python/R/bash)
- **install_package**: Install Python packages via pip (Python only)

### Special Actions
- **update_function_block**: Replace entire function block code
  ```json
  {
    "type": "update_function_block",
    "code": "def run(path_dict, params):\n    # Complete fixed code...",
    "confidence": 0.8
  }
  ```
  - Used in final debugging turn
  - Includes confidence score (0-1)
  - Validates syntax automatically
  - Required for compliance in enhanced debug mode

## Integration with Container Execution

### Default Mode: InteractiveExecutor
With `enable_interactive_debug=True` (default):

1. **Container Start**: InteractiveExecutor starts container with `tail -f /dev/null`
2. **Initial Execution**: Runs `python run.py` via `exec_run`
3. **On Error**: InContainerDebugSession invokes bug fixer
4. **Fix Applied**: ContainerActionHandler executes fixes via `exec_run`
5. **Retry**: Re-executes in same container
6. **Container Persists**: Until all debug attempts exhausted

### Legacy Mode (Deprecated)
The external bug fixing approach where MainAgent modifies files outside containers will be removed. This mode:
- Creates new containers for each attempt
- Loses installed packages between attempts
- Has no access to runtime state
- Is slower and less reliable

## Configuration

Key parameters:
- `max_turns`: Maximum debugging turns (default: 5)
- `enable_web_agent`: Use web research (default: True)
- `max_debug_trials`: Retries per node (default: 3)
- `WEB_AGENT_TIMEOUT`: Environment variable for web agent timeout (default: 90s)
  - Typical research duration: 40-60 seconds
  - Prevents indefinite runs
  - Saves partial results on timeout

## Limitations

- Cannot fix fundamental logic errors without context
- Limited by container environment constraints
- Web agent may timeout on complex searches
- Some errors require human intervention

## Recent Improvements

1. **InteractiveExecutor as Default**: In-container debugging is now the default mode
2. **Container Persistence**: Containers stay running between debug attempts
3. **Real-time Fixes**: Code modifications happen inside the actual runtime environment
4. **Web Agent Integration**: Research results guide in-container fixes
5. **Better State Preservation**: Installed packages and runtime state persist

## Future Direction

The project is moving towards exclusive use of InteractiveExecutor for all bug fixing:
- External bug fixing will be removed
- All debugging will happen inside containers
- Better integration with container runtime
- Faster and more reliable fixes