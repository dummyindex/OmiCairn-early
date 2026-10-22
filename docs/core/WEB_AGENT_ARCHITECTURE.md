# Web Agent Architecture

## Overview

The Web Agent is a sophisticated research system built with LangGraph that performs intelligent web searches, crawls content, analyzes results, and generates comprehensive research reports. It integrates seamlessly with the bug fixer to provide real-time error research and solution discovery.

## Architecture Diagram

```mermaid
graph TB
    subgraph WebAgentSystem[Web Agent System]
        LangGraphAgent[LangGraph Agent<br/>• State machine orchestration<br/>• 5-phase workflow<br/>• Cost optimization]
        
        Planning[Planning Phase<br/>• Sub-query generation<br/>• Search strategy<br/>• Uses LLM]
        
        Searching[Searching Phase<br/>• Multi-source search<br/>• No LLM (Free)<br/>• Deduplication]
        
        Crawling[Crawling Phase<br/>• Full content extraction<br/>• Quality scoring<br/>• Adaptive limits]
        
        Analyzing[Analyzing Phase<br/>• Pattern identification<br/>• Relevance scoring<br/>• Uses LLM]
        
        Synthesizing[Synthesizing Phase<br/>• Report generation<br/>• Structured output<br/>• Uses LLM]
    end
    
    subgraph SearchSources[Search Sources]
        DuckDuckGo[DuckDuckGo<br/>General web]
        ArXiv[arXiv<br/>Academic papers]
        GitHub[GitHub<br/>Code examples]
        StackOverflow[Stack Overflow<br/>Q&A solutions]
    end
    
    subgraph ContentProcessing[Content Processing]
        Crawl4AI[Crawl4AI<br/>• Async crawling<br/>• JS rendering<br/>• Content extraction]
        
        ArXivConverter[ar5iv Converter<br/>• PDF → HTML<br/>• Paper parsing<br/>• Section extraction]
    end
    
    LangGraphAgent --> Planning
    Planning --> Searching
    Searching --> Crawling
    Crawling --> Analyzing
    Analyzing --> Synthesizing
    
    Searching --> SearchSources
    Crawling --> ContentProcessing
    
    style WebAgentSystem fill:#e3f2fd
    style SearchSources fill:#f3e5f5
    style ContentProcessing fill:#e8f5e9
```

## Core Components

### 1. LangGraph Agent (`agents/web_agent_langgraph/langgraph_agent.py`)

**Purpose**: Main orchestrator using LangGraph state machine for research workflow.

**Key Features**:
- 5-phase workflow (Planning → Searching → Crawling → Analyzing → Synthesizing)
- State management with checkpointing
- Cost-aware execution
- Structured JSON outputs

**Workflow Definition**:
```python
workflow = StateGraph(ResearchState)
workflow.add_node("planning", self.planning_node)
workflow.add_node("searching", self.searching_node)
workflow.add_node("crawling", self.crawling_node)
workflow.add_node("analyzing", self.analyzing_node)
workflow.add_node("synthesizing", self.synthesizing_node)

workflow.add_edge(START, "planning")
workflow.add_edge("planning", "searching")
workflow.add_edge("searching", "crawling")
workflow.add_edge("crawling", "analyzing")
workflow.add_edge("analyzing", "synthesizing")
workflow.add_edge("synthesizing", END)
```

### 2. Search Tools (`agents/web_agent_langgraph/search_tools.py`)

**Purpose**: Multi-source search implementation with crawling support.

**Search Sources**:
1. **DuckDuckGo**: General web search
2. **arXiv**: Academic papers
3. **GitHub**: Code repositories
4. **Stack Overflow**: Programming Q&A

**Key Methods**:
```python
async def search_and_crawl(
    self,
    query: str,
    source: str = "all",
    crawl: bool = True,
    crawl_limit: int = 5
) -> List[SearchResult]:
    """Search and optionally crawl content."""

async def search_web(self, query: str, max_results: int = 3) -> List[SearchResult]:
    """DuckDuckGo web search."""

async def search_arxiv(self, query: str, max_results: int = 3) -> List[SearchResult]:
    """arXiv paper search with ar5iv conversion."""

async def search_github(self, query: str, max_results: int = 3) -> List[SearchResult]:
    """GitHub repository search."""

async def search_stackoverflow(self, query: str, max_results: int = 3) -> List[SearchResult]:
    """Stack Overflow Q&A search."""
```

