# Cell Type Annotation Domain Knowledge

Essential API patterns and implementation requirements for cell type annotation packages.

## CellTypist

### Critical Requirements
1. **MUST download models first**: Call `celltypist.models.download_models()` before annotation
2. **Data MUST be normalized**: Use log-normalized data (10,000 counts/cell)
3. **Correct API calls**:
   ```python
   # CORRECT API
   celltypist.models.download_models()  # Download models (safe to call multiple times)
   predictions = celltypist.annotate(adata, model='Immune_All_Low.pkl')
   adata.obs['predicted'] = predictions.predicted_labels.predicted_labels
   ```

### Common Errors to Avoid
```python
# WRONG - These methods DO NOT exist:
celltypist.download_model()  # ❌ No such method
celltypist.models.load_model()  # ❌ Wrong method name
celltypist.CellTypist()  # ❌ No such class

# CORRECT alternatives:
celltypist.models.download_models()  # ✅ Downloads all models
celltypist.models.Model.load()  # ✅ Loads specific model
celltypist.annotate()  # ✅ Main annotation function
```

### Working Implementation
```python
def run(path_dict, params):
    import os
    import scanpy as sc
    import celltypist
    
    # Load data
    adata = sc.read_h5ad(os.path.join(path_dict['input_dir'], '_node_anndata.h5ad'))
    
    # Ensure normalization
    if 'normalized' not in adata.uns:
        if adata.raw is None:
            adata.raw = adata.copy()
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        adata.uns['normalized'] = True
    
    # Download models (required, safe to call multiple times)
    celltypist.models.download_models(force_update=False)
    
    # Annotate
    predictions = celltypist.annotate(
        adata,
        model=params.get('model', 'Immune_All_Low.pkl'),
        majority_voting=params.get('majority_voting', True)
    )
    
    # Extract results (note: double .predicted_labels)
    adata.obs['celltypist_predicted'] = predictions.predicted_labels.predicted_labels
    if hasattr(predictions.predicted_labels, 'majority_voting'):
        adata.obs['celltypist_majority'] = predictions.predicted_labels.majority_voting
    if hasattr(predictions.predicted_labels, 'conf_score'):
        adata.obs['celltypist_conf'] = predictions.predicted_labels.conf_score
    
    # Save
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    adata.write(os.path.join(path_dict['output_dir'], '_node_anndata.h5ad'))
    return adata
```

### Key Points
- Package: `celltypist>=1.6.0`
- Models download to `~/.celltypist/data/models/` (~50MB total)
- Common models: `Immune_All_Low.pkl`, `Immune_All_High.pkl`, `Healthy_COVID19_PBMC.pkl`
- Results structure: `predictions.predicted_labels.predicted_labels` (yes, double)

## Marker-based Annotation (Fallback)

When specialized packages fail, use marker-based annotation:

```python
def marker_based_annotation(adata, markers_dict):
    """
    markers_dict: {'T cells': ['CD3D', 'CD3E'], 'B cells': ['CD19', 'MS4A1']}
    """
    import pandas as pd
    import numpy as np
    
    scores = pd.DataFrame(index=adata.obs_names)
    
    for cell_type, markers in markers_dict.items():
        # Find available markers
        available = [m for m in markers if m in adata.var_names]
        if not available:
            scores[cell_type] = 0
            continue
        
        # Calculate mean expression
        expr = adata[:, available].X
        if hasattr(expr, 'toarray'):
            expr = expr.toarray()
        scores[cell_type] = np.mean(expr, axis=1)
    
    # Assign cell type
    adata.obs['marker_celltype'] = scores.idxmax(axis=1)
    adata.obs['marker_score'] = scores.max(axis=1)
    return adata
```

## Common Blood Cell Markers

```python
blood_markers = {
    'T cells': ['CD3D', 'CD3E', 'CD4', 'CD8A'],
    'B cells': ['CD19', 'MS4A1', 'CD79A'],
    'NK cells': ['NCAM1', 'NKG7', 'GNLY'],
    'Monocytes': ['CD14', 'LYZ', 'S100A8'],
    'Dendritic': ['FCER1A', 'CST3'],
    'Platelets': ['PPBP', 'PF4']
}
```

## Package Availability
- **Python (pip)**: CellTypist, CellAssign (requires TensorFlow)
- **R only (not pip)**: ScType, SingleR, Garnett, SCINA, scCATCH
- **Always check**: Import package in try-except block with fallback to markers