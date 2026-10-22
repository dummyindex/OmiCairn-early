# Bug Fixer and Orchestrator Improvements Plan

## Date: August 11, 2025

## Executive Summary

This document outlines the development plan to address critical issues in the bug fixer and orchestrator components based on the analysis of the current implementation and execution results.

## Analysis of Current Issues

### 1. Analysis Tree Execution Results

From the benchmark run analysis:
- **Total nodes**: 4
- **Successful nodes**: 3 (marked as "completed")
- **Failed nodes**: 1 (scFates node failed due to missing module)
- **Key observation**: Despite the scFates node failing, the orchestrator marked nodes as "completed" even though they had errors during initial execution

### 2. Orchestrator Issues

#### Problem: Creating Child Nodes After Parent Failures
- The orchestrator continues to create child nodes even when parent nodes fail
- In the analyzed run, after scFates failed, no further nodes were created (correct behavior)
- However, the orchestrator marked nodes that required bug fixing as "completed" without distinguishing between "completed successfully on first try" vs "completed after bug fixes"

#### Root Cause:
```python
# In orchestrator_agent.py
elif result['state'] == NodeState.FAILED:
    self.failed_nodes.add(node.id)
    # Try to fix if possible
    if hasattr(self, 'handle_failed_node'):
        self.handle_failed_node(node, result.get('error', 'Unknown error'), '', '')
```

The orchestrator doesn't check if the parent node was successfully fixed before allowing children.

### 3. Bug Fixer Issues

#### A. Error Propagation Between Attempts
**Current Issue**: When a bug is fixed and a new error arises, the new error is not properly passed to the next debug attempt.

**Example**: 
- Attempt 1: ModuleNotFoundError for 'scfates'
- Attempt 2: Still shows the same ModuleNotFoundError instead of any new error after attempted fix

#### B. String-Based Action Detection
**Current Implementation**:
```python
if "fixed" in confirmation.lower() or "success" in confirmation.lower():
    success = True
```

This is fragile and relies on the LLM including specific words in its response.