### 3. Adaptive Crawler (`agents/web_agent_langgraph/adaptive_crawler.py`)

**Purpose**: Intelligent web content extraction with quality scoring.

**Key Features**:
- Asynchronous crawling with asyncio
- JavaScript rendering support
- Content quality scoring
- Adaptive crawl limits
- ar5iv integration for arXiv papers

**Main Method**:
```python
async def crawl_adaptively(
    self,
    urls: List[str],
    query: str,
    max_pages: int = 5,
    quality_threshold: float = 0.7
) -> List[CrawledContent]:
    """
    Crawl URLs adaptively based on content quality.
    Stops when sufficient high-quality content is found.
    """
```

### 4. Data Models (`agents/web_agent_langgraph/models.py`)

**Research State**:
```python
class ResearchState(BaseModel):
    query: str
    error_message: Optional[str]
    context: Optional[Dict[str, Any]]
    research_type: str = "quick"
    plan: Optional[ResearchPlan]
    search_results: List[SearchResult] = []
    crawled_content: List[CrawledContent] = []
    analysis: Optional[ResearchAnalysis]
    report: Optional[ResearchReport]
```

**Key Models**:
- `ResearchPlan`: Planning phase output
- `SearchResult`: Individual search result
- `CrawledContent`: Extracted page content
- `ResearchAnalysis`: Analysis findings
- `ResearchReport`: Final structured report

### 5. Web Agent Tool (`agents/web_agent_langgraph/web_agent_tool.py`)

**Purpose**: Integration interface for bug fixer and other agents.

**Key Features**:
- Simplified API for research requests
- Cost tracking
- Result caching
- Error handling

**Usage**:
```python
web_agent = WebAgentTool(
    model_name="gpt-4o-mini",
    embedding_model="text-embedding-3-small",
    enable_crawling=True,
    crawl_limit=3,
    timeout_seconds=90
)

result = await web_agent.research_error(
    error_message="AttributeError: 'DataFrame' object has no attribute 'append'",
    context={"library": "pandas", "version": "2.0"},
    research_type="quick"
)
```

## Workflow Phases

### 1. Planning Phase

**Purpose**: Generate targeted sub-queries for comprehensive search coverage.

**Process**:
1. Analyze main query/error
2. Generate 3-5 specific sub-queries
3. Plan search strategy
4. Determine research depth

**Example**:
```
Main Query: "Python asyncio best practices"
Sub-queries:
- "asyncio event loop best practices"
- "python async await patterns"
- "asyncio error handling"
- "asyncio performance optimization"
```

### 2. Searching Phase

**Purpose**: Execute searches across multiple sources without LLM usage.

**Features**:
- Parallel search execution
- Source-specific formatting
- URL deduplication
- No LLM cost (free)

### 3. Crawling Phase

**Purpose**: Extract full content from search results.

**Features**:
- Selective crawling of top results
- ar5iv conversion for arXiv papers
- Quality scoring and filtering
- Adaptive stopping when sufficient content found

**ar5iv Integration**:
```python
# Converts arXiv PDF URLs to HTML
"https://arxiv.org/pdf/2301.12345.pdf" 
→ "https://ar5iv.labs.arxiv.org/html/2301.12345"
```

### 4. Analyzing Phase

**Purpose**: Extract insights from search results and crawled content.

**Analysis Includes**:
- Key findings identification
- Pattern recognition
- Source reliability assessment
- Information gap detection
- Confidence scoring

### 5. Synthesizing Phase

**Purpose**: Generate comprehensive research report.

**Report Structure**:
```json
{
    "summary": "Executive summary",
    "detailed_findings": [
        {
            "finding": "Key insight",
            "source": "URL",
            "confidence": "high/medium/low"
        }
    ],
    "code_examples": [...],
    "recommendations": [...],
    "sources": [...],
    "confidence_score": 0.85
}
```

## Integration with Bug Fixer

### Automatic Triggering

