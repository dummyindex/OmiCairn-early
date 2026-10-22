# State System Guide

This document clarifies the different state systems used in the omicairn-agent-local codebase.

## Overview

The system uses three separate state tracking mechanisms:

1. **Node States** (`NodeState`) - Tracks the execution lifecycle of analysis nodes
2. **Job States** (`JobStatus`) - Tracks the container job execution status
3. **Job Review Statuses** - Tracks the quality review results of completed nodes

## 1. Node States (NodeState enum)

Node states track the high-level execution lifecycle of an `AnalysisNode`.

### Definition
```python
class NodeState(str, Enum):
    PENDING = "pending"      # Node created but not yet executed
    RUNNING = "running"      # Currently being executed
    COMPLETED = "completed"  # Execution finished successfully
    FAILED = "failed"       # Execution failed with errors
    DEBUGGING = "debugging"  # In debug/fix cycle
    SKIPPED = "skipped"     # Skipped (e.g., due to parent failure)
```

### Usage
- **Field**: `AnalysisNode.state`
- **Purpose**: Tracks whether a node has been executed and its execution outcome
- **Set by**: MainAgent, NodeExecutor, TreeManager
- **Read by**: Orchestrator, TreeVisualizer, MainAgent

### State Transitions
```
PENDING → RUNNING → COMPLETED
                 ↘ FAILED → DEBUGGING → COMPLETED/FAILED
```

## 2. Job States (JobStatus enum)

Job states track the low-level container execution status.

### Definition
```python
class JobStatus(str, Enum):
    PENDING = "pending"      # Job queued but not started
    RUNNING = "running"      # Container is running
    SUCCESS = "success"      # Container exited with code 0
    FAILED = "failed"       # Container exited with non-zero code
    TIMEOUT = "timeout"     # Container exceeded time limit
    CANCELLED = "cancelled" # Job was cancelled
```

### Usage
- **Field**: `JobInfo.status`
- **Purpose**: Tracks Docker container execution status
- **Set by**: JobExecutor, JobPool
- **Read by**: NodeExecutor (to set node state)

### Relationship to Node States
- `JobStatus.SUCCESS` → `NodeState.COMPLETED`
- `JobStatus.FAILED/TIMEOUT` → `NodeState.FAILED`

## 3. Job Review Statuses (JobReviewStatus enum)

Job review statuses track the quality assessment of completed nodes.

### Definition
```python
class JobReviewStatus(str, Enum):
    PASSED = "passed"           # Output meets quality standards
    FAILED = "failed"           # Quality issues identified
    NOT_REVIEWED = "not_reviewed" # Not yet reviewed (default)
    SKIPPED = "skipped"         # Review skipped (e.g., system nodes)
```

### Usage
- **Field**: `AnalysisNode.job_review_status`
- **Purpose**: Tracks quality review outcome separate from execution status
- **Set by**: JobReviewerAgent, MainAgent
- **Read by**: Orchestrator, TreeVisualizer

### Key Points
- **Independent of execution**: A node can be `COMPLETED` but `JOB_REVIEW_FAILED`
- **Triggers rework**: Failed reviews can trigger node rework
- **Optional**: Not all nodes are reviewed

## Migration Complete

All state-related constants have been migrated to enums in `models.py`:
- `NodeState` - For node execution lifecycle
- `JobStatus` - For container execution status  
- `JobReviewStatus` - For quality review results

The old constants have been removed from `constants.py`.

## Field Mappings

### AnalysisNode Fields

| Field | Type | Values | Purpose |
|-------|------|---------|---------|
| `state` | `NodeState` | PENDING, RUNNING, COMPLETED, FAILED, etc. | Execution lifecycle |
| `job_review_status` | `Optional[JobReviewStatus]` | PASSED, FAILED, NOT_REVIEWED, SKIPPED | Quality review result |

### JobInfo Fields

| Field | Type | Values | Purpose |
|-------|------|---------|---------|
| `status` | `JobStatus` | PENDING, RUNNING, SUCCESS, FAILED, etc. | Container execution status |

## Example Scenarios

### Successful Node
```python
node.state = NodeState.COMPLETED
node.job_review_status = JobReviewStatus.PASSED
# Execution successful, output quality good
```

### Failed Execution
```python
node.state = NodeState.FAILED
node.job_review_status = JobReviewStatus.NOT_REVIEWED
# Execution failed, no review needed
```

### Poor Quality Output
```python
node.state = NodeState.COMPLETED
node.job_review_status = JobReviewStatus.FAILED
node.needs_rework = True
# Execution successful but output has issues
```

### System Node
```python
node.state = NodeState.COMPLETED
node.job_review_status = JobReviewStatus.SKIPPED
# System nodes like data loading are not reviewed
```

## Best Practices

1. **Use enums consistently**: Always use `NodeState.COMPLETED`, `JobReviewStatus.FAILED`, etc.
2. **Import from models**: All state enums are in `models.py`
3. **Keep states independent**: Execution status and review status are separate concerns
4. **Don't mix state types**: JobStatus is for containers, NodeState is for analysis nodes

## Usage Examples

```python
from models import NodeState, JobReviewStatus, JobStatus

# Creating a node
node = AnalysisNode(
    state=NodeState.PENDING,
    job_review_status=JobReviewStatus.NOT_REVIEWED,
    # ... other fields
)

# Checking states
if node.state == NodeState.COMPLETED:
    # Node executed successfully
    pass

if node.job_review_status == JobReviewStatus.FAILED:
    # Quality issues detected
    pass
```