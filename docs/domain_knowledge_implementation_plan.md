# Domain Knowledge System Implementation Plan

**Status: ✅ IMPLEMENTED (2025-08-17)**

See the [domain_knowledge README](../domain_knowledge/README.md) for usage documentation.

## Overview

This document outlines the implementation plan for a modular domain knowledge system that will enhance the omicairn-agent-local codebase with domain-specific information injection into agent prompts. The system is designed to be extensible for future embedding-based knowledge matching while providing immediate value through static knowledge injection.

## Architecture Overview

```
omicairn-agent-local/
├── domain_knowledge/                    # Single submodule for all domain knowledge functionality
│   ├── __init__.py
│   ├── knowledge_service.py            # Main service interface
│   ├── prompt_injector.py              # Prompt enhancement logic
│   ├── embedding_matcher.py            # Future: Embedding-based matching (not included in this release)
│   ├── knowledge_registry.json         # Metadata about knowledge docs
│   └── domain_docs/                    # Knowledge documents repository
│       ├── single_cell_genomics.md     # Primary knowledge document
│       ├── general_bioinformatics.md   # Future: General bio knowledge
│       └── machine_learning.md         # Future: ML-specific knowledge
├── agents/
│   └── [Updated with knowledge injection points]
└── docs/
    └── domain_knowledge_implementation_plan.md
```

## Code-Level Implementation

### 1. Create Domain Knowledge Submodule Structure

#### 1.1 Module Initialization (`domain_knowledge/__init__.py`)

```python
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
```

#### 1.2 Knowledge Service (`domain_knowledge/knowledge_service.py`)

```python
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
```

#### 1.3 Prompt Injector (`domain_knowledge/prompt_injector.py`)

```python
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
    
    def __init__(self, knowledge_service: Optional[KnowledgeService] = None):
        self.knowledge_service = knowledge_service or KnowledgeService()
    
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
        formatted_knowledge = self.format_knowledge_for_prompt(combined_knowledge)
        
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
    
    def format_knowledge_for_prompt(self, knowledge: str, max_length: int = 4000) -> str:
        """Format and potentially truncate knowledge for prompt inclusion"""
        # Remove excessive whitespace
        knowledge = "\n".join(line.strip() for line in knowledge.split("\n") if line.strip())
        
        # Truncate if too long (with ellipsis)
        if len(knowledge) > max_length:
            knowledge = knowledge[:max_length-100] + "\n\n[... Knowledge truncated for space ...]"
        
        return knowledge
```

#### 1.4 Knowledge Registry (`domain_knowledge/knowledge_registry.json`)

```json
{
  "domains": {
    "single_cell_genomics": {
      "file": "single_cell_genomics.md",
      "description": "Single-cell RNA-seq analysis methods and best practices",
      "tags": ["pseudotime", "trajectory", "scanpy", "preprocessing", "clustering"],
      "last_updated": "2025-08-17",
      "priority": "high",
      "applicable_to": ["bug_fixer", "function_creator", "orchestrator"]
    }
  }
}
```

### 2. Integration Points

#### 2.1 Update Main Agent (`agents/main_agent.py`)

```python
# Add to imports
from domain_knowledge import get_knowledge_service, PromptInjector

class MainAgent:
    def __init__(self, 
                 openai_api_key: str,
                 bug_fixer_type: str = "unified",
                 bug_fixer_model: str = "gpt-4o-mini",
                 enable_interactive_debug: bool = True,
                 enable_domain_knowledge: bool = True,  # NEW
                 domain_knowledge_domains: List[str] = None):  # NEW
        
        # ... existing initialization ...
        
        # Initialize domain knowledge system
        self.enable_domain_knowledge = enable_domain_knowledge
        self.domain_knowledge_domains = domain_knowledge_domains or ["single_cell_genomics"]
        
        if self.enable_domain_knowledge:
            self.knowledge_service = get_knowledge_service()
            self.prompt_injector = PromptInjector(self.knowledge_service)
            logger.info(f"Domain knowledge enabled for domains: {self.domain_knowledge_domains}")
```

#### 2.2 Update Bug Fixer Prompt Templates (`agents/unified_bug_fixer/prompt_templates.py`)

