"""Structured error handler for logging errors to JSON files.

This handler integrates with Python's standard logging to capture ERROR and CRITICAL
logs with structured context, saving them as JSON for better debugging and analysis.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import traceback
import threading


class StructuredErrorHandler(logging.Handler):
    """Log handler that saves structured error data to JSON files.
    
    This handler automatically captures ERROR and CRITICAL level logs and saves them
    with full context to JSON files for analysis. It integrates seamlessly with the
    existing logging infrastructure.
    """
    
    def __init__(self, tree_root: Path, min_level: int = logging.ERROR):
        """Initialize the structured error handler.
        
        Args:
            tree_root: Root directory of the analysis tree
            min_level: Minimum log level to capture (default: ERROR)
        """
        super().__init__()
        self.tree_root = Path(tree_root)
        self.error_dir = self.tree_root / "error_logs"
        self.error_dir.mkdir(parents=True, exist_ok=True)
        
        # Create detailed subdirectory
        self.detailed_dir = self.error_dir / "detailed"
        self.detailed_dir.mkdir(exist_ok=True)
        
        # Set minimum level
        self.setLevel(min_level)
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Track errors for summary
        self.error_summary = {
            "start_time": datetime.now().isoformat(),
            "total_errors": 0,
            "total_warnings": 0,
            "by_level": {},
            "by_module": {},
            "by_node": {},
            "by_category": {}
        }
        
        # Save initial summary
        self._save_summary()
    
    def emit(self, record: logging.LogRecord):
        """Handle log records - save errors to structured JSON.
        
        Args:
            record: LogRecord to process
        """
        # Only process configured levels
        if record.levelno < self.level:
            return
            
        try:
            with self._lock:
                # Build structured error record
                error_record = self._build_error_record(record)
                
                # Save to detailed log
                self._save_error_record(error_record)
                
                # Update summary
                self._update_summary(error_record)
                
        except Exception:
            # Don't let handler errors break the application
            # This is a logging handler, it should fail silently
            pass
    
    def _build_error_record(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Build a structured error record from a LogRecord.
        
        Args:
            record: LogRecord to process
            
        Returns:
            Dictionary with structured error information
        """
        error_record = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "level_number": record.levelno,
            "module": record.name,
            "message": record.getMessage(),
            "filename": record.pathname,
            "line_number": record.lineno,
            "function": record.funcName,
            "thread": record.thread,
            "thread_name": record.threadName,
            "process": record.process,
        }
        
        # Add extra context if provided via extra={} parameter
        if hasattr(record, 'node_id'):
            error_record['node_id'] = record.node_id
            
        if hasattr(record, 'error_category'):
            error_record['error_category'] = record.error_category
            
        if hasattr(record, 'context'):
            error_record['context'] = record.context
            
        if hasattr(record, 'recovery_hint'):
            error_record['recovery_hint'] = record.recovery_hint
            
        if hasattr(record, 'attempts'):
            error_record['attempts'] = record.attempts
            
        if hasattr(record, 'agent_type'):
            error_record['agent_type'] = record.agent_type
            
        if hasattr(record, 'operation'):
            error_record['operation'] = record.operation
        
        # Add exception info if present
        if record.exc_info:
            error_record['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': ''.join(traceback.format_exception(*record.exc_info))
            }
        
        return error_record
    
    def _save_error_record(self, record: Dict[str, Any]):
        """Save individual error record to JSON file.
        
        Args:
            record: Error record dictionary to save
        """
        # Generate unique filename with timestamp and level
        # Use counter to ensure uniqueness even for simultaneous logs
        import time
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")  # Full microseconds
        level = record.get('level', 'ERROR')
        category = record.get('error_category', 'unknown')
        
        # Include node_id in filename if present (for easy glob matching)
        node_suffix = f"_node_{record['node_id']}" if record.get('node_id') else ""
        
        filename = f"{timestamp}_{level}_{category}{node_suffix}.json"
        filepath = self.detailed_dir / filename
        
        # Handle potential filename collisions
        counter = 0
        while filepath.exists():
            counter += 1
            filename = f"{timestamp}_{counter}_{level}_{category}{node_suffix}.json"
            filepath = self.detailed_dir / filename
        
        # Save JSON with pretty printing
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(record, f, indent=2, default=str, ensure_ascii=False)
    
    def _update_summary(self, record: Dict[str, Any]):
        """Update error summary statistics.
        
        Args:
            record: Error record to include in summary
        """
        # Update counts
        if record['level'] == 'WARNING':
            self.error_summary["total_warnings"] += 1
        else:
            self.error_summary["total_errors"] += 1
        
        # By level
        level = record.get('level', 'UNKNOWN')
        self.error_summary["by_level"][level] = \
            self.error_summary["by_level"].get(level, 0) + 1
        
        # By module
        module = record.get('module', 'unknown')
        self.error_summary["by_module"][module] = \
            self.error_summary["by_module"].get(module, 0) + 1
        
        # By node (if present)
        if record.get('node_id'):
            node_id = record['node_id']
            self.error_summary["by_node"][node_id] = \
                self.error_summary["by_node"].get(node_id, 0) + 1
        
        # By category (if present)
        if record.get('error_category'):
            category = record['error_category']
            self.error_summary["by_category"][category] = \
                self.error_summary["by_category"].get(category, 0) + 1
        
        # Save updated summary
        self._save_summary()
    
    def _save_summary(self):
        """Save the current error summary to disk."""
        summary_file = self.error_dir / "session_summary.json"
        
        # Add current timestamp
        summary_with_time = self.error_summary.copy()
        summary_with_time["last_updated"] = datetime.now().isoformat()
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_with_time, f, indent=2, ensure_ascii=False)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get the current error summary.
        
        Returns:
            Dictionary with error statistics
        """
        with self._lock:
            return self.error_summary.copy()
    
    def get_errors_by_node(self, node_id: str) -> list:
        """Get all errors for a specific node.
        
        Args:
            node_id: Node ID to filter by
            
        Returns:
            List of error records for the specified node
        """
        errors = []
        
        # Search through detailed logs - look for node_{node_id} in filename
        for json_file in self.detailed_dir.glob(f"*_node_{node_id}.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    error_data = json.load(f)
                    # Double-check the node_id matches
                    if error_data.get('node_id') == node_id:
                        errors.append(error_data)
            except (json.JSONDecodeError, IOError):
                continue
        
        return errors
    
    def get_errors_by_category(self, category: str) -> list:
        """Get all errors for a specific category.
        
        Args:
            category: Error category to filter by
            
        Returns:
            List of error records for the specified category
        """
        errors = []
        
        # Search through ALL detailed logs and filter by category field
        # We can't rely on filename alone since category might appear elsewhere
        for json_file in self.detailed_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    error_data = json.load(f)
                    if error_data.get('error_category') == category:
                        errors.append(error_data)
            except (json.JSONDecodeError, IOError):
                continue
        
        return errors
    
    def close(self):
        """Close the handler and save final summary."""
        with self._lock:
            # Add end time to summary
            self.error_summary["end_time"] = datetime.now().isoformat()
            self._save_summary()
        
        super().close()