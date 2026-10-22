"""Domain Knowledge System for omicairn-agent-local"""

from .knowledge_service import KnowledgeService
from .prompt_injector import PromptInjector

__all__ = ['KnowledgeService', 'PromptInjector']

# Singleton instance for easy access
_knowledge_service = None

def get_knowledge_service() -> KnowledgeService:
    """Get singleton instance of KnowledgeService"""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = KnowledgeService()
    return _knowledge_service