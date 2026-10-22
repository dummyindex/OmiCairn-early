# Job Review and Automatic Rework System

This document describes the enhanced job review and automatic rework system that ensures quality improvements when nodes fail job review, while preventing infinite loops.

## Overview

The system now features **automatic rework** without LLM involvement when job review fails. When the Job Reviewer Agent identifies critical quality issues (e.g., placeholder code, generated code that fakes the analysis, missing outputs), the system automatically creates a rework node. This system includes:

1. **Automatic Rework Creation**: System-driven, not LLM-decided
2. **Rework Counter**: Tracks how many times a task has been attempted
3. **Rework Limit**: Prevents infinite rework loops (default: 2 attempts)
4. **Context Propagation**: Automatic tracking via `propagate_failure_context_from`
5. **Enhanced Prompts**: Function creator receives specific guidance about failures

## Key Changes from Previous System

### Old System (LLM-Driven)
- Orchestrator LLM had to decide whether to create rework nodes
- Relied on LLM to set `propagate_failure_context_from` field
- Inconsistent rework tracking due to LLM variability
- Could miss rework opportunities or create infinite loops

### New System (System-Driven)
- **Automatic**: When `needs_rework=True`, orchestrator automatically creates rework action
- **No LLM Decision**: Rework is deterministic based on job review results
- **System Tracking**: `propagate_failure_context_from` is set automatically
- **Guaranteed Limits**: Hard enforcement of MAX_REWORK_ATTEMPTS

## Components

### 1. AnalysisNode Model (`models.py`)

Enhanced fields for rework tracking:

```python
# Job review fields
job_review_status: Optional[JobReviewStatus] = None
job_review_result: Optional[Dict[str, Any]] = None
job_review_summary: Optional[str] = None

# Rework tracking fields
needs_rework: bool = False  # Set by job reviewer when critical issues found
rework_attempts: int = 0  # Number of rework attempts for this task
original_task_name: Optional[str] = None  # Original task being reworked
rework_limit_reached: bool = False  # True when MAX_REWORK_ATTEMPTS hit
```

### 2. Constants (`constants.py`)

```python
MAX_REWORK_ATTEMPTS = 2  # Maximum rework attempts after job review failures
```

### 3. Main Agent - Job Review Integration (`agents/main_agent.py`)

The job review now happens immediately after node execution with automatic rework limit checking:

```python
# After job review fails a node
if review_result.passed:
    node.job_review_status = JobReviewStatus.PASSED
    node.needs_rework = False
else:
    node.job_review_status = JobReviewStatus.FAILED
    
    # Check rework limit IMMEDIATELY after review
    if node.rework_attempts >= MAX_REWORK_ATTEMPTS:
        logger.warning(f"Node {node.id} has reached rework limit")
        node.needs_rework = False
        node.rework_limit_reached = True
    else:
        node.needs_rework = True  # Will trigger automatic rework
        node.rework_limit_reached = False
```

### 4. Orchestrator Agent - Automatic Rework (`agents/orchestrator_agent.py`)

The orchestrator now automatically handles rework WITHOUT consulting the LLM:

```python
def plan_next_steps(self, task):
    # FIRST: Check for automatic rework (no LLM involved)
    rework_actions = []
    for node_info in tree_state.get('nodes', []):
        if node_info.get('needs_rework', False):
            # Automatic rework action creation
            node_id = node_info['id']
            node_name = node_info['name']
            
            rework_action = {
                "type": "create_new",
                "name": f"{node_name}_rework",
                "specification": {
                    "name": node_name,
                    "description": ...,
                    "task": ...,
                    # System sets this automatically, not LLM!
                    "propagate_failure_context_from": node_id
                }
            }
            rework_actions.append(rework_action)
    
    if rework_actions:
        # Return immediately without LLM consultation
        return {
            "satisfied": False,
            "reasoning": "Automatic rework for quality issues",
            "next_actions": rework_actions
        }
    
    # Only consult LLM if no automatic rework needed
    return self._plan_with_llm(...)
```

### 5. Context Propagation (`agents/main_agent.py`)

When creating a rework node, context is automatically inherited:

