# Perturb-seq Combinatorial Perturbation Prediction Benchmark

## Objective
Develop a reproducible benchmark for predicting combinatorial genetic perturbation outcomes using ALL available GEARS datasets. The task is to predict the gene expression profile of double perturbations from the expression profiles of their constituent single perturbations, comparing performance across different cell types, perturbation technologies (CRISPRa, CRISPRi, Perturb-seq), and biological contexts.

## Dataset Requirements

### Data Acquisition
Analyze ALL available GEARS datasets for comprehensive benchmarking:

1. **Norman 2019 (Primary)**
   - Cell line: K562
   - Technology: CRISPRa
   - ~110k cells, 287 perturbations (singles + pairs)

2. **Adamson 2016**
   - Cell line: K562
   - Technology: CRISPRi
   - Growth-based screen with combinatorial perturbations

3. **Dixit 2016**
   - Cell line: Bone marrow-derived dendritic cells (BMDCs)
   - Technology: Perturb-seq
   - Immune response perturbations

4. **Replogle 2022 K562 Essential**
   - Cell line: K562
   - Technology: CRISPRi
   - Essential gene perturbations

5. **Replogle 2022 RPE1 Essential**
   - Cell line: RPE1 (retinal pigment epithelial)
   - Technology: CRISPRi
   - Essential gene perturbations

Process each dataset independently and compare results across datasets.

### Quality Control
1. Remove low-quality cells:
2. Verify sgRNA assignments:
3. Document all filtering decisions

### Data Processing
1. Normalization: Apply log1p(CPM) normalization
2. Compute highly variable genes (HVGs)
3. Optional: Regress out confounders (library size, cell cycle)

### Generalization Regimes
1. **Seen genes, unseen pairs**: Both constituent genes seen individually during training
2. **One unseen gene**: One gene never seen during training
3. **Two unseen genes**: Neither gene seen during training (hardest)

## Implementation Requirements

### Baseline Models
1. **Additive Linear Model**:
   - Fit: δ_ab = c1·δ_a + c2·δ_b + ε
   - Where δ represents the perturbation effect
   - Report R² and Pearson correlation

2. **Nearest Neighbors**:
   - Find doubles whose singles are most similar to query singles
   - Predict by weighted averaging

### Advanced Models
1. **Shallow MLP/ResMLP**:
   - Map [x_a, x_b] → x_ab
   - Use L2 or Huber loss
   - Include gene-wise scaling

2. **Interaction-aware Model**:
   - Include bilinear terms or cross-attention
   - Capture non-additive interactions

## Evaluation Metrics

### Primary Metrics
1. Gene-wise Pearson correlation (r)
2. R² between predicted and true mean profiles
3. Report both macro and micro averages

### Secondary Metrics
1. **Top-K DE overlap**: Jaccard@K for K∈{50, 100, 200}
2. **Pathway enrichment**: GSEA NES correlation
3. **Calibration**: Residual distribution analysis

### Statistical Significance
- Bootstrap confidence intervals across doubles and genes

## Deliverables

### Code & Environment
1. Python implementation with requirements.txt/env.yml
2. Config-driven runs (YAML/JSON)
3. Makefile for reproducibility

### Artifacts
1. Trained model weights
2. Training logs
3. Seeds for reproducibility

## Analysis Requirements

### Dataset-Specific Analysis
1. **Cross-dataset comparison**: Compare model performance across all 5 datasets
2. **Technology comparison**: CRISPRa vs CRISPRi vs Perturb-seq
3. **Cell type effects**: K562 vs RPE1 vs BMDCs
4. **Dataset size effects**: Performance vs number of perturbations

### Ablation Studies
1. Effect of single perturbation quality on prediction
2. Zero-shot generalization to unseen genes
3. Analysis of specific gene interactions (e.g., CBL/CNN1 synergy in Norman)
4. Transfer learning: Train on one dataset, test on another

### Error Analysis
1. Where models fail vs. succeed per dataset
2. Cases beyond linear additivity
3. Stratify results by perturbation effect size
4. Technology-specific error patterns