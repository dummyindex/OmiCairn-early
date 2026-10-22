# Parallel Execution System

## Overview

The OmiCairn Agent system supports parallel execution of analysis nodes, allowing multiple independent branches of an analysis tree to execute simultaneously. This significantly reduces overall execution time for complex analysis workflows.

## Architecture

### Core Components

#### 1. JobPool (`job_executors/job_pool.py`)
The JobPool manages concurrent job execution with configurable limits.

**Key Features:**
- **Configurable parallelism**: Set max number of concurrent jobs via `max_parallel_jobs`
- **Priority scheduling**: Jobs execute based on priority scores
- **Dependency management**: Jobs wait for dependencies before executing
- **Callback system**: Notifies on job completion for reactive processing
- **Resource management**: Automatic cleanup and resource tracking

**Configuration:**
```python
from omicairn_agent_local.job_executors import JobPool

pool = JobPool(
    max_parallel_jobs=3,        # Max concurrent jobs
    executor_type="thread",     # "thread" or "process"
    enable_callbacks=True,      # Enable completion callbacks
    callback_timeout=30.0       # Callback timeout in seconds
)
```

#### 2. OrchestratorAgent Integration
The orchestrator agent leverages the JobPool for parallel node execution.

**Key Features:**
- **Reactive expansion**: Immediately processes node results upon completion
- **Smart scheduling**: Analyzes dependencies to maximize parallelism
- **Automatic branching**: Creates parallel branches based on analysis needs

**Usage:**
```python
orchestrator = OrchestratorAgent(
    tree_manager=tree_manager,
    function_selector=selector,
    bug_fixer=fixer,
    max_parallel_jobs=3,        # Parallel execution limit
    enable_reactive=True        # Enable reactive processing
)
```

## Execution Flow

### 1. Sequential vs Parallel Execution

#### Sequential (Traditional)
```
Node A → Complete → Node B → Complete → Node C → Complete
        (5 min)           (5 min)           (5 min)
        Total: 15 minutes
```

#### Parallel (With JobPool)
```
Node A → Complete
        ├→ Node B (5 min) ─┐
        └→ Node C (5 min) ─┴→ Complete
        Total: 10 minutes (A + max(B,C))
```

### 2. Dependency Resolution

The system automatically resolves dependencies:

```python
# Node structure
Root
├── Child1 (depends on Root)
│   ├── Grandchild1 (depends on Child1)
│   └── Grandchild2 (depends on Child1)
└── Child2 (depends on Root)
    └── Grandchild3 (depends on Child2)

# Execution order (with max_parallel_jobs=2)
Step 1: Root executes alone
Step 2: Child1 and Child2 execute in parallel
Step 3: Grandchild1 and Grandchild2 execute in parallel
Step 4: Grandchild3 executes
```

### 3. Reactive Node Expansion

When a node completes, the orchestrator immediately:
1. Receives completion callback
2. Analyzes node results
3. Decides on expansion (new child nodes)
4. Submits new jobs to the pool

```python
def _handle_node_completion(self, node_id: str, result: JobResult):
    """Callback for reactive expansion."""
    if result.status == JobStatus.COMPLETED:
        # Analyze results
        should_expand = self._analyze_results(result)
        
        if should_expand:
            # Create child nodes
            new_nodes = self._create_child_nodes(node_id)
            
            # Submit to job pool
            for node in new_nodes:
                self.job_pool.submit_job(node)
```

## Job States and Lifecycle

### Job States
- **PENDING**: Job created but not yet started
- **WAITING**: Waiting for dependencies
- **READY**: Dependencies met, ready to execute
- **RUNNING**: Currently executing
- **COMPLETED**: Successfully finished
- **FAILED**: Execution failed
- **CANCELLED**: Manually cancelled
- **TIMEOUT**: Exceeded time limit

### State Transitions
```
PENDING → WAITING → READY → RUNNING → COMPLETED
                      ↓         ↓          ↓
                  CANCELLED  FAILED    TIMEOUT
```

## Configuration Options

### JobPool Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_parallel_jobs` | int | 3 | Maximum concurrent jobs |
| `executor_type` | str | "thread" | Executor type: "thread" or "process" |
| `enable_callbacks` | bool | True | Enable completion callbacks |
| `callback_timeout` | float | 30.0 | Callback timeout in seconds |
| `job_timeout` | float | 3600.0 | Default job timeout |
| `priority_queue` | bool | True | Use priority scheduling |
| `max_retries` | int | 0 | Max retry attempts for failed jobs |

