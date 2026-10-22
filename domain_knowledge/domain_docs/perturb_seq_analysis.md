# Perturb-seq Analysis Domain Knowledge

## Table of Contents
1. [Overview](#overview)
2. [Core Concepts](#core-concepts)
3. [Technical Implementation](#technical-implementation)
4. [Data Structure Requirements](#data-structure-requirements)
5. [Analysis Pipeline](#analysis-pipeline)
6. [Common Challenges and Solutions](#common-challenges-and-solutions)
7. [Best Practices](#best-practices)
8. [Code Examples](#code-examples)

## Overview

Perturb-seq (Perturbation single-cell RNA sequencing) is a powerful technique that combines CRISPR-based genetic perturbations with single-cell RNA sequencing to study the effects of genetic modifications at single-cell resolution. This document provides comprehensive technical guidance for analyzing perturb-seq data, with specific focus on the Norman et al. CRISPRa dataset.

### Key Applications
- **Genetic Interaction (GI) Mapping**: Identify synergistic, buffering, or epistatic relationships between genes
- **Pathway Analysis**: Understand how perturbations affect cellular pathways and programs
- **Cell State Transitions**: Track how cells change in response to perturbations
- **Drug Target Discovery**: Identify potential therapeutic targets and combinations

## Core Concepts

### 1. Genetic Interactions (GI)
Genetic interactions occur when the combined effect of perturbing two genes differs from the expected additive effect of individual perturbations:
- **Synergy**: Combined effect > sum of individual effects
- **Buffering/Epistasis**: Combined effect < sum of individual effects
- **Suppression**: One perturbation masks the effect of another

### 2. GI Manifold
A low-dimensional representation of all perturbation profiles that reveals the landscape of cellular responses:
- Computed from mean expression profiles per perturbation
- Visualized using dimensionality reduction (PCA → UMAP)
- Clusters represent similar cellular responses

### 3. Linear GI Model
Mathematical framework for predicting double perturbation effects from singles:
```
d_ab = c1 * d_a + c2 * d_b + e
```
Where:
- `d_ab`: Effect of double perturbation
- `d_a`, `d_b`: Effects of single perturbations
- `c1`, `c2`: Interaction coefficients
- `e`: Non-linear interaction term

## Technical Implementation

### Required Python Packages
```python
# Core analysis
scanpy>=1.10.0
anndata>=0.10.0
pandas>=2.0.0
numpy>=1.24.0

# Visualization
matplotlib>=3.6.0
seaborn>=0.13.0
adjustText>=1.0.0

# Machine learning
scikit-learn>=1.3.0
umap-learn>=0.5.0
hdbscan>=0.8.0

# Statistics
scipy>=1.10.0
statsmodels>=0.14.0

# Network analysis
networkx>=3.0
leidenalg>=0.10.0
```

### Data Structure Requirements

The input AnnData object should contain:

#### Required Fields
```python
adata.obs:
  - 'condition': Perturbation identifier (e.g., "GENE1+GENE2", "ctrl")
  - 'cell_type': Cell type annotation (optional but recommended)

adata.var:
  - 'gene_name': Gene symbols

adata.X:
  - Raw or normalized count matrix
```

#### Optional Fields
```python
adata.obs:
  - 'dose_val': Perturbation dose/strength
  - 'control': Boolean indicating control cells
  - 'condition_name': Human-readable condition name

adata.uns:
  - 'go_annotations': Gene ontology annotations
  - 'pathway_info': Pathway membership data
```

## Analysis Pipeline

### Step 1: Data Preprocessing
```python
import scanpy as sc
import pandas as pd
import numpy as np

def preprocess_perturb_seq(adata):
    """Standard preprocessing for perturb-seq data"""
    
    # Calculate QC metrics
    sc.pp.calculate_qc_metrics(adata, inplace=True)
    
    # Filter cells and genes
    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.filter_genes(adata, min_cells=3)
    
    # Save raw counts
    adata.raw = adata.copy()
    
    # Normalization and log-transformation
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)
    
    # Find highly variable genes
    sc.pp.highly_variable_genes(adata, 
                                 min_mean=0.0125, 
                                 max_mean=3, 
                                 min_disp=0.5)
    
    # Keep only HVGs for downstream analysis
    adata = adata[:, adata.var.highly_variable]
    
    # Scale data
    sc.pp.scale(adata, max_value=10)
    
    # PCA
    sc.tl.pca(adata, svd_solver='arpack', n_comps=50)
    
    return adata
```

### Step 2: GI Manifold Construction
```python
import umap
import hdbscan

def construct_gi_manifold(adata):
    """Build GI manifold from mean perturbation profiles"""
    
    # Compute mean profiles per perturbation
    perturbations = adata.obs['condition'].unique()
    n_genes = adata.shape[1]
    
    mean_profiles = np.zeros((len(perturbations), n_genes))
    for i, pert in enumerate(perturbations):
        mask = adata.obs['condition'] == pert
        mean_profiles[i] = adata[mask].X.mean(axis=0)
    
    # PCA on mean profiles
    from sklearn.decomposition import PCA
    pca = PCA(n_components=min(50, len(perturbations)-1))
    profiles_pca = pca.fit_transform(mean_profiles)
    
    # UMAP embedding
    umap_model = umap.UMAP(
        n_components=2,
        n_neighbors=15,
        min_dist=0.1,
        metric='euclidean',
        random_state=42
    )
    profiles_umap = umap_model.fit_transform(profiles_pca)
    
    # Cluster perturbations
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=5,
        min_samples=2,
        metric='euclidean'
    )
    clusters = clusterer.fit_predict(profiles_umap)
    
    return {
        'perturbations': perturbations,
        'mean_profiles': mean_profiles,
        'pca_coords': profiles_pca,
        'umap_coords': profiles_umap,
        'clusters': clusters,
        'pca_model': pca,
        'umap_model': umap_model
    }
```

### Step 3: Marker Gene Analysis
```python
from scipy.stats import zscore

def analyze_marker_expression(adata, manifold_data, marker_panels):
    """Overlay marker gene expression on manifold"""
    
    marker_scores = {}
    
    for panel_name, genes in marker_panels.items():
        # Filter to available genes
        available = [g for g in genes if g in adata.raw.var_names]
        if not available:
            continue
        
        # Calculate z-scored mean expression per perturbation
        scores = []
        for pert in manifold_data['perturbations']:
            mask = adata.obs['condition'] == pert
            pert_expr = adata.raw[mask, available].X.mean(axis=0)
            z_scores = zscore(pert_expr)
            scores.append(np.mean(z_scores))
        
        marker_scores[panel_name] = np.array(scores)
    
    return marker_scores

# Example marker panels
MARKER_PANELS = {
    'Erythroid': ['HBB', 'HBA1', 'HBA2', 'HBG1', 'HBG2', 'GATA1', 'KLF1', 'ALAS2'],
    'Granulocyte': ['ELANE', 'MPO', 'AZU1', 'PRTN3', 'CSF3R', 'CTSG', 'DEFA1'],
    'Megakaryocyte': ['PF4', 'PPBP', 'GP9', 'ITGA2B', 'GP1BA'],
    'Cell_Cycle_G1': ['CDKN1A', 'CDKN1B', 'CDKN1C', 'RB1', 'RBL1', 'RBL2'],
    'Cell_Cycle_S': ['MCM2', 'MCM3', 'MCM4', 'MCM5', 'MCM6', 'PCNA', 'TYMS'],
    'Cell_Cycle_G2M': ['CCNB1', 'CCNB2', 'CDK1', 'AURKA', 'AURKB', 'PLK1'],
    'Apoptosis': ['CASP3', 'CASP7', 'CASP8', 'CASP9', 'BCL2', 'BAX', 'BAD'],
    'Stress_Response': ['HSPA1A', 'HSPA1B', 'HSP90AA1', 'HSPB1', 'ATF3', 'JUN', 'FOS']
}
```

### Step 4: Cell Cycle Analysis
```python
def analyze_cell_cycle_effects(adata):
    """Analyze cell cycle distribution changes"""
    
    # Cell cycle gene lists (Tirosh et al. 2016)
    s_genes = ['MCM5', 'PCNA', 'TYMS', 'FEN1', 'MCM2', 'MCM4', 'RRM1', 'UNG',
               'GINS2', 'MCM6', 'CDCA7', 'DTL', 'PRIM1', 'UHRF1', 'MLF1IP', 
               'HELLS', 'RFC2', 'RPA2', 'NASP', 'RAD51AP1', 'GMNN', 'WDR76', 
               'SLBP', 'CCNE2', 'UBR7', 'POLD3', 'MSH2', 'ATAD2', 'RAD51']
    
    g2m_genes = ['HMGB2', 'CDK1', 'NUSAP1', 'UBE2C', 'BIRC5', 'TPX2', 'TOP2A',
                 'NDC80', 'CKS2', 'NUF2', 'CKS1B', 'MKI67', 'TMPO', 'CENPF', 
                 'TACC3', 'FAM64A', 'SMC4', 'CCNB2', 'CKAP2L', 'CKAP2', 'AURKB',
                 'BUB1', 'KIF11', 'ANP32E', 'TUBB4B', 'GTSE1', 'KIF20B', 
                 'HJURP', 'CDCA3', 'HN1']
    
    # Filter to available genes
    s_genes = [g for g in s_genes if g in adata.raw.var_names]
    g2m_genes = [g for g in g2m_genes if g in adata.raw.var_names]
    
    # Score cell cycle
    sc.tl.score_genes_cycle(adata, s_genes=s_genes, g2m_genes=g2m_genes)
    
    # Analyze phase distributions per perturbation
    phase_stats = []
    for pert in adata.obs['condition'].unique():
        mask = adata.obs['condition'] == pert
        phases = adata.obs.loc[mask, 'phase'].value_counts(normalize=True)
        
        phase_stats.append({
            'perturbation': pert,
            'n_cells': mask.sum(),
            'G1': phases.get('G1', 0),
            'S': phases.get('S', 0),
            'G2M': phases.get('G2M', 0),
            's_score_mean': adata.obs.loc[mask, 'S_score'].mean(),
            'g2m_score_mean': adata.obs.loc[mask, 'G2M_score'].mean()
        })
    
    return pd.DataFrame(phase_stats)
```

### Step 5: Linear GI Model
```python
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import r2_score, mean_squared_error

def fit_linear_gi_model(adata, use_hvg_only=True, regularization=0.01):
    """Fit linear model: d_ab = c1*d_a + c2*d_b + e"""
    
    results = []
    perturbations = adata.obs['condition'].unique()
    
    # Identify double perturbations
    double_perts = [p for p in perturbations 
                   if '+' in p and p != 'ctrl' and p.count('+') == 1]
    
    # Get control profile
    ctrl_mask = adata.obs['condition'] == 'ctrl'
    if ctrl_mask.sum() == 0:
        raise ValueError("No control cells found")
    
    ctrl_profile = adata[ctrl_mask].X.mean(axis=0)
    
    for double in double_perts:
        # Parse perturbation names
        genes = double.split('+')
        if len(genes) != 2:
            continue
        
        # Find corresponding singles
        single_a = f"{genes[0]}+ctrl"
        single_b = f"ctrl+{genes[1]}"
        
        # Alternative naming conventions
        if single_a not in perturbations:
            single_a = genes[0]
        if single_b not in perturbations:
            single_b = genes[1]
        
        if single_a not in perturbations or single_b not in perturbations:
            continue
        
        # Get mean profiles
        mask_double = adata.obs['condition'] == double
        mask_single_a = adata.obs['condition'] == single_a
        mask_single_b = adata.obs['condition'] == single_b
        
        if mask_double.sum() < 10 or mask_single_a.sum() < 10 or mask_single_b.sum() < 10:
            continue  # Skip if too few cells
        
        # Calculate deviations from control
        double_dev = adata[mask_double].X.mean(axis=0) - ctrl_profile
        single_a_dev = adata[mask_single_a].X.mean(axis=0) - ctrl_profile
        single_b_dev = adata[mask_single_b].X.mean(axis=0) - ctrl_profile
        
        # Select genes for model (HVGs or differentially expressed)
        if use_hvg_only and 'highly_variable' in adata.var:
            gene_mask = adata.var['highly_variable'].values
        else:
            # Use genes with substantial effects
            effect_threshold = 0.1
            gene_mask = (np.abs(single_a_dev) > effect_threshold) | \
                       (np.abs(single_b_dev) > effect_threshold)
        
        if gene_mask.sum() < 10:
            continue
        
        # Fit model
        X = np.column_stack([single_a_dev[gene_mask], 
                           single_b_dev[gene_mask]])
        y = double_dev[gene_mask]
        
        # Use Ridge regression for regularization
        model = Ridge(alpha=regularization)
        model.fit(X, y)
        y_pred = model.predict(X)
        
        # Calculate metrics
        r2 = r2_score(y, y_pred)
        rmse = np.sqrt(mean_squared_error(y, y_pred))
        
        # Classify interaction type
        c1, c2 = model.coef_
        interaction_type = classify_interaction(c1, c2)
        
        results.append({
            'double_perturbation': double,
            'single_a': single_a,
            'single_b': single_b,
            'c1': c1,
            'c2': c2,
            'r2': r2,
            'rmse': rmse,
            'n_genes_used': gene_mask.sum(),
            'interaction_type': interaction_type
        })
    
    return pd.DataFrame(results)

def classify_interaction(c1, c2, threshold=0.2):
    """Classify GI type based on coefficients"""
    
    # Expected additive: c1 ≈ 1, c2 ≈ 1
    deviation = np.sqrt((c1 - 1)**2 + (c2 - 1)**2)
    
    if deviation < threshold:
        return 'additive'
    elif c1 + c2 > 2 + threshold:
        return 'synergistic'
    elif c1 + c2 < 2 - threshold:
        if min(c1, c2) < threshold:
            return 'epistatic'
        else:
            return 'buffering'
    elif abs(c1 - c2) > 1:
        return 'suppressive'
    else:
        return 'complex'
```

### Step 6: Pathway Analysis
```python
def analyze_pathway_interactions(adata, pathway_genes, perturbations_of_interest):
    """Analyze interactions within a pathway"""
    
    results = {
        'expression_changes': {},
        'trajectory_data': None,
        'interaction_network': None
    }
    
    # Filter to cells with perturbations of interest
    mask = adata.obs['condition'].isin(perturbations_of_interest)
    adata_subset = adata[mask].copy()
    
    # 1. Expression changes for pathway genes
    for pert in perturbations_of_interest:
        pert_mask = adata_subset.obs['condition'] == pert
        ctrl_mask = adata_subset.obs['condition'] == 'ctrl'
        
        if pert_mask.sum() > 0 and ctrl_mask.sum() > 0:
            # Calculate fold changes
            pert_expr = adata_subset[pert_mask, pathway_genes].X.mean(axis=0)
            ctrl_expr = adata_subset[ctrl_mask, pathway_genes].X.mean(axis=0)
            
            # Avoid division by zero
            ctrl_expr = np.where(ctrl_expr == 0, 1e-10, ctrl_expr)
            fold_change = pert_expr / ctrl_expr
            
            results['expression_changes'][pert] = {
                'fold_changes': fold_change,
                'genes': pathway_genes
            }
    
    # 2. Trajectory analysis
    if adata_subset.shape[0] > 100:  # Need enough cells
        # Compute neighbors and UMAP
        sc.pp.neighbors(adata_subset, n_neighbors=15, n_pcs=30)
        sc.tl.umap(adata_subset)
        
        # Diffusion map for pseudotime
        sc.tl.diffmap(adata_subset)
        
        # Store trajectory data
        results['trajectory_data'] = {
            'umap': adata_subset.obsm['X_umap'],
            'diffmap': adata_subset.obsm['X_diffmap'],
            'conditions': adata_subset.obs['condition'].values
        }
    
    # 3. Build interaction network
    import networkx as nx
    
    G = nx.DiGraph()
    
    # Add nodes for each perturbation
    for pert in perturbations_of_interest:
        if pert != 'ctrl':
            G.add_node(pert)
    
    # Add edges based on expression similarity
    from scipy.spatial.distance import cosine
    
    for i, pert1 in enumerate(perturbations_of_interest):
        if pert1 == 'ctrl':
            continue
        for pert2 in perturbations_of_interest[i+1:]:
            if pert2 == 'ctrl':
                continue
            
            # Calculate similarity between expression changes
            if pert1 in results['expression_changes'] and \
               pert2 in results['expression_changes']:
                fc1 = results['expression_changes'][pert1]['fold_changes']
                fc2 = results['expression_changes'][pert2]['fold_changes']
                
                similarity = 1 - cosine(fc1, fc2)
                if similarity > 0.5:  # Threshold for edge creation
                    G.add_edge(pert1, pert2, weight=similarity)
    
    results['interaction_network'] = G
    
    return results
```

## Common Challenges and Solutions

### Challenge 1: Batch Effects
**Problem**: Different experimental batches show systematic differences
**Solution**:
```python
# Use combat or scVI for batch correction
import scanpy.external as sce

# Combat
sc.pp.combat(adata, key='batch')

# Or use scVI
sce.pp.scvi(adata, batch_key='batch')
```

### Challenge 2: Sparse Perturbation Coverage
**Problem**: Some perturbations have very few cells
**Solution**:
```python
def filter_rare_perturbations(adata, min_cells=50):
    """Remove perturbations with too few cells"""
    pert_counts = adata.obs['condition'].value_counts()
    keep_perts = pert_counts[pert_counts >= min_cells].index
    return adata[adata.obs['condition'].isin(keep_perts)]
```

### Challenge 3: Control Selection
**Problem**: Identifying appropriate control cells
**Solution**:
```python
def identify_controls(adata):
    """Multiple strategies for control identification"""
    
    # Strategy 1: Explicit control labels
    if 'control' in adata.obs:
        return adata.obs['control'] == True
    
    # Strategy 2: Non-targeting guides
    control_patterns = ['ctrl', 'control', 'nt', 'non-targeting', 'gfp']
    control_mask = adata.obs['condition'].str.lower().str.contains(
        '|'.join(control_patterns), na=False
    )
    
    # No inferred controls: do not invent a control population from expression
    # statistics - require the user to specify control labels explicitly
    if not control_mask.any():
        raise ValueError("No control cells identified; specify control condition labels explicitly")
    
    return control_mask
```

### Challenge 4: Multi-guide Assignments
**Problem**: Cells with multiple guide RNAs
**Solution**:
```python
def handle_multi_guide_cells(adata, strategy='separate'):
    """Handle cells with multiple guides"""
    
    if strategy == 'separate':
        # Keep as separate category
        pass
    elif strategy == 'remove':
        # Remove multi-guide cells
        single_guide = ~adata.obs['condition'].str.contains('\\+', na=False)
        adata = adata[single_guide]
    elif strategy == 'assign_dominant':
        # Assign to dominant perturbation (requires guide counts)
        if 'guide_counts' in adata.obs:
            # Implementation depends on data structure
            pass
    
    return adata
```

## Best Practices

### 1. Quality Control
```python
def comprehensive_qc(adata):
    """Comprehensive quality control for perturb-seq"""
    
    metrics = {}
    
    # Basic metrics
    sc.pp.calculate_qc_metrics(adata, inplace=True)
    
    # Perturbation-specific metrics
    for pert in adata.obs['condition'].unique():
        mask = adata.obs['condition'] == pert
        metrics[pert] = {
            'n_cells': mask.sum(),
            'mean_genes': adata.obs.loc[mask, 'n_genes_by_counts'].mean(),
            'mean_counts': adata.obs.loc[mask, 'total_counts'].mean(),
            'percent_mito': adata.obs.loc[mask, 'pct_counts_mt'].mean() 
                           if 'pct_counts_mt' in adata.obs else 0
        }
    
    # Flag problematic perturbations
    metrics_df = pd.DataFrame(metrics).T
    problematic = metrics_df[
        (metrics_df['n_cells'] < 30) |
        (metrics_df['mean_genes'] < 500) |
        (metrics_df['percent_mito'] > 20)
    ]
    
    return metrics_df, problematic
```

### 2. Reproducibility
```python
def ensure_reproducibility():
    """Set seeds for reproducible analysis"""
    
    import random
    import numpy as np
    
    # Set seeds
    random.seed(42)
    np.random.seed(42)
    
    # Scanpy settings
    sc.settings.seed = 42
    
    # UMAP settings
    import umap
    umap.UMAP(random_state=42)
    
    print("Seeds set for reproducibility")
```

### 3. Validation
```python
def validate_gi_predictions(adata, gi_model_results, test_fraction=0.2):
    """Cross-validate GI model predictions"""
    
    from sklearn.model_selection import train_test_split
    
    validation_results = []
    
    for _, row in gi_model_results.iterrows():
        double = row['double_perturbation']
        single_a = row['single_a']
        single_b = row['single_b']
        
        # Get cells for cross-validation
        double_cells = adata.obs['condition'] == double
        
        if double_cells.sum() < 50:
            continue
        
        # Split cells
        indices = np.where(double_cells)[0]
        train_idx, test_idx = train_test_split(
            indices, test_size=test_fraction, random_state=42
        )
        
        # TEMPLATE ONLY: refit the model on train_idx and evaluate on test_idx.
        # Never report placeholder metrics.
        raise NotImplementedError("Implement model refitting/evaluation before using this template")
    
    return pd.DataFrame(validation_results)
```

### 4. Visualization Standards
```python
import matplotlib.pyplot as plt
import seaborn as sns

def setup_plot_style():
    """Set consistent plot style for publication"""
    
    # Set style
    plt.style.use('seaborn-v0_8-whitegrid')
    sns.set_palette("husl")
    
    # Figure parameters
    plt.rcParams.update({
        'figure.figsize': (10, 8),
        'figure.dpi': 150,
        'savefig.dpi': 300,
        'font.size': 12,
        'axes.labelsize': 14,
        'axes.titlesize': 16,
        'xtick.labelsize': 12,
        'ytick.labelsize': 12,
        'legend.fontsize': 12,
        'figure.titlesize': 18
    })
    
    # Scanpy settings
    sc.settings.set_figure_params(
        dpi=150,
        facecolor='white',
        frameon=False,
        fontsize=12
    )
```

## Code Examples

### Complete Analysis Pipeline
```python
def run_complete_perturb_seq_analysis(adata_path, output_dir):
    """Complete perturb-seq analysis pipeline"""
    
    import scanpy as sc
    from pathlib import Path
    
    # Setup
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / 'figures'
    figures_dir.mkdir(exist_ok=True)
    
    # Load data
    adata = sc.read_h5ad(adata_path)
    print(f"Loaded {adata.shape[0]} cells × {adata.shape[1]} genes")
    
    # 1. Preprocessing
    adata = preprocess_perturb_seq(adata)
    
    # 2. GI manifold
    manifold = construct_gi_manifold(adata)
    
    # 3. Marker analysis
    markers = analyze_marker_expression(adata, manifold, MARKER_PANELS)
    
    # 4. Cell cycle
    cc_stats = analyze_cell_cycle_effects(adata)
    
    # 5. Linear GI model
    gi_model = fit_linear_gi_model(adata)
    
    # 6. Save results
    adata.write(output_dir / 'processed.h5ad')
    
    # Save tables
    cc_stats.to_csv(output_dir / 'cell_cycle_stats.csv', index=False)
    gi_model.to_csv(output_dir / 'gi_model_results.csv', index=False)
    
    # Save manifold
    pd.DataFrame({
        'perturbation': manifold['perturbations'],
        'umap_1': manifold['umap_coords'][:, 0],
        'umap_2': manifold['umap_coords'][:, 1],
        'cluster': manifold['clusters']
    }).to_csv(output_dir / 'manifold_coordinates.csv', index=False)
    
    return {
        'adata': adata,
        'manifold': manifold,
        'markers': markers,
        'cell_cycle': cc_stats,
        'gi_model': gi_model
    }
```

### Advanced GI Analysis
```python
def advanced_gi_analysis(adata, go_annotations=None):
    """Advanced genetic interaction analysis with GO enrichment"""
    
    from scipy.stats import hypergeom
    import networkx as nx
    
    # Build interaction network
    gi_network = nx.Graph()
    
    # Fit all pairwise models
    gi_results = fit_linear_gi_model(adata)
    
    # Add strong interactions to network
    strong_interactions = gi_results[gi_results['r2'] > 0.5]
    
    for _, row in strong_interactions.iterrows():
        # Parse gene names
        genes_double = row['double_perturbation'].split('+')
        
        # Add nodes
        for gene in genes_double:
            if gene != 'ctrl':
                gi_network.add_node(gene)
        
        # Add edge with interaction strength
        if len(genes_double) == 2:
            gi_network.add_edge(
                genes_double[0], 
                genes_double[1],
                weight=row['r2'],
                interaction_type=row['interaction_type']
            )
    
    # Identify network modules
    import community
    modules = community.best_partition(gi_network)
    
    # GO enrichment for modules
    if go_annotations is not None:
        module_enrichment = {}
        
        for module_id in set(modules.values()):
            module_genes = [g for g, m in modules.items() if m == module_id]
            
            # TEMPLATE ONLY: perform a hypergeometric test against go_annotations here.
            raise NotImplementedError("Implement GO enrichment before using this template")
    
    return {
        'network': gi_network,
        'modules': modules,
        'enrichment': module_enrichment if go_annotations else None
    }
```

## Summary

This domain knowledge document provides comprehensive guidance for perturb-seq analysis, covering:

1. **Core concepts** of genetic interactions and manifolds
2. **Technical requirements** for data structures and packages
3. **Complete analysis pipeline** with code examples
4. **Solutions to common challenges** in perturb-seq data
5. **Best practices** for reproducible analysis
6. **Advanced techniques** for deeper insights

Key takeaways for successful perturb-seq analysis:
- Always perform thorough QC and preprocessing
- Use appropriate controls for normalization
- Validate GI models with cross-validation
- Consider batch effects and technical variation
- Document all parameters for reproducibility
- Visualize results at multiple levels (cell, perturbation, pathway)

This knowledge enables researchers and computational biologists to extract maximum biological insight from perturb-seq experiments, advancing our understanding of genetic interactions and cellular responses to perturbations.