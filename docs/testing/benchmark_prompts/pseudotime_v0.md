
1. Preprocess dataset if not already processed
   - Use Scanpy: normalize_total → log1p → highly_variable_genes → PCA → neighbors → UMAP

2. Select root cell based on biological criteria
   - Identify cell types using leiden clustering or existing cell type annotations
   - Find the earliest/progenitor cell type (e.g., stem cells, progenitors)
   - Select a representative cell from this population as root
   - Consider markers of stemness/early development if available
   - If root cell cannot be determined, use a randomly selected cell and document this choice

3. Run DPT + PAGA (Scanpy)
   - Set the biologically selected root cell
   - Compute pseudotime using sc.tl.dpt()
   - Store result in adata.obs['dpt']

4. Run Palantir
   - Use the same biological root cell
   - Use Scanpy's palantir implementation
   - Store result in adata.obs['palantir']

5. Run scFates
   - Use the same biological root cell
   - Learn trajectory tree and compute pseudotime
   - Store in adata.obs['scFates']

6. Run CellRank
   - Use PseudotimeKernel or VelocityKernel
   - Store pseudotime or absorption probabilities in adata.obs['cellrank']

7. Run DTFLOW
   - Use embedding (e.g. PCA or UMAP) to infer pseudotime
   - Store result in adata.obs['dtflow']

8. Compute evaluation metrics:
   - Compare each method's pseudotime with ground-truth labels (if available)
   - Use Kendall's tau, Spearman's rho, and MAE
   - Store all results in adata.uns['pseudotime_metrics']

9. Plot pseudotime over UMAP:
   - One subplot per method using adata.obs[method]

10. Plot metric comparisons:
    - One subplot per metric
    - Bar plots with methods on x-axis, scores on y-axis