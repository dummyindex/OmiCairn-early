# Deprecation Notice

This document outlines components and features that are deprecated and will be removed in future versions of omicairn-agent-local.

## Deprecated Components

### 1. External Bug Fixing in MainAgent

**Status**: Deprecated  
**Removal Target**: v2.0.0  
**Alternative**: InteractiveExecutor with in-container debugging

The external bug fixing approach where `MainAgent._attempt_fix()` modifies code files outside of containers is deprecated. This includes:

- `MainAgent._attempt_fix()` method (when not using InteractiveExecutor)
- Direct file modification in `node_dir/function_block/`
- Creating new containers for each retry attempt

**Migration Path**:
```python
# Old approach (deprecated)
agent = MainAgent(
    enable_interactive_debug=False  # Forces external bug fixing
)

# New approach (default)
agent = MainAgent(
    enable_interactive_debug=True  # Default, uses InteractiveExecutor
)
```

### 2. Standard NodeExecutor

**Status**: Deprecated  
**Removal Target**: v2.0.0  
**Alternative**: InteractiveNodeExecutor

The basic `NodeExecutor` class that doesn't support in-container debugging will be removed.

**Affected Code**:
- `analysis_tree_management/node_executor.py` (when used without interactive mode)
- Direct usage of `ExecutorManager` without InteractiveExecutor wrapper

### 3. Non-Interactive Execution Mode

**Status**: Deprecated  
**Removal Target**: v2.0.0  

The ability to disable interactive debugging will be removed. All execution will use InteractiveExecutor.

**Affected Parameters**:
- `enable_interactive_debug` parameter will be removed (always True)
- `MainAgent` constructor will always create InteractiveNodeExecutor

## Timeline

- **Current (v1.x)**: Both modes available, InteractiveExecutor is default
- **Next Minor (v1.5)**: Deprecation warnings added when using legacy mode
- **Major Release (v2.0)**: Legacy components removed entirely

## Benefits of Migration

Moving to InteractiveExecutor exclusively provides:

1. **Better Performance**: No container restarts between attempts
2. **State Preservation**: Installed packages and runtime state persist
3. **Accurate Debugging**: Bug fixer sees actual runtime environment
4. **Faster Iteration**: Immediate re-execution after fixes
5. **Simplified Architecture**: One execution path instead of two

## Code Cleanup Plan

When removing deprecated components:

1. Remove `enable_interactive_debug` parameter from MainAgent
2. Remove conditional logic for executor selection
3. Remove external bug fixing code from MainAgent
4. Merge InteractiveNodeExecutor functionality into NodeExecutor
5. Update all tests to use interactive mode only

## For Developers

If you're currently using the deprecated features:

1. Ensure your code works with `enable_interactive_debug=True`
2. Remove any dependencies on external file modification
3. Update tests to expect in-container debugging behavior
4. Remove any workarounds for container restart issues

## Questions?

For questions about the deprecation or migration assistance, please open an issue in the repository.