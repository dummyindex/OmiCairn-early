"""Data models for OmiCairn Agent Local."""

from enum import Enum
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
import uuid
from constants import DEFAULT_OPENAI_MODEL


class NodeState(str, Enum):
    """States of analysis nodes."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEBUGGING = "debugging"
    SKIPPED = "skipped"


class JobReviewStatus(str, Enum):
    """Job review statuses for quality assessment."""
    PASSED = "passed"           # Output meets quality standards
    FAILED = "failed"           # Quality issues identified
    NOT_REVIEWED = "not_reviewed"  # Not yet reviewed (default)
    SKIPPED = "skipped"         # Review skipped (e.g., for system nodes)


class FunctionBlockType(str, Enum):
    """Types of function blocks."""
    PYTHON = "python"
    R = "r"


class GenerationMode(str, Enum):
    """Function block generation modes."""
    MIXED = "mixed"  # Can use existing or generate new
    ONLY_NEW = "only_new"  # Only generate new blocks
    ONLY_EXISTING = "only_existing"  # Only use existing blocks


class FileType(str, Enum):
    """Types of files that can be inputs/outputs."""
    ANNDATA = "anndata"
    CSV = "csv"
    TSV = "tsv"
    JSON = "json"
    PARQUET = "parquet"
    H5 = "h5"
    ZARR = "zarr"
    IMAGE = "image"
    PDF = "pdf"
    TEXT = "text"
    BINARY = "binary"
    OTHER = "other"


class FileInfo(BaseModel):
    """Information about a file in the execution context."""
    filename: str
    filepath: str  # Relative path within the workspace
    filetype: FileType
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_by_node: Optional[str] = None
    created_at: Optional[datetime] = None


class ExecutionContext(BaseModel):
    """Context provided to function blocks during execution."""
    node_id: str
    tree_id: str
    
    # Input files from previous nodes
    input_files: List[FileInfo] = Field(default_factory=list)
    
    # Output files from previous nodes (for reference)
    available_files: List[FileInfo] = Field(default_factory=list)
    
    # Paths
    input_dir: str  # Where input files are located
    output_dir: str  # Where to write output files
    figures_dir: str  # Where to save figures
    
    # Metadata about the analysis tree
    tree_metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Previous node results for context
    previous_results: List[Dict[str, Any]] = Field(default_factory=list)


class InputSpecification(BaseModel):
    """Specification for function block inputs."""
    # Required input files
    required_files: List[Dict[str, Any]] = Field(default_factory=list)
    # Example: [{"name": "anndata.h5ad", "type": "anndata", "description": "Preprocessed scRNA-seq data"}]
    
    # Optional input files
    optional_files: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Whether the block can handle multiple input files
    accepts_multiple: bool = False
    
    # File naming conventions
    naming_convention: Optional[str] = None


class OutputSpecification(BaseModel):
    """Specification for function block outputs."""
    # Expected output files
    output_files: List[Dict[str, Any]] = Field(default_factory=list)
    # Example: [{"name": "anndata.h5ad", "type": "anndata", "description": "Data with velocity computed"}]
    
    # Expected figures
    figures: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Metadata that will be produced
    metadata_keys: List[str] = Field(default_factory=list)


class Arg(BaseModel):
    """Function block argument definition."""
    name: str
    value_type: str
    description: str
    optional: bool = False
    default_value: Optional[Union[str, int, float, bool, List]] = None
    render_type: str = "text"
    options: Optional[List[Union[str, int]]] = None


class StaticConfig(BaseModel):
    """Static configuration for a function block."""
    args: List[Arg]
    description: str
    tag: str
    document_url: str = ""
    source: str = "generated"
    preset_env: Optional[str] = None
    
    # New fields for general framework
    input_specification: Optional[InputSpecification] = None
    output_specification: Optional[OutputSpecification] = None
    enforce_validation: bool = False  # Optional enforcement, controlled by function block developer
    
    # Docker image override
    docker_image: Optional[str] = None  # Custom Docker image for this function block


class BaseFunctionBlock(BaseModel):
    """Base class for function blocks. 
    
    This is an abstract base that should not be instantiated directly.
    Use NewFunctionBlock for generated code or ExistingFunctionBlock for references.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    type: FunctionBlockType
    description: str
    
    @field_validator('type', mode='before')
    def validate_type(cls, v):
        if isinstance(v, str):
            return FunctionBlockType(v)
        return v
    parameters: Dict[str, Any] = Field(default_factory=dict)
    static_config: StaticConfig
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True


class NewFunctionBlock(BaseFunctionBlock):
    """Newly generated function block."""
    code: str
    requirements: str
    rest_task: Optional[str] = None
    new: bool = True
    output_description: Optional[str] = None  # Descriptive explanation of outputs produced


class ExistingFunctionBlock(BaseFunctionBlock):
    """Reference to existing function block."""
    function_block_id: str
    version_id: Optional[str] = None
    rest_task: Optional[str] = None
    new: bool = False
    docker_image: Optional[str] = None  # Custom Docker image override loaded from config.json


class NodeExecutionResult(BaseModel):
    """Result of executing a node."""
    node_id: str
    state: NodeState
    
    # Timing
    start_time: datetime
    end_time: datetime
    duration: float
    
    # Output files
    output_files: List[FileInfo] = Field(default_factory=list)
    figures: List[str] = Field(default_factory=list)
    
    # Logs and errors
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error: Optional[str] = None
    
    # Metadata produced by the function block
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Metrics
    memory_usage_mb: Optional[float] = None
    cpu_time_seconds: Optional[float] = None


