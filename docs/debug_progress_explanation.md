# Debug Progress File Explanation

## What is debug_progress.txt?

The `debug_progress.txt` file is a simple logging mechanism that tracks debugging attempts during the execution of function blocks. It's created in the `agent_tasks` directory of each node.

## Purpose

1. **Quick Status Check**: Provides a quick way to see if debugging was attempted and what errors occurred
2. **Error History**: Shows the progression of errors across multiple debug attempts
3. **Lightweight Logging**: Captures key error messages without the full debug session details

## File Location

```
node_directory/
└── agent_tasks/
    ├── debug_progress.txt          # Simple error tracking
    └── bug_fixer/                  # Detailed debug sessions
        └── attempt_1/
            ├── turn_1_*.md
            └── turn_1_*.json
```

## Content Format

Each entry contains:
- Timestamp
- Debug attempt number
- Error message (traceback)

Example:
```
[2025-08-14T13:46:23.446202] Debug attempt 1: 2025-08-14 17:46:23,249 - function_block_wrapper - ERROR - Traceback (most recent call last):
  File "/workspace/run.py", line 96, in main
    run(path_dict, params)  # Pass both path_dict and params
  File "/workspace/function_block.py", line 31, in run
    sc.pl.hist(adata.obs['n_genes'], bins=30, title='Distribution of Gene Counts',
AttributeError: module 'scanpy.plotting' has no attribute 'hist'
```

## Why It Exists

1. **Separation of Concerns**: 
   - `debug_progress.txt`: Simple error tracking for quick inspection
   - `bug_fixer/` directory: Full debugging session with LLM interactions

2. **Performance**: 
   - Written immediately when an error occurs
   - Doesn't require the overhead of creating full debug logs

3. **Debugging Workflow**:
   - First check `debug_progress.txt` to see if debugging was attempted
   - Then examine `bug_fixer/` logs for detailed debugging steps

## Implementation Details

The file is written by the `debug_callback` function in `interactive_node_executor.py`:

```python
def debug_callback(message):
    debug_log = agent_tasks_dir / "debug_progress.txt"
    with open(debug_log, 'a') as f:
        f.write(f"[{datetime.now().isoformat()}] {message}\n")
```

This callback is invoked by the `interactive_executor` whenever a debug attempt is made:

```python
if debug_callback:
    debug_callback(f"Debug attempt {attempt}: {last_error}")
```

## Relationship to Bug Fixer Logs

- **debug_progress.txt**: Contains error messages that triggered debugging
- **bug_fixer/attempt_N/**: Contains the full debugging session
  - LLM messages
  - Actions taken
  - Action results
  - Turn-by-turn progress

## Should It Be Changed?

The current implementation could be improved:

1. **Redundancy**: The error is already captured in bug_fixer logs
2. **Location**: Could be inside bug_fixer directory for better organization
3. **Format**: Could be JSON for easier parsing

However, it serves its purpose as a quick status indicator and doesn't interfere with the main debugging process.