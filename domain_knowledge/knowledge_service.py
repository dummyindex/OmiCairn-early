"""Service for managing and retrieving domain knowledge"""

import os
import json
from typing import List, Dict, Optional
from pathlib import Path

class KnowledgeService:
    def __init__(self):
        self.base_path = Path(__file__).parent
        self.docs_path = self.base_path / "domain_docs"
        self.registry_path = self.base_path / "knowledge_registry.json"
        self._registry = self._load_registry()
        self._knowledge_cache = {}
    
    def _load_registry(self) -> Dict:
        """Load knowledge registry metadata"""
        if self.registry_path.exists():
            with open(self.registry_path, 'r') as f:
                return json.load(f)
        return {"domains": {}}
    
    def get_knowledge_by_domain(self, domain: str) -> Optional[str]:
        """Retrieve knowledge content for a specific domain"""
        # Check cache first
        if domain in self._knowledge_cache:
            return self._knowledge_cache[domain]
        
        # Load from file
        if domain in self._registry.get("domains", {}):
            doc_info = self._registry["domains"][domain]
            doc_path = self.docs_path / doc_info["file"]
            
            if doc_path.exists():
                with open(doc_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self._knowledge_cache[domain] = content
                    return content
        
        return None
    
    def get_knowledge_by_tags(self, tags: List[str]) -> Dict[str, str]:
        """Retrieve knowledge that matches any of the provided tags"""
        matched_knowledge = {}
        
        for domain, info in self._registry.get("domains", {}).items():
            domain_tags = info.get("tags", [])
            if any(tag in domain_tags for tag in tags):
                knowledge = self.get_knowledge_by_domain(domain)
                if knowledge:
                    matched_knowledge[domain] = knowledge
        
        return matched_knowledge
    
    def get_all_available_domains(self) -> List[str]:
        """Get list of all available knowledge domains"""
        return list(self._registry.get("domains", {}).keys())
    
    def get_domain_metadata(self, domain: str) -> Optional[Dict]:
        """Get metadata for a specific domain"""
        return self._registry.get("domains", {}).get(domain)
    
    # Future implementation placeholder
    def get_knowledge_by_embedding_match(self, query: str, top_k: int = 3) -> List[Dict[str, str]]:
        """
        Future: Retrieve knowledge using embedding-based similarity matching
        
        TODO:
        1. Generate embedding for query
        2. Compare with pre-computed knowledge chunk embeddings
        3. Return top-k most similar knowledge chunks
        """
        # Placeholder - currently returns all knowledge
        return [{"domain": d, "content": self.get_knowledge_by_domain(d)} 
                for d in self.get_all_available_domains()]