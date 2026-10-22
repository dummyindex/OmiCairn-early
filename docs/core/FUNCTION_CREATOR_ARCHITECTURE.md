# Function Creator Agent Architecture

## Overview

The Function Creator Agent is responsible for selecting existing function blocks or generating new ones to fulfill specific analysis tasks within the OmiCairn workflow. It ensures all function blocks adhere to a standardized framework for seamless integration and execution.

## Architecture Diagram

```mermaid
graph TB
    subgraph FunctionCreatorSystem[Function Creator Agent]
        MainProcess[Main Process<br/>process_selection_or_creation()]
        
        Selector[Function Selector<br/>• Library search<br/>• Similarity matching<br/>• Compatibility check]
        
        Creator[Function Creator<br/>• LLM code generation<br/>• Framework compliance<br/>• Error handling]
        
        Validator[Code Validator<br/>• Syntax check<br/>• Import validation<br/>• Framework adherence]
        
        OutputLogger[Agent Output Logger<br/>• Task logging<br/>• LLM tracking<br/>• Decision recording]
    end
    
    subgraph FunctionLibrary[Function Block Library]
        Builtin[Built-in Blocks<br/>• Data conversion<br/>• Preprocessing<br/>• Standard analyses]
        
        Custom[Custom Blocks<br/>• User-created<br/>• Validated blocks<br/>• Reusable components]
    end
    
    MainProcess --> Selector
    MainProcess --> Creator
    Selector --> FunctionLibrary
    Creator --> Validator
    Creator --> OutputLogger
    Selector --> OutputLogger
    
    style FunctionCreatorSystem fill:#fff9c4
    style FunctionLibrary fill:#e8eaf6
```

## Key Components

### 1. FunctionCreatorAgent (`agents/function_creator_agent.py`)

**Purpose**: Unified agent for function block selection and creation.

**Key Responsibilities**:
- Analyze task requirements and context
- Search existing function block library
- Generate new function blocks when needed
- Ensure framework compliance
- Log all decisions and creations

**Key Methods**:

```python
def process_selection_or_creation(self, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Unified method to select existing or create new function blocks.
    
    Args:
        context: Contains task_description, user_request, parent_output, etc.
    
    Returns:
        Dict with 'function_block' (NewFunctionBlock or ExistingFunctionBlock)
    """

def create_function(
    self,
    task_description: str,
    user_request: str,
    parent_output: Optional[Dict[str, Any]] = None,
    data_summary: Optional[Dict[str, Any]] = None,
    language: str = "python",
    existing_code: Optional[str] = None,
    error_message: Optional[str] = None,
    node_dir: Optional[Path] = None
) -> NewFunctionBlock:
    """Generate new function block with LLM."""

def _search_existing_blocks(self, task_description: str, language: str) -> List[ExistingFunctionBlock]:
    """Search for existing function blocks matching the task."""

def _select_best_block(self, candidates: List[ExistingFunctionBlock], task_description: str) -> Optional[ExistingFunctionBlock]:
    """Select the best matching block from candidates."""
```

### 2. Function Block Framework

**Standardized Signature**:

```python
def run(path_dict, params):
    """
    Main entry point for the function block.
    
    Args:
        path_dict: Dictionary containing paths:
            - input_dir: Input directory path
            - output_dir: Output directory path
        params: Dictionary of parameters for this block
    
    Returns:
        None (outputs are written to files)
    """
```

**Required Structure**:

```python
import os
import scanpy as sc
from pathlib import Path

def run(path_dict, params):
    # 1. Load input data
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    adata = sc.read_h5ad(input_file)
    
    # 2. Set up output directories
    figures_dir = Path(path_dict["output_dir"]) / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    sc.settings.figdir = figures_dir
    
    # 3. Process data
    # ... your analysis code ...
    
    # 4. Save output data
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    adata.write(output_file)
    print(f"Output saved to {output_file}")
```

### 3. Generation Modes

**GenerationMode Enum**:
- `ONLY_NEW`: Always create new function blocks
- `ONLY_EXISTING`: Only use existing blocks
- `MIXED`: Intelligently choose between new and existing

**Mode Selection Logic**:

```python
if generation_mode == GenerationMode.ONLY_NEW:
    # Always create new
    return self.create_function(...)
elif generation_mode == GenerationMode.ONLY_EXISTING:
    # Must find existing or fail
    existing = self._search_existing_blocks(...)
    if not existing:
        raise ValueError("No existing blocks found")
elif generation_mode == GenerationMode.MIXED:
    # Try existing first, create if needed
    existing = self._search_existing_blocks(...)
    if existing and confidence > threshold:
        return existing[0]
    else:
        return self.create_function(...)
```

## Function Block Types

### Built-in Function Blocks

Located in `function_blocks/builtin/`:

1. **Data Conversion**:
   - `convert_anndata_to_sc_matrix`: H5AD → SingleCellExperiment
   - `convert_sc_matrix_to_anndata`: SingleCellExperiment → H5AD
   - `convert_seurat_to_sc_matrix`: Seurat → SingleCellExperiment
   - `convert_sc_matrix_to_seuratobject`: SingleCellExperiment → Seurat