### Orchestrator Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_parallel_jobs` | int | 3 | Passed to JobPool |
| `enable_reactive` | bool | True | Enable reactive expansion |
| `expansion_strategy` | str | "adaptive" | Node expansion strategy |
| `priority_strategy` | str | "depth_first" | Job priority assignment |

## Usage Examples

### Example 1: Basic Parallel Execution

```python
from omicairn_agent_local.job_executors import JobPool
from omicairn_agent_local.models import Job, JobStatus

# Create job pool
pool = JobPool(max_parallel_jobs=3)

# Submit jobs
job1 = Job(
    id="job1",
    name="Quality Control",
    execute_fn=lambda: run_qc(data),
    priority=10
)

job2 = Job(
    id="job2", 
    name="Normalization",
    execute_fn=lambda: normalize(data),
    priority=10,
    dependencies=["job1"]
)

job3 = Job(
    id="job3",
    name="Feature Selection",
    execute_fn=lambda: select_features(data),
    priority=10,
    dependencies=["job1"]
)

# Submit all jobs
pool.submit_job(job1)
pool.submit_job(job2)
pool.submit_job(job3)

# Wait for completion
pool.wait_all()

# job2 and job3 execute in parallel after job1 completes
```

### Example 2: Analysis Tree with Parallel Branches

```python
from omicairn_agent_local.agents import OrchestratorAgent
from omicairn_agent_local.analysis_tree_management import AnalysisTreeManager

# Create tree manager
tree_manager = AnalysisTreeManager()

# Create analysis tree
tree = tree_manager.create_tree(
    user_request="Perform comprehensive single-cell analysis",
    input_data_path="/data/pbmc.h5ad",
    max_nodes=20,
    max_children_per_node=3
)

# Configure orchestrator for parallel execution
orchestrator = OrchestratorAgent(
    tree_manager=tree_manager,
    max_parallel_jobs=4,  # Run up to 4 nodes simultaneously
    enable_reactive=True   # React immediately to completions
)

# Execute tree with parallel processing
context = {
    "tree": tree,
    "user_request": tree.user_request,
    "max_iterations": 10
}

result = orchestrator.process(context)

# The orchestrator will:
# 1. Execute root node
# 2. Create multiple child branches based on analysis
# 3. Execute branches in parallel (up to 4 at once)
# 4. Reactively expand nodes as they complete
```

### Example 3: Function Block Following Framework

```python
def run(adata=None, **parameters):
    """
    Function block following framework conventions.
    Compatible with parallel execution.
    """
    import scanpy as sc
    import os
    
    # Standard input loading (FRAMEWORK CONVENTION)
    if adata is None:
        adata = sc.read_h5ad('/workspace/input/_node_anndata.h5ad')
    
    print(f"Processing {adata.n_obs} cells")
    
    # Perform analysis
    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.normalize_total(adata)
    sc.pp.log1p(adata)
    
    # Standard output saving (FRAMEWORK CONVENTION)
    os.makedirs('/workspace/output', exist_ok=True)
    adata.write('/workspace/output/_node_anndata.h5ad')
    
    return adata
```

## Performance Considerations

### Thread vs Process Executors

**Thread Executor** (`executor_type="thread"`):
- Best for I/O-bound tasks
- Lower memory overhead
- Shared memory between jobs
- Good for most bioinformatics pipelines

**Process Executor** (`executor_type="process"`):
- Best for CPU-bound tasks
- Higher memory overhead
- Isolated memory spaces
- Better for compute-intensive operations

### Optimization Tips

1. **Set appropriate parallelism level**:
   - Too low: Underutilized resources
   - Too high: Resource contention, memory issues
   - Recommended: Number of CPU cores - 1

2. **Use priority effectively**:
   ```python
   # Higher priority for critical path
   critical_job.priority = 100
   optional_job.priority = 10
   ```

3. **Manage dependencies wisely**:
   - Minimize dependency chains
   - Group independent tasks
   - Use callbacks for dynamic dependencies

