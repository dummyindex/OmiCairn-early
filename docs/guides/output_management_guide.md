# Output Management Guide

## Overview

When working with biological data analysis, especially single-cell RNA-seq data, it's common to encounter datasets with thousands of genes and cells. Printing all gene names or cell indices can overwhelm the bug fixer with massive outputs. This guide provides best practices for managing output in function blocks and debugging sessions.

## Best Practices for Printing Gene/Cell Information

### Good Practice - Limit Output with Slicing

```python
# Good: Print first 100 genes with total count
print(f"First 100 genes: {adata.var_names[:100].tolist()}")
print(f"Total genes: {len(adata.var_names)}")

# Good: Print first 100 cells
print(f"First 100 cells: {adata.obs_names[:100].tolist()}")
print(f"Total cells: {len(adata.obs_names)}")

# Good: Show summary of columns
obs_cols = list(adata.obs.columns)
print(f"Total obs columns: {len(obs_cols)}")
print(f"First 10 columns: {obs_cols[:10]}")
if len(obs_cols) > 10:
    print(f"  ... and {len(obs_cols) - 10} more columns")

# Good: Sampling approach for large data
if len(adata.var_names) > 100:
    print(f"Sample of genes (every 100th): {adata.var_names[::len(adata.var_names)//100][:10].tolist()}")
```

### Bad Practice - Printing Everything

```python
# Bad: Prints thousands of gene names
print(f"All genes: {adata.var_names.tolist()}")

# Bad: Prints all cell indices
print(f"All cells: {adata.obs_names.tolist()}")

# Bad: Dumps entire column lists
print(f"All columns: {list(adata.obs.columns)}")
print(f"All var columns: {list(adata.var.columns)}")
```

## Exploring Data Structure Efficiently

When debugging data-related errors, use these patterns:

### 1. Quick Data Overview

```python
# Execute this to get a comprehensive but concise overview
python -c "
import scanpy as sc
import glob

files = glob.glob('/workspace/input/*.h5ad')
if files:
    adata = sc.read_h5ad(files[0])
    print(f'=== DATA OVERVIEW ===')
    print(f'Shape: {adata.shape}')
    print(f'Memory usage: {adata.X.nbytes / 1e6:.1f} MB')
    
    # Show limited column samples
    print(f'\\nObs columns ({len(adata.obs.columns)}): {list(adata.obs.columns)[:10]}')
    if len(adata.obs.columns) > 10:
        print(f'  ... and {len(adata.obs.columns) - 10} more')
    
    # Show gene statistics, not all names
    print(f'\\nGenes: {len(adata.var_names)} total')
    print(f'First 10: {list(adata.var_names[:10])}')
    print(f'Last 10: {list(adata.var_names[-10:])}')
    
    # Check for common gene patterns
    mito_genes = sum(1 for g in adata.var_names if g.startswith(('MT-', 'mt-')))
    ribo_genes = sum(1 for g in adata.var_names if g.startswith(('RPS', 'RPL')))
    print(f'\\nMitochondrial genes: {mito_genes}')
    print(f'Ribosomal genes: {ribo_genes}')
"
```

### 2. Finding Specific Patterns

```python
# Instead of printing all genes, search for specific patterns
python -c "
import scanpy as sc
adata = sc.read_h5ad('/workspace/input/data.h5ad')

# Find genes matching a pattern
pattern = 'CD'  # Looking for CD markers
matching = [g for g in adata.var_names if pattern in g]
print(f'Genes containing "{pattern}": {len(matching)} found')
print(f'First 20 matches: {matching[:20]}')
"
```

### 3. Column Analysis Without Overload

```python
# Analyze columns by type/pattern instead of printing all
python -c "
import scanpy as sc
adata = sc.read_h5ad('/workspace/input/data.h5ad')

# Group columns by pattern
obs_cols = list(adata.obs.columns)
numeric_cols = [c for c in obs_cols if adata.obs[c].dtype.kind in 'iufc']
string_cols = [c for c in obs_cols if adata.obs[c].dtype == 'object']
bool_cols = [c for c in obs_cols if adata.obs[c].dtype == 'bool']

print(f'Column types:')
print(f'  Numeric: {len(numeric_cols)} columns')
print(f'  String: {len(string_cols)} columns')
print(f'  Boolean: {len(bool_cols)} columns')

# Show examples of each type
print(f'\\nNumeric columns (first 5): {numeric_cols[:5]}')
print(f'String columns (first 5): {string_cols[:5]}')
"
```

## Configuration for Output Limits

The ActionExecutor now supports configurable output limits:

- **max_output_chars**: Default 10,000 characters per stdout/stderr
- **max_output_lines**: Default 1,000 lines per stdout/stderr

When output exceeds these limits, it's automatically truncated with a message indicating the original size.

## Tips for Function Block Authors

1. **Always use head/tail operations** when displaying data samples
2. **Print counts instead of full lists** for large collections
3. **Use statistical summaries** instead of raw data dumps
4. **Implement progress indicators** for long-running operations instead of printing each item
5. **Log to files** for detailed debugging, print summaries to stdout

## Common Patterns to Avoid

```python
# Avoid these patterns that can produce massive outputs:

# 1. Printing all unique values
print(adata.obs['cell_type'].unique())  # Could be thousands

# Better:
unique_types = adata.obs['cell_type'].unique()
print(f"Found {len(unique_types)} unique cell types")
print(f"First 10: {unique_types[:10]}")

# 2. Iterating and printing each item
for gene in adata.var_names:
    print(f"Processing {gene}")  # Don't do this!

# Better:
print(f"Processing {len(adata.var_names)} genes...")
for i, gene in enumerate(adata.var_names):
    if i % 1000 == 0:
        print(f"  Processed {i}/{len(adata.var_names)} genes")

# 3. Converting large sparse matrices to dense for printing
print(adata.X.toarray())  # Memory explosion!

# Better:
print(f"Expression matrix: {adata.X.shape}, sparse={scipy.sparse.issparse(adata.X)}")
print(f"Sparsity: {1 - (adata.X.nnz / (adata.X.shape[0] * adata.X.shape[1])):.2%}")
```

## Summary

When working with large biological datasets:
- **Limit output** to the first 10-100 items
- **Show counts** instead of full lists
- **Use sampling** for very large collections
- **Print summaries** not raw data
- **Configure output limits** in ActionExecutor when needed

This approach ensures the bug fixer can effectively debug issues without being overwhelmed by massive outputs.