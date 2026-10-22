"""Research interface for web agent."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from .schemas import ResearchConfig, ResearchResult


class ResearchInterface(ABC):
    """Abstract interface for research agents."""
    
    @abstractmethod
    async def conduct_research(self, config: ResearchConfig) -> ResearchResult:
        """Conduct research based on configuration.
        
        Args:
            config: Research configuration
            
        Returns:
            Research result
        """
        pass
    
    @abstractmethod
    async def conduct_research_for_error(
        self,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ResearchResult:
        """Conduct research for a specific error.
        
        Args:
            error_message: Error message to research
            context: Additional context
            
        Returns:
            Research result
        """
        pass