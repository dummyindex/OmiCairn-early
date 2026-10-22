# Web Agent + Bug Fixer Integration Guide

## Overview

The Web Agent has been fully integrated with the Unified Bug Fixer to provide enhanced error research capabilities. The integration uses a cost-optimized configuration with LangGraph and crawl4ai for comprehensive web research.

## Architecture

```
UnifiedBugFixer
    ├── WebAgentTool (primary research)
    │   ├── LangGraphResearchAgent
    │   ├── SearchTools (DuckDuckGo, arXiv, GitHub, StackOverflow)
    │   └── AdaptiveCrawler (Crawl4AI)
    └── DebugSession (fix implementation)
```

## Key Features

1. **Automatic Research Triggering**
   - Triggered for specific error types (AttributeError, ImportError, etc.)
   - Activated on second+ attempts for any error
   - Confidence-based quality assessment

2. **Cost Optimization**
   - Default model: `gpt-4o-mini` (~$0.001 per research)
   - Minimal embeddings: `text-embedding-3-small`
   - Limited crawl depth (3 pages default)

3. **Enhanced Content**
   - Full page crawling vs snippets
   - arXiv ar5iv HTML conversion
   - Quality scoring for relevance

## Usage

### Basic Integration

```python
from agents.unified_bug_fixer import UnifiedBugFixer

# Initialize with web agent enabled (default)
bug_fixer = UnifiedBugFixer(
    model_name="gpt-4o-mini",
    enable_web_agent=True,  # Default
    max_turns=5
)

# Fix bug - web agent automatically triggered for research-worthy errors
result = bug_fixer.fix_bug(
    node_name="my_function",
    error_message="AttributeError: 'DataFrame' object has no attribute 'append'",
    working_directory=Path("./workspace"),
    stderr=traceback_string
)
```

### Orchestrator Integration

When used with the orchestrator, the bug fixer automatically:
1. Creates research output folders under `web_agent_research/`
2. Saves structured research data (JSON + Markdown)
3. Injects findings into debug context
4. Provides confidence scores for solution quality

### Output Structure

For each research attempt, the web agent creates:
```
working_directory/
├── web_agent_research/
│   └── attempt_1/
│       ├── research_report.md    # Human-readable report
│       ├── research_data.json    # Structured findings
│       └── research_report.json  # Full research metadata
```

### Research Data Format

```json
{
  "timestamp": "2025-08-09T18:00:00",
  "error_message": "AttributeError: ...",
  "context": {
    "library": "pandas",
    "function": "append"
  },
  "findings": [
    {
      "finding": "DataFrame.append() is deprecated in pandas 2.0",
      "relevance": "high"
    }
  ],
  "solutions": [
    {
      "solution": "Use pd.concat() instead of append()",
      "type": "recommendation"
    }
  ],
  "code_examples": [
    {
      "code": "df = pd.concat([df, new_row_df], ignore_index=True)",
      "language": "python"
    }
  ],
  "confidence": 0.85,
  "cost": 0.0011
}
```

## Docker Environment

The Python Docker images have been updated with web agent dependencies:

### Full Environment
```dockerfile
# docker/Dockerfile.python
COPY requirements-web-agent.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-web-agent.txt
RUN playwright install chromium
```

### Minimal Environment
Includes core packages:
- langchain, langchain-openai, langgraph
- duckduckgo-search
- openai, pydantic

## Configuration Options

### Bug Fixer Initialization
```python
UnifiedBugFixer(
    model_name="gpt-4o-mini",      # LLM for bug fixing
    enable_web_agent=True,          # Enable web research
    enable_web_search=False,        # Disable Claude web search
    max_turns=5,                    # Max debug turns
    save_debug_logs=True            # Save session logs
)
```

### Web Agent Settings
The web agent uses these defaults:
- Model: `gpt-4o-mini`
- Embeddings: `text-embedding-3-small`
- Crawl limit: 3 pages
- Research types: quick (1st attempt), detailed (2nd+ attempts)

## Best Practices

1. **Error Context**: The web agent automatically extracts context from errors
2. **Cost Control**: Limited to 3-5 crawled pages per research
3. **Caching**: Research results are saved and can be reused
4. **Fallback**: If web agent fails, bug fixer continues without research

## Troubleshooting

### Common Issues

1. **No web results**: DuckDuckGo may rate limit - agent falls back to arXiv/GitHub
2. **Low confidence**: Indicates poor quality results, may need manual intervention
3. **Crawl failures**: Some sites block crawlers, agent skips and continues

### Debug Mode

Enable detailed logging:
```python
import logging
logging.getLogger("agents.web_agent_langgraph").setLevel(logging.DEBUG)
```

## Future Enhancements

1. **Result Caching**: Avoid duplicate research for same errors
2. **ML-based URL Selection**: Smart filtering of which pages to crawl
3. **Multi-language Support**: Research in languages beyond English
4. **Integration with IDE**: Direct error research from development environment