"""Schema definitions for agent responses."""

from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field

from models import StaticConfig


class FunctionBlockContent(BaseModel):
    """Schema for new function block generation."""
    name: str
    task_description: str  # What the function should do
    parameters: Dict[str, Any] = Field(default_factory=dict)
    new: bool = True
    rest_task: Optional[str] = None


class ExistingFunctionBlockRef(BaseModel):
    """Schema for existing function block reference."""
    id: Union[str, int]
    name: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    new: bool = False
    rest_task: Optional[str] = None


class FunctionBlockRecommendation(BaseModel):
    """Schema for function block recommendations."""
    satisfied: bool
    next_level_function_blocks: List[Union[FunctionBlockContent, ExistingFunctionBlockRef]]
    reasoning: str


class NodeExecutionResult(BaseModel):
    """Result of node execution."""
    node_id: str
    status: Any  # NodeState
    output_path: Optional[str] = None
    error: Optional[str] = None
    execution_time: Optional[Any] = None  # datetime


class NodeExpansionDecision(BaseModel):
    """Decision about expanding from a node."""
    node_id: str
    should_expand: bool
    reason: str
    suggested_analyses: List[str] = Field(default_factory=list)
    add_to_report: bool = True


class OrchestratorTask(BaseModel):
    """Task for orchestrator agent."""
    task_id: str
    tree: Any  # AnalysisTree
    input_data_path: Any  # Path
    user_request: str
    max_iterations: int = 10
    timeout: Optional[float] = None


class OrchestratorResult(BaseModel):
    """Result from orchestrator agent."""
    task_id: str
    tree_id: str
    completed_nodes: List[str]
    failed_nodes: List[str]
    node_results: Dict[str, Any]
    expansion_decisions: Dict[str, Any]
    output_dir: str
    statistics: Dict[str, Any]