The bug fixer automatically uses web research for:
1. **First Attempt**: ImportError, AttributeError, ModuleNotFoundError
2. **Subsequent Attempts**: Any error type
3. **Complex Errors**: Errors with limited local context

### Research Flow

```python
# In UnifiedBugFixer
if self.enable_web_agent and should_research:
    research_result = await self.web_agent_tool.research_error(
        error_message=error_message,
        context={
            "code_snippet": relevant_code,
            "library": detected_library,
            "error_type": error_type
        },
        research_type="quick"  # or "detailed" for complex errors
    )
    
    # Incorporate findings into debug session
    enhanced_context = self._enhance_context_with_research(
        original_context, research_result
    )
```

## Cost Optimization

### Model Selection
- Default: `gpt-4o-mini` for cost efficiency
- Planning/Analysis/Synthesis: ~500-1000 tokens each
- Total cost: ~$0.0008-0.0015 per research

### Optimization Strategies
1. **Free Search Phase**: No LLM usage
2. **Selective Crawling**: Only top-ranked results
3. **Caching**: Avoid redundant searches
4. **Token Limits**: Constrained prompts
5. **JSON Mode**: Efficient structured outputs

## Output Management

### Log Directory Structure
```
agent_tasks/
└── web_agent_research/
    └── attempt_N/
        ├── research_report.md      # Human-readable report
        ├── research_data.json      # Structured data
        └── research_report.json    # Full report JSON
```

### Report Formats

**Markdown Report** (`research_report.md`):
```markdown
# Research Report: [Query]

## Summary
Executive summary of findings...

## Detailed Findings
1. **Finding**: Description
   - Source: [URL]
   - Confidence: High

## Code Examples
```python
# Example code
```

## Recommendations
- Recommendation 1
- Recommendation 2
```

**JSON Data** (`research_data.json`):
Structured data for programmatic access with all findings, sources, and metadata.

## CLI Interface

### Basic Usage
```bash
# Quick research
python -m agents.web_agent_langgraph.cli "Python asyncio basics"

# Error research
python -m agents.web_agent_langgraph.cli \
    --error "AttributeError: 'NoneType' object" \
    --context '{"function": "split"}'

# Detailed research with crawling
python -m agents.web_agent_langgraph.cli \
    "Machine learning algorithms" \
    --type detailed \
    --crawl-limit 10
```

### Advanced Options
```bash
# Save outputs
--output report.md --json data.json

# Debug mode
--dump-path ./debug --verbose

# Performance tuning
--no-crawl              # Disable crawling
--crawl-limit 5         # Limit crawled pages
--search-only           # Only search, no analysis
--quiet                 # Minimal output
```

## Performance Metrics

> Rough, unbenchmarked indications from early development; these are not reported results.

### Speed
- Quick research: 20-30 seconds
- Detailed research: 40-60 seconds
- Deep research: 60-120 seconds

### Content Volume
- Without crawling: ~1-2KB per research
- With crawling: ~50-200KB per research
- 50-100x content increase

### Quality Improvements
- Before: Based on 200-char snippets
- After: Based on full article content

## Best Practices

### 1. Query Formulation
- Be specific with error messages
- Include relevant context
- Use technical terms

### 2. Research Type Selection
- `quick`: Simple errors, known issues
- `detailed`: Complex errors, multiple components
- `deep`: Novel problems, research needed

### 3. Cost Management
- Use caching for repeated errors
- Limit crawl depth appropriately
- Monitor token usage

### 4. Integration
- Handle timeouts gracefully
- Parse structured outputs
- Log research attempts

## Future Enhancements

### Planned Features

1. **Content Caching**
   - Cache crawled content
   - TTL-based expiration
   - Deduplication

2. **Enhanced Sources**
   - Documentation sites
   - Package repositories
   - Forum discussions

3. **ML-Based Selection**
   - Relevance prediction
   - Quality scoring
   - Crawl prioritization

4. **Multi-Modal Support**
   - Image analysis
   - Code screenshot OCR
   - Diagram understanding

### Extension Points

1. **Custom Search Sources**
2. **Specialized Crawlers**
3. **Domain-Specific Analysis**
4. **Integration APIs**
5. **Result Post-Processing**