# Input/Output Specification Implementation

## Overview

This document describes the hybrid approach implemented for handling input/output file specifications in the omicairn-agent-local system.

## Changes Implemented

### 1. Optional Validation Enforcement

**Change**: Added `enforce_validation: bool = False` to `StaticConfig` model

**Location**: `models.py`
```python
class StaticConfig(BaseModel):
    # ... existing fields ...
    input_specification: Optional[InputSpecification] = None
    output_specification: Optional[OutputSpecification] = None
    enforce_validation: bool = False  # Optional enforcement, controlled by function block developer
```

**Impact**: 
- Function block developers can now control whether validation is enforced
- Default is `False` - validation errors are logged but don't fail execution
- When `True` - validation failures will fail the execution

**Modified**: `job_executors/interactive_executor.py`
- Added check for `enforce_validation` flag
- Input/output validation only fails execution when enforcement is enabled
- Otherwise, validation errors are logged as warnings

### 2. Output Description Field

**Change**: Added `output_description: Optional[str]` to `NewFunctionBlock`

**Location**: `models.py`
```python
class NewFunctionBlock(FunctionBlock):
    # ... existing fields ...
    output_description: Optional[str] = None  # Descriptive explanation of outputs produced
```

**Purpose**: Allows function blocks to document what they produce, helping downstream nodes understand available data.

### 3. Enhanced Prompts for File Conventions

#### Function Creator Agent Prompt Updates

**Location**: `agents/function_creator_agent.py`

**Added sections**:

1. **File Conventions for Single-Cell Genomics**:
   - Clear explanation of standard naming convention
   - Distinction between root nodes and downstream nodes
   - Emphasis on defensive coding

2. **Input Directory Structure**:
   - Shows available files in input directory
   - Can display full directory tree if provided
   - Helps LLM understand actual file context

3. **Output Description Requirements**:
   - Requires description of what the node produces
   - Asks for details about new columns, files, plots
   - Provides examples of good descriptions

#### Bug Fixer Prompt Updates

**Location**: `agents/unified_bug_fixer/prompt_templates.py`

**Added**:
- File convention guidelines for single-cell genomics pipeline
- Reminder about standard input/output naming
- Note about checking actual files if standard names don't exist

## Usage Example

### Function Block with Output Description

```python
block = NewFunctionBlock(
    name="leiden_clustering",
    type=FunctionBlockType.PYTHON,
    description="Perform Leiden clustering on the dataset",
    code=clustering_code,
    requirements="scanpy\nleiden",
    output_description="Adds cluster labels to adata.obs['leiden']. Generates UMAP plot colored by clusters as 'umap_clusters.png'."
)
```

### Function Block with Optional Validation

```python
static_config = StaticConfig(
    args=[],
    description="Trajectory inference",
    tag="trajectory",
    input_specification=InputSpecification(
        required_files=[{"name": "_node_anndata.h5ad", "type": "anndata"}]
    ),
    output_specification=OutputSpecification(
        output_files=[{"name": "_node_anndata.h5ad", "type": "anndata"}]
    ),
    enforce_validation=True  # Strictly enforce for this critical node
)
```

## Benefits

1. **Flexibility**: Function block developers control validation enforcement
2. **Better Context**: LLM receives actual directory structure and file information
3. **Documentation**: Output descriptions help downstream nodes understand data
4. **Hybrid Approach**: Maintains conventions while allowing flexibility

## Testing Notes (historical)

> These notes record development-time testing. The test scripts named below are not included in this
> release and the results have not been re-verified against this version of the code.

### ✅ Mock LLM Tests (Completed)
Created comprehensive mock tests validating:
- Input directory information gathering
- Parent output descriptions in prompts
- Output description storage in metadata  
- Enhanced file convention prompts
- JSON schema requirements for output descriptions

**Location**: `tests/test_enhanced_prompts_mock.py`
**Result (reported during development)**: all 6 tests passed

### ✅ OpenAI 4o-mini Integration Tests (Completed) 
Validated enhanced features with real LLM:
- Function creator generates proper naming conventions
- Comprehensive output descriptions provided automatically
- Directory tree information gathered and used effectively
- Parent-child node communication via output descriptions
- Optional validation enforcement correctly configured

**Location**: `test_openai_4o_mini.py`
**Result (reported during development)**: tests passed

### ✅ Pseudotime Benchmark Integration (Completed)
Full system test demonstrating:
- Enhanced prompts working in complex analysis pipeline
- Proper file convention usage throughout workflow
- Interactive debugging with enhanced context
- Adaptive orchestration using output descriptions
- Complete end-to-end functionality

**Result (reported during development)**: the pipeline ran end to end on a multi-step pseudotime analysis

## Implementation Status

✅ **COMPLETED**: All planned features implemented and tested
- Optional validation enforcement (default: False)
- Enhanced prompts with file conventions and directory info
- Parent output descriptions flowing to child nodes
- Metadata storage system for output descriptions  
- Comprehensive testing suite (mock + real LLM + integration)

## Usage Recommendations

1. **Enable enhanced features** by default - no configuration needed
2. **Use output descriptions** to document what each node produces
3. **Set enforce_validation=True** only for critical nodes requiring strict validation
4. **Review generated function blocks** - LLM-generated code should always be reviewed
5. **Test with mock LLM** first when developing new features