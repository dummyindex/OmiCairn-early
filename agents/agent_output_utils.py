"""Utility module for agent output logging to node directories."""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import traceback


class AgentOutputLogger:
    """Handles logging of agent activities to node directories."""
    
    def __init__(self, node_dir: Path, agent_name: str):
        """Initialize the output logger.
        
        Args:
            node_dir: Path to the node directory (nodes/node_{nodeId})
            agent_name: Name of the agent (e.g., 'function_creator', 'bug_fixer')
        """
        self.node_dir = Path(node_dir)
        self.agent_name = agent_name
        
        # Create agent_tasks directory if it doesn't exist
        self.agent_tasks_dir = self.node_dir / "agent_tasks"
        self.agent_tasks_dir.mkdir(parents=True, exist_ok=True)
        
        # Create agent-specific subdirectory
        self.agent_dir = self.agent_tasks_dir / agent_name
        self.agent_dir.mkdir(exist_ok=True)
        
        # Track task counter for this session
        self.task_counter = self._get_next_task_number()
    
    def _get_next_task_number(self) -> int:
        """Get the next task number based on existing files."""
        existing_tasks = list(self.agent_dir.glob("task_*.json"))
        if not existing_tasks:
            return 1
        
        # Extract task numbers and find the maximum
        task_numbers = []
        for task_file in existing_tasks:
            try:
                num = int(task_file.stem.split('_')[1])
                task_numbers.append(num)
            except (IndexError, ValueError):
                continue
        
        return max(task_numbers, default=0) + 1
    
    def log_llm_interaction(
        self,
        task_type: str,
        llm_input: Dict[str, Any],
        llm_output: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Path:
        """Log an LLM interaction.
        
        Args:
            task_type: Type of task (e.g., 'create_function', 'fix_bug', 'select_function')
            llm_input: Input sent to LLM (messages, schema, etc.)
            llm_output: Output received from LLM
            error: Error message if the interaction failed
            metadata: Additional metadata to log
            
        Returns:
            Path to the saved log file
        """
        timestamp = datetime.now().isoformat()
        task_id = f"task_{self.task_counter:04d}_{task_type}"
        
        log_data = {
            "task_id": task_id,
            "task_type": task_type,
            "agent": self.agent_name,
            "timestamp": timestamp,
            "llm_input": llm_input,
            "llm_output": llm_output,
            "error": error,
            "metadata": metadata or {}
        }
        
        # Save to JSON file
        log_file = self.agent_dir / f"{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2, default=str)
        
        self.task_counter += 1
        return log_file
    
    def log_bug_fix_attempt(
        self,
        attempt_number: int,
        error_info: Dict[str, Any],
        fix_strategy: str,
        llm_input: Dict[str, Any],
        llm_output: Optional[Dict[str, Any]] = None,
        fixed_code: Optional[str] = None,
        success: bool = False,
        error: Optional[str] = None,
        previous_attempts: Optional[List[Dict[str, Any]]] = None
    ) -> Path:
        """Log a bug fix attempt.
        
        Args:
            attempt_number: The attempt number (1, 2, 3, etc.)
            error_info: Information about the error being fixed
            fix_strategy: Strategy used for fixing
            llm_input: Input sent to LLM
            llm_output: Output from LLM
            fixed_code: The fixed code if successful
            success: Whether the fix was successful
            error: Error message if the fix failed
            
        Returns:
            Path to the saved log file
        """
        timestamp = datetime.now().isoformat()
        task_id = f"fix_attempt_{attempt_number:02d}"
        
        log_data = {
            "task_id": task_id,
            "task_type": "bug_fix_attempt",
            "agent": self.agent_name,
            "timestamp": timestamp,
            "attempt_number": attempt_number,
            "error_info": error_info,
            "fix_strategy": fix_strategy,
            "llm_input": llm_input,
            "llm_output": llm_output,
            "fixed_code": fixed_code,
            "success": success,
            "error": error,
            "previous_attempts_summary": self._summarize_attempts(previous_attempts) if previous_attempts else []
        }
        
        # Save to dedicated bug fix directory
        bug_fix_dir = self.agent_dir / "bug_fixes"
        bug_fix_dir.mkdir(exist_ok=True)
        
        log_file = bug_fix_dir / f"{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2, default=str)
        
        return log_file
    
    def _summarize_attempts(self, attempts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Create a summary of previous attempts for logging.
        
        Args:
            attempts: List of previous attempt data
            
        Returns:
            Summarized list for logging
        """
        summaries = []
        for attempt in attempts:
            summary = {
                "attempt": attempt.get("attempt_number", 0),
                "error_type": attempt.get("llm_analysis", {}).get("error_type", "Unknown"),
                "root_cause": attempt.get("llm_analysis", {}).get("root_cause", "Unknown"),
                "strategy": attempt.get("llm_analysis", {}).get("fix_strategy", "Unknown")
            }
            summaries.append(summary)
        return summaries
    
    def log_selection_process(
        self,
        available_functions: List[Dict[str, Any]],
        requirements: Dict[str, Any],
        llm_input: Dict[str, Any],
        llm_output: Optional[Dict[str, Any]] = None,
        selected_function: Optional[str] = None,
        selection_reason: Optional[str] = None,
        error: Optional[str] = None
    ) -> Path:
        """Log a function selection process.
        
        Args:
            available_functions: List of available function blocks
            requirements: Requirements for selection
            llm_input: Input sent to LLM
            llm_output: Output from LLM
            selected_function: Name of selected function
            selection_reason: Reason for selection
            error: Error message if selection failed
            
        Returns:
            Path to the saved log file
        """
        timestamp = datetime.now().isoformat()
        task_id = f"selection_{self.task_counter:04d}"
        
        log_data = {
            "task_id": task_id,
            "task_type": "function_selection",
            "agent": self.agent_name,
            "timestamp": timestamp,
            "available_functions": available_functions,
            "requirements": requirements,
            "llm_input": llm_input,
            "llm_output": llm_output,
            "selected_function": selected_function,
            "selection_reason": selection_reason,
            "error": error
        }
        
        log_file = self.agent_dir / f"{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2, default=str)
        
        self.task_counter += 1
        return log_file
    
    def save_summary(
        self,
        total_tasks: int,
        successful_tasks: int,
        failed_tasks: int,
        task_details: List[Dict[str, Any]]
    ) -> Path:
        """Save a summary of all agent activities.
        
        Args:
            total_tasks: Total number of tasks performed
            successful_tasks: Number of successful tasks
            failed_tasks: Number of failed tasks
            task_details: List of task details
            
        Returns:
            Path to the summary file
        """
        summary = {
            "agent": self.agent_name,
            "timestamp": datetime.now().isoformat(),
            "statistics": {
                "total_tasks": total_tasks,
                "successful_tasks": successful_tasks,
                "failed_tasks": failed_tasks,
                "success_rate": successful_tasks / total_tasks if total_tasks > 0 else 0
            },
            "task_details": task_details
        }
        
        summary_file = self.agent_dir / "summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        return summary_file
    
    def save_function_block_versions(
        self,
        original_code: Optional[str],
        fixed_code: Optional[str],
        version: int
    ) -> Path:
        """Save different versions of function block code.
        
        Args:
            original_code: Original code
            fixed_code: Fixed/updated code
            version: Version number
            
        Returns:
            Path to the versions directory
        """
        versions_dir = self.agent_dir / "code_versions"
        versions_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if original_code:
            original_file = versions_dir / f"v{version}_original_{timestamp}.py"
            with open(original_file, 'w') as f:
                f.write(original_code)
        
        if fixed_code:
            fixed_file = versions_dir / f"v{version}_fixed_{timestamp}.py"
            with open(fixed_file, 'w') as f:
                f.write(fixed_code)
        
        return versions_dir


def create_agent_logger(node_dir: Path, agent_name: str) -> AgentOutputLogger:
    """Factory function to create an agent logger.
    
    Args:
        node_dir: Path to the node directory
        agent_name: Name of the agent
        
    Returns:
        AgentOutputLogger instance
    """
    return AgentOutputLogger(node_dir, agent_name)