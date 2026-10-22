# Function Blocks Library

This directory contains example function blocks used during development of this early-stage research prototype. They can serve as templates, but may require adjustments for your data and package versions.

## Purpose

Function blocks stored here:
- Were exercised in the development Docker environment of the omicairn system
- Are documented with usage notes
- Include dependency specifications
- Are not guaranteed to be bug-free (this is an early research release)

## Directory Structure

```
function_blocks/
├── builtin/                     # Core system function blocks
│   ├── celltypist_annotation/  # Automated cell type annotation
│   ├── convert_anndata_to_sc_matrix/
│   ├── convert_sc_matrix_to_anndata/
│   ├── convert_sc_matrix_to_seuratobject/
│   └── convert_seurat_to_sc_matrix/
├── trajectory_analysis/         # Trajectory inference methods
│   └── scfates/                # scFates trajectory analysis
│       ├── code.py
│       ├── config.json
│       └── requirements.txt
└── scrnaq/                     # Single-cell RNA-seq analysis
    ├── dpt_paga/               # DPT + PAGA pseudotime
    ├── palantir/               # Palantir pseudotime
    ├── cellrank/               # CellRank trajectory
    └── scfates/                # scFates (copy for organization)
```

## Available Function Blocks

### Built-in Function Blocks

#### CellTypist Annotation (`builtin/celltypist_annotation/`)
- **Description**: Automated cell type annotation using pre-trained models
- **Key Features**:
  - Automatic model download handling
  - Supports multiple pre-trained models (Immune_All_Low, Immune_All_High, etc.)
  - Majority voting for robust predictions
  - Confidence scores for each prediction
  - Automatic data normalization if needed
- **Critical Notes**:
  - MUST call `celltypist.models.download_models()` before annotation
  - Data must be normalized and log-transformed
  - Results in `predictions.predicted_labels.predicted_labels` (double attribute)
- **Parameters**:
  - `model`: Model name (default: 'Immune_All_Low.pkl')
  - `majority_voting`: Enable majority voting (default: True)
  - `over_clustering`: Over-clustering method for fine-grained types (optional)
- **Outputs**: `celltypist_predicted`, `celltypist_majority`, `celltypist_conf` columns

#### Data Format Conversions
Located in `builtin/convert_*` - these handle data format conversions between Python and R.

### Trajectory Analysis

#### scFates (`trajectory_analysis/scfates/`)
- **Description**: Performs trajectory inference using scFates with correct API usage
- **Key Features**:
  - Uses `tl.curve` (linear principal curve; `tl.tree` is the branching alternative)
  - Handles graph initialization properly
  - Includes dependency constraints (numpy<1.24)
  - Generates trajectory plots
- **Parameters**:
  - `n_nodes`: Number of nodes for the principal graph (default: 10)
  - `use_rep`: Representation to use (default: "X_pca")
  - `device`: Computation device (default: "cpu")
  - `n_map`: Number of mappings for test_association (default: 100)
  - `spline_df`: Degrees of freedom for spline fitting (default: 5)

### Single-Cell RNA-seq Analysis (`scrnaq/`)

#### DPT + PAGA (`scrnaq/dpt_paga/`)
- **Description**: Diffusion Pseudotime with PAGA for trajectory inference
- **Key Features**:
  - Automatic preprocessing (PCA, neighbors, clustering) if missing
  - PAGA graph abstraction for trajectory structure
  - Diffusion map and pseudotime computation
  - Automatic or manual root cell selection
  - Multiple visualizations (PAGA graph, pseudotime on UMAP/diffmap)
- **Outputs**: `dpt_pseudotime` in obs, PAGA connectivity, CSV export

#### Palantir (`scrnaq/palantir/`)
- **Description**: Continuous pseudotime with branch probabilities
- **Key Features**:
  - Proper API usage (run_diffusion_maps, run_palantir)
  - Automatic start cell detection
  - Entropy computation for differentiation potential
  - Branch probability estimation
  - Terminal state identification
- **Outputs**: `palantir_pseudotime`, `palantir_entropy`, branch probabilities

#### CellRank (`scrnaq/cellrank/`)
- **Description**: Probabilistic fate mapping using Markov chains
- **Key Features**:
  - Supports connectivity and velocity kernels
  - Terminal state identification with GPCCA
  - Absorption probability computation
  - Lineage driver gene detection
  - Pseudotime from fate probabilities
- **Outputs**: Terminal states, fate probabilities, lineage drivers

#### scFates (`scrnaq/scfates/`)
- **Description**: Copy of trajectory_analysis/scfates for organizational purposes
- **Note**: Same functionality as above, included in scrnaq for completeness

## Usage

To use a function block from this library:

1. Copy the entire function block directory to your node's `function_block/` directory
2. Or reference the files individually:
   - Copy `code.py` to your node's `code.py`
   - Copy `requirements.txt` to your node's `requirements.txt`
   - Use `config.json` as a template for your node's configuration

Example:
```bash
# Copy entire scFates function block
cp -r function_blocks/trajectory_analysis/scfates/* test_outputs/TREEID/nodes/node_NODEID/function_block/
```

## Adding New Function Blocks

When adding new verified function blocks:

1. Create a category directory if it doesn't exist (e.g., `clustering/`, `visualization/`)
2. Create a subdirectory for your specific method
3. Include these files:
   - `code.py` or `code.r`: The function implementation
   - `requirements.txt`: All dependencies
   - `config.json`: Parameter definitions and documentation
4. Ensure the code follows the standard signature:
   - Python: `def run(path_dict, params):`
   - R: `run <- function(path_dict, params)`
5. Update this README with description and usage notes
6. Document any special considerations or known issues

## Organization Guidelines

- **builtin/**: Core system functionality (conversions, utilities)
- **trajectory_analysis/**: Trajectory inference methods (scFates, Palantir, etc.)
- **clustering/**: Clustering algorithms (future)
- **visualization/**: Plotting and visualization tools (future)
- **preprocessing/**: Data preprocessing steps (future)