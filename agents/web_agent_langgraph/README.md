# LangGraph Web Research Agent

A sophisticated research agent built with LangGraph that performs web searches, analyzes results, and generates comprehensive research reports with structured JSON outputs.

## Architecture Overview

The LangGraph research agent follows a 4-phase workflow:

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌───────────────┐
│  PLANNING   │───►│  SEARCHING   │───►│  ANALYZING  │───►│ SYNTHESIZING  │
└─────────────┘    └──────────────┘    └─────────────┘    └───────────────┘
      │                    │                    │                    │
      ▼                    ▼                    ▼                    ▼
  Create sub-      Search multiple      Analyze results      Generate final
  queries from     sources without      with LLM to          research report
  main query       using LLM            extract insights     in JSON format
```

### Phase Details:

1. **Planning Phase** (Uses LLM)
   - Takes the main research query
   - Generates 3-5 specific sub-queries for better search coverage
   - Plans search strategy across different sources
   - Output: `ResearchPlan` with sub-queries and strategy

2. **Searching Phase** (No LLM - Free)
   - Executes searches across multiple sources:
     - **Web**: DuckDuckGo search (general web results)
     - **arXiv**: Academic papers (returns PDF URLs)
     - **GitHub**: Code repositories and examples
     - **Stack Overflow**: Programming Q&A
   - Deduplicates results by URL
   - Output: List of `SearchResult` objects with titles, URLs, and snippets

3. **Analyzing Phase** (Uses LLM)
   - Reviews all search results
   - Identifies key findings and patterns
   - Determines most relevant URLs
   - Identifies information gaps
   - Output: `ResearchAnalysis` with findings and confidence score

4. **Synthesizing Phase** (Uses LLM)
   - Creates comprehensive research report
   - Structures findings with sources
   - Extracts code examples if applicable
   - Provides recommendations
   - Output: `ResearchReport` in structured JSON format

## Additional Features

### Adaptive Content Crawling with Crawl4AI
The agent now automatically crawls and extracts full content from search results:
- **Full article content** instead of 200-char snippets
- **Intelligent crawling** that stops when sufficient information is gathered
- **Quality scoring** for each crawled page

### arXiv ar5iv Integration
For arXiv papers:
- Automatically converts PDF URLs to ar5iv HTML versions
- Example: `arxiv.org/pdf/2301.12345.pdf` → `ar5iv.labs.arxiv.org/html/2301.12345`
- Extracts full paper content in readable format
- Provides complete context for academic research

## Data Models (Pydantic)

All data is structured using Pydantic models for type safety and JSON serialization:

```python
ResearchState          # Main workflow state
├── ResearchPlan       # Planning phase output
├── SearchResult[]     # Search results
├── ResearchAnalysis   # Analysis phase output
└── ResearchReport     # Final report
```

## Output Directories

1. **Logs Directory**: `agent_tasks/langgraph_research_logs/`
   - Auto-saves every research as both `.json` and `.md`
   - Filename format: `research_YYYYMMDD_HHMMSS_<query_slug>.*`

2. **Process Dumps**: When `--dump-path` is specified
   - Saves state after each phase
   - Files: `1_planning_*.json`, `2_searching_*.json`, etc.

3. **Custom Output**: When `--output` is specified
   - Saves to user-specified location

## CLI Usage

### Basic Research
```bash
# Quick research (cheapest, fastest)
python -m agents.web_agent_langgraph.cli "Python asyncio basics"

# Detailed research
python -m agents.web_agent_langgraph.cli "Machine learning algorithms" --type detailed

# Deep research (most comprehensive)
python -m agents.web_agent_langgraph.cli "Quantum computing" --type deep
```

### Search-Only Mode (Free - No LLM)
```bash
# Just search, no analysis
python -m agents.web_agent_langgraph.cli --search-only "Python pandas merge"

# Returns JSON with all search results grouped by source
```

### Error Research
```bash
# Research a specific error
python -m agents.web_agent_langgraph.cli \
  --error "AttributeError: 'NoneType' object has no attribute 'split'" \
  --context '{"library": "pandas", "function": "read_csv"}'
```

### Advanced Options
```bash
# Save to specific file
python -m agents.web_agent_langgraph.cli "REST API patterns" \
  --output ./reports/api_research.md \
  --json ./reports/api_research.json

# Enable process dumping for debugging
python -m agents.web_agent_langgraph.cli "Python decorators" \
  --dump-path ./debug_dump \
  --type detailed

# Quiet mode (minimal output)
python -m agents.web_agent_langgraph.cli "Python generators" --quiet

# Disable crawling for faster results
python -m agents.web_agent_langgraph.cli "Quick lookup" --no-crawl

# Custom crawl limit
python -m agents.web_agent_langgraph.cli "Deep research" --crawl-limit 15
```

## Cost Optimization

The agent is optimized for low cost:
- Default model: `gpt-4o-mini` (actual cost depends on query, research type and current provider pricing; the agent reports a per-run estimate)
- Search phase uses no LLM (free)
- Limited search results (3 per source by default)
- JSON mode for structured outputs (more efficient)

## Integration with Bug Fixer

The agent integrates with `UnifiedBugFixer`:
```python
# Enable the web research agent for complex errors
bug_fixer = UnifiedBugFixer(
    llm_service=llm_service,
    enable_web_agent=True
)

# Automatically triggers research for:
# - AttributeError, ImportError, ModuleNotFoundError (1st attempt)
# - Any error on 2nd+ attempts
```

## Future Enhancements

1. **arXiv Enhancement**:
   - Extract text from downloaded PDFs
   - Parse paper sections (intro, methods, results)

2. **Selective Fetching**:
   - Only fetch top-ranked URLs
   - Implement smart filtering based on relevance
   - Add timeout and retry logic

3. **Caching**:
   - Cache search results
   - Cache fetched content
   - Implement TTL for cache entries

## Example Output Structure

```json
{
  "query": "Python asyncio tutorial",
  "summary": "Asyncio is Python's built-in library for asynchronous programming...",
  "detailed_findings": [
    {
      "finding": "Asyncio uses an event loop to manage asynchronous tasks",
      "source": "https://docs.python.org/3/library/asyncio.html",
      "confidence": "high"
    }
  ],
  "code_examples": [
    {
      "description": "Basic async function example",
      "code": "async def hello():\n    await asyncio.sleep(1)\n    print('Hello')",
      "language": "python"
    }
  ],
  "recommendations": [
    "Start with basic coroutines before moving to advanced patterns",
    "Use asyncio.run() for simple scripts"
  ],
  "sources": [
    {
      "title": "Python asyncio Documentation",
      "url": "https://docs.python.org/3/library/asyncio.html",
      "relevance": "high"
    }
  ],
  "limitations": [
    "Research based on search snippets, not full content"
  ],
  "confidence_score": 0.85
}
```

## Dependencies

- `langgraph`: State machine orchestration
- `langchain`: LLM integration
- `ddgs` (formerly `duckduckgo-search`): Web search
- `arxiv`: Academic paper search
- `crawl4ai`: Full-page content crawling (optional; disable with `--no-crawl`)
- `beautifulsoup4`: HTML parsing
- `aiohttp`: Async HTTP client

## Responsible use

The agent issues web searches and fetches third-party pages. Users are responsible for complying with the terms of
service and robots.txt policies of the sites that are searched or crawled, and for respecting their rate limits.
