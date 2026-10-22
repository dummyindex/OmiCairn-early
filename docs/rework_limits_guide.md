# Rework Limits Guide

This document explains how the omicairn-agent-local system handles rework limits with the new automatic rework system to prevent infinite loops when job review fails nodes repeatedly.

## Overview

When the Job Reviewer identifies critical quality issues, the system **automatically** triggers rework without LLM involvement. To prevent infinite rework loops, the system enforces a maximum rework limit with immediate checking after job review.

## Key Components

### 1. Rework Counter (`AnalysisNode.rework_attempts`)

Each node tracks how many times its task has been reworked:
- `rework_attempts = 0`: Original implementation
- `rework_attempts = 1`: First rework attempt
- `rework_attempts = 2`: Second rework attempt (hits the limit)

### 2. Rework Limit (`MAX_REWORK_ATTEMPTS`)

Defined in `constants.py`:
```python
MAX_REWORK_ATTEMPTS = 2  # Maximum times to rework a node after job review failures
```

### 3. New Automatic Enforcement

#### Immediate Limit Check (MainAgent)
Right after job review, before orchestrator involvement:

```python
# In MainAgent._apply_job_review()
if review_result.failed:
    node.job_review_status = JobReviewStatus.FAILED
    
    # Check limit IMMEDIATELY
    if node.rework_attempts >= MAX_REWORK_ATTEMPTS:
        logger.warning(f"Node {node.id} has reached rework limit")
        node.needs_rework = False  # Don't trigger automatic rework
        node.rework_limit_reached = True
    else:
        node.needs_rework = True  # Will trigger automatic rework
```

#### Automatic Rework Creation (Orchestrator)
No LLM decision needed:

```python
# In OrchestratorAgent.plan_next_steps()
# FIRST thing checked - before any LLM call
for node_info in tree_state.get('nodes', []):
    if node_info.get('needs_rework', False):
        # Automatic rework action - no LLM involved
        create_rework_action(node_info)
```

#### Prevention of Excess Attempts (MainAgent)
Double-check when creating nodes:

```python
# When creating a rework node
if spec.get('propagate_failure_context_from'):
    source_node = tree.nodes[source_node_id]
    next_rework_count = source_node.rework_attempts + 1
    
    if next_rework_count > MAX_REWORK_ATTEMPTS:
        logger.warning("Skipping - would exceed rework limit")
        continue  # Skip this action
```

## How Limits Are Enforced

### Old System (LLM-Based)
1. Job review fails → Node marked as failed
2. Orchestrator LLM sees failure → May or may not suggest rework
3. LLM counts attempts → May miscount or ignore limits
4. Inconsistent enforcement

### New System (Automatic)
1. Job review fails → System checks `rework_attempts`
2. Under limit → Sets `needs_rework=True` automatically
3. At limit → Sets `rework_limit_reached=True` automatically
4. Orchestrator sees `needs_rework` → Creates rework immediately (no LLM)
5. **Guaranteed enforcement** at every level

## Alternative Approaches When Limit Reached

When `rework_limit_reached=True`, the orchestrator LLM is informed and suggests:

### 1. Task Decomposition
```python
# Instead of one complex node
"analyze_and_visualize_everything"

# Break into simpler nodes
"prepare_data" → "run_analysis" → "create_plots" → "save_results"
```

### 2. Alternative Methods
```python
# If scFates keeps failing after 2 attempts
# Try simpler alternatives
"use_dpt_pseudotime" or "use_palantir" instead
```

### 3. Simplify Requirements
- Reduce number of outputs
- Use simpler algorithms
- Process subset of data

### 4. Skip Non-Critical Steps
- Continue with downstream analyses if possible
- Focus on core objectives
- Document what was skipped

### 5. Manual Intervention Notes
- Create summary of attempts
- Document manual steps needed
- Export intermediate data for external processing

## Example Scenario with New System

```
User Request: "Perform clustering with visualization"

Attempt 1: clustering_analysis (rework_attempts=0)
- Execution: ✅ completed
- Job Review: ❌ FAILED - Uses placeholder data (np.linspace)
- System Action: Sets needs_rework=True (0 < 2)

Orchestrator (automatic):
- Sees needs_rework=True
- Creates rework without LLM consultation
- Sets propagate_failure_context_from="node_001"

Attempt 2: clustering_analysis (rework_attempts=1)
- Execution: ✅ completed  
- Job Review: ❌ FAILED - Still using fake data
- System Action: Sets needs_rework=True (1 < 2)

Orchestrator (automatic):
- Creates second rework immediately

Attempt 3: clustering_analysis (rework_attempts=2)
- Execution: ✅ completed
- Job Review: ❌ FAILED - Persistent issues
- System Action: Sets rework_limit_reached=True (2 >= 2)
- NO needs_rework flag set

Orchestrator (LLM consulted):
- No automatic rework triggered
- LLM suggests alternative: "simple_kmeans_clustering"
```

## System Responses at Limit

### 1. Node Flags
```python
node.needs_rework = False  # Prevents automatic rework
node.rework_limit_reached = True  # Signals limit hit
node.job_review_summary += "\n[System: Rework limit reached after 2 attempts]"
```

### 2. Orchestrator Prompt
```
The following nodes have hit rework limits:
- clustering_analysis: 2 rework attempts (LIMIT REACHED)
  Cannot create another rework of this task
  Consider alternative approaches listed above
```

### 3. Logging
```
WARNING - Node {id} has reached rework limit (2 attempts). Not setting needs_rework.
INFO - Rework limit reached for task 'clustering_analysis'
```

## Benefits of New System

1. **Deterministic Limits**: No LLM variability in enforcement
2. **Immediate Checking**: Limits checked right after job review
3. **Automatic Tracking**: System handles all counters
4. **Clear State**: `rework_limit_reached` flag is explicit
5. **No Infinite Loops**: Guaranteed prevention

## Configuration

To adjust the rework limit:

```python
# In constants.py
MAX_REWORK_ATTEMPTS = 3  # Allow more attempts

# Or for testing
MAX_REWORK_ATTEMPTS = 1  # Fail fast for development
```

## Best Practices

1. **Set Appropriate Limits**: 
   - Production: 2-3 attempts (balanced)
   - Development: 1 attempt (fail fast)
   - Complex tasks: 3-5 attempts (more tolerance)

2. **Clear Job Reviews**: Ensure job reviewer provides specific, actionable feedback

3. **Context Propagation**: Always use `propagate_failure_context_from` for rework nodes

4. **Alternative Planning**: Have backup approaches for critical functionality

5. **Monitor Patterns**: Track which tasks frequently hit limits to improve prompts

## Troubleshooting

### Rework Not Triggering
- Check `needs_rework` flag after job review
- Verify `rework_attempts < MAX_REWORK_ATTEMPTS`
- Ensure job review is actually failing the node

### Too Many Reworks
- Verify limit is being checked after job review
- Check `rework_limit_reached` is set properly
- Ensure counter increments correctly

### Context Not Passed
- Verify `propagate_failure_context_from` is set
- Check source node exists
- Ensure new node inherits `rework_attempts`

## Testing

Key test files:
- `tests/test_rework_with_context_propagation.py` - Rework flow and limits