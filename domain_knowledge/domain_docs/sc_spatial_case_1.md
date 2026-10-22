# Domain Knowledge: Single Cell Spatial Transcriptomics Analysis

## Overview
This document provides **patterns and principles** for spatial transcriptomics analysis. Focus on understanding concepts and adapting patterns to your specific requirements rather than copying code verbatim.

## Core Principles

### 1. Spatial Data Handling
- **Flexible coordinate detection**: Check multiple possible keys (`spatial`, `X_spatial`, `obsm['spatial']`)
- **Fail loudly on missing coordinates**: if no spatial coordinates are found, raise an informative error (mock coordinates belong only in unit tests, never in analysis outputs)
- **Format agnostic**: Support both Visium and generic spatial formats

### 2. Dependency Management
- **Version flexibility**: Use `>=` constraints rather than exact versions
- **Core dependencies**: Focus on essential packages first
- **Fallback strategies**: Provide alternatives when packages fail to install

## Key Patterns

### Pattern 1: Robust Data Loading
```python
# Adapt this pattern - don't copy verbatim
def load_spatial_data(path_dict):
    """Load data with flexible file detection."""
    # Check for previous nodes first
    if has_previous_nodes():
        data = load_from_previous_nodes()
    
    # Fallback to input directory
    if data is None:
        data = find_and_load_h5ad(path_dict['input_dir'])
    
    return data
```

### Pattern 2: Spatial Coordinate Detection
```python
# Key concept: Be flexible with spatial coordinate formats
def find_spatial_coords(adata):
    """Detect spatial coordinates flexibly."""
    # Check common locations
    for key in ['spatial', 'X_spatial', 'spatial_coords']:
        if key in adata.obsm:
            return key
    
    # Never fabricate coordinates in an analysis block
    raise KeyError(f"No spatial coordinates found in adata.obsm: {list(adata.obsm.keys())}")
```

### Pattern 3: Matplotlib Backend Setup
```python
# IMPORTANT: Set backend BEFORE importing pyplot
import matplotlib
matplotlib.use('Agg')  # For headless execution
import matplotlib.pyplot as plt
```

## Spatial Analysis Methods

### 1. Squidpy Integration

**Dependencies** (verified in Docker container on 2025-09-18):
```txt
# Exact version that was successfully installed (Docker test 2025-09-18):
squidpy==1.6.5      # ✅ This exact version confirmed installed
# Note: squidpy 1.6.5 automatically installs numpy 2.2.6 which breaks h5py
# You MUST either:
# Option 1: Pre-install numpy<2.0 before squidpy
# Option 2: Reinstall h5py after squidpy installation

# Recommended exact versions for compatibility:
squidpy==1.6.5
numpy==1.26.4       # Pin this BEFORE installing squidpy
h5py==3.11.0        # Reinstall if numpy gets upgraded
scanpy>=1.9.5       # Will be compatible with numpy 1.26.x
anndata>=0.10.0
pandas>=2.0.0
scipy>=1.11.0
matplotlib>=3.7.0
igraph>=0.10.0
leidenalg>=0.10.0

# Alternative: Flexible versions with constraints
squidpy>=1.3.0,<1.7  # Version 1.6.5 tested and working
scanpy>=1.9.5
anndata>=0.10.0
numpy>=1.26.0,<2.0  # IMPORTANT: numpy 2.x causes h5py compatibility issues
pandas>=2.0.0
scipy>=1.11.0
matplotlib>=3.7.0
igraph>=0.10.0
leidenalg>=0.10.0
```

**Installation Note**: 
Squidpy 1.6.5 was successfully installed and tested. Critical: If squidpy installation upgrades numpy to 2.x, you'll get "numpy.dtype size changed" error. Solutions:
1. Pin numpy==1.26.4 before installing squidpy
2. Or reinstall h5py after squidpy: `pip install --force-reinstall h5py`
3. Or use the exact versions listed above for guaranteed compatibility

**Key Functions**:
- `sq.gr.spatial_neighbors()` - Build spatial graph
- `sq.gr.nhood_enrichment()` - Neighborhood analysis
- `sq.gr.co_occurrence()` - Co-occurrence patterns
- `sq.pl.spatial_scatter()` - Visualization

**Common Issues and Solutions**:
- **Numpy compatibility**: If you get "numpy.dtype size changed" error, reinstall h5py: `pip install --force-reinstall h5py`
- **Dependency conflicts**: Use `>=` version constraints with upper bounds where needed
- **Missing spatial info**: Add minimal `adata.uns['spatial'] = {}` if needed
- **Coordinate format**: Use `coord_type="generic"` for non-Visium data

### 2. Metabolic Analysis

