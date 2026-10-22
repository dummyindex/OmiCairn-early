# Pseudotime Analysis Function Blocks Summary

This directory contains four example pseudotime analysis function blocks that ran successfully in the development Docker environment of this early-stage research prototype. They may need adjustments for other data or package versions.

## Available Methods

### 1. DPT + PAGA (`dpt_paga/`)
- **Description**: Diffusion Pseudotime with PAGA (Partition-based Graph Abstraction)
- **Key Features**:
  - Computes diffusion pseudotime using scanpy's dpt
  - Creates PAGA graph for trajectory visualization
- **Status**: ran in development Docker environment

### 2. Palantir (`palantir/`)
- **Description**: Palantir pseudotime and branch probabilities
- **Key Features**:
  - Determines multiscale diffusion space
  - Computes pseudotime and entropy
  - Estimates branch probabilities
- **Fixes Applied**:
  - Added `adata.obs_names_make_unique()` to handle duplicate cell names
  - Fixed multiscale space computation: `determine_multiscale_space(adata)`
  - Corrected diffusion map key: use 'DM_EigenVectors' instead of 'X_diffmap'
- **Status**: ran in development Docker environment

### 3. CellRank (`cellrank/`)
- **Description**: CellRank trajectory analysis using precomputed pseudotime
- **Key Features**:
  - Requires pseudotime as input (does not compute pseudotime)
  - Uses PseudotimeKernel to create directed transition matrices
  - Computes terminal/initial states and fate probabilities
  - Handles GPCCA fitting timeouts gracefully
- **Important**: CellRank uses pseudotime to direct the transition matrix, not to compute pseudotime
- **Status**: ran in development Docker environment

### 4. scFates (`scfates/`)
- **Description**: scFates trajectory analysis using ElPiGraph
- **Key Features**:
  - Fits principal curves through data
  - Uses ElPiGraph algorithm
  - Visualizes trajectory on UMAP
- **Fixes Applied**:
  - Corrected import: `import scFates as scf` (capital F)
  - Added PCA computation if missing
  - Made R-dependent test_association optional
  - Added UMAP computation for visualization
- **Status**: ran in development Docker environment

## Testing

Development tests for these blocks:

1. **Individual debug tests** in `tests/domain_fb/scrnaq/`:
   - `test_palantir_debug.py`
   - `test_cellrank_minimal.py`
   - `test_scfates_debug.py`

2. **Comprehensive unittest** in `test_pseudotime_unittest.py`:
   - Tests all methods in Docker containers
   - Verifies outputs and metadata
   - Generates summary reports

## Common Requirements

All methods require:
- Input: `_node_anndata.h5ad` in the input directory
- Output: `_node_anndata.h5ad` in the output directory
- Basic preprocessing (PCA, neighbors, UMAP/tSNE)

## Usage Example

```python
from job_executors.python_executor import PythonExecutor
from models import NewFunctionBlock, FunctionBlockType
from utils.docker_utils import DockerManager

# Load function block
with open("dpt_paga/code.py", 'r') as f:
    code = f.read()
    
with open("dpt_paga/requirements.txt", 'r') as f:
    requirements = f.read()

# Create function block
function_block = NewFunctionBlock(
    id="dpt-paga-1",
    name="dpt_paga_pseudotime",
    type=FunctionBlockType.PYTHON,
    description="DPT+PAGA pseudotime",
    code=code,
    requirements=requirements,
    parameters={
        "n_dcs": 10,
        "n_neighbors": 30,
        "min_group_size": 0.01
    }
)

# Execute
docker_manager = DockerManager()
executor = PythonExecutor(docker_manager)
result = executor.execute(
    function_block=function_block,
    input_data_path=input_dir,
    output_dir=output_dir,
    parameters=function_block.parameters
)
```

## Notes

- All methods add pseudotime information to `adata.obs`
- Visualization figures are saved to `{output_dir}/figures/`
- Additional results (CSV files) may be generated in the output directory
- Each method has specific parameter options - see individual `config.json` files