```python
def get_bug_fixer_system_prompt(language: str = "python", 
                                enable_domain_knowledge: bool = False,
                                prompt_injector: Optional[PromptInjector] = None,
                                domains: List[str] = None) -> str:
    """Get system prompt for bug fixer with optional domain knowledge injection"""
    
    base_prompt = BUG_FIXER_SYSTEM_PROMPT_PYTHON if language.lower() == "python" else BUG_FIXER_SYSTEM_PROMPT_R
    
    # Inject domain knowledge if enabled
    if enable_domain_knowledge and prompt_injector and domains:
        base_prompt = prompt_injector.inject_domain_knowledge(base_prompt, domains)
    
    return base_prompt
```

#### 2.3 Update Function Creator (`agents/function_creator.py`)

```python
class FunctionCreator:
    def __init__(self, llm_service: LLMService, 
                 enable_domain_knowledge: bool = False,
                 domain_knowledge_domains: List[str] = None):
        self.llm_service = llm_service
        self.enable_domain_knowledge = enable_domain_knowledge
        self.domain_knowledge_domains = domain_knowledge_domains or []
        
        if self.enable_domain_knowledge:
            from domain_knowledge import get_knowledge_service, PromptInjector
            self.knowledge_service = get_knowledge_service()
            self.prompt_injector = PromptInjector(self.knowledge_service)
    
    def _enhance_prompt_with_domain_knowledge(self, prompt: str) -> str:
        """Enhance function creation prompt with domain knowledge"""
        if self.enable_domain_knowledge and self.prompt_injector:
            return self.prompt_injector.inject_domain_knowledge(
                prompt, self.domain_knowledge_domains
            )
        return prompt
```

### 3. Single-Cell Genomics Knowledge Document

#### 3.1 Create Knowledge Document (`domain_knowledge/domain_docs/single_cell_genomics.md`)

```markdown
# Single-Cell Genomics Analysis Knowledge

## Pseudotime Analysis Methods

### DPT (Diffusion Pseudotime) - Scanpy Implementation

**Prerequisites (CRITICAL - Must run in order)**:
```python
# 1. Preprocessing
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)
sc.pp.highly_variable_genes(adata)
adata = adata[:, adata.var.highly_variable]

# 2. PCA (required)
sc.tl.pca(adata, svd_solver='arpack')

# 3. Neighbors graph (MUST come before diffmap)
sc.pp.neighbors(adata, n_neighbors=30, n_pcs=40)

# 4. Diffusion map (MUST come before DPT)
sc.tl.diffmap(adata)

# 5. Set root cell (MUST be set before DPT)
# Prefer a biologically justified root cell; the diffusion-component extreme below is only a heuristic
adata.uns['iroot'] = np.argmin(adata.obsm['X_diffmap'][:, 0])  # Or specific cell index

# 6. Finally, run DPT
sc.tl.dpt(adata)
```

**Common Errors and Solutions**:
- `ValueError: You need to run pp.neighbors and tl.diffmap first`
  - Solution: Follow the exact preprocessing order above
- `ValueError: Root cell not set`
  - Solution: Set `adata.uns['iroot'] = cell_index` before running DPT

### Palantir - Version-Specific Implementation

**Installation and Version Issues**:
```python
# Correct installation
pip install palantir==1.4.1  # Specific version recommended

# API has changed between versions!
# OLD (pre-1.3): palantir.run_palantir()
# NEW (1.3+): palantir.core.run_palantir()
```

**Correct Implementation**:
```python
import palantir

# 1. PCA is required
if 'X_pca' not in adata.obsm:
    sc.tl.pca(adata)

# 2. Run Palantir with correct API
pr_res = palantir.core.run_palantir(
    adata,
    early_cell='cell_id',  # Or use automatic selection
    num_waypoints=500
)

# 3. Extract pseudotime
adata.obs['palantir_pseudotime'] = pr_res.pseudotime
```

### scFates - Complex Dependencies

**Installation (ORDER MATTERS)**:
```python
# Install in this specific order
pip install numpy==1.23.5  # numpy<1.24 required
pip install ElPiGraph-python
pip install scfates
```

**API note**:
```python
# scf.tl.tree() (branching principal graph) and scf.tl.curve() (linear principal curve)
# are distinct scFates methods; choose based on the expected trajectory topology.

