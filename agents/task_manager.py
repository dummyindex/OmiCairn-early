"""Agent task management system for tracking and organizing agent activities."""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from enum import Enum

from models import AnalysisTree, AnalysisNode, BaseFunctionBlock
from utils.logger import get_logger

logger = get_logger(__name__)


class TaskType(str, Enum):
    """Types of agent tasks."""
    ORCHESTRATION = "orchestration"
    BUG_FIXING = "bug_fixing"
    FUNCTION_SELECTION = "function_selection"
    TREE_EXPANSION = "tree_expansion"


class TaskStatus(str, Enum):
    """Status of agent tasks."""
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    DELEGATED = "delegated"


class AgentTask:
    """Represents a single agent task with its context and history."""
    
    def __init__(
        self,
        task_id: str,
        task_type: TaskType,
        agent_name: str,
        description: str,
        context: Dict[str, Any],
        parent_task_id: Optional[str] = None
    ):
        self.task_id = task_id
        self.task_type = task_type
        self.agent_name = agent_name
        self.description = description
        self.context = context
        self.parent_task_id = parent_task_id
        self.status = TaskStatus.CREATED
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.completed_at: Optional[datetime] = None
        self.subtasks: List[str] = []
        self.llm_interactions: List[Dict[str, Any]] = []
        self.results: Dict[str, Any] = {}
        self.error: Optional[str] = None
        
        # Entity references
        self.analysis_id: Optional[str] = context.get('analysis_id')
        self.node_id: Optional[str] = context.get('node_id')
        self.function_block_id: Optional[str] = context.get('function_block_id')
        self.job_id: Optional[str] = context.get('job_id')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary for serialization."""
        return {
            'task_id': self.task_id,
            'task_type': self.task_type,
            'agent_name': self.agent_name,
            'description': self.description,
            'context': self.context,
            'parent_task_id': self.parent_task_id,
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'subtasks': self.subtasks,
            'llm_interactions': self.llm_interactions,
            'results': self.results,
            'error': self.error,
            'entity_refs': {
                'analysis_id': self.analysis_id,
                'node_id': self.node_id,
                'function_block_id': self.function_block_id,
                'job_id': self.job_id
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentTask':
        """Create task from dictionary."""
        task = cls(
            task_id=data['task_id'],
            task_type=TaskType(data['task_type']),
            agent_name=data['agent_name'],
            description=data['description'],
            context=data['context'],
            parent_task_id=data.get('parent_task_id')
        )
        
        task.status = TaskStatus(data['status'])
        task.created_at = datetime.fromisoformat(data['created_at'])
        task.updated_at = datetime.fromisoformat(data['updated_at'])
        if data.get('completed_at'):
            task.completed_at = datetime.fromisoformat(data['completed_at'])
        
        task.subtasks = data.get('subtasks', [])
        task.llm_interactions = data.get('llm_interactions', [])
        task.results = data.get('results', {})
        task.error = data.get('error')
        
        # Restore entity references
        entity_refs = data.get('entity_refs', {})
        task.analysis_id = entity_refs.get('analysis_id')
        task.node_id = entity_refs.get('node_id')
        task.function_block_id = entity_refs.get('function_block_id')
        task.job_id = entity_refs.get('job_id')
        
        return task


class TaskManager:
    """Manages agent tasks and their folder structure."""
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.tasks_dir = self.base_dir / "agent_tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.active_tasks: Dict[str, AgentTask] = {}
        
    def create_task(
        self,
        task_type: TaskType,
        agent_name: str,
        description: str,
        context: Dict[str, Any],
        parent_task_id: Optional[str] = None
    ) -> AgentTask:
        """Create a new agent task."""
        task_id = str(uuid.uuid4())
        task = AgentTask(
            task_id=task_id,
            task_type=task_type,
            agent_name=agent_name,
            description=description,
            context=context,
            parent_task_id=parent_task_id
        )
        
        # Create task folder
        task_dir = self._get_task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        
        # Save initial task info
        self._save_task(task)
        
        # Track in memory
        self.active_tasks[task_id] = task
        
        logger.info(f"Created task {task_id} for {agent_name}: {description}")
        
        return task
    
    def update_task_status(
        self, 
        task_id: str, 
        status: TaskStatus,
        results: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """Update task status."""
        task = self.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return
            
        task.status = status
        task.updated_at = datetime.now()
        
        if status == TaskStatus.COMPLETED:
            task.completed_at = datetime.now()
            
        if results:
            task.results.update(results)
            
        if error:
            task.error = error
            
        self._save_task(task)
        logger.info(f"Updated task {task_id} status to {status}")
    
    def add_subtask(self, parent_task_id: str, subtask_id: str) -> None:
        """Add a subtask reference to parent task."""
        parent_task = self.get_task(parent_task_id)
        if parent_task:
            parent_task.subtasks.append(subtask_id)
            parent_task.updated_at = datetime.now()
            self._save_task(parent_task)
    
    def log_llm_interaction(
        self,
        task_id: str,
        prompt: str,
        response: str,
        model: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an LLM interaction for a task."""
        task = self.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return
            
        interaction = {
            'timestamp': datetime.now().isoformat(),
            'model': model,
            'prompt': prompt,
            'response': response,
            'metadata': metadata or {}
        }
        
        task.llm_interactions.append(interaction)
        task.updated_at = datetime.now()
        
        # Save interaction to separate file
        interaction_file = self._get_task_dir(task_id) / f"llm_interaction_{len(task.llm_interactions)}.json"
        with open(interaction_file, 'w') as f:
            json.dump(interaction, f, indent=2)
            
        self._save_task(task)
        logger.info(f"Logged LLM interaction for task {task_id}")
    
    def get_task(self, task_id: str) -> Optional[AgentTask]:
        """Get a task by ID."""
        # Check memory first
        if task_id in self.active_tasks:
            return self.active_tasks[task_id]
            
        # Try loading from disk
        task_file = self._get_task_dir(task_id) / "task_info.json"
        if task_file.exists():
            with open(task_file, 'r') as f:
                data = json.load(f)
                task = AgentTask.from_dict(data)
                self.active_tasks[task_id] = task
                return task
                
        return None
    
    def get_tasks_by_entity(
        self,
        analysis_id: Optional[str] = None,
        node_id: Optional[str] = None,
        function_block_id: Optional[str] = None,
        job_id: Optional[str] = None
    ) -> List[AgentTask]:
        """Get tasks associated with specific entities."""
        matching_tasks = []
        
        # Load all tasks
        for task_dir in self.tasks_dir.iterdir():
            if task_dir.is_dir():
                task_file = task_dir / "task_info.json"
                if task_file.exists():
                    task = self.get_task(task_dir.name)
                    if task:
                        match = True
                        if analysis_id and task.analysis_id != analysis_id:
                            match = False
                        if node_id and task.node_id != node_id:
                            match = False
                        if function_block_id and task.function_block_id != function_block_id:
                            match = False
                        if job_id and task.job_id != job_id:
                            match = False
                            
                        if match:
                            matching_tasks.append(task)
                            
        return matching_tasks
    
    def save_task_artifact(
        self,
        task_id: str,
        filename: str,
        content: Union[str, bytes, Dict[str, Any]]
    ) -> Path:
        """Save an artifact to the task folder."""
        task_dir = self._get_task_dir(task_id)
        artifact_path = task_dir / filename
        
        if isinstance(content, dict):
            with open(artifact_path, 'w') as f:
                json.dump(content, f, indent=2)
        elif isinstance(content, str):
            artifact_path.write_text(content)
        else:
            artifact_path.write_bytes(content)
            
        logger.info(f"Saved artifact {filename} for task {task_id}")
        return artifact_path
    
    def _get_task_dir(self, task_id: str) -> Path:
        """Get the directory for a task."""
        return self.tasks_dir / task_id
    
    def _save_task(self, task: AgentTask) -> None:
        """Save task information to disk."""
        task_file = self._get_task_dir(task.task_id) / "task_info.json"
        with open(task_file, 'w') as f:
            json.dump(task.to_dict(), f, indent=2)
    
    def create_task_summary(self, task_id: str) -> Dict[str, Any]:
        """Create a summary of a task and its subtasks."""
        task = self.get_task(task_id)
        if not task:
            return {}
            
        summary = {
            'task_id': task.task_id,
            'type': task.task_type,
            'agent': task.agent_name,
            'description': task.description,
            'status': task.status,
            'created': task.created_at.isoformat(),
            'duration': None,
            'llm_interactions_count': len(task.llm_interactions),
            'subtasks': []
        }
        
        if task.completed_at:
            duration = (task.completed_at - task.created_at).total_seconds()
            summary['duration'] = f"{duration:.1f}s"
            
        # Add subtask summaries
        for subtask_id in task.subtasks:
            subtask_summary = self.create_task_summary(subtask_id)
            if subtask_summary:
                summary['subtasks'].append(subtask_summary)
                
        return summary