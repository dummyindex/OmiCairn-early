# Bug Fixer Experience and Best Practices

This document contains accumulated experience from debugging various single-cell RNA-seq analysis pipelines. These lessons should guide efficient debugging strategies.

## Common Error Patterns and Solutions

### 1. Missing Preprocessing Steps

**Error**: `KeyError: 'No "neighbors" in .uns'`
- **Cause**: Leiden/Louvain clustering requires pre-computed neighbor graph
- **Solution**: Add `sc.pp.neighbors(adata)` before clustering
- **Example fix**:
  ```python
  # Compute neighbors before clustering
  sc.pp.neighbors(adata)
  sc.tl.leiden(adata, resolution=resolution)
  ```

**Error**: `KeyError: 'X_pca' not found`
- **Cause**: Dimensionality reduction methods need PCA
- **Solution**: Add `sc.tl.pca(adata)` before using PCA coordinates
- **Example fix**:
  ```python
  # Ensure PCA is computed
  if 'X_pca' not in adata.obsm:
      sc.tl.pca(adata, svd_solver='arpack')
  ```

### 2. API Misuse Patterns

**Error**: `AttributeError: module 'scanpy.plotting' has no attribute 'hist'`
- **Cause**: Incorrect method name
- **Solution**: Use `sc.pl.histogram` instead of `sc.pl.hist`
- **General pattern**: Scanpy uses full names, not abbreviations

**Error**: `AttributeError: module 'scanpy' has no attribute 'pl.umap'`
- **Cause**: Incorrect attribute access
- **Solution**: Use `sc.pl.umap(adata)` not `scanpy.pl.umap(adata)`

### 3. Missing Data Columns

**Error**: `KeyError: 'n_genes' not in adata.obs`
- **Cause**: Column not calculated
- **Solution**: Calculate before use
- **Example fix**:
  ```python
  # Calculate n_genes if missing
  if 'n_genes' not in adata.obs.columns:
      adata.obs['n_genes'] = (adata.X > 0).sum(axis=1).A1 if hasattr(adata.X, 'A1') else (adata.X > 0).sum(axis=1)
  ```

### 4. Package Import Issues

**Error**: `ModuleNotFoundError: No module named 'louvain'`
- **Important**: `sc.tl.louvain()` needs the separate `louvain` package
- **Solution**: Prefer `sc.tl.leiden()` (needs `leidenalg`), or install `louvain` if Louvain is explicitly required

**Error**: `ImportError: cannot import name 'palantir' from 'palantir'`
- **Cause**: Wrong import pattern
- **Solution**: Use `import palantir` not `from palantir import palantir`

### 5. Data Structure Issues

**Common missing columns in adata.obs**:
- `n_genes`: Number of genes per cell
- `n_counts`: Total counts per cell
- `percent_mito`: Mitochondrial gene percentage
- Solution: Calculate these metrics after loading data

**Missing embeddings in adata.obsm**:
- `X_pca`: PCA coordinates
- `X_umap`: UMAP coordinates
- `X_diffmap`: Diffusion map coordinates
- Solution: Run the corresponding computation function

## Efficient Debugging Strategies

### 1. ALWAYS Start with Data Exploration
```python
# First command should explore the data structure
import scanpy as sc
import glob
files = glob.glob('/workspace/input/*.h5ad')
if files:
    adata = sc.read_h5ad(files[0])
    print(f"Shape: {adata.shape}")
    print(f"obs columns: {list(adata.obs.columns)}")
    print(f"var columns: {list(adata.var.columns)}")
    print(f"obsm keys: {list(adata.obsm.keys())}")
    print(f"uns keys: {list(adata.uns.keys())}")
```

### 2. Common Preprocessing Pipeline
Most analyses require this sequence:
1. Filter cells and genes
2. Normalize and log-transform
3. Find highly variable genes
4. Scale data (for PCA)
5. Run PCA
6. Compute neighbors
7. Run UMAP/clustering

### 3. Defensive Coding Patterns
```python
# Check before using
if 'neighbors' not in adata.uns:
    sc.pp.neighbors(adata)

# Handle sparse matrices
if hasattr(adata.X, 'A1'):  # Sparse matrix
    values = adata.X.sum(axis=1).A1
else:  # Dense matrix
    values = adata.X.sum(axis=1)
```

### 4. Package-Specific Gotchas

**Scanpy**:
- Methods are in submodules: `sc.tl.*`, `sc.pl.*`, `sc.pp.*`
- Plotting functions often require computed data (run analysis first)
- Some functions modify adata in-place, others return new objects

**Leiden/Louvain**:
- Requires neighbors graph
- Resolution parameter affects cluster count
- Use `directed=False` to avoid weight vector errors

## Quick Fix Checklist

1. **For KeyError on data access**:
   - Check actual column names with `list(adata.obs.columns)`
   - Calculate missing metrics if needed
   - Use defensive access: `adata.obs.get('column', default)`

2. **For AttributeError on module methods**:
   - Verify correct submodule: `dir(sc.pl)` to list available methods
   - Check documentation for API changes
   - Common: `hist` → `histogram`, `write_h5ad` → `write`

3. **For clustering errors**:
   - Ensure neighbors are computed first
   - Check if PCA was run (required for neighbors)
   - Verify data is normalized and scaled

4. **For plotting errors**:
   - Ensure the data being plotted exists
   - Check if required computations were done
   - Verify column names match exactly (case-sensitive)

## Time-Saving Tips

1. **Don't waste turns on exploration** - Get all info in one command
2. **Fix the root cause** - Missing preprocessing is often the real issue
3. **Use update_function_block early** - Don't wait until turn 5
4. **Include all imports** - Even if they seem obvious
5. **Test fixes incrementally** - But aim for complete solution

## Common Pitfalls to Avoid

1. **Prefer Leiden over Louvain** - `sc.tl.louvain` needs the extra `louvain` package
2. **Don't assume column names** - Always verify first
3. **Don't skip preprocessing** - Most errors come from missing steps
4. **Don't use try-except to hide errors** - Fix the actual problem
5. **Don't forget to save outputs** - Pipeline will break without output files

## Library Compatibility Notes

- **leidenalg**: May have issues with weight vectors, use `directed=False`
- **numpy**: Some operations differ between versions
- **scanpy**: API occasionally changes between versions
- **matplotlib**: Backend issues in containers - use `Agg` backend

Remember: Most errors stem from missing preprocessing steps or incorrect API usage. Always verify the data structure before making assumptions.