import scfates as scf

# Run trajectory inference (linear example)
scf.tl.curve(adata, Nodes=30, use_rep="X_pca", seed=42)
```

### CellRank - Kernel-Based Approach

**Correct Implementation**:
```python
import cellrank as cr

# 1. Create kernel (choose appropriate type)
# For RNA velocity data:
if 'velocity_graph' in adata.uns:
    kernel = cr.kernels.VelocityKernel(adata)
# For pseudotime data:
elif 'dpt_pseudotime' in adata.obs:
    kernel = cr.kernels.PseudotimeKernel(adata, time_key='dpt_pseudotime')
else:
    # Fallback to connectivity
    kernel = cr.kernels.ConnectivityKernel(adata)

# 2. Compute transition matrix
kernel.compute_transition_matrix()

# 3. Estimate terminal states
g = cr.estimators.GPCCA(kernel)
g.fit(cluster_key='clusters')
g.predict_terminal_states()

# 4. Compute absorption probabilities
g.compute_absorption_probabilities()
```

### DTFLOW - Installation Challenges

DTFLOW was not installable from PyPI when this prototype was developed. Follow the instructions in the upstream
repository (https://github.com/statway/DTFLOW). Do not substitute another method under the DTFLOW name.

## File Access Patterns

### Previous Nodes Interface (CRITICAL)

**NEVER assume filenames - always check what's available**:
```python
from function_block_runtime import previous_nodes

# List all previous nodes and their files
nodes = previous_nodes.list()
for i, node in enumerate(nodes):
    print(f"Node {i+1}: {node['name']}")
    print(f"  Files: {node['files']}")

# Get specific file (returns Path object, not string!)
file_path = previous_nodes.get_file_path(1, 'filename.h5ad')
if file_path and file_path.exists():
    adata = sc.read_h5ad(file_path)
```

**Common Mistakes**:
- ❌ `adata = previous_nodes.get_file_path(1, 'data.h5ad')` (Path is not AnnData!)
- ✅ `path = previous_nodes.get_file_path(1, 'data.h5ad'); adata = sc.read_h5ad(path)`

### Output File Naming

**Method-specific naming prevents conflicts**:
```python
# Save with method-specific names
output_file = os.path.join(path_dict['output_dir'], f'{method_name}_results.h5ad')
adata.write(output_file)

# Also save method results in standard location
adata.obs[f'{method_name}_pseudotime'] = pseudotime_values
```

## Common Preprocessing Requirements

### Standard Single-Cell Pipeline

```python
# 1. Quality control
sc.pp.calculate_qc_metrics(adata, percent_top=None, log1p=False, inplace=True)
sc.pp.filter_cells(adata, min_genes=200)
sc.pp.filter_genes(adata, min_cells=3)

# 2. Normalization (MUST come before log1p)
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)

# 3. Feature selection
sc.pp.highly_variable_genes(adata, min_mean=0.0125, max_mean=3, min_disp=0.5)
adata.raw = adata  # Save full data
adata = adata[:, adata.var.highly_variable]

# 4. Scaling (AFTER subsetting to HVGs)
sc.pp.scale(adata, max_value=10)

# 5. Dimensional reduction
sc.tl.pca(adata, svd_solver='arpack')
sc.pp.neighbors(adata, n_neighbors=10, n_pcs=40)
sc.tl.umap(adata)
```

## Error Patterns and Solutions

### Memory Issues
```python
# Use sparse matrices
adata.X = scipy.sparse.csr_matrix(adata.X)

# Process in chunks
for chunk in adata.chunked_X(1000):
    process(chunk)

# Reduce precision
adata.X = adata.X.astype(np.float32)
```

### API Version Mismatches

Always check package version and use appropriate API:
```python
import scanpy as sc
print(f"Scanpy version: {sc.__version__}")

# Version-specific code
if version.parse(sc.__version__) >= version.parse("1.8.0"):
    # New API
else:
    # Old API