```python
# Automatic context propagation from failed node
if spec.get('propagate_failure_context_from'):
    source_node_id = spec['propagate_failure_context_from']
    source_node = tree.nodes[source_node_id]
    
    # Inherit rework counter
    rework_count = source_node.rework_attempts + 1
    original_task = source_node.original_task_name or source_node.function_block.name
    
    # Set on new node
    node.rework_attempts = rework_count
    node.original_task_name = original_task
    
    # Clear needs_rework flag (new attempt starting)
    source_node.needs_rework = False
```

## Workflow

### 1. Initial Node Execution
```
Node executes → Success/Failure → Job Review
```

### 2. Job Review Decision
```
If quality issues found:
  → Check rework attempts < MAX_REWORK_ATTEMPTS
  → If under limit: Set needs_rework=True
  → If at limit: Set rework_limit_reached=True
```

### 3. Orchestrator Automatic Action
```
Sees needs_rework=True → Creates rework action automatically
No LLM involvement → Returns action immediately
```

### 4. Rework Node Creation
```
Main agent creates node → Sets propagate_failure_context_from
Increments rework_attempts → Tracks original_task_name
```

### 5. Function Creator Enhancement
```
Receives failure context → Generates improved implementation
Addresses specific issues → Avoids previous mistakes
```

## Example Flow

```
1. User: "Perform clustering analysis with visualization"

2. Node created: clustering_analysis
   - Implementation uses placeholder data
   - Execution: ✅ completed
   - Job Review: ❌ failed (generated code used np.linspace instead of real clustering)
   - Sets: needs_rework=True, rework_attempts=0

3. Orchestrator (automatic, no LLM):
   - Sees needs_rework=True
   - Creates rework action with propagate_failure_context_from="node_001"
   
4. New node created: clustering_analysis (attempt #1)
   - Inherits: rework_attempts=1, original_task_name="clustering_analysis"
   - Function creator receives context about placeholder issue
   - Implements real clustering
   
5. If still fails:
   - rework_attempts=1 < MAX_REWORK_ATTEMPTS=2
   - Another automatic rework created
   
6. After 2 attempts:
   - rework_limit_reached=True
   - No more automatic reworks
   - Orchestrator must find alternative approach
```

## Root Node Exception

The system includes special handling for the data loading root node:

```python
# Skip job review for system-generated root node
if node.function_block.name == ROOT_NODE_NAME and not node.parent_id:
    node.job_review_status = JobReviewStatus.SKIPPED
    node.job_review_summary = "System-generated root node - review skipped"
    return
```

## Orchestrator Satisfaction Criteria

The orchestrator prompt now explicitly states:

```
SATISFACTION CRITERIA:
- CRITICAL: The data loading root node (load_input_data) does NOT count as satisfying analysis requests!
  * This node only loads/passes through data - it performs NO analysis
  * If only the root node exists, the actual analysis has NOT started yet
- NEVER mark satisfied=true if only the root node exists, unless loading data was the only request
```

## Benefits

1. **Deterministic Behavior**: No LLM variability in rework decisions
2. **Guaranteed Limits**: Hard enforcement prevents infinite loops
3. **Automatic Tracking**: System handles all context propagation
4. **Faster Response**: No LLM call needed for rework decisions
5. **Clear Accountability**: System logs show automatic decisions
6. **Quality Focus**: Ensures issues are addressed systematically

## Configuration

Adjust rework limits in `constants.py`:

```python
MAX_REWORK_ATTEMPTS = 3  # Increase for more attempts
```

## Testing

Key test files:
- `tests/test_rework_with_context_propagation.py` - Rework node creation and context propagation
- `tests/agents/test_job_reviewer_complete.py` - Job reviewer agent

## Monitoring

Look for these log messages:

```
# Automatic rework creation
"Node {id} needs rework - creating rework action automatically"

# Limit reached
"Node {id} has reached rework limit (2 attempts). Not setting needs_rework."

# Context propagation
"Inheriting rework count from node {id}: attempt #2"
```

## Troubleshooting

### Issue: Rework not happening
- Check `needs_rework` flag is set to True
- Verify `rework_attempts < MAX_REWORK_ATTEMPTS`
- Ensure orchestrator is being called after job review

### Issue: Infinite rework attempts
- Verify MAX_REWORK_ATTEMPTS is set properly
- Check that rework_limit_reached is being set
- Ensure rework counter is incrementing

### Issue: Context not propagating
- Verify `propagate_failure_context_from` is set
- Check source node exists in tree
- Ensure context extraction logic is working