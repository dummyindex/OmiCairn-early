"""Schema definitions for web agent."""

from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ResearchType(str, Enum):
    """Types of research depth."""
    QUICK = "quick"
    DETAILED = "detailed"
    DEEP = "deep"


class ResearchStatus(str, Enum):
    """Status of research operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ResearchConfig(BaseModel):
    """Configuration for research operation."""
    query: str = Field(description="Research query")
    research_type: ResearchType = Field(default=ResearchType.QUICK)
    max_search_results: int = Field(default=5)
    enable_crawling: bool = Field(default=True)
    crawl_limit: Optional[int] = Field(default=None)
    save_to_file: Optional[str] = Field(default=None)
    dump_path: Optional[str] = Field(default=None)
    timeout: int = Field(default=120, description="Timeout in seconds")


class ResearchResult(BaseModel):
    """Result of research operation."""
    query: str
    report: str
    sources: List[Dict[str, Any]]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: ResearchStatus = Field(default=ResearchStatus.COMPLETED)
    error: Optional[str] = None
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    duration_seconds: float = Field(default=0.0)
    cost_estimate: float = Field(default=0.0)
    success: bool = Field(default=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self.model_dump(exclude_none=True, mode='json')