#### C. JSON Parsing for Actions
**Current Implementation**:
```python
# Complex regex and fallback parsing
json_pattern = r'```json\s*({[^`]+})\s*```'
json_matches = re.findall(json_pattern, response, re.DOTALL)
```

This requires parsing and is error-prone.

## Development Plan

### 0. Add Function Block Input/Output Validation

#### Motivation
Function blocks need clear specifications of expected inputs and outputs to enable proper validation and better debugging. This will help catch issues early and provide clearer error messages.

#### Implementation Steps:

1. **Extend Function Block Configuration Schema**
```python
# In models.py - Update FunctionBlock static_config
class FunctionBlockStaticConfig(BaseModel):
    # ... existing fields ...
    input_specification: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Expected input structure and validation rules"
    )
    output_specification: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="Expected output structure and validation rules"
    )

# Example specification:
{
    "input_specification": {
        "required_files": ["_node_anndata.h5ad"],
        "anndata_requirements": {
            "min_cells": 100,
            "min_genes": 200,
            "required_obs": [],
            "required_var": [],
            "required_uns": [],
            "required_obsm": []
        }
    },
    "output_specification": {
        "required_files": ["_node_anndata.h5ad"],
        "anndata_requirements": {
            "required_obs": ["dpt_pseudotime"],
            "required_var": [],
            "required_uns": ["iroot"],
            "required_obsm": ["X_diffmap"]
        },
        "optional_files": ["figures/*.png"]
    }
}
```

2. **Create Validation Module**
```python
# New file: utils/function_block_validator.py
import scanpy as sc
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class FunctionBlockValidator:
    """Validates function block inputs and outputs against specifications."""
    
    def __init__(self, specification: Dict[str, Any]):
        self.spec = specification
    
    def validate_input(self, input_dir: Path) -> Tuple[bool, List[str]]:
        """Validate input directory against specification.
        
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        if not self.spec:
            return True, []
        
        input_spec = self.spec.get('input_specification', {})
        
        # Check required files
        for file in input_spec.get('required_files', []):
            file_path = input_dir / file
            if not file_path.exists():
                errors.append(f"Required input file missing: {file}")
        
        # Check AnnData requirements if specified
        if 'anndata_requirements' in input_spec and '_node_anndata.h5ad' in input_spec.get('required_files', []):
            adata_errors = self._validate_anndata(
                input_dir / '_node_anndata.h5ad',
                input_spec['anndata_requirements']
            )
            errors.extend(adata_errors)
        
        return len(errors) == 0, errors
    
    def validate_output(self, output_dir: Path) -> Tuple[bool, List[str]]:
        """Validate output directory against specification.
        
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        if not self.spec:
            return True, []
        
        output_spec = self.spec.get('output_specification', {})
        
        # Check required files
        for file in output_spec.get('required_files', []):
            file_path = output_dir / file
            if not file_path.exists():
                errors.append(f"Required output file missing: {file}")
        
        # Check AnnData requirements
        if 'anndata_requirements' in output_spec and '_node_anndata.h5ad' in output_spec.get('required_files', []):
            adata_errors = self._validate_anndata(
                output_dir / '_node_anndata.h5ad',
                output_spec['anndata_requirements']
            )
            errors.extend(adata_errors)
        
        return len(errors) == 0, errors
    
    def _validate_anndata(self, adata_path: Path, requirements: Dict[str, Any]) -> List[str]:
        """Validate AnnData object against requirements."""
        errors = []
        
        try:
            adata = sc.read_h5ad(adata_path)
            
            # Check dimensions
            if 'min_cells' in requirements and adata.n_obs < requirements['min_cells']:
                errors.append(f"AnnData has {adata.n_obs} cells, minimum required: {requirements['min_cells']}")
            
            if 'min_genes' in requirements and adata.n_vars < requirements['min_genes']:
                errors.append(f"AnnData has {adata.n_vars} genes, minimum required: {requirements['min_genes']}")
            
            # Check required columns/keys
            for col in requirements.get('required_obs', []):
                if col not in adata.obs.columns:
                    errors.append(f"Required obs column missing: {col}")
            
            for col in requirements.get('required_var', []):
                if col not in adata.var.columns:
                    errors.append(f"Required var column missing: {col}")
            
            for key in requirements.get('required_uns', []):
                if key not in adata.uns:
                    errors.append(f"Required uns key missing: {key}")
            
            for key in requirements.get('required_obsm', []):
                if key not in adata.obsm:
                    errors.append(f"Required obsm key missing: {key}")
                    
        except Exception as e:
            errors.append(f"Failed to read AnnData file: {str(e)}")
        
        return errors
```

3. **Integrate Validation into Execution**
```python
# In job_executors/interactive_executor.py
def _run_with_validation(self, attempt: int = 1) -> Dict[str, Any]:
    """Run function block with input/output validation."""
    
    # Pre-flight validation
    if self.function_block.static_config:
        validator = FunctionBlockValidator(self.function_block.static_config.dict())
        
        # Validate inputs
        input_valid, input_errors = validator.validate_input(Path(self.volume_mapping['input']))
        if not input_valid:
            logger.error(f"Input validation failed: {input_errors}")
            return {
                'success': False,
                'error': f"Input validation failed: {'; '.join(input_errors)}",
                'validation_type': 'input'
            }
        else:
            logger.info("Input validation passed")
    
    # Execute function block
    result = self._execute_in_container(attempt)
    
    # Post-execution validation
    if result['success'] and self.function_block.static_config:
        output_valid, output_errors = validator.validate_output(Path(self.volume_mapping['output']))
        if not output_valid:
            logger.error(f"Output validation failed: {output_errors}")
            result['success'] = False
            result['error'] = f"Output validation failed: {'; '.join(output_errors)}"
            result['validation_type'] = 'output'
        else:
            logger.info("Output validation passed")
    
    return result
```

4. **Update Function Creator to Include Specifications**
```python
# In agents/function_creator_agent.py
def _create_function_with_validation(self, task_description: str, parent_outputs: List[str]) -> Dict:
    """Create function block with input/output specifications."""
    
    # Add to prompt
    prompt_addition = """
Also generate input and output specifications for validation:
- input_specification: What files and data structures are expected
- output_specification: What files and data structures will be produced

For AnnData files, specify required columns in obs, var, uns, and obsm.
"""
    
    # The LLM will generate specifications along with the code
```

### 1. Fix Error Propagation in Bug Fixer

#### Implementation Steps:

1. **Track Error Evolution**
```python
class DebugSession:
    def __init__(self, ...):
        # Add error tracking
        self.error_history = []  # Track all errors encountered
        self.current_error = None
        self.error_evolution = []  # Track how errors change between attempts
```

2. **Capture New Errors After Each Fix**
```python
def _execute_and_capture_error(self):
    """Execute the function block and capture any new error."""
    result = self.action_executor.execute_action({
        'type': 'execute_command',
        'command': 'python /workspace/run.py'
    })
    
    if not result['success']:
        new_error = result.get('error', '')
        if new_error != self.current_error:
            self.error_evolution.append({
                'attempt': self.current_attempt,
                'previous_error': self.current_error,
                'new_error': new_error,
                'is_same': False
            })
            self.current_error = new_error
    
    return result
```

3. **Pass Error History to Next Attempt**
```python
def run_debug_session(self, ..., previous_attempts: Optional[List[Dict]] = None):
    # Include error evolution in context
    context = {
        'previous_attempts': previous_attempts or [],
        'error_history': self.error_history,
        'error_evolution': self.error_evolution
    }
```

### 2. Implement JSON Mode for LLM Responses

#### A. Add JSON Schema Support to LLM Service

```python
# In base_llm_service.py
def call_llm_with_json_schema(
    self, 
    messages: List[Dict[str, str]], 
    json_schema: Dict[str, Any],
    temperature: float = 0.1
) -> Dict[str, Any]:
    """Call LLM with JSON schema enforcement."""
    response = self.client.chat.completions.create(
        model=self.model,
        messages=messages,
        temperature=temperature,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "debug_response",
                "schema": json_schema,
                "strict": True
            }
        }
    )
    return json.loads(response.choices[0].message.content)