**Approach**: Use pathway databases for metabolic scoring
```python
# Pattern: Score metabolic pathways
def score_metabolism(adata, pathway_database):
    """Score cells for metabolic activity."""
    # 1. Load pathway gene sets
    # 2. Calculate enrichment scores
    # 3. Store in adata.obs
```

**Useful Packages**:
- `gseapy` for pathway enrichment (use `gseapy.ssgsea`)
- `decoupler` for pathway activity inference
- Standard gene set scoring with `scanpy.tl.score_genes`

### 3. AUCell Scoring

**Concept**: Score cells based on gene set activity
```python
# Pattern for AUCell-like scoring
def score_gene_sets(adata, gene_sets):
    """Score cells for gene set activity."""
    for name, genes in gene_sets.items():
        # Filter to available genes
        valid_genes = [g for g in genes if g in adata.var_names]
        if valid_genes:
            sc.tl.score_genes(adata, valid_genes, score_name=name)
```

### 4. GO Enrichment Analysis

**Flexible Approach**:
```python
# Pattern: Enrichment analysis with fallbacks
def enrichment_analysis(genes, background=None):
    """Perform enrichment with multiple methods."""
    try:
        # Method 1: gseapy.enrichr (web-based, no local database needed)
        results = enrichr_analysis(genes)
    except Exception as e:
        # Method 2: Statistical enrichment with scipy (record the method actually used)
        print(f"WARNING: enrichr failed ({e}); using hypergeometric test")
        results = hypergeometric_enrichment(genes, background)
    
    return results
```

## Error Handling Best Practices

### 1. Graceful Degradation
```python
# Don't fail completely - provide partial results
try:
    advanced_analysis()
except Exception as e:
    print(f"WARNING: advanced analysis failed: {e}; using simpler method")
    basic_analysis()  # Fallback to simpler approach
    results['method_used'] = 'basic (fallback)'  # always disclose which method produced the outputs
```

### 2. Informative Error Messages
```python
if required_column not in adata.obs:
    available = list(adata.obs.columns)[:10]
    raise ValueError(
        f"Column '{required_column}' not found. "
        f"Available columns: {available}"
    )
```

### 3. Validate Before Processing
```python
# Check requirements upfront
def validate_inputs(adata):
    checks = {
        'has_counts': adata.X is not None,
        'has_coords': any(k for k in adata.obsm if 'spatial' in k),
        'has_genes': adata.n_vars > 0
    }
    return checks
```

## Output Organization

### Standard Structure
```
output_dir/
├── figures/
│   ├── spatial_clusters.png
│   ├── gene_expression_*.png
│   └── enrichment_*.png
├── tables/
│   ├── enrichment_results.csv
│   └── metabolic_scores.csv
├── _node_anndata.h5ad  # Processed data
└── analysis_summary.csv
```

### File Naming Conventions
- Use descriptive names: `spatial_leiden_clusters.png` not `plot1.png`
- Include parameters: `neighbors_k6_distance.png`
- Timestamp if needed: `analysis_20250918_143022.csv`

## Common Pitfalls to Avoid

1. **Don't hardcode paths or filenames**
2. **Don't assume specific data formats**
3. **Don't use exact package versions unless critical**
4. **Don't ignore error messages - handle them gracefully**
5. **Don't create monolithic functions - keep them modular**

## Validation Checklist

Before finalizing your function block:
- [ ] Raises an informative error when spatial coordinates are missing (never fabricates them)
- [ ] Sets matplotlib backend before importing pyplot
- [ ] Uses flexible file detection
- [ ] Provides informative error messages
- [ ] Creates output directories as needed
- [ ] Saves both data and visualizations
- [ ] Documents what was done in summary files

## Quick Reference

### Essential Imports
```python
import os
import warnings
from pathlib import Path
import matplotlib
matplotlib.use('Agg')  # Set BEFORE pyplot
import matplotlib.pyplot as plt
import scanpy as sc
import pandas as pd
import numpy as np
```

### Flexible Parameter Handling
```python
# Get parameters with sensible defaults
clustering_key = params.get('clustering_key', 'leiden')
n_neighbors = params.get('n_neighbors', 15)
resolution = params.get('resolution', 1.0)
```

### Safe Feature Access
```python
# Check before using
if 'gene_name' in adata.var_names:
    process_gene('gene_name')
else:
    print(f"Gene 'gene_name' not found, skipping...")
```

## Summary

Focus on:
1. **Adaptability** over rigid implementations
2. **Patterns** over complete code blocks  
3. **Error handling** over assuming success
4. **Validation** over blind processing

Remember: The goal is to understand concepts and adapt them to your specific analysis needs, not to copy code verbatim.