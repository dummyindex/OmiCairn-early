# Function Block Validation

## Overview

The OmiCairn Agent framework includes automatic validation for function blocks to ensure data integrity and catch errors early. This validation occurs at two stages:

1. **Pre-flight validation**: Before execution, validates that required inputs are present
2. **Post-execution validation**: After execution, validates that expected outputs were created

## How It Works

### 1. Validation Configuration

Function blocks can define validation specifications in their `static_config`:

```json
{
  "static_config": {
    "args": [...],
    "description": "...",
    "tag": "...",
    "input_specification": {
      "required_files": ["_node_anndata.h5ad"],
      "anndata_requirements": {
        "min_cells": 100,
        "min_genes": 200,
        "required_obs": ["cell_type", "batch"],
        "required_var": ["gene_ids"],
        "required_uns": ["log1p"],
        "required_obsm": ["X_pca"],
        "required_layers": ["counts"]
      }
    },
    "output_specification": {
      "required_files": ["_node_anndata.h5ad"],
      "anndata_requirements": {
        "required_obs": ["dpt_pseudotime"],
        "required_obsm": ["X_diffmap"],
        "required_uns": ["iroot", "diffmap_evals"]
      }
    }
  }
}
```

### 2. Validation Process

The `FunctionBlockValidator` class performs validation:

```python
from utils.function_block_validator import FunctionBlockValidator

# Create validator with function block's static config
validator = FunctionBlockValidator(function_block.static_config.dict())

# Pre-flight validation
input_valid, input_errors = validator.validate_input(input_dir)
if not input_valid:
    # Execution stops with clear error message
    raise ValidationError(f"Input validation failed: {'; '.join(input_errors)}")

# ... execute function block ...

# Post-execution validation
output_valid, output_errors = validator.validate_output(output_dir)
if not output_valid:
    # Treat as execution failure
    raise ValidationError(f"Output validation failed: {'; '.join(output_errors)}")
```

### 3. Error Messages

Validation provides clear, actionable error messages:

```
Input validation failed: Required obs column missing: 'cell_type'
```

```
Output validation failed: Required output file missing: _node_anndata.h5ad
```

## Validation Checks

### File Validation
- Checks that required files exist
- Validates file paths and accessibility

### AnnData Validation
For `_node_anndata.h5ad` files, validates:

1. **Dimensions**:
   - `min_cells`: Minimum number of cells (observations)
   - `min_genes`: Minimum number of genes (variables)

2. **Data Structure**:
   - `required_obs`: Columns that must exist in `adata.obs`
   - `required_var`: Columns that must exist in `adata.var`
   - `required_uns`: Keys that must exist in `adata.uns` (unstructured data)
   - `required_obsm`: Keys that must exist in `adata.obsm` (multi-dimensional observations)
   - `required_layers`: Keys that must exist in `adata.layers`

## Benefits

1. **Early Error Detection**: Catches missing inputs before wasting compute time
2. **Clear Error Messages**: Tells you exactly what's missing
3. **Data Integrity**: Ensures outputs meet expectations
4. **Better Debugging**: Validation errors are easier to fix than runtime errors
5. **Pipeline Reliability**: Prevents cascading failures from missing data

## Best Practices

### For Function Block Creators

1. **Define Clear Specifications**: Be specific about what your function block needs and produces
2. **Use Minimal Requirements**: Only require what's actually necessary
3. **Document Changes**: If your block adds new columns/embeddings, specify them in output_specification
4. **Test Validation**: Ensure your specifications match your implementation

Example for a pseudotime analysis block:

```python
def run(path_dict, params):
    # This block needs:
    # - Input: adata with X_pca
    # - Output: adata with dpt_pseudotime column
    
    import scanpy as sc
    import os
    
    # Load input (validated to have X_pca)
    adata = sc.read_h5ad(os.path.join(path_dict['input_dir'], '_node_anndata.h5ad'))
    
    # Compute pseudotime (writes adata.obs['dpt_pseudotime'])
    sc.tl.dpt(adata)
    
    # Save output (will be validated to have dpt_pseudotime)
    adata.write(os.path.join(path_dict['output_dir'], '_node_anndata.h5ad'))
```

### For Bug Fixers

When you see validation errors:

1. **Input Validation Failed**: 
   - Check if previous node created the expected output
   - Verify file paths are correct
   - Ensure required data structures exist

2. **Output Validation Failed**:
   - Make sure the function saves its output file
   - Check that all required columns/embeddings are added
   - Verify output directory creation

## Integration with Other Components

### Interactive Executor
The validation is integrated into the `InteractiveExecutor`:
- Runs pre-flight validation before starting container
- Runs post-execution validation after successful execution
- Treats validation failures as execution failures for retry logic

### Bug Fixer
The bug fixer is aware of validation errors:
- Receives clear error messages about what's missing
- Can distinguish between validation failures and runtime errors
- Has prompts explaining how to fix common validation issues

### Function Creator
The function creator agent:
- Can generate validation specifications based on task requirements
- Understands the validation framework when creating new blocks
- Includes specifications in generated function blocks

## Future Enhancements

1. **Schema Validation**: Validate data types and value ranges
2. **Custom Validators**: Allow function blocks to define custom validation logic
3. **Validation Reports**: Generate detailed reports of what was validated
4. **Performance Metrics**: Track validation overhead and optimize as needed