```

## Best Practices

1. **Always validate inputs**: Check for required slots (obsm, uns, etc.)
2. **Save intermediate results**: Write checkpoints after expensive computations
3. **Use consistent naming**: Follow conventions for obs/var/uns keys
4. **Document parameters**: Include rationale for parameter choices
5. **Handle edge cases**: Empty results, single cells, disconnected graphs
```

### 4. Future Extensions

#### 4.1 Embedding Matcher Placeholder (`domain_knowledge/embedding_matcher.py`, not included in this release)

```python
"""Future: Embedding-based knowledge matching"""

from typing import List, Dict, Tuple
import numpy as np

class EmbeddingMatcher:
    """
    Placeholder for future embedding-based knowledge retrieval
    
    TODO: Implement when adding semantic search capabilities
    """
    
    def __init__(self, embedding_model: str = "text-embedding-ada-002"):
        self.embedding_model = embedding_model
        self.knowledge_embeddings = {}
        # TODO: Initialize embedding model client
    
    def precompute_knowledge_embeddings(self, knowledge_docs: Dict[str, str]):
        """
        Pre-compute embeddings for all knowledge chunks
        
        TODO:
        1. Chunk knowledge documents into semantic units
        2. Generate embeddings for each chunk
        3. Store with metadata for retrieval
        """
        pass
    
    def match_knowledge_by_query(self, query: str, top_k: int = 3) -> List[Tuple[str, float]]:
        """
        Find most relevant knowledge chunks for a query
        
        TODO:
        1. Generate query embedding
        2. Compute cosine similarity with knowledge embeddings
        3. Return top-k matches with scores
        """
        # Placeholder implementation
        return []
    
    def match_by_error_context(self, error_msg: str, code_context: str, top_k: int = 3) -> List[Dict]:
        """
        Specialized matching for debugging context
        
        TODO:
        1. Extract key terms from error and code
        2. Generate context-aware embedding
        3. Match against knowledge base
        4. Prioritize based on error type
        """
        return []
```

## Testing Strategy

### Unit Tests (`tests/test_domain_knowledge.py`)

```python
import pytest
from domain_knowledge import KnowledgeService, PromptInjector

def test_knowledge_service_initialization():
    service = KnowledgeService()
    assert service is not None
    assert len(service.get_all_available_domains()) > 0

def test_domain_knowledge_retrieval():
    service = KnowledgeService()
    knowledge = service.get_knowledge_by_domain("single_cell_genomics")
    assert knowledge is not None
    assert "pseudotime" in knowledge.lower()

def test_prompt_injection():
    injector = PromptInjector()
    base_prompt = "You are an AI assistant.\n\nAvailable Actions:\n- read_file"
    enhanced = injector.inject_domain_knowledge(base_prompt, ["single_cell_genomics"])
    
    assert "DOMAIN-SPECIFIC KNOWLEDGE" in enhanced
    assert "pseudotime" in enhanced.lower()
    assert "Available Actions" in enhanced  # Original content preserved

def test_knowledge_caching():
    service = KnowledgeService()
    # First call loads from file
    knowledge1 = service.get_knowledge_by_domain("single_cell_genomics")
    # Second call should use cache
    knowledge2 = service.get_knowledge_by_domain("single_cell_genomics")
    assert knowledge1 == knowledge2
```

## Integration Example

### Using Domain Knowledge in Main Agent

```python
# Initialize main agent with domain knowledge
agent = MainAgent(
    openai_api_key=api_key,
    bug_fixer_type="unified",
    enable_domain_knowledge=True,
    domain_knowledge_domains=["single_cell_genomics"]
)

# The bug fixer and function creator will automatically receive
# enhanced prompts with single-cell genomics knowledge

result = agent.run_analysis(
    input_data_path="data.h5ad",
    user_request="Perform pseudotime analysis using multiple methods",
    output_dir="results/"
)
```

## Goals (not benchmarked)

- Target: improve the pseudotime-task completion rate (to be evaluated; no benchmark result is claimed here)
- Reduce API-related errors (correct method calls)
- Proper preprocessing pipelines
- Better error handling and recovery
- Method-specific file naming to prevent conflicts