# Function Block Versioning Architecture

## Overview

This document explains the versioning architecture for function blocks in the omicairn-agent-local system.

## Key Principle: Single Responsibility

### Function Creator: Version 1 Only

The function creator agent is responsible for:
- Creating the initial function block implementation
- Always saving as **version 1**
- Never modifying existing function blocks

### Bug Fixer: Versions 2+

The bug fixer agent is responsible for:
- Fixing errors in existing function blocks
- Creating versions 2, 3, 4, etc.
- Maintaining a history of all fixes attempted

## Directory Structure

```
node_<node_id>/
├── function_block/           # Current working version
│   ├── code.py
│   ├── config.json
│   └── requirements.txt
└── agent_tasks/
    ├── function_creator/     # Initial creation only
    │   ├── code_versions/
    │   │   └── v1_00_TIMESTAMP.py  # Always version 1
    │   └── creation_TIMESTAMP.json
    └── bug_fixer/           # All subsequent versions
        ├── code_versions/
        │   ├── v02_original_TIMESTAMP.py
        │   ├── v03_fixed_TIMESTAMP.py
        │   ├── v04_original_TIMESTAMP.py
        │   └── v05_fixed_TIMESTAMP.py
        └── attempt_*/
```

## Implementation Details

### Function Creator Logging

In `agents/main_agent.py`, the `_log_function_creation_to_node` method:
```python
# Function creator ALWAYS creates version 1, subsequent versions are from bug fixer
code_file = code_dir / f"v1_{block_index:02d}_{timestamp.strftime('%Y%m%d_%H%M%S')}.py"
```

### Metadata Clarification

The logging now distinguishes between:
- `orchestrator_iteration`: The planning iteration when the node was created
- `function_block_version`: Always 1 for function creator

Example log entry:
```json
{
  "task_type": "function_creation",
  "orchestrator_iteration": 3,    // Planning iteration
  "function_block_version": 1,    // Always 1 for creator
  "function_block": {...}
}
```

## Why This Architecture?

1. **Clear Separation of Concerns**: Function creator creates, bug fixer fixes
2. **Audit Trail**: Easy to see the original implementation vs. all fixes
3. **No Confusion**: Version numbers clearly indicate who created what
4. **Debugging**: Can always trace back to the original implementation

## Common Misconceptions

- ❌ Function creator creates multiple versions based on orchestrator iteration
- ✅ Function creator always creates version 1, regardless of when it runs

- ❌ Version numbers indicate orchestrator planning iterations
- ✅ Version numbers indicate function block evolution (1=created, 2+=fixed)

## Testing

See `tests/test_function_creator_versioning.py` for verification that:
- Function creator always creates v1 files
- Metadata correctly distinguishes orchestrator iteration from version