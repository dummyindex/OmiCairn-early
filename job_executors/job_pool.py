"""Job pool for managing parallel execution with configurable limits."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from queue import Queue, PriorityQueue
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import uuid
import time
from utils import setup_logger

logger = setup_logger(__name__)


class JobStatus(Enum):
    """Job execution status."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(Enum):
    """Job priority levels."""
    LOW = 3
    NORMAL = 2
    HIGH = 1
    CRITICAL = 0


@dataclass
class JobResult:
    """Result of a job execution."""
    job_id: str
    status: JobStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Job:
    """Represents a job to be executed."""
    job_id: str
    node_id: str
    tree_id: str
    execute_fn: Callable
    args: Tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    priority: JobPriority = JobPriority.NORMAL
    callback: Optional[Callable[[JobResult], None]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    dependencies: Set[str] = field(default_factory=set)  # Job IDs this job depends on
    
    def __lt__(self, other):
        """Compare jobs by priority for priority queue."""
        return self.priority.value < other.priority.value


class JobPool:
    """
    Manages parallel job execution with configurable limits.
    
    Designed to support future distributed execution across machines/AWS.
    """
    
    def __init__(
        self,
        max_parallel_jobs: int = 3,
        executor_type: str = "thread",  # "thread", "process", or "async"
        enable_callbacks: bool = True
    ):
        """
        Initialize job pool.
        
        Args:
            max_parallel_jobs: Maximum number of jobs to run in parallel
            executor_type: Type of executor to use
            enable_callbacks: Whether to enable callback notifications
        """
        self.max_parallel_jobs = max_parallel_jobs
        self.executor_type = executor_type
        self.enable_callbacks = enable_callbacks
        
        # Job management
        self.jobs: Dict[str, Job] = {}
        self.job_queue = PriorityQueue()
        self.running_jobs: Set[str] = set()
        self.completed_jobs: Set[str] = set()
        self.failed_jobs: Set[str] = set()
        
        # Results storage
        self.results: Dict[str, JobResult] = {}
        
        # Synchronization
        self.lock = threading.Lock()
        self.job_complete_event = threading.Event()
        self.shutdown_event = threading.Event()
        
        # Executor
        if executor_type == "thread":
            self.executor = ThreadPoolExecutor(max_workers=max_parallel_jobs)
        elif executor_type == "process":
            from concurrent.futures import ProcessPoolExecutor
            self.executor = ProcessPoolExecutor(max_workers=max_parallel_jobs)
        else:
            self.executor = None  # For async execution
            
        # Start worker thread
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        
        logger.info(f"JobPool initialized with max_parallel_jobs={max_parallel_jobs}, executor_type={executor_type}")
    
    def submit_job(
        self,
        node_id: str,
        tree_id: str,
        execute_fn: Callable,
        args: Tuple = (),
        kwargs: Dict[str, Any] = None,
        priority: JobPriority = JobPriority.NORMAL,
        callback: Optional[Callable[[JobResult], None]] = None,
        dependencies: Set[str] = None,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Submit a job to the pool.
        
        Args:
            node_id: Node ID this job belongs to
            tree_id: Tree ID this job belongs to
            execute_fn: Function to execute
            args: Positional arguments for the function
            kwargs: Keyword arguments for the function
            priority: Job priority
            callback: Callback function to call when job completes
            dependencies: Set of job IDs this job depends on
            metadata: Additional metadata for the job
            
        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())
        
        job = Job(
            job_id=job_id,
            node_id=node_id,
            tree_id=tree_id,
            execute_fn=execute_fn,
            args=args,
            kwargs=kwargs or {},
            priority=priority,
            callback=callback,
            dependencies=dependencies or set(),
            metadata=metadata or {}
        )
        
        with self.lock:
            self.jobs[job_id] = job
            
            # Check if dependencies are satisfied
            if self._can_run_job(job):
                self.job_queue.put(job)
                logger.info(f"Job {job_id} queued for node {node_id}")
            else:
                logger.info(f"Job {job_id} waiting for dependencies: {job.dependencies}")
        
        # Signal worker thread
        self.job_complete_event.set()
        
        return job_id
    
    def _can_run_job(self, job: Job) -> bool:
        """Check if a job's dependencies are satisfied."""
        return job.dependencies.issubset(self.completed_jobs)
    
    def _worker_loop(self):
        """Worker loop that processes jobs from the queue."""
        logger.info("JobPool worker thread started")
        
        while not self.shutdown_event.is_set():
            # Wait for signal or timeout
            self.job_complete_event.wait(timeout=1.0)
            self.job_complete_event.clear()
            
            # Process jobs
            with self.lock:
                # Check for newly runnable jobs (dependencies satisfied)
                for job_id, job in self.jobs.items():
                    if (job_id not in self.completed_jobs and 
                        job_id not in self.failed_jobs and
                        job_id not in self.running_jobs and
                        job_id not in [j.job_id for j in list(self.job_queue.queue)] and
                        self._can_run_job(job)):
                        self.job_queue.put(job)
                        logger.info(f"Job {job_id} dependencies satisfied, queued")
                
                # Start new jobs if we have capacity
                while (len(self.running_jobs) < self.max_parallel_jobs and 
                       not self.job_queue.empty()):
                    job = self.job_queue.get()
                    self._start_job(job)
        
        logger.info("JobPool worker thread stopped")
    
    def _start_job(self, job: Job):
        """Start executing a job."""
        self.running_jobs.add(job.job_id)
        logger.info(f"Starting job {job.job_id} for node {job.node_id}")
        
        if self.executor_type == "async":
            # For async execution, we'd use asyncio
            asyncio.create_task(self._execute_job_async(job))
        else:
            # Submit to thread/process pool
            future = self.executor.submit(self._execute_job, job)
            future.add_done_callback(lambda f: self._handle_job_completion(job, f))
    
    def _execute_job(self, job: Job) -> JobResult:
        """Execute a job and return the result."""
        start_time = datetime.now()
        result = JobResult(
            job_id=job.job_id,
            status=JobStatus.RUNNING,
            start_time=start_time,
            metadata=job.metadata
        )
        
        try:
            # Execute the job
            logger.info(f"Executing job {job.job_id}")
            execution_result = job.execute_fn(*job.args, **job.kwargs)
            
            # Success
            end_time = datetime.now()
            result.status = JobStatus.COMPLETED
            result.result = execution_result
            result.end_time = end_time
            result.duration = (end_time - start_time).total_seconds()
            
            logger.info(f"Job {job.job_id} completed successfully in {result.duration:.2f}s")
            
        except Exception as e:
            # Failure
            end_time = datetime.now()
            result.status = JobStatus.FAILED
            result.error = str(e)
            result.end_time = end_time
            result.duration = (end_time - start_time).total_seconds()
            
            logger.error(f"Job {job.job_id} failed: {e}")
        
        return result
    
    async def _execute_job_async(self, job: Job) -> JobResult:
        """Execute a job asynchronously."""
        # Implementation for async execution
        pass
    
    def _handle_job_completion(self, job: Job, future: Future):
        """Handle job completion."""
        try:
            result = future.result()
        except Exception as e:
            # Create failure result if execution itself failed
            result = JobResult(
                job_id=job.job_id,
                status=JobStatus.FAILED,
                error=str(e),
                metadata=job.metadata
            )
        
        with self.lock:
            # Update state
            self.running_jobs.discard(job.job_id)
            if result.status == JobStatus.COMPLETED:
                self.completed_jobs.add(job.job_id)
            else:
                self.failed_jobs.add(job.job_id)
            
            # Store result
            self.results[job.job_id] = result
            
            # Log status
            running_count = len(self.running_jobs)
            queued_count = self.job_queue.qsize()
            completed_count = len(self.completed_jobs)
            failed_count = len(self.failed_jobs)
            
            logger.info(
                f"Job pool status - Running: {running_count}, "
                f"Queued: {queued_count}, Completed: {completed_count}, "
                f"Failed: {failed_count}"
            )
        
        # Execute callback if provided
        if self.enable_callbacks and job.callback:
            try:
                job.callback(result)
            except Exception as e:
                logger.error(f"Error in job callback: {e}")
        
        # Signal that a job completed (may enable other jobs)
        self.job_complete_event.set()
    
    def wait_for_job(self, job_id: str, timeout: Optional[float] = None) -> JobResult:
        """
        Wait for a specific job to complete.
        
        Args:
            job_id: Job ID to wait for
            timeout: Maximum time to wait in seconds
            
        Returns:
            Job result
        """
        start_time = time.time()
        
        while True:
            with self.lock:
                if job_id in self.results:
                    return self.results[job_id]
            
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Timeout waiting for job {job_id}")
            
            time.sleep(0.1)
    
    def wait_for_all(self, timeout: Optional[float] = None) -> Dict[str, JobResult]:
        """
        Wait for all submitted jobs to complete.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            Dictionary of all job results
        """
        start_time = time.time()
        
        while True:
            with self.lock:
                total_jobs = len(self.jobs)
                completed = len(self.completed_jobs) + len(self.failed_jobs)
                
                if completed >= total_jobs:
                    return self.results.copy()
            
            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError("Timeout waiting for all jobs")
            
            time.sleep(0.1)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the job pool."""
        with self.lock:
            return {
                "max_parallel_jobs": self.max_parallel_jobs,
                "total_jobs": len(self.jobs),
                "running": len(self.running_jobs),
                "queued": self.job_queue.qsize(),
                "completed": len(self.completed_jobs),
                "failed": len(self.failed_jobs),
                "running_job_ids": list(self.running_jobs),
                "failed_job_ids": list(self.failed_jobs)
            }
    
    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a pending job.
        
        Args:
            job_id: Job ID to cancel
            
        Returns:
            True if cancelled, False if job not found or already running/completed
        """
        with self.lock:
            if job_id in self.running_jobs or job_id in self.completed_jobs:
                return False
            
            # Remove from queue if present
            # Note: This is inefficient but works for now
            temp_queue = PriorityQueue()
            cancelled = False
            
            while not self.job_queue.empty():
                job = self.job_queue.get()
                if job.job_id != job_id:
                    temp_queue.put(job)
                else:
                    cancelled = True
                    self.failed_jobs.add(job_id)
                    self.results[job_id] = JobResult(
                        job_id=job_id,
                        status=JobStatus.CANCELLED,
                        metadata=job.metadata
                    )
            
            self.job_queue = temp_queue
            return cancelled
    
    def shutdown(self, wait: bool = True, timeout: float = 30):
        """
        Shutdown the job pool.
        
        Args:
            wait: Whether to wait for running jobs to complete
            timeout: Maximum time to wait for shutdown
        """
        logger.info("Shutting down job pool")
        
        # Signal shutdown
        self.shutdown_event.set()
        self.job_complete_event.set()
        
        if wait:
            # Wait for running jobs to complete
            start_time = time.time()
            while len(self.running_jobs) > 0:
                if time.time() - start_time > timeout:
                    logger.warning("Timeout waiting for jobs to complete during shutdown")
                    break
                time.sleep(0.1)
        
        # Shutdown executor
        if self.executor:
            self.executor.shutdown(wait=wait)
        
        # Wait for worker thread
        self.worker_thread.join(timeout=5)
        
        logger.info("Job pool shutdown complete")


class DistributedJobPool(JobPool):
    """
    Extended job pool for distributed execution.
    
    This is a placeholder for future implementation that will support
    distributed execution across multiple machines, AWS, etc.
    """
    
    def __init__(
        self,
        max_parallel_jobs: int = 3,
        executor_type: str = "thread",
        enable_callbacks: bool = True,
        distributed_config: Dict[str, Any] = None
    ):
        """
        Initialize distributed job pool.
        
        Args:
            max_parallel_jobs: Maximum number of jobs per node
            executor_type: Type of executor to use
            enable_callbacks: Whether to enable callbacks
            distributed_config: Configuration for distributed execution
        """
        super().__init__(max_parallel_jobs, executor_type, enable_callbacks)
        self.distributed_config = distributed_config or {}
        
        # Future: Initialize connection to job queue service (Redis, SQS, etc.)
        # Future: Register with coordinator service
        # Future: Setup heartbeat mechanism
    
    def submit_remote_job(self, job: Job, target_node: str = None) -> str:
        """
        Submit a job for remote execution.
        
        Args:
            job: Job to execute
            target_node: Specific node to execute on (optional)
            
        Returns:
            Job ID
        """
        # Future implementation for remote job submission
        logger.info(f"Remote job submission not yet implemented, executing locally")
        return self.submit_job(
            node_id=job.node_id,
            tree_id=job.tree_id,
            execute_fn=job.execute_fn,
            args=job.args,
            kwargs=job.kwargs,
            priority=job.priority,
            callback=job.callback,
            dependencies=job.dependencies,
            metadata=job.metadata
        )