"""
Timing tracker for agent operations.
Tracks execution time for various agent actions and saves to JSON.
"""

import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from contextlib import contextmanager

class TimingTracker:
    """Track timing information for agent operations."""
    
    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize timing tracker.
        
        Args:
            output_dir: Directory to save timing information
        """
        self.output_dir = Path(output_dir) if output_dir else None
        self.timings: List[Dict[str, Any]] = []
        self.current_operation: Optional[Dict[str, Any]] = None
        self.start_time = time.time()
        
    def start_operation(self, operation_type: str, operation_name: str, 
                        metadata: Optional[Dict[str, Any]] = None) -> None:
        """Start timing an operation.
        
        Args:
            operation_type: Type of operation (e.g., 'action', 'llm_call', 'execution')
            operation_name: Name of the operation (e.g., 'read_file', 'function_creation')
            metadata: Additional metadata to store
        """
        self.current_operation = {
            'type': operation_type,
            'name': operation_name,
            'start_time': time.time(),
            'start_timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
    
    def end_operation(self, success: bool = True, error: Optional[str] = None,
                      result_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """End timing an operation.
        
        Args:
            success: Whether the operation succeeded
            error: Error message if failed
            result_metadata: Additional result metadata
            
        Returns:
            Timing information for the operation
        """
        if not self.current_operation:
            return {}
        
        end_time = time.time()
        duration = end_time - self.current_operation['start_time']
        
        timing_info = {
            **self.current_operation,
            'end_time': end_time,
            'end_timestamp': datetime.now().isoformat(),
            'duration_seconds': duration,
            'success': success,
            'error': error,
            'result_metadata': result_metadata or {}
        }
        
        self.timings.append(timing_info)
        self.current_operation = None
        
        # Auto-save if output directory is set
        if self.output_dir:
            self.save()
        
        return timing_info
    
    @contextmanager
    def track_operation(self, operation_type: str, operation_name: str,
                        metadata: Optional[Dict[str, Any]] = None):
        """Context manager for tracking operation timing.
        
        Usage:
            with tracker.track_operation('action', 'read_file'):
                # Do operation
                pass
        """
        self.start_operation(operation_type, operation_name, metadata)
        error_msg = None
        success = True
        
        try:
            yield self
        except Exception as e:
            error_msg = str(e)
            success = False
            raise
        finally:
            self.end_operation(success=success, error=error_msg)
    
    def add_timing(self, timing_info: Dict[str, Any]) -> None:
        """Add external timing information.
        
        Args:
            timing_info: Timing information dictionary
        """
        self.timings.append(timing_info)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all timings.
        
        Returns:
            Summary statistics
        """
        if not self.timings:
            return {
                'total_operations': 0,
                'total_duration': 0,
                'operations_by_type': {},
                'average_duration_by_type': {}
            }
        
        total_duration = sum(t.get('duration_seconds', 0) for t in self.timings)
        operations_by_type = {}
        duration_by_type = {}
        
        for timing in self.timings:
            op_type = timing.get('type', 'unknown')
            if op_type not in operations_by_type:
                operations_by_type[op_type] = 0
                duration_by_type[op_type] = []
            operations_by_type[op_type] += 1
            duration_by_type[op_type].append(timing.get('duration_seconds', 0))
        
        average_duration_by_type = {
            op_type: sum(durations) / len(durations) if durations else 0
            for op_type, durations in duration_by_type.items()
        }
        
        return {
            'total_operations': len(self.timings),
            'total_duration': total_duration,
            'total_time_elapsed': time.time() - self.start_time,
            'operations_by_type': operations_by_type,
            'average_duration_by_type': average_duration_by_type,
            'success_rate': sum(1 for t in self.timings if t.get('success', True)) / len(self.timings) if self.timings else 1.0
        }
    
    def save(self, filename: str = 'timing_info.json') -> Path:
        """Save timing information to JSON file.
        
        Args:
            filename: Name of the output file
            
        Returns:
            Path to saved file
        """
        if not self.output_dir:
            raise ValueError("No output directory specified")
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_file = self.output_dir / filename
        
        data = {
            'summary': self.get_summary(),
            'timings': self.timings,
            'start_time': self.start_time,
            'save_timestamp': datetime.now().isoformat()
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        return output_file
    
    def load(self, filepath: Path) -> None:
        """Load timing information from JSON file.
        
        Args:
            filepath: Path to JSON file
        """
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        self.timings = data.get('timings', [])
        self.start_time = data.get('start_time', time.time())


class ActionTimingTracker(TimingTracker):
    """Specialized timing tracker for bug fixer actions."""
    
    def track_action(self, action_type: str, turn_number: int,
                     metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Track a bug fixer action.
        
        Args:
            action_type: Type of action (e.g., 'read_file', 'update_function_block')
            turn_number: Current turn number
            metadata: Additional metadata
            
        Returns:
            Context manager for tracking
        """
        full_metadata = {
            'turn_number': turn_number,
            'action_type': action_type,
            **(metadata or {})
        }
        return self.track_operation('bug_fixer_action', action_type, full_metadata)
    
    def get_action_summary(self) -> Dict[str, Any]:
        """Get summary specifically for bug fixer actions.
        
        Returns:
            Action-specific summary
        """
        action_timings = [t for t in self.timings if t.get('type') == 'bug_fixer_action']
        
        if not action_timings:
            return {
                'total_actions': 0,
                'total_duration': 0,
                'actions_by_type': {},
                'average_duration_by_action': {},
                'turns': []
            }
        
        actions_by_type = {}
        duration_by_action = {}
        turns = {}
        
        for timing in action_timings:
            action_type = timing.get('name', 'unknown')
            turn_num = timing.get('metadata', {}).get('turn_number', 0)
            
            if action_type not in actions_by_type:
                actions_by_type[action_type] = 0
                duration_by_action[action_type] = []
            
            actions_by_type[action_type] += 1
            duration_by_action[action_type].append(timing.get('duration_seconds', 0))
            
            if turn_num not in turns:
                turns[turn_num] = []
            turns[turn_num].append({
                'action': action_type,
                'duration': timing.get('duration_seconds', 0),
                'success': timing.get('success', True)
            })
        
        average_duration_by_action = {
            action: sum(durations) / len(durations) if durations else 0
            for action, durations in duration_by_action.items()
        }
        
        return {
            'total_actions': len(action_timings),
            'total_duration': sum(t.get('duration_seconds', 0) for t in action_timings),
            'actions_by_type': actions_by_type,
            'average_duration_by_action': average_duration_by_action,
            'turns': [{'turn': k, 'actions': v} for k, v in sorted(turns.items())]
        }