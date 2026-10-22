# Package Validation and Common Error Patterns

## Overview

This document provides guidance on common package installation errors and validation patterns for the omicairn-agent-local system. It serves as a reference to prevent common mistakes during function block creation and improve debugging efficiency.

## Common Package Installation Errors

### 1. Non-existent Packages

**Error Pattern**: `ERROR: No matching distribution found for [package]`

**Common Examples**:
- `dtflow` - Does not exist on PyPI (from enhanced pseudotime benchmark)
- `scvelo-extras` - Incorrect package name
- `scanpy-tools` - Not a real package

**Solution**: 
- Verify package exists on PyPI before adding to requirements
- Use correct package names (e.g., `scvelo` instead of `scvelo-extras`)
- Check official documentation for correct installation instructions

### 2. Built-in Python Modules

**Error Pattern**: Attempting to install standard library modules

**Common Mistakes**:
- `json` - Built-in Python module, should NOT be in requirements.txt
- `os` - Built-in module
- `sys` - Built-in module
- `glob` - Built-in module
- `pathlib` - Built-in module (Python 3.4+)

**Solution**: Never include standard library modules in requirements.txt

### 3. Package Name Variations

**Correct Package Names for Common Tools**:

| Incorrect | Correct | Notes |
|-----------|---------|-------|
| `sklearn` | `scikit-learn` | Common confusion |
| `cv2` | `opencv-python` | Import name differs from package |
| `igraph` | `python-igraph` | Python binding name |
| `PIL` | `Pillow` | Modern fork of PIL |
| `umap` | `umap-learn` | Correct package for UMAP |

### 4. Version Conflicts

**Common Issues**:
- Specifying incompatible version ranges
- Missing version specifications for critical packages
- Using deprecated package versions

**Best Practices**:
```txt
# Good: Specify compatible versions
scanpy>=1.9.0,<2.0.0
pandas>=1.3.0
numpy>=1.21.0

# Bad: Too restrictive
scanpy==1.9.3
pandas==1.3.5
numpy==1.21.2
```

## Package Validation Checklist

### Before Adding to requirements.txt:

1. **Verify Package Exists**:
   ```bash
   pip search [package-name]  # Note: pip search is disabled, use PyPI website
   # Or check: https://pypi.org/project/[package-name]/
   ```

2. **Check Import Name**:
   - Package name may differ from import name
   - Example: `scikit-learn` (package) vs `sklearn` (import)

3. **Verify Not Built-in**:
   ```python
   import sys
   print([package] in sys.modules)  # Should be False for external packages
   ```

4. **Check Dependencies**:
   - Some packages have system dependencies
   - Example: `python-igraph` requires C libraries

## Common Domain-Specific Packages

### Single-Cell Analysis
- `scanpy` - Core single-cell analysis
- `scvelo` - RNA velocity analysis
- `cellrank` - Cell fate mapping
- `palantir` - Trajectory inference
- `paga` - Part of scanpy, not separate package

### Trajectory Analysis
- `slingshot` - R package, needs rpy2 for Python
- `monocle3` - R package
- `destiny` - R package for diffusion maps

### Cell Type Annotation
- `celltypist` - Automated cell type annotation
- `scanorama` - Batch correction and integration
- `harmony-pytorch` - Batch correction

## Error Pattern Templates

### Pattern 1: Module Not Found After Installation
**Symptom**: Package installs but import fails
**Common Causes**:
- Wrong package name (e.g., installed `umap` instead of `umap-learn`)
- Missing dependencies
- Python environment issues

### Pattern 2: Version Incompatibility
**Symptom**: Runtime errors after successful installation
**Common Causes**:
- API changes between versions
- Deprecated functions
- Incompatible dependency versions

### Pattern 3: Missing System Dependencies
**Symptom**: Installation fails with compilation errors
**Common Packages Affected**:
- `python-igraph` - Needs C libraries
- `rpy2` - Needs R installation
- `pycairo` - Needs cairo libraries

## Validation Functions

### Example Package Validator (Pseudocode)
```python
BUILTIN_MODULES = {
    'json', 'os', 'sys', 'glob', 'pathlib', 'collections',
    'itertools', 'functools', 'datetime', 'math', 'random'
}

PACKAGE_ALIASES = {
    'sklearn': 'scikit-learn',
    'cv2': 'opencv-python',
    'igraph': 'python-igraph',
    'PIL': 'Pillow',
    'umap': 'umap-learn'
}

def validate_package(package_name):
    # Check if built-in
    if package_name in BUILTIN_MODULES:
        return False, f"{package_name} is a built-in module"
    
    # Check for common aliases
    if package_name in PACKAGE_ALIASES:
        correct_name = PACKAGE_ALIASES[package_name]
        return False, f"Use '{correct_name}' instead of '{package_name}'"
    
    # Additional validation logic here
    return True, "Valid package"
```

## Integration with Function Creator

The function creator should:
1. Validate all packages before adding to requirements.txt
2. Warn about potential issues
3. Suggest correct package names
4. Skip built-in modules automatically

## Debugging Tips

1. **Check Error Logs First**: Look for "No matching distribution" errors
2. **Verify Package Names**: Cross-reference with PyPI
3. **Test Imports**: Try importing in a clean environment
4. **Check Documentation**: Official docs often have correct package names
5. **Use Virtual Environments**: Isolate package testing

## Future Improvements

1. **Automated Package Validation**: Pre-check packages against PyPI API
2. **Package Name Database**: Maintain curated list of correct names
3. **Version Compatibility Matrix**: Track known working combinations
4. **Smart Suggestions**: LLM-powered package name corrections