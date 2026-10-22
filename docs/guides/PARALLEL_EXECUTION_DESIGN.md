# Parallel Execution Design

## Overview

This document describes the parallel execution system implemented for the OmiCairn Agent Local system. The design enables efficient parallel processing of analysis nodes while maintaining proper dependencies and enabling reactive expansion.

## Architecture

### Core Components

#### 1. JobPool
The `JobPool` class manages parallel job execution with configurable limits.

**Key Features:**
- Configurable maximum parallel jobs
- Priority-based job scheduling
- Dependency management
- Callback notifications
- Thread/process/async executor support

**Design Principles:**
- Separation of job management from subprocess execution
- Future-ready for distributed execution (AWS, multi-machine)
- Clean abstraction for different executor types

#### 2. Enhanced Orchestrator Agent
The orchestrator agent has been updated to leverage the job pool for parallel execution.

**New Capabilities:**
- Parallel node execution with dependency tracking
- Reactive node expansion on completion
- Real-time decision making
- No direct subprocess management

### Execution Flow

```
1. Job Submission
   ├── Node submitted to job pool
   ├── Dependencies checked
   └── Job queued with priority

2. Job Execution
   ├── Worker thread picks up job
   ├── Executes in parallel (up to max limit)
   └── Results stored

3. Completion Handling
   ├── Callback invoked
   ├── Orchestrator notified
   ├── Expansion decision made
   └── New nodes potentially added
```

## Implementation Details

### Job Pool Configuration

```python
job_pool = JobPool(
    max_parallel_jobs=3,      # Configurable limit
    executor_type="thread",   # thread/process/async
    enable_callbacks=True     # For reactive expansion
)
```

### Dependency Management

Jobs can declare dependencies on other jobs:

```python
job_id = job_pool.submit_job(
    node_id=node.id,
    tree_id=tree.id,
    execute_fn=execute_node,
    dependencies={parent_job_id},  # Wait for parent
    callback=handle_completion
)
```

### Priority Scheduling

Jobs are scheduled based on priority:
- `CRITICAL`: Highest priority
- `HIGH`: Above normal
- `NORMAL`: Default
- `LOW`: Background tasks

### Reactive Expansion

When a node completes, the orchestrator:
1. Receives callback notification
2. Analyzes node results
3. Makes expansion decision
4. Optionally creates child nodes
5. Submits new jobs to pool

## Configuration

### Command Line Arguments (planned)

Note: the flags below are part of the design and are not yet exposed by `cli.py`.

```bash
python -m omicairn_agent_local.cli \
    --max-parallel-jobs 5 \
    --executor-type thread
```

### Environment Variables

```bash
# Note: These environment variables are planned but not yet implemented
# export OMICAIRN_MAX_PARALLEL_JOBS=5
# export OMICAIRN_EXECUTOR_TYPE=thread
# Currently, parallel jobs must be configured in code (default: 3)
```

### Configuration File

```yaml
execution:
  max_parallel_jobs: 5
  executor_type: thread
  enable_callbacks: true
  timeout: 300
```

## Callback System

### Callback Interface

```python
def node_completion_callback(result: JobResult):
    """Handle node completion."""
    if result.status == JobStatus.COMPLETED:
        # Make expansion decision
        # Update tree state
        # Submit new jobs
```

### Event Flow

1. **Job Completes** → Executor notifies pool
2. **Pool Updates State** → Marks job complete
3. **Callback Invoked** → Agent notified
4. **Agent Reacts** → Makes decisions
5. **New Jobs Created** → Cycle continues

## Future Extensions

### Distributed Execution

The design supports future distributed execution:

```python
class DistributedJobPool(JobPool):
    """Extended pool for distributed execution."""
    
    def submit_remote_job(self, job, target_node):
        """Submit job to remote node."""
        # AWS Lambda integration
        # Kubernetes job submission
        # Cloud function execution
```

### Web Server Integration

Future web server for job notifications:

```python
@app.post("/job/complete/{job_id}")
async def job_complete_webhook(job_id: str, result: JobResult):
    """Webhook for job completion."""
    orchestrator.handle_completion(job_id, result)
```

### Message Queue Integration

Support for message queues:
- Redis pub/sub for notifications
- RabbitMQ for job distribution
- AWS SQS for cloud deployment

## Performance Considerations

### Optimal Configuration

- **CPU-bound tasks**: Use process executor
- **I/O-bound tasks**: Use thread executor
- **Network tasks**: Use async executor

### Scaling Guidelines

```
max_parallel_jobs = min(
    available_cpu_cores,
    available_memory_gb * 2,
    docker_container_limit
)
```

### Resource Management

- Memory monitoring per job
- CPU usage tracking
- Automatic throttling on resource pressure

## Testing

### Unit Tests

```python
def test_parallel_execution():
    """Test that jobs run in parallel."""
    pool = JobPool(max_parallel_jobs=2)
    # Submit 4 jobs
    # Verify at least 2 run concurrently
```

### Integration Tests

```python
def test_reactive_expansion():
    """Test expansion on node completion."""
    orchestrator = OrchestratorAgent(max_parallel_jobs=3)
    # Execute tree
    # Verify expansion decisions
```

### Performance Tests

```python
def test_throughput():
    """Test job throughput."""
    # Submit 100 jobs
    # Measure completion time
    # Verify parallelism benefit
```

## Monitoring

### Metrics

- Jobs per second
- Average execution time
- Queue depth
- Worker utilization
- Callback latency

### Logging

```python
logger.info(f"Job pool status - Running: {running}, Queued: {queued}, Completed: {completed}")
```

### Health Checks

```python
status = job_pool.get_status()
# Returns: running jobs, queue size, completion stats
```

## Error Handling

### Retry Logic

Jobs can be retried on failure:
```python
if job.retries < max_retries:
    job.retries += 1
    job_pool.submit_job(job)
```

### Failure Propagation

Child jobs cancelled if parent fails:
```python
if parent_failed:
    for child in children:
        job_pool.cancel_job(child)
```

### Graceful Shutdown

```python
job_pool.shutdown(wait=True, timeout=30)
# Waits for running jobs
# Cancels queued jobs
# Cleans up resources
```

## Best Practices

1. **Set appropriate parallel limits** based on resources
2. **Use callbacks** for reactive behavior
3. **Declare dependencies** explicitly
4. **Handle failures** gracefully
5. **Monitor performance** regularly
6. **Test with various loads** 
7. **Plan for distributed execution** from the start

## Migration Guide

### From Sequential to Parallel

```python
# Before (sequential)
for node in nodes:
    execute_node(node)

# After (parallel)
for node in nodes:
    job_pool.submit_job(
        execute_fn=execute_node,
        args=(node,)
    )
job_pool.wait_for_all()
```

### Adding Callbacks

```python
# Add callback for reactive behavior
job_pool.submit_job(
    execute_fn=execute_node,
    callback=handle_completion
)
```

## Conclusion

The parallel execution system provides:
- ✅ Efficient parallel processing
- ✅ Proper dependency management
- ✅ Reactive expansion capability
- ✅ Future-ready for distribution
- ✅ Clean separation of concerns

This design enables significant performance improvements while maintaining system reliability and preparing for future scalability needs.