4. **Monitor resource usage**:
   ```python
   status = pool.get_status()
   print(f"Running jobs: {status['running_jobs']}")
   print(f"Queue size: {status['queue_size']}")
   print(f"Total processed: {status['total_processed']}")
   ```

## Error Handling

### Job Failure Handling

```python
# Configure retry policy
pool = JobPool(
    max_parallel_jobs=3,
    max_retries=2,  # Retry failed jobs twice
    retry_delay=5.0  # Wait 5 seconds between retries
)

# Handle failures in callbacks
def handle_completion(job_id, result):
    if result.status == JobStatus.FAILED:
        logger.error(f"Job {job_id} failed: {result.error}")
        # Implement recovery logic
    elif result.status == JobStatus.TIMEOUT:
        logger.warning(f"Job {job_id} timed out")
        # Handle timeout

pool.register_callback(handle_completion)
```

### Graceful Shutdown

```python
try:
    # Execute jobs
    pool.wait_all(timeout=3600)
except KeyboardInterrupt:
    # Graceful shutdown
    pool.shutdown(wait=True, timeout=30)
    logger.info("Shutdown complete")
```

## Monitoring and Debugging

### Logging

The system provides comprehensive logging:

```python
import logging

# Enable debug logging
logging.getLogger("omicairn_agent_local.job_pool").setLevel(logging.DEBUG)

# Logs show:
# - Job submission and scheduling
# - State transitions
# - Dependency resolution
# - Callback execution
# - Resource usage
```

### Metrics Collection

```python
# Get pool metrics
metrics = pool.get_metrics()

print(f"Total jobs processed: {metrics['total_processed']}")
print(f"Average wait time: {metrics['avg_wait_time']:.2f}s")
print(f"Average execution time: {metrics['avg_execution_time']:.2f}s")
print(f"Success rate: {metrics['success_rate']:.1%}")
```

### Visualization

```python
# Export execution timeline
timeline = pool.export_timeline()

# Visualize with matplotlib
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(12, 6))
for job in timeline:
    ax.barh(job['id'], job['duration'], 
            left=job['start_time'], height=0.8)

ax.set_xlabel('Time (seconds)')
ax.set_ylabel('Job ID')
ax.set_title('Parallel Execution Timeline')
plt.tight_layout()
plt.show()
```

## Best Practices

### 1. Design for Parallelism
- Keep nodes independent when possible
- Minimize shared state
- Use standard I/O conventions

### 2. Handle Data Flow
- Follow framework conventions for input/output
- Use `/workspace/input/_node_anndata.h5ad` for input
- Save to `/workspace/output/_node_anndata.h5ad`

### 3. Resource Management
- Set reasonable timeouts
- Monitor memory usage
- Clean up temporary files

### 4. Testing
- Test with various parallelism levels
- Verify dependency handling
- Test failure scenarios

### 5. Production Deployment
- Start with conservative parallelism
- Monitor system resources
- Implement proper logging
- Set up alerting for failures

## Troubleshooting

### Common Issues

**Issue**: Jobs not executing in parallel
- Check `max_parallel_jobs` setting
- Verify no unnecessary dependencies
- Check executor type matches workload

**Issue**: Memory errors with high parallelism
- Reduce `max_parallel_jobs`
- Switch to process executor
- Implement memory monitoring

**Issue**: Deadlocks in dependency resolution
- Check for circular dependencies
- Verify dependency IDs are correct
- Enable debug logging

**Issue**: Callbacks not firing
- Verify `enable_callbacks=True`
- Check callback timeout settings
- Ensure callback functions are thread-safe

## Future Enhancements

### Planned Features
1. **Distributed Execution**: Support for multi-machine clusters
2. **Dynamic Scaling**: Auto-adjust parallelism based on resources
3. **Cost Optimization**: Choose execution strategy based on cost
4. **Advanced Scheduling**: ML-based job scheduling
5. **Checkpoint/Resume**: Save and restore execution state

### Integration Points
- AWS Batch for cloud execution
- Kubernetes for container orchestration
- Apache Airflow for workflow management
- Ray for distributed computing

## References

- [Function Block Framework](../FUNCTION_BLOCK_FRAMEWORK.md)
- [Analysis Tree Structure](../core/ANALYSIS_TREE_STRUCTURE.md)

> Note: this guide partly describes intended APIs of an early-stage prototype; check the code for what is implemented.