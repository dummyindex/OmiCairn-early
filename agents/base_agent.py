"""Base agent class for all agent types."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pathlib import Path

from utils.logger import get_logger
from models import AnalysisTree, AnalysisNode
from agents.task_manager import TaskManager, TaskType, TaskStatus

logger = get_logger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all agents."""
    
    def __init__(self, name: str, task_manager: Optional[TaskManager] = None):
        self.name = name
        self.logger = get_logger(f"{__name__}.{name}")
        self.task_manager = task_manager
        self.current_task_id: Optional[str] = None
        
    @abstractmethod
    def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process the agent's task with given context.
        
        Args:
            context: Dictionary containing all necessary information
            
        Returns:
            Dictionary with results and any modifications to context
        """
        pass
    
    def validate_context(self, context: Dict[str, Any], required_keys: List[str]) -> None:
        """Validate that context contains required keys.
        
        Args:
            context: Context dictionary to validate
            required_keys: List of required keys
            
        Raises:
            ValueError: If any required key is missing
        """
        missing = [key for key in required_keys if key not in context]
        if missing:
            raise ValueError(f"Missing required context keys: {missing}")
    
    def create_task(
        self,
        task_type: TaskType,
        description: str,
        context: Dict[str, Any],
        parent_task_id: Optional[str] = None
    ) -> Optional[str]:
        """Create a new task for this agent."""
        if not self.task_manager:
            return None
            
        task = self.task_manager.create_task(
            task_type=task_type,
            agent_name=self.name,
            description=description,
            context=context,
            parent_task_id=parent_task_id
        )
        
        self.current_task_id = task.task_id
        return task.task_id
    
    def update_task_status(
        self,
        status: TaskStatus,
        results: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """Update the current task status."""
        if self.current_task_id and self.task_manager:
            self.task_manager.update_task_status(
                self.current_task_id,
                status=status,
                results=results,
                error=error
            )
    
    def log_llm_interaction(
        self,
        prompt: str,
        response: str,
        model: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an LLM interaction for the current task."""
        if self.current_task_id and self.task_manager:
            self.task_manager.log_llm_interaction(
                task_id=self.current_task_id,
                prompt=prompt,
                response=response,
                model=model,
                metadata=metadata
            )