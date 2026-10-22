"""Timing utilities for performance tracking."""

import time
import functools
from datetime import datetime
from typing import Any, Callable, Dict, Optional
from utils.logger import get_logger

logger = get_logger(__name__)


class TimingContext:
    """Context manager for timing operations."""
    
    def __init__(self, operation_name: str, logger_instance=None):
        self.operation_name = operation_name
        self.logger = logger_instance or logger
        self.start_time = None
        self.end_time = None
        
    def __enter__(self):
        self.start_time = time.time()
        self.logger.debug(f"Starting {self.operation_name}")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        duration = self.end_time - self.start_time
        
        if exc_type:
            self.logger.error(
                f"{self.operation_name} failed after {duration:.2f}s: {exc_val}"
            )
        else:
            self.logger.info(
                f"{self.operation_name} completed in {duration:.2f}s"
            )
    
    @property
    def duration(self) -> float:
        """Get the duration of the operation."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0


def time_operation(operation_name: Optional[str] = None):
    """Decorator to time function execution."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Use function name if operation name not provided
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            # Get logger for the module
            func_logger = get_logger(func.__module__)
            
            start_time = time.time()
            func_logger.debug(f"Starting {op_name}")
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                func_logger.info(f"{op_name} completed in {duration:.2f}s")
                
                # Add timing to result if it's a dict
                if isinstance(result, dict):
                    result['_timing'] = {
                        'operation': op_name,
                        'duration': duration,
                        'timestamp': datetime.now().isoformat()
                    }
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                func_logger.error(
                    f"{op_name} failed after {duration:.2f}s: {str(e)}"
                )
                raise
                
        return wrapper
    return decorator


class OperationTimer:
    """Track timing for multiple operations."""
    
    def __init__(self):
        self.timings: Dict[str, float] = {}
        self.active_timers: Dict[str, float] = {}
        
    def start(self, operation: str):
        """Start timing an operation."""
        self.active_timers[operation] = time.time()
        logger.debug(f"Timer started: {operation}")
        
    def stop(self, operation: str) -> float:
        """Stop timing an operation and return duration."""
        if operation not in self.active_timers:
            logger.warning(f"Timer not found: {operation}")
            return 0.0
            
        start_time = self.active_timers.pop(operation)
        duration = time.time() - start_time
        
        # Add to cumulative timing
        if operation in self.timings:
            self.timings[operation] += duration
        else:
            self.timings[operation] = duration
            
        logger.info(f"Timer stopped: {operation} ({duration:.2f}s)")
        return duration
        
    def get_summary(self) -> Dict[str, Any]:
        """Get timing summary."""
        total_time = sum(self.timings.values())
        
        summary = {
            'total_duration': total_time,
            'operations': {
                op: {
                    'duration': duration,
                    'percentage': (duration / total_time * 100) if total_time > 0 else 0
                }
                for op, duration in sorted(
                    self.timings.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
            }
        }
        
        return summary
        
    def log_summary(self):
        """Log timing summary."""
        summary = self.get_summary()
        
        logger.info("=== Timing Summary ===")
        logger.info(f"Total duration: {summary['total_duration']:.2f}s")
        
        for op, stats in summary['operations'].items():
            logger.info(
                f"  {op}: {stats['duration']:.2f}s ({stats['percentage']:.1f}%)"
            )