```

#### B. Define Schemas for Debug Actions

```python
# In debug_schemas.py
DEBUG_ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action_required": {"type": "boolean"},
        "action": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["read_file", "write_file", "execute_command", "install_package", "list_directory"]},
                "parameters": {"type": "object"}
            },
            "required": ["type", "parameters"]
        },
        "explanation": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1}
    },
    "required": ["action_required", "explanation"]
}

DEBUG_COMPLETION_SCHEMA = {
    "type": "object", 
    "properties": {
        "is_fixed": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "summary": {"type": "string"},
        "remaining_issues": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["is_fixed", "confidence", "summary"]
}
```

#### C. Update Debug Session to Use JSON Mode

```python
def _get_llm_action(self) -> Dict[str, Any]:
    """Get action from LLM using JSON mode."""
    response = self.llm_service.call_llm_with_json_schema(
        messages=self.messages,
        json_schema=DEBUG_ACTION_SCHEMA
    )
    
    # No parsing needed - response is already a dict
    if response['action_required']:
        return response['action'], response['explanation']
    else:
        return None, response['explanation']

def _check_if_fixed(self) -> Tuple[bool, str]:
    """Check if the bug is fixed using JSON mode."""
    check_messages = self.messages + [{
        "role": "user",
        "content": "Based on the actions taken, is the bug now fixed? Provide your assessment."
    }]
    
    response = self.llm_service.call_llm_with_json_schema(
        messages=check_messages,
        json_schema=DEBUG_COMPLETION_SCHEMA
    )
    
    return response['is_fixed'], response['summary']
```

### 3. Fix Orchestrator Node Creation Logic

#### A. Add Parent State Validation

```python
def _can_add_children_to_node(self, node: AnalysisNode) -> bool:
    """Check if children can be added to a node."""
    # Don't add children to failed nodes
    if node.state == NodeState.FAILED:
        return False
    
    # Don't add children to nodes that are still being debugged
    if node.state == NodeState.PENDING and node.debug_attempts > 0:
        return False
    
    # Check if node has valid output
    if node.state == NodeState.COMPLETED:
        # Verify output exists
        if not self._verify_node_output(node):
            logger.warning(f"Node {node.id} marked as completed but has no valid output")
            return False
    
    return True
```

#### B. Improve Expansion Decision Logic

```python
def _expand_tree(self, tree: AnalysisTree, user_request: str, context: Dict) -> bool:
    """Expand tree with new nodes only from successful parents."""
    # Get only truly successful leaf nodes
    successful_leaves = [
        node for node in tree.get_leaf_nodes()
        if node.state == NodeState.COMPLETED and self._verify_node_output(node)
    ]
    
    if not successful_leaves:
        logger.info("No successful leaf nodes to expand from")
        return self._check_if_satisfied(tree, user_request)
    
    # Continue with expansion...
```

### 4. Enhance Node State Tracking

#### A. Add Detailed State Information

```python
class NodeExecutionState:
    """Detailed execution state for a node."""
    def __init__(self):
        self.initial_execution_status: str = "pending"  # pending, success, failed
        self.debug_attempts: List[Dict] = []
        self.final_status: str = "pending"  # pending, success, failed
        self.has_valid_output: bool = False
        self.errors_encountered: List[str] = []
        self.fixes_applied: List[str] = []
```

#### B. Update Analysis Node Model

```python
# In models.py
class AnalysisNode(BaseModel):
    # ... existing fields ...
    execution_state: Optional[NodeExecutionState] = None
    
    def is_truly_successful(self) -> bool:
        """Check if node executed successfully (with or without debugging)."""
        return (
            self.state == NodeState.COMPLETED and
            self.execution_state and
            self.execution_state.has_valid_output
        )
```

### 5. Improve Debug Progress Tracking

#### A. Structured Debug Progress Format

```python
class DebugProgressTracker:
    """Track debug progress with structured format."""
    
    def __init__(self, progress_file: Path):
        self.progress_file = progress_file
        self.attempts = []
    
    def add_attempt(self, attempt_data: Dict):
        """Add a debug attempt with structured data."""
        attempt = {
            'timestamp': datetime.now().isoformat(),
            'attempt_number': len(self.attempts) + 1,
            'error': attempt_data.get('error'),
            'error_type': self._classify_error(attempt_data.get('error')),
            'actions_taken': attempt_data.get('actions', []),
            'files_modified': attempt_data.get('files_modified', []),
            'fix_applied': attempt_data.get('fix_applied'),
            'outcome': attempt_data.get('outcome'),  # success, failed, new_error
            'new_error': attempt_data.get('new_error') if attempt_data.get('outcome') == 'new_error' else None
        }
        self.attempts.append(attempt)
        self._save_progress()
```

## Implementation Priority

1. **High Priority** (Implement immediately):
   - Add function block input/output validation
   - Implement JSON mode for LLM responses
   - Fix error propagation between debug attempts
   - Fix orchestrator node creation logic

2. **Medium Priority** (Implement next):
   - Enhance node state tracking
   - Improve debug progress tracking
   - Add parent state validation

3. **Low Priority** (Nice to have):
   - Add debug session analytics
   - Implement fix pattern recognition
   - Add automated fix verification

## Testing Strategy

1. **Unit Tests**:
   - Test error propagation logic
   - Test JSON schema validation
   - Test node state transitions

2. **Integration Tests**:
   - Test full debug session with multiple errors
   - Test orchestrator with mixed success/failure nodes
   - Test parallel execution with dependencies

3. **Benchmark Tests**:
   - Run pseudotime benchmark with new implementation
   - Verify no child nodes created after failures
   - Verify error evolution tracking

## Success Metrics

1. **Bug Fixer**:
   - 100% of new errors after fixes are captured and passed to next attempt
   - 0% string parsing errors with JSON mode
   - Debug sessions complete in fewer attempts

2. **Orchestrator**:
   - 0 child nodes created after parent failures
   - 100% accurate node state tracking
   - Clear distinction between initial success and success after debugging

3. **Overall**:
   - Pseudotime benchmark completes successfully
   - All nodes that claim "completed" status have valid outputs
   - Debug logs clearly show error evolution

## Conclusion

These improvements will make the system more robust, reliable, and easier to debug. The JSON mode implementation will eliminate parsing errors, while proper error propagation will ensure the bug fixer can handle evolving errors effectively.