class AnalysisNode(BaseModel):
    """Node in the analysis tree."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None
    analysis_id: str
    function_block: Union[NewFunctionBlock, ExistingFunctionBlock]
    state: NodeState = NodeState.PENDING
    level: int = 0
    children: List[str] = Field(default_factory=list)
    
    # Execution info
    execution_result: Optional[NodeExecutionResult] = None
    debug_attempts: int = 0
    
    # Legacy fields for compatibility
    output_data_id: Optional[str] = None
    figures: List[str] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: Optional[float] = None
    
    # Job review fields - separate from execution status
    job_review_status: Optional[JobReviewStatus] = None  # Quality review status
    job_review_result: Optional[Dict[str, Any]] = None  # Full review details
    job_review_summary: Optional[str] = None  # Human-readable summary
    needs_rework: bool = False  # Whether node needs to be reworked based on review
    rework_attempts: int = 0  # Number of times this task has been attempted due to job review failures
    rework_limit_reached: bool = False  # Whether this node has hit the maximum rework attempts
    rework_of_node_id: Optional[str] = None  # If this is a rework, which node it's reworking
    has_successful_rework: bool = False  # Whether this node has a successful rework
    propagated_failure_context: Optional[Dict[str, Any]] = None  # Failure context from previous failed node
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True


class AnalysisTree(BaseModel):
    """The hierarchical analysis tree."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    root_node_id: Optional[str] = None
    nodes: Dict[str, AnalysisNode] = Field(default_factory=dict)
    
    # User input
    user_request: str
    input_data_path: str  # Can be a file or directory
    
    # Configuration
    max_nodes: int
    max_children_per_node: int
    max_debug_trials: int
    generation_mode: GenerationMode = GenerationMode.MIXED
    llm_model: str = DEFAULT_OPENAI_MODEL
    
    # State
    total_nodes: int = 0
    completed_nodes: int = 0
    failed_nodes: int = 0
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True
    
    def add_node(self, node: AnalysisNode) -> None:
        """Add a node to the tree."""
        self.nodes[node.id] = node
        self.total_nodes += 1
        
        if node.parent_id and node.parent_id in self.nodes:
            parent = self.nodes[node.parent_id]
            if node.id not in parent.children:
                parent.children.append(node.id)
    
    def get_node(self, node_id: str) -> Optional[AnalysisNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)
    
    def update_node_state(self, node_id: str, state: NodeState) -> None:
        """Update node state and maintain accurate statistics."""
        if node_id in self.nodes:
            old_state = self.nodes[node_id].state
            
            # Only update if state actually changed
            if old_state != state:
                self.nodes[node_id].state = state
                self.nodes[node_id].updated_at = datetime.now()
                
                # Update statistics based on state transitions
                # Decrement old state counter
                if old_state == NodeState.COMPLETED:
                    self.completed_nodes = max(0, self.completed_nodes - 1)
                elif old_state == NodeState.FAILED:
                    self.failed_nodes = max(0, self.failed_nodes - 1)
                
                # Increment new state counter
                if state == NodeState.COMPLETED:
                    self.completed_nodes += 1
                elif state == NodeState.FAILED:
                    self.failed_nodes += 1
    
    def get_node_by_id(self, node_id: str) -> Optional[AnalysisNode]:
        """Get a node by its ID."""
        return self.nodes.get(node_id)
    
    def get_children(self, node_id: str) -> List[AnalysisNode]:
        """Get all children of a node."""
        node = self.get_node_by_id(node_id)
        if not node:
            return []
        return [self.nodes[child_id] for child_id in node.children if child_id in self.nodes]
    
    def get_ancestry_path(self, node_id: str) -> List[str]:
        """Get the path from root to a node."""
        path = []
        current_id = node_id
        
        while current_id:
            if current_id in path:  # Prevent infinite loop
                break
            path.append(current_id)
            node = self.get_node_by_id(current_id)
            if not node:
                break
            current_id = node.parent_id
        
        return list(reversed(path))


class ExecutionResult(BaseModel):
    """Result from executing a function block."""
    success: bool
    output_data_path: Optional[str] = None
    figures: List[str] = Field(default_factory=list)
    logs: str = ""
    error: Optional[str] = None
    duration: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    exit_code: Optional[int] = None
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


# Job execution models
class JobStatus(str, Enum):
    """Status of a job execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class JobInfo(BaseModel):
    """Information about a job execution."""
    job_id: str
    node_id: str
    container_id: Optional[str] = None
    status: JobStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    
    # Resource usage
    memory_usage_mb: Optional[float] = None
    cpu_time_seconds: Optional[float] = None
    
    # File paths
    stdout_path: Optional[str] = None
    stderr_path: Optional[str] = None
    metrics_path: Optional[str] = None
    
    class Config:
        use_enum_values = True


class ExecutionRequest(BaseModel):
    """Request to execute a function block."""
    node: AnalysisNode
    execution_context: ExecutionContext
    timeout_seconds: int = 600
    memory_limit: str = "8g"
    cpu_limit: float = 4.0


class ExecutionResponse(BaseModel):
    """Response from executing a function block."""
    success: bool
    execution_result: Optional[NodeExecutionResult] = None
    job_info: Optional[JobInfo] = None
    error: Optional[str] = None