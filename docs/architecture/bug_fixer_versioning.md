# Bug Fixer Versioning and Code Management

## Overview

This document explains how the bug fixer manages code versions and ensures it always works with the latest code during debugging sessions.

## Key Components

### 1. CodeVersionManager

Located in `agents/unified_bug_fixer/code_versioning.py`, this class handles:
- Saving sequential versions of code (v01, v02, v03, etc.)
- Updating both `code.py` and `function_block.py` in sync
- Preserving version history with meaningful suffixes
- Tracking the latest version metadata

### 2. Version Numbering

The bug fixer creates versions starting from v02 (since function creator creates v01):

```
v01_original_20250818_140000.py      # First save of original buggy code
v02_original_fb_20250818_140000.py   # Original function_block.py (if different)
v03_fixed_20250818_140005.py         # First fix attempt
v04_original_20250818_140100.py      # Before second fix
v05_original_fb_20250818_140100.py   # function_block.py before second fix
v06_fixed_20250818_140105.py         # Second fix attempt
```

### 3. update_function_block Action

The `update_function_block` action:
1. Saves the current code as "original" version
2. Saves the new code as "fixed" version
3. Updates both `code.py` and `function_block.py`
4. Updates `requirements.txt`
5. Creates/updates `latest_version.json` metadata
6. Automatically re-executes the code to verify the fix

## Workflow

### During Bug Fixing

1. **Initial Error**: Bug fixer reads the current `function_block.py`
2. **First Fix Attempt**:
   - Saves current code as v01_original, v02_original_fb
   - Applies fix and saves as v03_fixed
   - Updates working files
   - Re-executes to test
3. **Subsequent Attempts**:
   - Always reads the latest `function_block.py` (not old versions)
   - Continues versioning sequentially
   - Each fix builds on the previous attempt

### Code Synchronization

The system maintains two identical copies:
- `code.py`: The main execution file
- `function_block.py`: Legacy compatibility

Both are always updated together to prevent inconsistencies.

### Re-execution with Latest Code

After each `update_function_block`:
1. The container's `/workspace/function_block.py` is updated
2. The host's `node_dir/function_block/` files are updated
3. Re-execution uses the newly updated code
4. Results show whether the fix resolved the issue

## Version History Tracking

The `latest_version.json` file tracks:
```json
{
  "timestamp": "2025-08-18T14:01:05",
  "version_file": "v06_fixed_20250818_140105.py",
  "language": "python",
  "requirements_updated": true,
  "files_updated": ["code.py", "function_block.py"]
}
```

## Testing

See the following test files:
- `tests/test_bug_fixer_versioning.py`: Tests version numbering and file updates
- `tests/test_bug_fixer_re_execution.py`: Tests re-execution with latest code

## Best Practices

1. **Always Use Latest**: Bug fixer always reads current `function_block.py`, not historical versions
2. **Sequential Numbering**: Versions increment sequentially, never skip numbers
3. **Meaningful Suffixes**: Use "original", "fixed", "syntax_error" etc. for clarity
4. **Sync Files**: Always update both code.py and function_block.py together
5. **Test After Fix**: Re-execution verifies each fix attempt

## Common Issues

### Version Numbers Don't Match Attempts
- Multiple files saved per attempt (original, original_fb, fixed)
- Version numbers increment for each file saved

### Code Not Updated
- Check both container and host directories
- Verify `CodeVersionManager` initialized with correct node_dir
- Ensure write permissions on directories

### Re-execution Uses Old Code
- Verify update_function_block completed successfully
- Check container's /workspace/ has latest code
- Ensure no caching issues in execution