# Domain Knowledge System

The Domain Knowledge System enhances omicairn-agent-local with domain-specific expertise that can be injected into agent prompts, improving success rates for specialized tasks.

## Overview

This system provides:
- **Knowledge Management**: Centralized storage and retrieval of domain-specific knowledge documents
- **Prompt Injection**: Automatic injection of relevant knowledge into agent prompts
- **Extensible Architecture**: Designed for future embedding-based knowledge matching
- **Multi-Agent Support**: Works with MainAgent, bug fixer, and function creator

## Current Implementation

### Knowledge Domains

Currently implemented:
- **single_cell_genomics**: Comprehensive knowledge about single-cell RNA-seq analysis, pseudotime methods, and common pitfalls
- **pseudotime_implementation**: Specific implementation fixes and troubleshooting for pseudotime methods
- **function_block_faq**: Common issues and solutions for function block development, including previous_nodes usage and debugging tips

### Architecture

```
domain_knowledge/
├── __init__.py              # Module initialization and singleton
├── knowledge_service.py     # Knowledge retrieval and management
├── prompt_injector.py       # Prompt enhancement logic
├── knowledge_registry.json  # Knowledge metadata and configuration
└── domain_docs/            # Knowledge documents
    ├── single_cell_genomics.md
    ├── pseudotime_implementation_experience.md
    ├── function_block_faq.md
    └── ...                   # see knowledge_registry.json for the full list
```

## Usage

### Basic Usage with MainAgent

```python
from agents.main_agent import MainAgent

# Enable domain knowledge (default)
agent = MainAgent(
    openai_api_key="your-key",
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

### Direct Usage

```python
from domain_knowledge import get_knowledge_service, PromptInjector

# Get knowledge service singleton
knowledge_service = get_knowledge_service()

# Retrieve knowledge
knowledge = knowledge_service.get_knowledge_by_domain("single_cell_genomics")

# Inject into prompts
injector = PromptInjector(knowledge_service)
enhanced_prompt = injector.inject_domain_knowledge(
    base_prompt, 
    ["single_cell_genomics"]
)
```

## Adding New Knowledge Domains

1. Create a new markdown file in `domain_docs/`:
   ```markdown
   # Your Domain Knowledge
   
   ## Key Concepts
   ...
   
   ## Common Patterns
   ...
   
   ## Best Practices
   ...
   ```

2. Update `knowledge_registry.json`:
   ```json
   {
     "domains": {
       "your_domain": {
         "file": "your_domain.md",
         "description": "Description of your domain",
         "tags": ["tag1", "tag2"],
         "last_updated": "2025-08-17",
         "priority": "high",
         "applicable_to": ["bug_fixer", "function_creator"]
       }
     }
   }
   ```

3. Use in code:
   ```python
   agent = MainAgent(
       openai_api_key="key",
       domain_knowledge_domains=["your_domain", "single_cell_genomics"]
   )
   ```

## Knowledge Document Guidelines

When creating domain knowledge documents:

1. **Structure**: Use clear headers and sections
2. **Code Examples**: Include working code snippets with correct syntax
3. **Error Patterns**: Document common errors and their solutions
4. **API Changes**: Note version-specific API differences
5. **Prerequisites**: List required steps in order
6. **Best Practices**: Include domain-specific conventions

## Benefits

Intended benefits (qualitative; not systematically benchmarked in this early research version):
- Fewer API-misuse errors by injecting curated package-usage notes
- Better preprocessing pipelines with proper step ordering
- Domain-specific guidance for error handling

## Future Extensions

### Embedding-Based Matching (Planned)

The system is designed to support future embedding-based knowledge retrieval:

```python
# Future implementation
knowledge_chunks = knowledge_service.get_knowledge_by_embedding_match(
    query="How to handle diffusion map errors",
    top_k=3
)
```

### Additional Domains (Planned)

- `general_bioinformatics`: General bioinformatics patterns
- `machine_learning`: ML-specific optimizations
- `data_preprocessing`: Data cleaning and normalization
- `visualization`: Plotting and figure generation

## Testing

Run domain knowledge tests:

```bash
python -m pytest tests/test_domain_knowledge_injection.py -v
```

## Configuration

Domain knowledge is enabled by default. To disable:

```python
agent = MainAgent(
    openai_api_key="key",
    enable_domain_knowledge=False
)
```

## Performance Considerations

- Knowledge is cached after first retrieval
- Prompt injection adds ~4000 characters to prompts
- No significant latency impact
- Knowledge can be truncated if exceeding max_length