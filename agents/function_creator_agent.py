"""Agent responsible for creating new function blocks with proper implementation."""

import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from agents.base_agent import BaseAgent
from agents.agent_output_utils import AgentOutputLogger
from models import (
    NewFunctionBlock, FunctionBlockType, StaticConfig, Arg,
    InputSpecification, OutputSpecification, FileInfo, FileType,
    ExistingFunctionBlock, GenerationMode, AnalysisTree, AnalysisNode
)
from llm_service import OpenAIService
from utils import setup_logger

logger = setup_logger(__name__)


class FunctionCreatorAgent(BaseAgent):
    """Agent that creates or selects function blocks based on analysis requirements.
    
    This unified agent handles both:
    1. Creating new function blocks with code generation
    2. Selecting appropriate existing function blocks
    3. Deciding whether to create new or use existing blocks
    """
    
    def __init__(self, llm_service: OpenAIService, 
                 enable_domain_knowledge: bool = False,
                 domain_knowledge_domains: Optional[List[str]] = None,
                 llm_seed: Optional[int] = None,
                 enable_code_checker: bool = True,
                 log_llm_to_stdout: bool = False):
        """Initialize the function creator agent.
        
        Args:
            llm_service: The LLM service to use
            enable_domain_knowledge: Enable domain-specific knowledge injection
            domain_knowledge_domains: List of domain knowledge to inject
            llm_seed: Seed for LLM reproducibility (optional)
            enable_code_checker: Enable code quality checking after creation
            log_llm_to_stdout: Whether to log LLM interactions to stdout (default: False)
        """
        super().__init__("function_creator")
        self.llm_service = llm_service
        self.logger = logger
        self.enable_domain_knowledge = enable_domain_knowledge
        self.domain_knowledge_domains = domain_knowledge_domains or []
        self.llm_seed = llm_seed
        self.enable_code_checker = enable_code_checker
        self.log_llm_to_stdout = log_llm_to_stdout
        
        # Cache for last LLM interaction (for post-creation logging)
        self._last_llm_interaction = None
        
        # Initialize code checker if enabled
        self.code_checker = None
        if self.enable_code_checker:
            try:
                from agents.code_checker_agent import CodeCheckerAgent
                # Pass domain knowledge settings to code checker
                code_checker_domains = ["code_quality_best_practices"]
                if enable_domain_knowledge and domain_knowledge_domains:
                    # Add code quality to existing domains if not already present
                    if "code_quality_best_practices" not in domain_knowledge_domains:
                        code_checker_domains = domain_knowledge_domains + ["code_quality_best_practices"]
                    else:
                        code_checker_domains = domain_knowledge_domains
                
                self.code_checker = CodeCheckerAgent(
                    llm_service, 
                    llm_seed=llm_seed,
                    enable_domain_knowledge=enable_domain_knowledge,
                    domain_knowledge_domains=code_checker_domains
                )
                logger.info("Code checker enabled for function creator")
            except Exception as e:
                logger.warning(f"Failed to initialize code checker: {e}")
                self.enable_code_checker = False
        
        # Initialize domain knowledge system if enabled
        if self.enable_domain_knowledge:
            from domain_knowledge import get_knowledge_service, PromptInjector
            self.knowledge_service = get_knowledge_service()
            self.prompt_injector = PromptInjector(self.knowledge_service)
            logger.info(f"Domain knowledge enabled for function creator: {self.domain_knowledge_domains}")
    
    # Detailed documentation for function block implementation
    FUNCTION_BLOCK_DOCUMENTATION = """
# Function Block Implementation Guide - SIMPLIFIED FRAMEWORK

## Required Structure
Every function block MUST have a function named 'run' that takes path_dict and params:

```python
def run(path_dict, params):
    '''
    Main entry point for the function block.
    
    Args:
        path_dict: Dictionary containing paths:
            - input_dir: Input directory path
            - output_dir: Output directory path
        params: Dictionary of parameters for this block
    
    Returns:
        None (outputs are written to files)
    '''
    # Your implementation here
```

## CRITICAL INPUT/OUTPUT CONVENTIONS

### Input Data:
- Function blocks receive path_dict and params arguments
- Construct input path using path_dict["input_dir"]
- Be flexible with file formats - adapt to the task requirements

**For the FIRST/ROOT node only (reads original data):**
```python
import os

# Check what files are available in the input directory
input_files = os.listdir(path_dict["input_dir"])
print(f"Available input files: {input_files}")

# Choose and read appropriate input files based on your analysis needs
# Examples for different file types:

# For CSV files:
csv_files = [f for f in input_files if f.endswith('.csv')]
if csv_files:
    import pandas as pd
    df = pd.read_csv(os.path.join(path_dict["input_dir"], csv_files[0]))

# For data files specific to your analysis domain:
data_files = [f for f in input_files if f.endswith('.extension')]
if data_files:
    import your_data_library
    # Choose appropriate file based on context
    if len(data_files) == 1:
        # Single file - use it
        data_object = your_data_library.load_data(os.path.join(path_dict["input_dir"], data_files[0]))
    else:
        # Multiple files - choose based on your analysis needs
        # For example: look for specific patterns in filenames
        # processed_files = [f for f in data_files if 'processed' in f]
        # Or use the largest/most recent file
        # Or prompt user context to decide which file to use
        print(f"Found {len(data_files)} data files: {data_files}")
        # Choose based on your specific criteria
        chosen_file = data_files[0]  # Replace with your selection logic
        data_object = your_data_library.load_data(os.path.join(path_dict["input_dir"], chosen_file))

# For JSON files:
json_files = [f for f in input_files if f.endswith('.json')]
if json_files:
    import json
    # Similarly, choose appropriate JSON file based on context
    if len(json_files) == 1:
        with open(os.path.join(path_dict["input_dir"], json_files[0]), 'r') as f:
            data = json.load(f)
    else:
        # Multiple JSON files - select based on analysis needs
        print(f"Found {len(json_files)} JSON files: {json_files}")
        # Add your selection logic here
```


### Output Data:
- Construct output path using path_dict["output_dir"]
- Use descriptive naming for your output files
```python
# Save output data - use descriptive naming based on the file type and processing done
# Examples:

# For DataFrames:
df.to_csv(os.path.join(path_dict["output_dir"], "processed_data.csv"), index=False)

# For your data format:
data_library.save_data(data_object, os.path.join(path_dict["output_dir"], "processed_data.extension"))

# For JSON:
with open(os.path.join(path_dict["output_dir"], "results.json"), 'w') as f:
    json.dump(results, f)

print(f"Output saved to {output_file}")
```

### Additional Files:
- Figures: Save to `os.path.join(path_dict["output_dir"], "figures")`
- Metrics/Reports: Save to `path_dict["output_dir"]`

### Figure Saving for Analysis Libraries:
When using plotting functions, configure the figure directory properly:
```python
import your_plotting_library as plt_lib
from pathlib import Path

# Set figure directory - CRITICAL for saving plots
figures_dir = Path(path_dict["output_dir"]) / "figures"
figures_dir.mkdir(parents=True, exist_ok=True)
plt_lib.settings.figure_directory = figures_dir

# Now plots will save to the correct location
plt_lib.plot_embedding(data_object, color_by='clusters', save='_clusters.png', show=False)
# This saves to: figures_dir / 'embedding_clusters.png'
```
- Logs: Print to stdout (will be captured)

## R Function Block Structure

### R Function Signature:
```r
run <- function(path_dict, params) {
    # Function implementation
}
```

### R Input/Output Patterns:
```r
# Load required libraries
library(Seurat)

# Construct file paths
input_file <- file.path(path_dict$input_dir, "data_object.rds")
output_file <- file.path(path_dict$output_dir, "processed_object.rds")

# Read input
if (file.exists(input_file)) {
    data_obj <- readRDS(input_file)
} else {
    stop(paste("Input file not found:", input_file))
}

# Process data with actual R operations (implement specific analysis)
data_obj <- normalize_data(data_obj)
data_obj <- compute_metrics(data_obj)

# Save output
saveRDS(data_obj, output_file)
cat("Output saved to:", output_file, "\n")

# Create figures directory
figures_dir <- file.path(path_dict$output_dir, "figures")
dir.create(figures_dir, recursive = TRUE, showWarnings = FALSE)
```

### R Package Management:
**CRITICAL**: R function blocks use the same requirements field as Python:
- R packages are specified directly in the requirements field
- The system automatically generates install_packages.R from your requirements
- Format for R requirements:
  - CRAN packages: just the package name (e.g., "Seurat", "ggplot2")
  - Bioconductor packages: "Bioconductor::package_name" (e.g., "Bioconductor::SingleCellExperiment")
  - GitHub packages: "user/repo" format (e.g., "dynverse/princurve")
- Example R requirements:
  ```
  Seurat
  slingshot
  Bioconductor::SingleCellExperiment
  ggplot2
  ```

### Language Interoperability:
- Python blocks commonly work with .h5ad files (AnnData), R blocks with .rds files (Seurat)
- If you need to convert between formats, the orchestrator may suggest using builtin conversion blocks:
  - convert_anndata_to_sc_matrix (Python → shared format)
  - convert_sc_matrix_to_anndata (shared format → Python)
  - convert_seurat_to_sc_matrix (R → shared format)
  - convert_sc_matrix_to_seuratobject (shared format → R)
- Do NOT use rpy2 or reticulate for cross-language calls

## Directory Structure
- `path_dict["input_dir"]`: Input directory (read-only)
  - May contain various input files from previous nodes
  - Common patterns: .h5ad files for Python, .rds files for R
  - Check directory contents to find appropriate input files
- `path_dict["output_dir"]`: Output directory (write here)
  - Save your main output file with any descriptive name
  - `figures/`: Directory for plots
  - Other output files as needed

## Common Patterns

### 1. Data Loading Function Block
```python
def run(path_dict, params):
    import os
    import glob
    
    # List all available files in input directory
    input_files = os.listdir(path_dict["input_dir"])
    print(f"Available input files: {input_files}")
    
    # Find appropriate data file based on extension or content
    # Could be .h5ad, .csv, .txt, .rds, .json, or any other format
    data_files = [f for f in input_files if f.endswith(('.h5ad', '.csv', '.h5', '.mat', '.txt', '.json', '.parquet', '.feather'))]
    if not data_files:
        # If no common data formats found, just use the first file
        data_files = input_files
    
    if not data_files:
        raise FileNotFoundError("No input files found")
    
    # Use the first suitable file found
    input_file = os.path.join(path_dict["input_dir"], data_files[0])
    print(f"Using input file: {data_files[0]}")
    
    # Output can use convention or descriptive name
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    # Read input
    adata = sc.read_h5ad(input_file)
    
    # Get parameters with defaults
    min_genes = params.get('min_genes', 200)
    min_cells = params.get('min_cells', 3)
    
    # Apply filters
    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_genes(adata, min_cells=min_cells)
    
    print(f"Filtered to {adata.shape[0]} cells and {adata.shape[1]} genes")
    
    # Save output - REQUIRED
    adata.write(output_file)
    print(f"Output saved to {output_file}")
```

### 2. Clustering with Metrics
```python
def run(path_dict, params):
    import scanpy as sc
    import pandas as pd
    from sklearn import metrics
    import os
    import glob
    
    # List all available files in input directory
    input_files = os.listdir(path_dict["input_dir"])
    print(f"Available input files: {input_files}")
    
    # Find appropriate data file based on extension or content
    # Could be any data format for your analysis
    data_files = [f for f in input_files if f.endswith(('.bin', '.csv', '.h5', '.mat', '.txt', '.extension'))]
    if not data_files:
        # If no common data formats found, just use the first file
        data_files = input_files
    
    if not data_files:
        raise FileNotFoundError("No input files found")
    
    # Use the first suitable file found
    input_file = os.path.join(path_dict["input_dir"], data_files[0])
    print(f"Using input file: {data_files[0]}")
    
    # Output with descriptive name
    output_file = os.path.join(path_dict["output_dir"], "clustered_data.h5ad")
    
    # Read input
    adata = sc.read_h5ad(input_file)
    
    # Get parameters
    resolution = params.get('resolution', 1.0)
    ground_truth_key = params.get('ground_truth_key', 'cell_type')
    
    # Run clustering - choose appropriate method and library
    sc.tl.leiden(adata, resolution=resolution)
    
    # Calculate metrics if ground truth exists
    if ground_truth_key in adata.obs.columns:
        ari = metrics.adjusted_rand_score(
            adata.obs[ground_truth_key], 
            adata.obs['leiden']
        )
        adata.uns['clustering_metrics'] = {'ARI': ari}
        print(f"Clustering ARI: {ari:.3f}")
        
        # Save metrics to file
        metrics_df = pd.DataFrame({'metric': ['ARI'], 'value': [ari]})
        metrics_file = os.path.join(path_dict["output_dir"], 'clustering_metrics.csv')
        metrics_df.to_csv(metrics_file, index=False)
    
    # Save output
    adata.write(output_file)
    print(f"Output saved to {output_file}")
```

### 3. Common Scanpy Pitfalls to Avoid

**CRITICAL: Scanpy plotting API requirements:**
- `sc.pl.scatter`, `sc.pl.umap`, `sc.pl.pca` expect column names (strings), NOT numpy arrays or pandas Series
- The `color` parameter must be a string representing a column name in `.obs` or `.var`
- To save figures properly, always set `sc.settings.figdir` first
- For histograms, use matplotlib directly or sc.pl.violin/sc.pl.scatter with appropriate data

**CRITICAL: AnnData slicing issues:**
- When you slice an AnnData object (e.g., `adata[mask]`), the `.raw` attribute is NOT preserved
- NEVER use `sliced_adata.raw.X` - it will be None and cause AttributeError
- Use `sliced_adata.X` directly instead
- For root cell selection, use indices directly: `np.where(adata.obs['cluster'] == target)[0]`
**CRITICAL: DPT/Pseudotime specific issues:**
- DPT creates `adata.obs['dpt_pseudotime']`, NOT `adata.obs['dpt']`
- Always check if a computation result exists before trying to access it
- Don't try to load CSV files that haven't been created yet
- Don't use ellipsis (...) as placeholders - write complete working code
- For DPT, ALWAYS set `adata.uns['iroot']` BEFORE calling `sc.tl.dpt()`:
  ```python
  # REQUIRED before DPT:
  if 'iroot' not in adata.uns:
      # Prefer a user-given root (params) or a documented marker-based choice.
      # A random root changes the result: seed it, warn, and record it in outputs.
      rng = np.random.default_rng(params.get('seed', 0))
      adata.uns['iroot'] = int(rng.integers(adata.n_obs))
      print(f"WARNING: no root cell given; using seeded random root {adata.uns['iroot']}")
  sc.tl.dpt(adata)
  ```

**Incorrect (will fail):**
```python
# WRONG - passing Series/array instead of column name
labels = adata.obs['kmeans']  
sc.pl.umap(adata, color=labels, ...)  # ERROR!

# WRONG - passing numpy array from obsm
sc.pl.scatter(adata, x=adata.obsm['X_pca'][:, 0], ...)  # ERROR!
```

**Correct:**
```python
# RIGHT - pass column name as string
sc.pl.umap(adata, color='kmeans', ...)  

# RIGHT - for PCA visualization
sc.pl.pca(adata, color='leiden', ...)

# RIGHT - for histograms, use matplotlib directly
import matplotlib.pyplot as plt
plt.figure(figsize=(8, 6))
plt.hist(adata.obs['n_genes'], bins=30)
plt.xlabel('Number of Genes')
plt.ylabel('Number of Cells')
plt.title('Gene Count Distribution')
plt.savefig(os.path.join(figures_dir, 'gene_counts.png'))
plt.close()
# RIGHT - for root cell selection from a cluster
cluster_mask = adata.obs['leiden'] == target_cluster
cluster_indices = np.where(cluster_mask)[0]
if len(cluster_indices) == 0:
    raise ValueError(f"Root cluster {target_cluster!r} has no cells")
rng = np.random.default_rng(params.get('seed', 0))  # seeded for reproducibility
iroot = rng.choice(cluster_indices)
adata.uns['iroot'] = int(iroot)
```

### 4. Saving Figures
```python
def run(path_dict, params):
    import scanpy as sc
    import matplotlib.pyplot as plt
    from pathlib import Path
    import os
    import glob
    
    # List all available files in input directory
    input_files = os.listdir(path_dict["input_dir"])
    print(f"Available input files: {input_files}")
    
    # Find appropriate data file based on extension or content
    # Could be any data format for your analysis
    data_files = [f for f in input_files if f.endswith(('.bin', '.csv', '.h5', '.mat', '.txt', '.extension'))]
    if not data_files:
        # If no common data formats found, just use the first file
        data_files = input_files
    
    if not data_files:
        raise FileNotFoundError("No input files found")
    
    # Use the first suitable file found
    input_file = os.path.join(path_dict["input_dir"], data_files[0])
    print(f"Using input file: {data_files[0]}")
    
    # Output file
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    # Read input
    adata = sc.read_h5ad(input_file)
    
    # Create figures directory
    figures_dir = Path(path_dict["output_dir"]) / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    
    # Create and save UMAP plot
    if 'X_umap' in adata.obsm:
        sc.pl.umap(adata, color='leiden' if 'leiden' in adata.obs.columns else None, 
                   show=False, save='_clusters.png')
        print(f"Saved UMAP figure")
    
    # Save output
    adata.write(output_file)
    print(f"Output saved to {output_file}")
```

## Important Requirements
1. ALWAYS name the main function 'run' with path_dict and params arguments
2. params is passed directly as a dictionary - no need to load from file
3. Find input files by checking path_dict["input_dir"] contents
4. Save outputs to path_dict["output_dir"] with clear, descriptive names
5. Include all necessary imports inside the function
6. Use parameters from params dict with appropriate defaults
7. Print informative messages about what was done
8. Handle errors gracefully with try/except blocks
9. NO PLACEHOLDER CODE - Always provide complete, working implementations:
   - NO commented-out code like "# dtflow.run(adata) # TODO: implement"
   - NO fake column names like 'placeholder_column' or 'some_key'
   - If a method/package doesn't exist, raise a clear error; never substitute another method under the requested method's name (any fallback must be labeled as such in outputs and logs)
   - Every line of code must be functional and complete
9. ALWAYS create meaningful visualizations and save to os.path.join(path_dict["output_dir"], "figures"):
   - Quality control: histogram of gene counts, cell counts distribution
   - PCA: variance ratio plot, PCA scatter plots
   - UMAP/tSNE: embedding plots with different colors
   - Clustering: cluster visualization, silhouette scores, metrics
   - Use matplotlib.pyplot with Agg backend: plt.switch_backend('Agg')
   - Always close plots: plt.close() after saving
10. Check if input files exist before reading

## Accessing Files from Previous Nodes

Function blocks can access output files from previous nodes in the analysis tree using the `previous_nodes` interface:

### ⚠️ CRITICAL: ALWAYS USE DYNAMIC DISCOVERY PATTERN
**NEVER hardcode filenames or node indices!** Files in `node['files']` include the subdirectory prefix (e.g., 'outputs/data.h5ad').

### Python Usage:
```python
from function_block_runtime import previous_nodes  # CORRECT: Always use this import pattern
# NEVER use: import previous_nodes  # This is INCORRECT and will fail!

def run(path_dict, params):
    import scanpy as sc
    
    # ✅ CORRECT: Dynamic discovery pattern - ALWAYS USE THIS!
    nodes = previous_nodes.list()
    adata = None
    
    for node in nodes:
        # Files include 'outputs/' prefix - use them AS-IS
        h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
        if h5ad_files:
            # Pass the FULL path from node['files'] including 'outputs/' prefix
            path = previous_nodes.get_file_path(node['index'], h5ad_files[0])
            if path and path.exists():
                adata = sc.read_h5ad(path)
                print(f"Loaded h5ad data from node {node['index']}: {adata.shape}")
                break
    
    if adata is None:
        raise FileNotFoundError("No h5ad file found in previous nodes")
        
        # Look for CSV files in this node
        csv_files = [f for f in node['files'] if f.endswith('.csv')]
        if csv_files and metrics is None:
            csv_path = previous_nodes.get_file_path(node['index'], csv_files[0])
            if csv_path:
                import pandas as pd
                metrics = pd.read_csv(csv_path)
                print(f"Loaded CSV data from node {node['index']}: {metrics.shape}")
    
    # Get all files from nodes as needed
    for node in nodes:
        all_files = previous_nodes.get_all_files(node['index'])
        print(f"All files from node {node['index']}: {list(all_files.keys())[:5]}...")
    
    # Always handle the case where files might not exist
    if preprocessed_data is not None:
        print(f"Successfully loaded h5ad data: {preprocessed_data.shape}")
```

### Common Use Cases:
1. **Comparing Results**: Load clustering results from different methods
2. **Combining Analyses**: Merge results from parallel branches
3. **Retrieving Metadata**: Access QC metrics, gene lists, or parameters from earlier steps
4. **Quality Checks**: Compare current results with previous preprocessing steps

### Important Notes:
- Node indices are 1-based (node 1, node 2, etc.)
- Only ancestor nodes (in the same branch) are accessible
- Files are accessed by their relative path within the node's output directory
- The interface handles missing files gracefully - always check for None
- Common file formats (.h5ad, .csv, .json, .npy) are automatically parsed
"""

    SYSTEM_PROMPT = """You are an expert data analysis function block creator specializing in various computational data analysis tasks.

Your task is to create complete, working function blocks that follow the framework conventions for processing data.

⚠️ CRITICAL - NO PLACEHOLDER CODE:
- NEVER use placeholder code like "# Add your analysis here" or "# TODO: implement"
- NEVER use fake/placeholder column names like 'some_column' or 'placeholder_key'
- NEVER comment out the actual implementation expecting users to fill it in
- ALWAYS provide complete, working implementations
- If a package doesn't exist (e.g., DTFLOW), raise a clear error; never substitute another method under the requested method's name (any fallback must be clearly labeled as a fallback)

CRITICAL PRINCIPLES:
1. **FILE HANDLING - ALWAYS BE FLEXIBLE - DO NOT HARDCODE FILENAMES**: 
   - **READING INPUT FILES - CRITICAL**:
     * ⚠️ NEVER assume specific file types or names exist
     * ⚠️ ALWAYS check what's actually available in the input directory
     * ⚠️ Be flexible - adapt to whatever files and formats are present
     * Files can have ANY names and formats based on the analysis
     * If needed, you can access files from previous nodes using the previous_nodes interface
     * Remember: Files might be in subdirectories like previous_nodes/
   
   - **WRITING OUTPUT FILES** (FLEXIBLE APPROACH):
     * DO NOT hardcode '_node_anndata.h5ad' - this is just an OPTIONAL convention
     * Use descriptive names: filtered_cells.h5ad, normalized_data.h5ad, clustered_results.h5ad, etc.
     * ⚠️ CRITICAL: previous_nodes.get_file_path() returns a SINGLE Path object, NOT a list!
     * ❌ NEVER DO THIS: list(previous_nodes.get_file_path(...)) - this will cause TypeError: 'PosixPath' object is not iterable
     * ✅ CORRECT: path = previous_nodes.get_file_path(node_index, file_path) - returns one Path or None
     * Document your output filenames clearly for downstream nodes
     * Any clear, descriptive filename is better than a hardcoded convention
   
   - **MANDATORY CODE PATTERN - ALWAYS USE DYNAMIC DISCOVERY**:
     ```python
     # ⚠️ CRITICAL: NEVER hardcode node indices like 1, 2, 3 - they vary!
     # Files in node['files'] already include 'outputs/' prefix - use AS-IS!
     
     from pathlib import Path
     prev_nodes_dir = Path(path_dict['input_dir']) / 'previous_nodes'
     
     if prev_nodes_dir.exists():
         from function_block_runtime import previous_nodes
         
         # ✅ PATTERN 1: Find any h5ad file from most recent node
         nodes = previous_nodes.list()
         adata = None
         
         for node in reversed(nodes):  # Start from most recent
             h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
             if h5ad_files:
                 # Prefer files with 'outputs/' prefix
                 output_files = [f for f in h5ad_files if 'outputs/' in f]
                 target_file = output_files[0] if output_files else h5ad_files[0]
                 path = previous_nodes.get_file_path(node['index'], target_file)
                 if path and path.exists():
                     import scanpy as sc
                     adata = sc.read_h5ad(path)
                     break
         
         # ✅ PATTERN 2: Find specific file by name pattern
         for node in nodes:
             # Look for specific filename patterns
             if any('processed' in f for f in node['files']):
                 matching_files = [f for f in node['files'] if 'processed' in f and f.endswith('.h5ad')]
                 if matching_files:
                     path = previous_nodes.get_file_path(node['index'], matching_files[0])
                     if path and path.exists():
                         adata = sc.read_h5ad(path)
                         break
         
         if adata is None:
             raise FileNotFoundError("No h5ad file found in previous nodes")
     else:
         # Root node - direct file access
         input_path = Path(path_dict['input_dir'])
         adata = sc.read_h5ad(input_path / 'input_data.h5ad')
     ```
     
     ⚠️ CRITICAL: 
     - Files have subdirectory prefix: 'outputs/data.h5ad' NOT 'data.h5ad'
     - Use exact paths from parent's output description
     - Don't search - KNOW what file you need based on parent's outputs
     
     ## COMMON MISTAKES:
     
     ❌ WRONG: Hardcoding filenames without checking what's actually there
     # ❌ WRONG - Hardcoded indices assume specific tree structure
     # DON'T DO: path = previous_nodes.get_file_path(1, '_node_anndata.h5ad')  # BAD - hardcoded index!
     # DON'T DO: path = previous_nodes.get_file_path(2, 'data.h5ad')  # BAD - hardcoded index!
     
     ✅ CORRECT: ALWAYS use dynamic discovery with files from node['files']
     for node in nodes:
         for file in node['files']:  # These already have 'outputs/' prefix
             if file.endswith('.h5ad'):
                 path = previous_nodes.get_file_path(node['index'], file)
     
     ❌ WRONG: Wrapping get_file_path with list() - IT RETURNS ONE PATH, NOT A LIST!
     # DON'T DO: h5ad_files = list(previous_nodes.get_file_path(2, 'outputs/data.h5ad'))  # TypeError!
     
     ❌ WRONG: Using hardcoded node indices - DON'T DO THIS!
     # DON'T DO: file_path = previous_nodes.get_file_path(2, 'outputs/data.h5ad')  # Assumes node 2 exists!
     
     ✅ CORRECT: ALWAYS use dynamic discovery to find the right node
     nodes = previous_nodes.list()
     for node in nodes:
         if 'outputs/data.h5ad' in node['files']:
             file_path = previous_nodes.get_file_path(node['index'], 'outputs/data.h5ad')
             if file_path:
                 adata = sc.read_h5ad(file_path)
                 break
     ```

1.5. **INPUT/OUTPUT VALIDATION (AUTOMATIC)**: 
   The framework automatically validates function blocks before and after execution:
   - Pre-flight validation: Checks required input files and data structure
   - Post-execution validation: Verifies outputs match specifications
   - Define specifications in static_config to enable validation:
   ```json
   "input_specification": {
     "required_files": [],  # DO NOT hardcode '_node_anndata.h5ad' - specify by extension
     "data_requirements": {
       "min_samples": 100,
       "required_attributes": ["sample_type"],  # Required attributes
       "required_embeddings": ["primary_projection"]  # Required embeddings
     }
   },
   "output_specification": {
     "required_files": [],  # Specify output files based on what you create
     "data_requirements": {
       "required_attributes": ["trajectory_result"],  # New attributes added
       "required_embeddings": ["special_projection"]  # New embeddings added
     }
   }
   ```
   - Validation failures provide clear error messages to help debugging
2. **ONE TASK PER FUNCTION BLOCK**: Each function block must perform exactly ONE specific task
   - NEVER combine multiple steps like "filter AND normalize AND log transform" in one block
   - Each distinct operation (filter, normalize, log1p, PCA, UMAP, etc.) must be its own block
   - If the user lists steps as "1. First step... 2. Second step... 3. Third step...", create SEPARATE blocks
3. **MODULAR WORKFLOW**: Complex requests must be broken into multiple sequential nodes
4. **PROPER SEQUENCING**: Ensure correct order of operations (e.g., normalize before PCA, PCA before clustering)
4. **LANGUAGE DETECTION**: 
   - Identify whether the requested tool/package is R or Python based
   - R packages: Seurat, Monocle3, Slingshot, scater, etc.
   - Python packages: various analysis libraries based on your domain
   - If user mentions "(R)" or "(Python)", respect that language choice
   - Set the "type" field to "r" or "python" accordingly
5. **PREPROCESSING REQUIREMENTS**: Many analysis methods require preprocessing:
   - Pseudotime methods (DPT, PAGA) need: normalization, log transform, highly variable genes, PCA, neighbors
   - Clustering needs: normalization, scaling, PCA, neighbors
   - UMAP/tSNE need: PCA or highly variable genes
6. **DATA VERIFICATION**: Always check if required data exists before using it:
   - Check for required columns in adata.obs before accessing
   - Check for embeddings (X_pca, X_umap) in adata.obsm before using
   - Verify computation results exist before trying to access them
7. **COMMON PLOTTING MISTAKES**: 
   - sc.pl.umap(adata, color='X') requires X to be in adata.obs (cell-level), NOT adata.var
   - NEVER use: sc.pl.umap(adata, color='highly_variable') - this will fail!
   - 'highly_variable' is a gene attribute (adata.var), not cell attribute
   - For initial plots, omit color or use: sc.pl.umap(adata, show=False, save='_umap.png')
   - Valid color options: sample-level attributes like 'clusters', 'sample_type', etc.


LANGUAGE SUPPORT:
- You can create both Python and R function blocks
- Python blocks commonly process AnnData objects (but can handle any format)
- R blocks commonly process Seurat objects (but can handle any format)
- If format conversion is needed, the orchestrator may suggest using builtin conversion function blocks
- Do NOT use rpy2 or reticulate for language interoperability

CRITICAL REQUIREMENTS FOR PYTHON:
1. Function signature: def run(path_dict, params)
   NEVER add previous_nodes as a parameter: def run(path_dict, params, previous_nodes) # WRONG!
   The previous_nodes is imported, not passed as parameter
2. **IMPORT ALL MODULES**: Your function MUST import ALL modules it uses, including:
   - Standard library modules: import os, import json, import glob, import sys
   - Data science packages: import numpy as np, import pandas as pd
   - Specialized packages: import scanpy as sc, import matplotlib.pyplot as plt
   - NEVER use a module without importing it first (e.g., using json.load() requires import json)
   - The run() function must be completely self-contained with all necessary imports
3. Input/output paths use path_dict["input_dir"] and path_dict["output_dir"]
4. **FLEXIBLY** read input files based on what's actually available:
   - ALWAYS check the available_files list provided in the input_context
   - Adapt to whatever files are present - don't assume file types
   - Files can have ANY names and ANY extensions
   - Let the task determine what files to read
4. **OUTPUT** can use ANY filename that makes sense for your task
5. Create figures in "figures" subdirectory
6. Handle parameters appropriately from params argument
7. Return the processed adata object
8. NEVER use placeholders like ... or pass - write complete working code
9. NEVER try to read files that don't exist (e.g., CSV files from other methods)
10. For complex requests with multiple methods, focus on ONE method per node
11. IMPORT SYNTAX for common packages:
    - `import package_a` (NOT `from package_a import package_a`)
    - `import PackageB as pb` (NOT `from PackageB import PackageB`)
    - `import package_c as pc` (NOT `from package_c import package_c`)
    - Check package docs if unsure about import syntax

CRITICAL REQUIREMENTS FOR R:
1. Function signature: run <- function(path_dict, params)
2. Input/output paths use path_dict$input_dir and path_dict$output_dir
3. Read input data object from appropriate file format
4. Save output data object to appropriate file format
5. Create figures in "figures" subdirectory
6. Handle parameters appropriately from params list
7. Return the processed Seurat object
8. **PACKAGE REQUIREMENTS**: List R packages in requirements field (NOT requirements.txt):
   - CRAN packages: just package name (e.g., "Seurat")
   - Bioconductor: "Bioconductor::package_name"
   - GitHub: "user/repo" format

IMPORTANT CODING GUIDELINES:
- Use proper string formatting - avoid complex f-strings with nested quotes/brackets
- For complex paths, use variables: figures_dir = Path(path_dict["output_dir"]) / "figures"
- Check if required data exists before using it (e.g., check for 'X_pca' before using it)
- Always create the figures directory before saving figures to it
- Handle missing ground truth data gracefully with informative messages

You are experienced with bioinformatics libraries and will create appropriate implementations based on the task requirements.

Always ensure your code is production-ready with proper error handling, informative output, and meaningful visualizations."""
    
    def process(self, context: Dict[str, Any]) -> Optional[NewFunctionBlock]:
        """Create a new function block based on requirements.
        
        Required context keys:
            - task_description: str - What the function should do
            - parent_output: Optional[Dict] - Output from parent node
            - user_request: str - Original user request
            - generation_mode: str - Generation mode
            
        Optional context keys:
            - input_specification: InputSpecification - Required input files
            - output_specification: OutputSpecification - Expected outputs
            - parameters: Dict - Default parameters
            - node_dir: Path - Node directory for logging (nodes/node_xxx)
            
        Returns:
            NewFunctionBlock or None if creation fails
        """
        self.validate_context(context, ['task_description', 'user_request'])
        
        if not self.llm_service:
            self.logger.error("No LLM service available for function creation")
            return None
        
        # Initialize agent logger if node_dir is provided
        agent_logger = None
        if 'node_dir' in context:
            # This is node-specific logging
            agent_logger = AgentOutputLogger(context['node_dir'], 'function_creator')
        
        try:
            # Build the prompt
            prompt = self._build_creation_prompt(context)
            
            # Prepare system prompt with domain knowledge if enabled
            system_prompt = self.SYSTEM_PROMPT
            if self.enable_domain_knowledge and self.prompt_injector:
                system_prompt = self.prompt_injector.inject_domain_knowledge(
                    system_prompt, self.domain_knowledge_domains
                )
                logger.info(f"Injected domain knowledge into function creator prompt")
            
            # Create messages for LLM
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self.FUNCTION_BLOCK_DOCUMENTATION},
                {"role": "user", "content": prompt}
            ]
            
            # Define response schema for structured JSON output
            schema = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                        "function_block": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string", "description": "Function block name (snake_case)"},
                                "description": {"type": "string", "description": "Brief description"},
                                "code": {"type": "string", "description": "Complete Python/R code with function signature: Python: def run(path_dict, params) or R: run <- function(path_dict, params)"},
                                "requirements": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "CRITICAL: List ALL external packages your code imports! For Python: pip packages like scanpy, pandas, numpy, matplotlib, palantir, scfates, cellrank (NOT built-in modules like os/sys). For R: package names (Seurat), Bioconductor::package, or user/repo format. Missing packages = runtime failure!"
                                },
                                "output_description": {
                                    "type": "string",
                                    "description": "REQUIRED: Describe what this node produces - data modifications, files created, plots generated, new columns added. Helps downstream nodes understand available data."
                                },
                                "parameters": {
                                    "type": "string",
                                    "description": "Default parameter values as JSON string (e.g., '{\"key1\": \"value1\", \"key2\": 42}')"
                                },
                                "type": {
                                    "type": "string",
                                    "enum": ["python", "r"],
                                    "description": "Language type of the function block - 'python' or 'r'"
                                },
                                "static_config": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "args": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "additionalProperties": False,
                                                "properties": {
                                                    "name": {"type": "string"},
                                                    "value_type": {"type": "string", "enum": ["int", "float", "str", "bool", "list", "dict"]},
                                                    "description": {"type": "string"},
                                                    "optional": {"type": "boolean"},
                                                    "default_value": {"type": "string", "description": "Default value as string"}
                                                },
                                                "required": ["name", "value_type", "description", "optional", "default_value"]
                                            }
                                        },
                                        "description": {"type": "string"},
                                        "tag": {"type": "string", "enum": ["quality_control", "normalization", "clustering", "visualization", "analysis", "integration"]}
                                    },
                                    "required": ["args", "description", "tag"]
                                }
                            },
                            "required": ["name", "description", "code", "requirements", "output_description", "parameters", "type", "static_config"]
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Explanation of the approach and implementation choices"
                        }
                },
                "required": ["function_block", "reasoning"]
            }
            
            # Prepare LLM input for logging
            llm_input = {
                'messages': messages,
                'schema': schema,
                'temperature': 0.3,
                'max_tokens': 4000,
                'model': self.llm_service.model,
                'timestamp': datetime.now().isoformat()
            }
            
            # Call LLM
            self.logger.info(f"Creating function block with {self.llm_service.model}")
            
            # Log LLM input to stdout if enabled
            if self.log_llm_to_stdout:
                self.logger.info("\n" + "="*80)
                self.logger.info("FUNCTION CREATOR LLM INPUT:")
                self.logger.info(f"Model: {self.llm_service.model}")
                self.logger.info(f"Temperature: 0.3")
                self.logger.info(f"System prompt length: {len(self.SYSTEM_PROMPT)} chars")
                self.logger.info(f"User prompt length: {len(prompt)} chars")
                self.logger.info("\n--- SYSTEM PROMPT ---")
                self.logger.info(self.SYSTEM_PROMPT)
                self.logger.info("\n--- USER PROMPT ---")
                self.logger.info(prompt)
                self.logger.info("\n--- END OF PROMPTS ---")
                self.logger.info("="*80 + "\n")
            
            try:
                # GPT-5 models need higher token limits for complex schemas due to reasoning tokens
                max_tokens = 6000 if self.llm_service.model.startswith('gpt-5') else 4000
                
                result = self.llm_service.chat_completion_json(
                    messages=messages,
                    json_schema=schema,
                    temperature=0.3,
                    max_tokens=max_tokens,
                    seed=self.llm_seed
                )
                self.logger.debug(f"LLM response type: {type(result)}")
                self.logger.debug(f"LLM response: {result}")
                
                # Log LLM output to stdout if enabled
                if self.log_llm_to_stdout:
                    self.logger.info("\n" + "="*80)
                    self.logger.info("FUNCTION CREATOR LLM OUTPUT:")
                    self.logger.info(f"Response type: {type(result)}")
                    self.logger.info("\n--- FULL LLM RESPONSE ---")
                    self.logger.info(json.dumps(result, indent=2))
                    self.logger.info("\n--- END OF RESPONSE ---")
                    self.logger.info("="*80 + "\n")
            except Exception as e:
                self.logger.error(f"Error calling LLM: {e}")
                # Return None instead of raising to allow graceful failure
                if agent_logger:
                    agent_logger.log_llm_interaction(
                        task_type='create_function',
                        llm_input=llm_input,
                        llm_output=None,
                        error=str(e),
                        metadata={'context': context}
                    )
                return None
            
            # Extract function_block from nested structure first
            fb_data = result.get('function_block', result)  # Handle both nested and flat formats
            
            # Cache LLM interaction data for later use (after node is created)
            self._last_llm_interaction = {
                "timestamp": datetime.now().isoformat(),
                "model": self.llm_service.model,
                "input": {
                    "specification": {
                        "name": context.get('function_name', ''),
                        "description": context.get('description', ''),
                        "task": context.get('task_description', '')
                    },
                    "input_context": context.get('input_context', {}),
                    "full_context": context,
                    "raw_messages": messages,  # Full raw messages sent to LLM
                    "json_schema": schema,     # The schema used for structured output
                    "llm_parameters": {
                        "temperature": 0.3,
                        "max_tokens": max_tokens,
                        "model": self.llm_service.model,
                        "seed": self.llm_seed
                    },
                    "system_prompt": system_prompt  # Save system prompt separately
                },
                "output": {
                    "success": True,
                    "function_block": fb_data,
                    "raw_response": result  # Full raw response from LLM
                }
            }
            
            # Log LLM interaction if agent_logger available (standard compatibility)
            if agent_logger:
                agent_logger.log_llm_interaction(
                    task_type='create_function',
                    llm_input=llm_input,
                    llm_output=result,
                    metadata={
                        'task_description': context.get('task_description'),
                        'parent_output': context.get('parent_output')
                    }
                )
            
            # Convert to NewFunctionBlock
            try:
                function_block = self._create_function_block(fb_data, context)
            except Exception as e:
                self.logger.error(f"Error in _create_function_block: {e}")
                self.logger.error(f"fb_data: {fb_data}")
                raise
            
            # Save function block code version if agent_logger available
            if function_block and agent_logger:
                agent_logger.save_function_block_versions(
                    original_code=function_block.code,
                    fixed_code=None,
                    version=1
                )
            
            return function_block
            
        except Exception as e:
            self.logger.error(f"Error creating function block: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Log error if agent_logger available
            if agent_logger:
                agent_logger.log_llm_interaction(
                    task_type='create_function',
                    llm_input=llm_input if 'llm_input' in locals() else None,
                    llm_output=None,
                    error=str(e),
                    metadata={'context': context}
                )
            
            return None
    
    def _build_creation_prompt(self, context: Dict[str, Any]) -> str:
        """Build prompt for function block creation."""
        parts = []
        
        parts.append("## Task")
        parts.append(f"Create a function block for: {context['task_description']}")
        
        parts.append("\n## Context")
        parts.append(f"User Request: {context['user_request']}")
        
        # Add node position information
        parts.append("\n**IMPORTANT FILE CONVENTIONS FOR DATA ANALYSIS WORKFLOW**:")
        parts.append("This is a flexible data analysis pipeline that can handle various file formats:")
        parts.append("")
        parts.append("## FLEXIBLE File Handling:")
        parts.append("- INPUT: Check available_files list and adapt to whatever files are present")
        parts.append("- OUTPUT: Can use '_node_anndata.h5ad' (convention) OR descriptive names")
        parts.append("- Never hardcode input filenames - be adaptive!")
        parts.append("")
        parts.append("## Input Discovery Pattern:")
        parts.append("```python")
        parts.append("# First check if you have previous nodes")
        parts.append("prev_nodes_dir = os.path.join(path_dict['input_dir'], 'previous_nodes')")
        parts.append("if os.path.exists(prev_nodes_dir):")
        parts.append("    # Use previous_nodes interface - files are NOT directly in input_dir!")
        parts.append("    from function_block_runtime import previous_nodes")
        parts.append("    # See MANDATORY CODE PATTERN above for full example")
        parts.append("else:")
        parts.append("    # Root node - files are directly in input_dir")
        parts.append("    input_files = os.listdir(path_dict['input_dir'])")
        parts.append("    print(f'Available files: {input_files}')")
        parts.append("```")
        parts.append("")
        parts.append("## Output Flexibility:")
        parts.append("- Use descriptive names based on your output: 'results.csv', 'processed_data.json', etc.")
        parts.append("- For H5AD files, you can use '_node_anndata.h5ad' convention or descriptive names")
        parts.append("- ⚠️ CRITICAL: previous_nodes.get_file_path() returns ONE Path object, NOT a list!")
        parts.append("- ❌ NEVER: list(previous_nodes.get_file_path(...)) - causes TypeError!")
        parts.append("- ✅ CORRECT: path = previous_nodes.get_file_path(index, 'outputs/file.h5ad')")
        parts.append("- Document your output files in output_description")
        
        # Add input context if available
        if 'input_context' in context:
            input_ctx = context['input_context']
            
            # Add previous nodes information if available
            if input_ctx.get('previous_nodes'):
                prev_nodes = input_ctx['previous_nodes']
                parts.append("\n## Previous Nodes Available")
                parts.append(f"You have access to outputs from {prev_nodes['count']} previous nodes in the analysis tree.")
                parts.append("\n### Available Nodes and Files:")
                parts.append(prev_nodes['access_info'])
                
                # Add runtime file structure if available
                if prev_nodes.get('runtime_file_structure'):
                    parts.append("\n### Actual Runtime Files (from execution metadata):")
                    for idx, runtime_info in prev_nodes['runtime_file_structure'].items():
                        parts.append(f"\nNode {idx}:")
                        if runtime_info.get('outputs'):
                            parts.append(f"  Output files: {', '.join(runtime_info['outputs'])}")
                        if runtime_info.get('figures'):
                            parts.append(f"  Figure files: {', '.join(runtime_info['figures'])}")
                
                parts.append("\n### How to Access Previous Nodes' Files:")
                parts.append(prev_nodes['python_interface'])
                parts.append("\nIMPORTANT: Use the PreviousNodesAccess interface when you need data from earlier steps in the analysis pipeline.")
            
            parts.append("\n## Input Directory Structure")
            
            # Handle root nodes
            if input_ctx.get('available_files') and not input_ctx.get('previous_nodes'):
                parts.append("Available files in input directory:")
                for file in input_ctx['available_files']:
                    parts.append(f"  - {file}")
            
            # Handle nodes with parent
            if input_ctx.get('parent_output_files'):
                parts.append("⚠️ IMPORTANT: The parent node produced these files:")
                for file in input_ctx['parent_output_files']:
                    parts.append(f"  - {file}")
                    
                # Add detailed file info if available
                if input_ctx.get('parent_output_files_detail'):
                    parts.append("\nDetailed file information:")
                    for file_info in input_ctx['parent_output_files_detail']:
                        parts.append(f"  - {file_info['name']} ({file_info['type']}, {file_info['size']} bytes)")
                        if file_info.get('data_structure'):
                            ds = file_info['data_structure']
                            if 'shape' in ds:
                                parts.append(f"    Shape: {ds['shape']}")
                            if 'obs_columns' in ds:
                                parts.append(f"    Obs columns: {', '.join(ds['obs_columns'][:5])}")
                                if len(ds['obs_columns']) > 5:
                                    parts.append(f"    ... and {len(ds['obs_columns']) - 5} more columns")
                
                parts.append("\nThese files are NOT directly in your input_dir!")
                parts.append("They will be staged in: input/previous_nodes/node_1/outputs/")
                parts.append("Access them using the previous_nodes interface as shown in MANDATORY CODE PATTERN above.")
            
            # Show expected structure
            if input_ctx.get('expected_input_structure'):
                parts.append("\nExpected input directory structure after staging:")
                parts.append("```")
                parts.append(input_ctx['expected_input_structure'])
                parts.append("```")
            
            # Show actual tree if available
            if input_ctx.get('directory_tree'):
                parts.append("\nDirectory tree:")
                parts.append(input_ctx['directory_tree'])
            if input_ctx.get('is_root_node'):
                parts.append("\nThis is a ROOT node - input files have their original names")
                parts.append("Check for files based on their extensions and content, not specific names")
            if input_ctx.get('parent_node_name'):
                parts.append(f"\nInput comes from: {input_ctx['parent_node_name']}")
                parts.append("⚠️ DO NOT assume the parent saved as '_node_anndata.h5ad' - CHECK THE ACTUAL FILES!")
                parts.append("⚠️ get_file_path() returns ONE Path, NOT a list! NEVER wrap with list()!")

                # Add parent's output description if available
                if input_ctx.get('parent_output_description'):
                    parts.append("\n## Parent Node Output Description:")
                    parts.append(input_ctx['parent_output_description'])
                    parts.append("Use this information to understand what data and columns are available for your processing.")

                # Add original input directory tree for child nodes
                if input_ctx.get('original_input_directory_tree'):
                    parts.append("\n## Original Input Directory Structure:")
                    parts.append("The original input directory (used by the root node) has this structure:")
                    parts.append(input_ctx['original_input_directory_tree'])
                    if input_ctx.get('original_input_path'):
                        parts.append(f"\nOriginal input path: {input_ctx['original_input_path']}")
                    parts.append("\nUse this to understand the complete input data organization, especially for multi-file datasets or subdirectories.")
                    
            if input_ctx.get('parent_data_structure'):
                parts.append("\n## Available Data from Parent:")
                data_struct = input_ctx['parent_data_structure']
                if data_struct.get('shape'):
                    parts.append(f"Data shape: {data_struct['shape']}")
                if data_struct.get('obs_columns'):
                    parts.append(f"Observation/row metadata columns: {', '.join(data_struct['obs_columns'])}")
                if data_struct.get('var_columns'):
                    parts.append(f"Variable/column metadata columns: {', '.join(data_struct['var_columns'])}")
                if data_struct.get('obsm_keys'):
                    parts.append(f"Observation embeddings/matrices: {', '.join(data_struct['obsm_keys'])}")
                if data_struct.get('varm_keys'):
                    parts.append(f"Variable embeddings/matrices: {', '.join(data_struct['varm_keys'])}")
                if data_struct.get('uns_keys'):
                    parts.append(f"Unstructured metadata: {', '.join(data_struct['uns_keys'])}")
        
        # Add language detection hints
        parts.append("\n## Language Detection")
        user_request_lower = context['user_request'].lower()
        if "(r)" in user_request_lower or any(pkg in user_request_lower for pkg in ["package_e", "package_f", "r_library_1", "r_library_2"]):
            parts.append("**Note**: This request mentions R-specific packages/tools. Create an R function block with type='r'.")
        elif "(python)" in user_request_lower or any(pkg in user_request_lower for pkg in ["package_a", "package_b", "package_c", "python_lib"]):
            parts.append("**Note**: This request mentions Python-specific packages/tools. Create a Python function block with type='python'.")
        else:
            parts.append("Determine the appropriate language (Python or R) based on the requested tools/packages.")
        
        # Add parent output structure if available
        if 'parent_output_structure' in context:
            parts.append("\n## Input Data Structure (from previous processing step)")
            parent_struct = context['parent_output_structure']
            parts.append(f"Data shape: {parent_struct.get('shape', 'Unknown')}")
            
            if parent_struct.get('obs_columns'):
                parts.append(f"Available observation columns: {', '.join(parent_struct['obs_columns'])}")
            
            if parent_struct.get('obsm_keys'):
                parts.append(f"Available embeddings: {', '.join(parent_struct['obsm_keys'])}")
            
            if parent_struct.get('uns_keys'):
                parts.append(f"Available unstructured data: {', '.join(parent_struct['uns_keys'])}")
        
        if 'parent_output' in context:
            parts.append(f"\nParent Node Output: {context['parent_output']}")
        
        if 'input_specification' in context:
            spec = context['input_specification']
            parts.append("\n## Required Input Files")
            for file_info in spec.required_files:
                parts.append(f"- {file_info['name']}: {file_info['description']}")
        
        if 'parameters' in context:
            parts.append("\n## Suggested Parameters")
            for key, value in context['parameters'].items():
                parts.append(f"- {key}: {value}")
        
        parts.append("\n## Function Structure")
        parts.append("Your function should:")
        parts.append("1. Define function with signature: def run(path_dict, params)")
        parts.append("2. Read input data from path_dict['input_dir']")
        parts.append("3. Process the data according to the task")
        parts.append("4. Save outputs to path_dict['output_dir']")
        parts.append("5. Create visualizations if appropriate for this specific task")
        parts.append("6. Print informative messages about the processing")
        parts.append("7. Return the processed data")
        
        parts.append("\n## Output Description (REQUIRED)")
        parts.append("Provide a clear description of what this node produces:")
        parts.append("- What data is added/modified in the AnnData object?")
        parts.append("- What files are created (besides _node_anndata.h5ad)?")
        parts.append("- What figures/plots are generated?")
        parts.append("- What new columns/embeddings/metadata are added?")
        parts.append("This helps downstream nodes understand available data.")
        parts.append("")
        parts.append("Example output_description:")
        parts.append("'This node performs Leiden clustering and adds cluster labels to adata.obs[\"leiden\"]. '")
        parts.append("'It also generates a UMAP plot colored by clusters saved as umap_clusters.png.'")
        
        parts.append("\n## Parameter Handling")
        parts.append("The params argument may contain nested dictionaries with metadata.")
        parts.append("To extract parameter values safely, define and use this helper function:")
        parts.append("```python")
        parts.append("def get_param(params, key, default):")
        parts.append("    val = params.get(key, default)")
        parts.append("    if isinstance(val, dict) and 'default_value' in val:")
        parts.append("        return val.get('default_value', default)")
        parts.append("    return val if val is not None else default")
        parts.append("```")
        parts.append("Then use it like: min_genes = get_param(params, 'min_genes', 200)")
        
        # Critical dependency management section
        dependency_section = f"""
## Requirements - CRITICAL DEPENDENCY MANAGEMENT
**EXTREMELY IMPORTANT**: List ALL external packages your code uses!
Missing packages = runtime failure = user frustration

### Python Requirements Rules:
1. List ALL external packages that need pip install
2. Do NOT include built-in modules (os, sys, json, etc.)
3. ALWAYS include these core packages when used:
   - domain-specific analysis libraries
   - pandas (for dataframes)
   - numpy (for arrays)
   - matplotlib (for plotting)
   - seaborn (for advanced plots)
   - scipy (for scientific computing)
   - scikit-learn or sklearn (for ML algorithms)

## DOMAIN-SPECIFIC PACKAGE KNOWLEDGE

### 1. Analysis Method Packages
#### Package Names (CRITICAL - exact capitalization):
- **Package A**: `pip install package-a` → `import package_a`
- **Package B**: `pip install packageb` → `import PackageB` (NOTE: capital letters) 
- **Package C**: `pip install package-c` → `import package_c as pc`
- **Method X**: Included in main library → `library.method.x()`
- **Method Y**: Included in main library → `library.method.y()`
- **Package D**: May need GitHub install
- **Package E**: R only → `library(packageE)`
- **Package F**: R only → `library(packageF)`

#### Correct API Usage (CRITICAL - avoid common errors):

**Package A:**
```python
import package_a
# CORRECT - use correct method name:
results = package_a.analyze_data(data_object, start_point=reference_point)
# WRONG - package_a.package_a() doesn't exist!
```

**Package B (COMPLETE WORKING EXAMPLE):**
```python
# IMPORTANT: Import with correct capitalization
import PackageB as pb

# Ensure prerequisites
if 'primary_embedding' not in data_object.embeddings:
    analysis_lib.compute_embedding(data_object, n_components=50)
if 'special_embedding' not in data_object.embeddings:
    analysis_lib.build_graph(data_object, n_neighbors=30)
    analysis_lib.compute_special_embedding(data_object)

# Run main analysis
pb.methods.analyze(data_object, method='advanced', seed=42)

# Extract results if available  
if 'segment' in data_object.attributes and 'position' in data_object.attributes:
    data_object.results['analysis_output'] = data_object.attributes['position']
    
# If the method did not produce its outputs, fail loudly - never substitute another quantity
if 'analysis_output' not in data_object.results:
    raise RuntimeError("PackageB did not produce 'segment'/'position'; analysis failed")
```

**Package C:**
```python
import package_c as pc
# Compute transition matrix
pc.compute.transition_matrix(data_object, weight_parameter=0.2)
# Find terminal states
pc.analyze.terminal_states(data_object, cluster_key='groups')
# Compute probabilities
pc.compute.probabilities(data_object)
```

#### CRITICAL PLOTTING API KNOWLEDGE:

**❌ WRONG - These functions DO NOT exist in most libraries:**
```python
# These will cause AttributeError:
lib.plot.hist()          # Often DOES NOT EXIST! 
lib.plot.histogram()      # Often DOES NOT EXIST!
lib.plot.plot()           # Often DOES NOT EXIST!
```

**✅ CORRECT - Use matplotlib for histograms and basic plots:**
```python
import matplotlib.pyplot as plt
import numpy as np

# For histograms - use matplotlib:
plt.hist(data_object.values.sum(axis=1), bins=50)
plt.xlabel('Total values')
plt.ylabel('Number of samples') 
plt.title('Value Distribution')
plt.savefig('histogram.png')
plt.close()

# For any custom plotting - use matplotlib:
plt.scatter(data_object.embeddings['projection'][:, 0], data_object.embeddings['projection'][:, 1])
plt.xlabel('Dimension 1')
plt.ylabel('Dimension 2')
plt.savefig('projection_scatter.png')
plt.close()
```

**✅ CORRECT - Common plotting functions in analysis libraries:**
```python
# These typically exist in plotting libraries:
plot_lib.embedding(data_object, color='groups', save='_embedding_groups.png', show=False)
plot_lib.variance_ratio(data_object, log=True, save='_variance.png', show=False)  
plot_lib.top_features(data_object, n_top=20, save='_top_features.png', show=False)
plot_lib.distribution(data_object, ['feature_1', 'feature_2'], save='_distribution.png', show=False)
```

**PLOTTING TROUBLESHOOTING RULES:**
1. If you need a histogram → Use `plt.hist()`, NOT library-specific histogram functions
2. If you need custom plots → Use matplotlib directly  
3. If using library plots → Always set `show=False` and use `save` parameter
4. Always call `plt.close()` after matplotlib plots to free memory

#### Package-Specific Requirements:
- **Package A**: Requires base packages (main_library, numpy, pandas)
- **Package B**: Requires numpy, pandas, scipy
- **Package C**: Requires additional_library for advanced features

### 2. Clustering Packages
- **Method 1**: `pip install clustering-alg1` → `lib.cluster.method1()`
- **Method 2**: Included in main library → `lib.cluster.method2()`
- **Method 3**: `pip install ClusterMethod3` → `import clustermethod3`

### 3. Visualization Packages  
- **plotly**: `pip install plotly` → `import plotly`
- **altair**: `pip install altair` → `import altair as alt`
- **holoviews**: `pip install holoviews` → `import holoviews as hv`

### Common Import Name Mismatches:
- `pip install scikit-learn` → `import sklearn`
- `pip install python-igraph` → `import igraph`
- `pip install PhenoGraph` → `import phenograph`
- `pip install leidenalg` → `import leidenalg`

### Example Requirements Lists:

**Basic analysis:**
`requirements = ["main-analysis-library", "pandas", "numpy", "matplotlib", "seaborn"]`

**Analysis with Package A:**
`requirements = ["main-analysis-library", "pandas", "numpy", "matplotlib", "seaborn", "package-a"]`

**Analysis with Package B:**  
`requirements = ["main-analysis-library", "pandas", "numpy", "matplotlib", "seaborn", "packageb"]`  
Note: Import as `import PackageB` (capital letters)

**Multiple analysis methods:**
`requirements = ["main-analysis-library", "pandas", "numpy", "matplotlib", "seaborn", "package-a", "packageb", "package-c"]`

**Clustering with Method 1:**
`requirements = ["main-analysis-library", "pandas", "numpy", "matplotlib", "clustering-alg1"]`

**REMEMBER**: It's better to include a package you might not use than to miss one you do use!
"""
        parts.append(dependency_section)
        
        # Add job review failure context if this is a rework
        if 'input_context' in context:
            input_ctx = context['input_context']
            if input_ctx.get('previous_implementation_failed'):
                parts.append("\n## ⚠️ CRITICAL: PREVIOUS IMPLEMENTATION FAILED JOB REVIEW")
                parts.append("This task was attempted before but failed quality review. You MUST address these issues:")
                parts.append("")
                
                # Add job review concerns
                if input_ctx.get('job_review_concerns'):
                    parts.append("### Job Review Concerns:")
                    for concern in input_ctx['job_review_concerns']:
                        severity_icon = "🔴" if concern['severity'] == "critical" else "⚠️"
                        parts.append(f"{severity_icon} **{concern['type'].upper()}**: {concern['description']}")
                        if concern.get('suggested_fix'):
                            parts.append(f"   Suggested fix: {concern['suggested_fix']}")
                        parts.append("")
                
                # Add job review summary
                if input_ctx.get('job_review_summary'):
                    parts.append("### Job Review Summary:")
                    parts.append(input_ctx['job_review_summary'])
                    parts.append("")
                
                # Add previous failed code snippet
                if input_ctx.get('previous_code_snippet'):
                    parts.append("### Previous Failed Implementation (DO NOT COPY):")
                    parts.append("```python")
                    parts.append(input_ctx['previous_code_snippet'])
                    parts.append("```")
                    parts.append("")
                
                parts.append("### Requirements for This Implementation:")
                parts.append("1. Address ALL critical concerns listed above")
                parts.append("2. Implement real, working code - NO placeholders or TODOs")
                parts.append("3. Ensure outputs are actually saved to the output directory")
                parts.append("4. If you claim to save figures, they MUST be produced")
                parts.append("5. Validate your implementation produces the expected outputs")
                parts.append("")
        
        # Add failure context if available (from _node_failure_context.json)
        if 'input_dir' in context:
            failure_context_path = Path(context['input_dir']) / '_node_failure_context.json'
            if failure_context_path.exists():
                try:
                    with open(failure_context_path) as f:
                        failure_context = json.load(f)
                    
                    parts.append("\n## ⚠️ PREVIOUS FAILURE CONTEXT")
                    parts.append("A previous attempt at a similar task failed. Learn from these issues:")
                    parts.append("")
                    
                    # Add execution failure details
                    if 'execution_failure' in failure_context:
                        exec_fail = failure_context['execution_failure']
                        parts.append("### Execution Failure")
                        parts.append(f"- **Error Type**: {exec_fail['error_type']}")
                        parts.append(f"- **Error Message**: {exec_fail['error_message']}")
                        if exec_fail.get('exit_code', -1) != -1:
                            parts.append(f"- **Exit Code**: {exec_fail['exit_code']}")
                        parts.append("")
                    
                    # Add job review failure details
                    if 'job_review_failure' in failure_context:
                        review = failure_context['job_review_failure']
                        parts.append("### Job Review Issues")
                        parts.append(f"- **Summary**: {review['summary']}")
                        if review.get('concerns'):
                            parts.append("- **Concerns**:")
                            for concern in review['concerns']:
                                parts.append(f"  • {concern['type']}: {concern['description']}")
                        parts.append("")
                    
                    # Add problematic implementation details
                    if 'function_block_implementation' in failure_context:
                        impl = failure_context['function_block_implementation']
                        parts.append("### Failed Implementation Details")
                        parts.append(f"- **Function**: {impl['name']}")
                        parts.append(f"- **Language**: {impl['language']}")
                        if impl.get('requirements'):
                            parts.append(f"- **Requirements that failed**: {', '.join(impl['requirements'])}")
                        parts.append(f"- **Debug attempts**: {impl['debug_attempts']}")
                        parts.append("")
                    
                    # Add bug fixer insights
                    if 'bug_fixer_attempts' in failure_context:
                        bf = failure_context['bug_fixer_attempts']
                        parts.append("### Key Issues Discovered")
                        for issue in bf.get('learned_issues', []):
                            parts.append(f"- {issue}")
                        parts.append("")
                        
                        parts.append("**IMPORTANT**: Do NOT repeat these mistakes:")
                        parts.append("- If a package doesn't exist on PyPI, don't try to use it")
                        parts.append("- If an approach failed after multiple attempts, try something different")
                        parts.append("- Ensure all preprocessing requirements are met before using advanced methods")
                        parts.append("")
                    
                except Exception as e:
                    logger.debug(f"Could not load failure context: {e}")
        
        return "\n".join(parts)
    
    def _create_function_block(self, result: Dict[str, Any], context: Dict[str, Any]) -> NewFunctionBlock:
        """Convert LLM result to NewFunctionBlock."""
        
        # Parse static config - handle if it's missing
        static_config_data = result.get('static_config', {})
        
        # Ensure we have required fields
        if not static_config_data:
            static_config_data = {
                'args': [],
                'description': result.get('description', 'Generated function block'),
                'tag': 'analysis'
            }
        
        args = []
        for arg_data in static_config_data.get('args', []):
            try:
                args.append(Arg(
                    name=arg_data['name'],
                    value_type=arg_data['value_type'],
                    description=arg_data['description'],
                    optional=arg_data.get('optional', True),
                    default_value=arg_data.get('default_value')
                ))
            except Exception as e:
                self.logger.error(f"Error creating Arg: {e}")
                self.logger.error(f"arg_data: {arg_data}")
                raise
        
        static_config = StaticConfig(
            args=args,
            description=static_config_data.get('description', result.get('description', 'Generated function block')),
            tag=static_config_data.get('tag', 'analysis')
        )
        
        # Add input/output specifications if provided
        if 'input_specification' in context:
            static_config.input_specification = context['input_specification']
        if 'output_specification' in context:
            static_config.output_specification = context['output_specification']
        
        # Determine language from LLM response or code analysis
        code = result['code']
        # First check if LLM explicitly specified the type
        if 'type' in result:
            fb_type = FunctionBlockType.R if result['type'].lower() == 'r' else FunctionBlockType.PYTHON
        else:
            # Fallback to code analysis if type not specified
            fb_type = FunctionBlockType.R if 'library(' in code or '<-' in code else FunctionBlockType.PYTHON
        
        # Handle requirements as either array or string
        requirements = result.get('requirements', '')
        if isinstance(requirements, list):
            requirements = '\n'.join(requirements)
        
        # Handle parameters as either dict or JSON string
        parameters = result.get('parameters', {})
        if isinstance(parameters, str):
            try:
                parameters = json.loads(parameters)
            except json.JSONDecodeError:
                self.logger.warning(f"Failed to parse parameters JSON string: {parameters}")
                parameters = {}
        
        return NewFunctionBlock(
            name=result['name'],
            type=fb_type,
            description=result['description'],
            code=code,
            requirements=requirements,
            parameters=parameters,
            static_config=static_config,
            output_description=result.get('output_description')
        )
    
    def set_node_directory(self, node_dir):
        """Set the current node directory for evidence saving."""
        self._current_node_dir = node_dir
    
    def create_function_block(self, specification: Dict[str, Any]) -> Optional[NewFunctionBlock]:
        """Create a function block from specification.
        
        Args:
            specification: Dictionary with name, description, task, etc.
            
        Returns:
            NewFunctionBlock if successful, None otherwise
        """
        # If specification already has the right format (from create_from_specification), use it directly
        if all(key in specification for key in ["task_description", "user_request"]):
            return self.process(specification)
        
        # Otherwise, convert specification to context format expected by process method
        context = {
            "task_description": specification.get("task", specification.get("description", "")),
            "user_request": specification.get("user_request", specification.get("task", specification.get("description", ""))),
            "function_name": specification.get("name", "unknown_function"),
            "description": specification.get("description", ""),
            "requirements": specification.get("requirements", ""),
            "parameters": specification.get("parameters", {}),
            "input_type": "adata",
            "output_type": "adata"
        }
        
        # Pass through parent output structure if available
        if "parent_output_structure" in specification:
            context["parent_output_structure"] = specification["parent_output_structure"]
        
        # Pass through input_context if available
        if "input_context" in specification:
            context["input_context"] = specification["input_context"]
        
        return self.process(context)
    
    def process_selection_or_creation(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Unified method to select existing or create new function blocks.
        
        This method replaces the separate FunctionSelectorAgent functionality.
        
        Required context keys:
            - user_request: str
            - tree: AnalysisTree
            - current_node: Optional[AnalysisNode]
            - parent_chain: List[AnalysisNode]
            - generation_mode: GenerationMode
            - max_children: int
            - data_summary: Optional[Dict[str, Any]]
            
        Returns:
            Dict with:
                - function_blocks: List[Union[NewFunctionBlock, ExistingFunctionBlock]]
                - satisfied: bool
                - reasoning: str
        """
        try:
            user_request = context['user_request']
            tree = context['tree']
            current_node = context.get('current_node')
            parent_chain = context.get('parent_chain', [])
            generation_mode = context['generation_mode']
            max_children = context['max_children']
            data_summary = context.get('data_summary', {})
        except Exception as e:
            self.logger.error(f"Error extracting context: {e}", exc_info=True)
            raise
        
        # Build prompt for LLM to decide what function blocks are needed
        try:
            prompt = self._build_selection_prompt(
                user_request=user_request,
                tree_state=self._get_tree_state(tree),
                current_node=current_node,
                parent_chain=parent_chain,
                generation_mode=generation_mode,
                max_children=max_children,
                data_summary=data_summary
            )
        except Exception as e:
            self.logger.error(f"Error building selection prompt: {e}", exc_info=True)
            raise
        
        # Define schema for response
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                    "satisfied": {"type": "boolean", "description": "Whether the user request is fully satisfied"},
                    "reasoning": {"type": "string", "description": "Explanation of the decision"},
                    "next_function_blocks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "task": {"type": "string"},
                                "create_new": {"type": "boolean", "description": "True to create new, False to use existing"},
                                "parameters": {"type": "string", "description": "Parameters as JSON string"}
                            },
                            "required": ["name", "description", "task", "create_new"]
                        }
                    }
            },
            "required": ["satisfied", "reasoning", "next_function_blocks"]
        }
        
        try:
            # Call LLM
            messages = [
                {"role": "system", "content": self.SELECTION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]
            
            result = self.llm_service.chat_completion_json(
                messages=messages,
                json_schema=schema,
                temperature=0.7,
                max_tokens=2000,
                seed=self.llm_seed
            )
            
            # Process recommendations
            function_blocks = []
            for fb_spec in result.get('next_function_blocks', []):
                # Enforce generation mode
                should_create_new = fb_spec.get('create_new', True)
                if generation_mode == GenerationMode.ONLY_NEW:
                    should_create_new = True
                elif generation_mode == GenerationMode.ONLY_EXISTING:
                    should_create_new = False
                    
                if should_create_new:
                    # Create new function block
                    creation_context = {
                        'task_description': fb_spec['task'],
                        'user_request': user_request,
                        'function_name': fb_spec['name'],
                        'description': fb_spec['description'],
                        'parameters': fb_spec.get('parameters', {}),
                        'is_root_node': context.get('is_root_node', False)  # Pass through root node flag
                    }
                    
                    # Add parent output structure if available
                    if current_node and hasattr(current_node, 'output_data_structure'):
                        creation_context['parent_output_structure'] = current_node.output_data_structure
                    
                    block = self.process(creation_context)
                    if block:
                        function_blocks.append(block)
                else:
                    # For now, we don't have a library of existing blocks
                    # In future, this would look up existing blocks
                    logger.warning(f"Existing block requested but not implemented: {fb_spec['name']}")
                    # Fallback: create new block anyway
                    logger.info(f"Falling back to creating new block for: {fb_spec['name']}")
                    creation_context = {
                        'task_description': fb_spec['task'],
                        'user_request': user_request,
                        'function_name': fb_spec['name'],
                        'description': fb_spec['description'],
                        'parameters': fb_spec.get('parameters', {}),
                        'is_root_node': context.get('is_root_node', False)
                    }
                    block = self.process(creation_context)
                    if block:
                        function_blocks.append(block)
            
            return {
                'function_blocks': function_blocks,
                'satisfied': result.get('satisfied', False),
                'reasoning': result.get('reasoning', '')
            }
            
        except Exception as e:
            logger.error(f"Error in process_selection_or_creation: {e}", exc_info=True)
            import traceback
            tb_str = traceback.format_exc()
            logger.error(f"Full traceback:\n{tb_str}")
            return {
                'function_blocks': [],
                'satisfied': False,
                'reasoning': f'Error: {str(e)}'
            }
    
    def _build_selection_prompt(
        self,
        user_request: str,
        tree_state: Dict[str, Any],
        current_node: Optional[AnalysisNode],
        parent_chain: List[AnalysisNode],
        generation_mode: GenerationMode,
        max_children: int,
        data_summary: Dict[str, Any]
    ) -> str:
        """Build prompt for function block selection/creation decision."""
        parts = []
        
        parts.append("## Analysis Context")
        parts.append(f"User Request: {user_request}")
        parts.append("")
        
        parts.append("## Current Analysis State")
        parts.append(f"Total nodes: {tree_state['total_nodes']}")
        parts.append(f"Completed: {tree_state['completed_nodes']}")
        parts.append(f"Failed: {tree_state['failed_nodes']}")
        parts.append("")
        
        if parent_chain:
            parts.append("## Previous Analysis Steps")
            for i, node in enumerate(parent_chain):
                parts.append(f"{i+1}. {node.function_block.name}: {node.function_block.description}")
            parts.append("")
        
        if current_node:
            parts.append("## Current Node")
            parts.append(f"Name: {current_node.function_block.name}")
            parts.append(f"Description: {current_node.function_block.description}")
            parts.append("")
        
        if data_summary:
            parts.append("## Current Data State")
            parts.append(f"Shape: {data_summary.get('n_obs', '?')} observations × {data_summary.get('n_vars', '?')} variables")
            if data_summary.get('obs_columns'):
                parts.append(f"Observation columns: {', '.join(data_summary['obs_columns'])}")
            if data_summary.get('obsm_keys'):
                parts.append(f"Embeddings: {', '.join(data_summary['obsm_keys'])}")
            parts.append("")
        
        parts.append("## Task")
        parts.append(f"Recommend up to {max_children} function blocks for the next analysis steps.")
        parts.append("For each function block, decide whether to create new or use existing.")
        parts.append("")
        
        parts.append("Consider:")
        parts.append("- What analysis steps are needed to fulfill the user request?")
        parts.append("- What has already been done?")
        parts.append("- What logical next steps would progress toward the goal?")
        parts.append("- Are we satisfied that the request has been fulfilled?")
        parts.append("- Should we create new custom blocks or use standard existing ones?")
        
        return "\n".join(parts)
    
    def _get_tree_state(self, tree: AnalysisTree) -> Dict[str, Any]:
        """Get summary of tree state."""
        from models import NodeState
        completed = sum(1 for n in tree.nodes.values() if (n.state == NodeState.COMPLETED if isinstance(n.state, NodeState) else n.state == NodeState.COMPLETED.value))
        failed = sum(1 for n in tree.nodes.values() if (n.state == NodeState.FAILED if isinstance(n.state, NodeState) else n.state == NodeState.FAILED.value))
        pending = sum(1 for n in tree.nodes.values() if (n.state == NodeState.PENDING if isinstance(n.state, NodeState) else n.state == NodeState.PENDING.value))
        
        return {
            'total_nodes': len(tree.nodes),
            'completed_nodes': completed,
            'failed_nodes': failed,
            'pending_nodes': pending
        }
    
    def create_from_specification(self, spec: Dict[str, Any], input_context: Optional[Dict[str, Any]] = None, node_dir: Optional[Path] = None, node_id: Optional[str] = None, iteration: int = 1) -> Optional[NewFunctionBlock]:
        """Create a function block from orchestrator specification.
        
        Args:
            spec: Specification containing name, description, and task
            input_context: Optional context about input data (e.g., parent output info)
            
        Returns:
            NewFunctionBlock or None if creation fails
        """
        try:
            # Create context for function creation
            context = {
                'task_description': spec.get('task', spec.get('description', '')),
                'user_request': spec.get('task', ''),
                'function_name': spec['name'],
                'description': spec.get('description', ''),
                'parameters': {},
                'is_root_node': spec.get('is_root', False),
                'node_id': node_id,
                'iteration': iteration
            }
            
            # Add input context if provided
            if input_context:
                context['input_context'] = input_context
                # Add helpful info about expected input
                if input_context.get('available_files'):
                    context['input_files_info'] = f"Available input files: {', '.join(input_context['available_files'])}"
                if input_context.get('parent_output_type'):
                    context['parent_output_info'] = f"Parent node output type: {input_context['parent_output_type']}"
            
            # Add node_dir for logging if provided
            if node_dir:
                context['node_dir'] = node_dir
            
            # Create the function block
            block = self.create_function_block(context)
            
            if block:
                # Ensure the name matches specification
                block.name = spec['name']
                if not block.description:
                    block.description = spec.get('description', f"Function block for {spec['name']}")
                
                # Apply code checking if enabled
                if self.enable_code_checker and self.code_checker:
                    try:
                        check_result = self.code_checker.check_code(
                            code=block.code,
                            language=block.type.value,
                            requirements=block.requirements.split('\n') if block.requirements else [],
                            function_description=block.description,
                            config=block.static_config.model_dump() if hasattr(block.static_config, 'model_dump') else {}
                        )
                        
                        if check_result.must_fix and check_result.suggested_code:
                            logger.info(f"Code checker identified issues in {block.name}, applying fixes")
                            block.code = check_result.suggested_code
                            
                            # Log the code checking results
                            logger.info(f"Code check for {block.name}: valid={check_result.valid}, issues={len(check_result.issues)}")
                        
                        # Save code checker reports to function creator directory if available
                        if hasattr(self, '_current_node_dir') and self._current_node_dir:
                            save_dir = self._current_node_dir / "agent_tasks" / "function_creator"
                            self.code_checker.save_reports_to_directory(save_dir)
                            
                        elif not check_result.valid:
                            logger.warning(f"Code checker found issues in {block.name} but no auto-fix available")
                            for issue in check_result.issues[:3]:  # Log first 3 issues
                                logger.warning(f"  - {issue.severity}: {issue.description}")
                    
                    except Exception as e:
                        logger.warning(f"Code checking failed for {block.name}: {e}")
                
            return block
            
        except Exception as e:
            logger.error(f"Failed to create function block from spec: {e}")
            return None
    
    def save_cached_llm_interaction(self, node_id: str, node_dir: Path, iteration: int = 1) -> None:
        """Save the cached LLM interaction data to the node directory.
        
        Args:
            node_id: The actual node ID
            node_dir: Path to the node directory
            iteration: Orchestrator planning iteration (not function block version)
        """
        if not self._last_llm_interaction:
            logger.warning("No cached LLM interaction data to save")
            return
        
        try:
            # Create agent tasks directory
            agent_tasks_dir = node_dir / "agent_tasks" / "function_creator"
            agent_tasks_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now()
            interaction_data = self._last_llm_interaction.copy()
            
            # Update with actual node information
            interaction_data["node_id"] = node_id
            interaction_data["node_name"] = interaction_data["input"]["specification"]["name"]
            interaction_data["orchestrator_iteration"] = iteration  # Planning iteration, not version
            interaction_data["function_block_version"] = 1  # Function creator always creates v1
            
            # Save JSON file with complete raw data
            json_file = agent_tasks_dir / f"llm_interaction_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
            with open(json_file, 'w') as f:
                json.dump(interaction_data, f, indent=2, default=str)
            
            # Save MD file with formatted content including full prompts
            md_file = agent_tasks_dir / f"llm_interaction_{timestamp.strftime('%Y%m%d_%H%M%S')}.md"
            with open(md_file, 'w') as f:
                f.write("# LLM Interaction Log\n\n")
                f.write(f"**Timestamp:** {interaction_data['timestamp']}\n")
                f.write(f"**Model:** {interaction_data['model']}\n")
                f.write(f"**Node ID:** {node_id}\n")
                f.write(f"**Node Name:** {interaction_data['input']['specification']['name']}\n")
                f.write(f"**Orchestrator Iteration:** {iteration}\n")
                f.write(f"**Function Block Version:** 1\n\n")
                
                f.write("## Input Specification\n\n")
                f.write("```json\n")
                f.write(json.dumps(interaction_data["input"]["specification"], indent=2))
                f.write("\n```\n\n")
                
                if interaction_data["input"].get('input_context'):
                    f.write("## Input Context\n\n")
                    f.write("```json\n")
                    f.write(json.dumps(interaction_data["input"]["input_context"], indent=2))
                    f.write("\n```\n\n")
                
                f.write("## Raw LLM Messages\n\n")
                f.write("### System Prompt\n\n")
                system_prompt = interaction_data["input"]["system_prompt"]
                f.write(f"*Length: {len(system_prompt)} characters*\n\n")
                f.write("```\n")
                f.write(system_prompt)
                f.write("\n```\n\n")
                
                f.write("### User Messages\n\n")
                for i, msg in enumerate(interaction_data["input"]["raw_messages"]):
                    if msg['role'] == 'user':
                        f.write(f"#### User Message {i+1}\n\n")
                        f.write(f"*Length: {len(msg['content'])} characters*\n\n")
                        f.write("```\n")
                        f.write(msg['content'])
                        f.write("\n```\n\n")
                
                f.write("### JSON Schema\n\n")
                f.write("```json\n")
                f.write(json.dumps(interaction_data["input"]["json_schema"], indent=2))
                f.write("\n```\n\n")
                
                f.write("### LLM Parameters\n\n")
                params = interaction_data["input"]["llm_parameters"]
                f.write(f"- Temperature: {params['temperature']}\n")
                f.write(f"- Max Tokens: {params['max_tokens']}\n")
                f.write(f"- Model: {params['model']}\n")
                f.write(f"- Seed: {params['seed']}\n\n")
                
                f.write("## LLM Response\n\n")
                if interaction_data["output"]:
                    f.write("### Function Block Created\n\n")
                    fb = interaction_data["output"]["function_block"]
                    f.write(f"**Name:** {fb.get('name', 'N/A')}\n")
                    f.write(f"**Type:** {fb.get('type', 'N/A')}\n")
                    f.write(f"**Description:** {fb.get('description', 'N/A')}\n\n")
                    
                    if fb.get('requirements'):
                        f.write("### Requirements\n\n")
                        f.write("```\n")
                        if isinstance(fb['requirements'], list):
                            f.write('\n'.join(fb['requirements']))
                        else:
                            f.write(str(fb['requirements']))
                        f.write("\n```\n\n")
                    
                    if fb.get('code'):
                        f.write("### Code\n\n")
                        f.write(f"```{fb.get('type', 'python')}\n")
                        f.write(fb['code'])
                        f.write("\n```\n\n")
                    
                    if fb.get('output_description'):
                        f.write("### Output Description\n\n")
                        f.write(fb['output_description'])
                        f.write("\n\n")
                
                f.write("## Full Raw Response\n\n")
                f.write("```json\n")
                f.write(json.dumps(interaction_data["output"]["raw_response"], indent=2))
                f.write("\n```\n")
            
            logger.info(f"Saved raw LLM interaction to {json_file} and {md_file}")
            
        except Exception as e:
            logger.error(f"Failed to save cached LLM interaction: {e}")
        finally:
            # Clear the cache
            self._last_llm_interaction = None
    
    # Add selection system prompt
    SELECTION_SYSTEM_PROMPT = """You are an expert data analyst specializing in various computational data analysis tasks.

Your task is to recommend function blocks that process data to fulfill user requests.

CRITICAL PRINCIPLES:
1. **CREATE MEANINGFUL FUNCTION NAMES**: Generate descriptive names based on the task
   - Names should clearly indicate what the function does
   - Use snake_case naming convention
   - Examples: "quality_control", "normalize_expression", "compute_umap", "dpt_analysis"
2. **ONE TASK PER FUNCTION BLOCK**: Each function block must perform exactly ONE specific task
   - NEVER combine multiple steps like "filter AND normalize AND log transform" in one block
   - Each distinct operation (filter, normalize, log1p, PCA, UMAP, etc.) must be its own block
   - If the user lists steps as "1. First step... 2. Second step... 3. Third step...", create SEPARATE blocks
3. **MODULAR WORKFLOW**: Complex requests must be broken into multiple sequential nodes
4. **PROPER SEQUENCING**: Ensure correct order of operations (e.g., normalize before PCA, PCA before clustering)

IMPORTANT - Request Satisfaction:
- Set satisfied=true ONLY when ALL requested analyses are completed
- Analyze the user request carefully to identify all requested tasks
- Preprocessing steps alone do NOT satisfy analysis requests

Common data analysis workflows include:
- Quality control and filtering (ONE node - ONLY filtering, no normalization)
- Normalization (ONE node - ONLY normalize_total, no log transform)
- Log transformation (ONE node - ONLY log1p)
- Highly variable gene selection (ONE node)
- Dimensionality reduction: PCA (ONE node), then UMAP/t-SNE (separate node)
- Clustering: Leiden or Louvain (ONE node)
- Differential expression analysis (ONE node per comparison)
- Trajectory inference (ONE node per method)
- Cell type annotation (ONE node)

EXAMPLE: If user says "filter cells, normalize, and log transform", create THREE nodes:
1. filter_cells (ONLY filtering)
2. normalize_data (ONLY normalization)
3. log_transform (ONLY log1p)

EXAMPLE: Function naming based on analysis tasks:
- "preprocess the data" → use name: "preprocess_data"
- "perform analysis method A" → use name: "method_a_analysis" 
- "run Package B for trajectory inference" → use name: "package_b_trajectory"
- "compare analysis methods" → use name: "compare_analysis_methods"
- "normalize and find variable features" → create TWO blocks: "normalize_data" and "find_variable_features"

For trajectory/temporal analysis specifically:
- Preprocessing: QC → Normalization → Feature Selection → Dimensionality Reduction → Graph Construction (separate nodes)
- Reference point selection: use biological criteria or a user-given parameter; if a random choice is unavoidable, seed it, emit a warning and record the selected reference and seed in the outputs
- Each analysis method is ONE node: Method A, Method B, Method C, Method D, Method E
- ALWAYS handle missing reference points: if not set, use appropriate default with warning
- Metrics computation is ONE node (after all methods complete)
- Visualization is ONE node (after metrics)

IMPORTANT: When the user requests multiple analyses (e.g., "run 5 analysis methods"), break it down:
1. First ensure preprocessing is complete
2. Create separate nodes for each analysis method
3. Create a final node for metrics/visualization

For each recommended function block, decide:
- create_new=true: For custom analysis specific to the user request
- create_new=false: For standard preprocessing steps with well-established methods"""