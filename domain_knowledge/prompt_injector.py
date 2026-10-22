"""Inject domain knowledge into agent prompts"""

from typing import List, Optional
from .knowledge_service import KnowledgeService

class PromptInjector:
    """Handles injection of domain knowledge into prompts"""
    
    # Template for domain knowledge section
    DOMAIN_KNOWLEDGE_TEMPLATE = """
## DOMAIN-SPECIFIC KNOWLEDGE

{knowledge_content}

This knowledge should inform your approach and solution strategies.
Consider domain-specific patterns, common issues, and best practices.
"""
    
    def __init__(self, knowledge_service: Optional[KnowledgeService] = None, 
                 max_knowledge_length: Optional[int] = None):
        """Initialize the prompt injector
        
        Args:
            knowledge_service: Service for retrieving domain knowledge
            max_knowledge_length: Maximum length for knowledge content (None for no limit)
        """
        self.knowledge_service = knowledge_service or KnowledgeService()
        self.max_knowledge_length = max_knowledge_length
    
    def inject_domain_knowledge(self, base_prompt: str, domains: List[str]) -> str:
        """Inject domain knowledge into a base prompt"""
        # Collect all relevant knowledge
        knowledge_sections = []
        
        for domain in domains:
            knowledge = self.knowledge_service.get_knowledge_by_domain(domain)
            if knowledge:
                knowledge_sections.append(f"### {domain.upper()} KNOWLEDGE\n\n{knowledge}")
        
        if not knowledge_sections:
            return base_prompt
        
        # Combine all knowledge sections
        combined_knowledge = "\n\n".join(knowledge_sections)
        formatted_knowledge = self.format_knowledge_for_prompt(combined_knowledge, self.max_knowledge_length)
        
        # Find insertion point (before "Available Actions" or at the end)
        insertion_markers = [
            "Available Actions",
            "Action Format:",
            "## Available Tools",
            "CRITICAL RULES:"
        ]
        
        insertion_point = len(base_prompt)
        for marker in insertion_markers:
            if marker in base_prompt:
                insertion_point = base_prompt.find(marker)
                break
        
        # Insert knowledge section
        return (base_prompt[:insertion_point] + 
                self.DOMAIN_KNOWLEDGE_TEMPLATE.format(knowledge_content=formatted_knowledge) + 
                "\n\n" + 
                base_prompt[insertion_point:])
    
    def inject_knowledge_section(self, prompt: str, knowledge: str, section_name: str) -> str:
        """Inject a specific knowledge section into a prompt"""
        section = f"\n## {section_name}\n\n{knowledge}\n"
        
        # Find appropriate insertion point
        if "Available Actions" in prompt:
            insertion_point = prompt.find("Available Actions")
        else:
            insertion_point = len(prompt)
        
        return prompt[:insertion_point] + section + prompt[insertion_point:]
    
    def format_knowledge_for_prompt(self, knowledge: str, max_length: Optional[int] = None) -> str:
        """Format and potentially truncate knowledge for prompt inclusion
        
        Args:
            knowledge: The knowledge content to format
            max_length: Maximum length for knowledge (None for no limit)
        """
        # Remove excessive whitespace
        knowledge = "\n".join(line.strip() for line in knowledge.split("\n") if line.strip())
        
        # Only truncate if a limit is specified
        if max_length is not None and len(knowledge) > max_length:
            # Try to preserve complete sections by finding last complete section
            truncation_point = max_length - 100
            # Look for a section break near the truncation point
            last_section = knowledge.rfind("\n##", 0, truncation_point)
            if last_section > truncation_point * 0.8:  # Only use if reasonably close
                knowledge = knowledge[:last_section] + "\n\n[... Knowledge truncated for space ...]"
            else:
                knowledge = knowledge[:truncation_point] + "\n\n[... Knowledge truncated for space ...]"
        
        return knowledge