2. **Preprocessing** (examples):
   - Quality control filtering
   - Normalization
   - Highly variable gene selection
   - Scaling and centering

3. **Analysis** (examples):
   - PCA computation
   - Clustering (Leiden, Louvain)
   - UMAP/t-SNE embedding
   - Differential expression

### Custom Function Blocks

Created dynamically based on user requests:
- Specialized analyses
- Novel algorithms
- Custom visualizations
- Integration with external tools

## Code Generation Process

### 1. Prompt Construction

The agent constructs detailed prompts including:
- Task description
- Input/output specifications
- Framework requirements
- Error context (if fixing)
- Relevant examples

### 2. LLM Interaction

```python
messages = [
    {"role": "system", "content": self.SYSTEM_PROMPT},
    {"role": "user", "content": prompt}
]

response = self.llm_service.chat_completion_json(
    messages=messages,
    json_schema=self.CODE_GENERATION_SCHEMA,
    temperature=0.3,
    max_tokens=8000
)
```

### 3. Response Parsing

**Expected JSON Structure**:
```json
{
    "name": "function_block_name",
    "description": "What this block does",
    "code": "def run(path_dict, params):\n    ...",
    "requirements": ["scanpy>=1.9.0", "pandas"],
    "parameters": {
        "resolution": 1.0,
        "n_neighbors": 15
    }
}
```

### 4. Validation

- Python/R syntax validation
- Import statement checking
- Framework compliance verification
- Parameter type validation

## Configuration and Parameters

### Static Configuration

Each function block includes a `config.json`:

```json
{
    "name": "leiden_clustering",
    "type": "python",
    "description": "Perform Leiden clustering",
    "category": "clustering",
    "parameters": {
        "resolution": {
            "type": "float",
            "default": 1.0,
            "description": "Resolution parameter"
        }
    },
    "input_specification": {
        "adata": {
            "type": "h5ad",
            "description": "Annotated data matrix",
            "required_features": ["X_pca"]
        }
    },
    "output_specification": {
        "adata": {
            "type": "h5ad",
            "added_features": ["leiden"]
        }
    }
}
```

### Parameter Handling

Parameters are passed through the execution chain:
1. User specifies in request
2. Orchestrator includes in plan
3. Function creator adds to block
4. Executor passes to container
5. Function block reads from `params` dict

## Error Handling

### Common Error Patterns

1. **Import Errors**: Missing packages
   - Solution: Update requirements.txt
   
2. **Data Access Errors**: Wrong file paths
   - Solution: Use standardized path_dict pattern
   
3. **Framework Violations**: Missing run() function
   - Solution: Regenerate with correct template
   
4. **Type Errors**: Parameter mismatches
   - Solution: Validate and convert types

### Integration with Bug Fixer

When a generated function block fails:
1. Error captured by executor
2. Bug fixer analyzes the error
3. Function creator called to regenerate
4. Fixed code validated and retried

## Logging and Monitoring

### Agent Output Logging

All function creator activities are logged:

```python
output_logger = AgentOutputLogger(
    agent_type="function_creator",
    output_dir=node_dir / "agent_tasks"
)

# Log selection process
output_logger.log_function_selection(
    task_description=task_description,
    candidates=candidates,
    selected=selected_block,
    confidence_scores=scores
)

# Log creation process
output_logger.log_agent_task(
    task_type="create_function",
    request={"task": task_description},
    response={"code": generated_code},
    metadata={"language": language}
)
```

### Log Files

Located in `node_dir/agent_tasks/creator_TIMESTAMP/`:
- `task_info.json`: Task metadata
- `llm_request.json`: Full LLM prompt
- `llm_response.json`: LLM response
- `task_summary.json`: Summary and metrics

## Best Practices

### 1. Code Generation

- Always include comprehensive error handling
- Add informative print statements
- Validate inputs before processing
- Create output directories if needed
- Follow the standardized framework

### 2. Function Naming

- Use descriptive snake_case names
- Include the analysis type (e.g., `leiden_clustering`)
- Avoid generic names like `process_data`
- Be consistent with existing conventions

### 3. Requirements

- Pin versions for reproducibility
- Include all direct dependencies
- Test in clean environment
- Avoid unnecessary dependencies

### 4. Documentation

- Add clear docstrings
- Explain parameters
- Document expected inputs/outputs
- Include usage examples

## Future Enhancements

### Planned Features

1. **Semantic Search**: Better matching of existing blocks
2. **Version Control**: Track block versions and changes
3. **Performance Metrics**: Benchmark block execution
4. **Auto-optimization**: Optimize generated code
5. **Multi-language**: Better R and Julia support

### Extension Points

1. **Custom Templates**: User-defined code templates
2. **External Libraries**: Integration with bioinformatics packages
3. **Validation Rules**: Custom validation logic
4. **Code Review**: Automated code quality checks
5. **Testing Framework**: Automatic test generation