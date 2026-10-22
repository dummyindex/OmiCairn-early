"""
Enhanced error tracking system for bug fixer that properly tracks execution results.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


class ErrorTracker:
    """Tracks errors and execution results throughout debugging session."""
    
    def __init__(self, initial_error: str, node_dir: Optional[Path] = None):
        """Initialize error tracker with the initial error."""
        self.initial_error = initial_error
        self.initial_error_type = self._extract_error_type(initial_error)
        self.node_dir = node_dir
        
        # Track all turns
        self.turns: List[Dict[str, Any]] = []
        
        # Track current state
        self.current_turn = 0
        self.is_resolved = False
        self.resolution_turn = None
        
        # Initialize tracking file (removed - redundant with all_attempts_summary.json)
        self.tracking_file = None
    
    def start_turn(self, turn_number: int) -> None:
        """Start a new debugging turn."""
        self.current_turn = turn_number
        self.turns.append({
            "turn": turn_number,
            "timestamp": datetime.now().isoformat(),
            "actions": [],
            "error_state": {
                "initial_error": self.initial_error,
                "initial_error_type": self.initial_error_type,
                "current_error": self.initial_error if turn_number == 1 else self._get_latest_error(),
                "is_resolved": False
            }
        })
    
    def record_action(self, action: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Record an action and its result."""
        if not self.turns:
            return
            
        current_turn = self.turns[-1]
        
        # Record the action
        action_record = {
            "type": action.get("type"),
            "timestamp": datetime.now().isoformat(),
            "success": result.get("success", False),
            "result_summary": self._summarize_result(action, result),
            "action": action  # Store the full action for access to command, path, etc.
        }
        
        # Store full action_result for actions that need detailed data in summaries
        # This enables proper exit_code, stdout, stderr extraction for write_and_run, execute_command, etc.
        action_type = action.get("type")
        if action_type in ['write_and_run', 'execute_command', 'update_function_block', 'read_file', 'write_file']:
            action_record["action_result"] = result
        
        # Check if this action resolved the error
        if action.get("type") == "update_function_block":
            # First check for placeholder validation failure
            if result.get("validation_failed") and result.get("placeholder_issues"):
                # Placeholder code was detected and rejected
                action_record["validation_failed"] = True
                action_record["placeholder_issues"] = result.get("placeholder_issues", [])
                error_msg = f"Placeholder validation failed: {', '.join(result.get('placeholder_issues', []))}"
                action_record["new_error"] = error_msg
                action_record["new_error_type"] = "PlaceholderValidationError"
                current_turn["error_state"]["current_error"] = error_msg
                current_turn["error_state"]["is_resolved"] = False
                
            else:
                re_execution = result.get("re_execution", {})
                # Check if the function actually executed successfully
                if re_execution.get("function_executed", False) and re_execution.get("success", False):
                    # The error is resolved!
                    self.is_resolved = True
                    self.resolution_turn = self.current_turn
                    action_record["resolved_error"] = True
                    action_record["resolution_details"] = {
                        "exit_code": re_execution.get("exit_code"),
                        "output_exists": re_execution.get("has_output", False),
                        "message": "Function block executed successfully",
                        "function_executed": True
                    }
                    current_turn["error_state"]["is_resolved"] = True
                else:
                    # Extract new error if execution failed
                    actual_error = re_execution.get("actual_error")
                    if actual_error:
                        action_record["new_error"] = actual_error
                        action_record["new_error_type"] = self._extract_error_type(actual_error)
                        current_turn["error_state"]["current_error"] = actual_error
                    elif re_execution.get("stderr"):
                        new_error = self._extract_error_from_output(re_execution.get("stderr"))
                        if new_error:
                            action_record["new_error"] = new_error
                            action_record["new_error_type"] = self._extract_error_type(new_error)
                            current_turn["error_state"]["current_error"] = new_error
        
        elif action.get("type") == "execute_command" and not result.get("success"):
            # Track errors from command execution
            if result.get("stderr"):
                new_error = self._extract_error_from_output(result.get("stderr"))
                if new_error:
                    action_record["new_error"] = new_error
                    action_record["new_error_type"] = self._extract_error_type(new_error)
        
        current_turn["actions"].append(action_record)
        # _save_state() removed - error_tracking.json is redundant with all_attempts_summary.json
    
    def should_continue_debugging(self) -> bool:
        """Check if debugging should continue."""
        return not self.is_resolved
    
    def get_resolution_summary(self) -> Dict[str, Any]:
        """Get summary of the debugging session."""
        summary = {
            "initial_error": self.initial_error,
            "initial_error_type": self.initial_error_type,
            "total_turns": len(self.turns),
            "is_resolved": self.is_resolved,
            "resolution_turn": self.resolution_turn,
            "turns_summary": []
        }
        
        for turn in self.turns:
            turn_summary = {
                "turn": turn["turn"],
                "actions_count": len(turn["actions"]),
                "actions": [
                    {
                        "type": a["type"],
                        "success": a["success"],
                        "resolved_error": a.get("resolved_error", False)
                    }
                    for a in turn["actions"]
                ],
                "error_resolved": turn["error_state"]["is_resolved"]
            }
            summary["turns_summary"].append(turn_summary)
        
        return summary
    
    def _extract_error_type(self, error: str) -> str:
        """Extract the error type from an error message."""
        import re
        
        # Common Python error patterns
        patterns = [
            r'(ModuleNotFoundError|ImportError):\s*No module named',
            r'(AttributeError):\s*module.*has no attribute',
            r'(KeyError):\s*[\'"]([^\'"]+)[\'"]',
            r'(ValueError):\s*',
            r'(TypeError):\s*',
            r'(NameError):\s*',
            r'(FileNotFoundError):\s*',
            r'(PermissionError):\s*',
            r'([A-Z]\w*Error):'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, error)
            if match:
                return match.group(1)
        
        return "UnknownError"
    
    def _extract_error_from_output(self, output: str) -> Optional[str]:
        """Extract the most relevant error from output, preserving full traceback."""
        lines = output.strip().split('\n')
        
        # Look for traceback
        traceback_start = -1
        for i, line in enumerate(lines):
            if 'Traceback (most recent call last):' in line:
                traceback_start = i
                break
        
        if traceback_start >= 0:
            # Return the full traceback from start to end
            # The traceback typically ends with an Error or Exception line
            error_lines = []
            for i in range(traceback_start, len(lines)):
                error_lines.append(lines[i])
                # Stop after we find the error line (but include it)
                if i > traceback_start and ('Error:' in lines[i] or 'Exception:' in lines[i]):
                    # Include a few more lines if they're indented (additional error context)
                    j = i + 1
                    while j < len(lines) and j < i + 3:
                        if lines[j].strip() and (lines[j].startswith(' ') or lines[j].startswith('\t')):
                            error_lines.append(lines[j])
                            j += 1
                        else:
                            break
                    break
            
            if error_lines:
                return '\n'.join(error_lines)
        
        # If no traceback, look for ERROR level log with context
        error_idx = -1
        for i in range(len(lines) - 1, -1, -1):
            if 'ERROR' in lines[i] and ('Error:' in lines[i] or 'Exception:' in lines[i]):
                error_idx = i
                break
        
        if error_idx >= 0:
            # Include some context lines before and after the error
            start = max(0, error_idx - 2)
            end = min(len(lines), error_idx + 3)
            return '\n'.join(lines[start:end])
        
        # If no clear error pattern, but output suggests failure, return last few lines
        if output.strip() and len(lines) > 0:
            # Return last 10 lines or full output if shorter
            num_lines = min(10, len(lines))
            return '\n'.join(lines[-num_lines:])
        
        return None
    
    def _get_latest_error(self) -> str:
        """Get the latest error from previous turns."""
        for turn in reversed(self.turns[:-1]):
            for action in reversed(turn["actions"]):
                if "new_error" in action:
                    return action["new_error"]
        return self.initial_error
    
    def _summarize_result(self, action: Dict[str, Any], result: Dict[str, Any]) -> str:
        """Create a brief summary of the action result."""
        if action.get("type") == "update_function_block":
            re_exec = result.get("re_execution", {})
            if re_exec.get("success"):
                return f"Code updated and executed successfully (exit_code: {re_exec.get('exit_code')})"
            else:
                return f"Code updated but execution failed (exit_code: {re_exec.get('exit_code')})"
        
        elif action.get("type") == "install_package":
            if result.get("success"):
                return f"Package installed successfully"
            else:
                return f"Package installation failed"
        
        elif action.get("type") == "write_file":
            if result.get("success"):
                return f"File written successfully ({result.get('bytes_written', 0)} bytes)"
            else:
                return f"File write failed"
        
        elif action.get("type") == "execute_command":
            if result.get("success"):
                return f"Command executed successfully"
            else:
                return f"Command failed with return code {result.get('return_code', -1)}"
        
        return "Action completed"
    
    def _save_state(self) -> None:
        """Save current state to file - DEPRECATED: Use all_attempts_summary.json instead."""
        # This method is no longer used as error_tracking.json is redundant
        # All information is saved in all_attempts_summary.json
        pass