# Adaptive Crawling Integration Plan for LangGraph Web Agent

## Executive Summary

This document outlines the integration of Crawl4AI's adaptive crawling capabilities into our LangGraph web research agent. The goal is to intelligently crawl and extract content from search results using semantic understanding, stopping when sufficient information is gathered.

## Architecture Overview

```
┌─────────────────┐
│  Search Phase   │
│  (DuckDuckGo)   │
└────────┬────────┘
         │ URLs
         ▼
┌─────────────────┐     ┌──────────────────┐
│ Adaptive Crawler│◄────│ Embedding Model  │
│   (Crawl4AI)    │     │ (Semantic Score) │
└────────┬────────┘     └──────────────────┘
         │ Content
         ▼
┌─────────────────┐
│ LangGraph Agent │
│   (Analysis)    │
└─────────────────┘
```

## Implementation Plan

### Phase 1: Core Infrastructure (Week 1)

#### 1.1 Install Dependencies
```bash
pip install crawl4ai
pip install sentence-transformers  # For embeddings
```

#### 1.2 Create Adaptive Crawler Module
```python
# agents/web_agent_langgraph/adaptive_crawler.py

from crawl4ai import AsyncWebCrawler, AdaptiveCrawler, AdaptiveConfig
from typing import List, Dict, Optional
import asyncio

class EnhancedAdaptiveCrawler:
    """Wrapper around Crawl4AI adaptive crawler with custom configurations."""
    
    def __init__(
        self,
        strategy: str = "embedding",  # or "statistical"
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        confidence_threshold: float = 0.7,
        max_pages: int = 10,
        top_k_links: int = 3
    ):
        self.config = AdaptiveConfig(
            strategy=strategy,
            embedding_model=embedding_model,
            confidence_threshold=confidence_threshold,
            max_pages=max_pages,
            top_k_links=top_k_links,
            n_query_variations=5,  # Generate query variations
            embedding_min_confidence_threshold=0.1
        )
        
    async def crawl_search_results(
        self, 
        search_results: List[Dict], 
        query: str,
        source_type: str = "web"
    ) -> Dict[str, Dict]:
        """Crawl search results adaptively based on query."""
        
        async with AsyncWebCrawler() as crawler:
            adaptive = AdaptiveCrawler(crawler, config=self.config)
            
            crawled_content = {}
            
            for result in search_results:
                if source_type == "arxiv":
                    # Convert to ar5iv HTML URL
                    url = self._convert_arxiv_url(result['url'])
                else:
                    url = result['url']
                
                try:
                    # Adaptive crawl starting from this URL
                    crawl_result = await adaptive.digest(
                        start_url=url,
                        query=query,
                        max_depth=2  # Follow links up to 2 levels deep
                    )
                    
                    crawled_content[result['url']] = {
                        'title': result['title'],
                        'original_snippet': result['snippet'],
                        'crawled_content': crawl_result.extracted_text,
                        'confidence': crawl_result.confidence_score,
                        'pages_crawled': len(crawl_result.crawled_pages),
                        'metadata': crawl_result.metadata
                    }
                    
                    # Stop if we have high confidence across results
                    if self._check_saturation(crawled_content):
                        break
                        
                except Exception as e:
                    crawled_content[result['url']] = {
                        'error': str(e),
                        'title': result['title']
                    }
            
            return crawled_content
```

### Phase 2: Integration with Search Tools (Week 1-2)

#### 2.1 Update Search Tools
```python
# agents/web_agent_langgraph/search_tools.py

class SearchTools:
    def __init__(self, enable_adaptive_crawling: bool = True):
        self.ddgs = DDGS()
        self.session = None
        self.enable_adaptive_crawling = enable_adaptive_crawling
        if enable_adaptive_crawling:
            self.adaptive_crawler = EnhancedAdaptiveCrawler()
    
    async def search_with_crawling(
        self, 
        query: str, 
        max_results: int = 5,
        crawl_depth: int = 2
    ) -> List[EnrichedSearchResult]:
        """Search and adaptively crawl results."""
        
        # Get initial search results
        search_results = self.search_web(query, max_results)
        
        if not self.enable_adaptive_crawling:
            return search_results
        
        # Convert to dict format for crawler
        results_dict = [
            {'url': r.url, 'title': r.title, 'snippet': r.snippet}
            for r in search_results
        ]
        
        # Crawl adaptively
        crawled_content = await self.adaptive_crawler.crawl_search_results(
            results_dict, 
            query,
            source_type='web'
        )
        
        # Enrich search results with crawled content
        enriched_results = []
        for result in search_results:
            enriched = EnrichedSearchResult(
                **result.dict(),
                crawled_content=crawled_content.get(result.url, {})
            )
            enriched_results.append(enriched)
        
        return enriched_results
```

#### 2.2 Create Enriched Result Model
```python
# agents/web_agent_langgraph/models.py

class CrawledContent(BaseModel):
    """Content extracted via adaptive crawling."""
    extracted_text: Optional[str] = None
    confidence: Optional[float] = None
    pages_crawled: Optional[int] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class EnrichedSearchResult(SearchResult):
    """Search result with adaptively crawled content."""
    crawled_content: Optional[CrawledContent] = None
    crawl_confidence: Optional[float] = None
```

### Phase 3: LangGraph Workflow Integration (Week 2)

#### 3.1 Add Adaptive Crawling Phase
```python
# agents/web_agent_langgraph/langgraph_agent.py

async def _adaptive_crawl(self, state: ResearchState) -> ResearchState:
    """Adaptively crawl top search results based on query."""
    state.current_phase = ResearchPhase.CRAWLING
    
    if state.dump_enabled and state.dump_path:
        self._dump_phase_data(state, "2a_crawling_start")
    
    # Select top results for crawling
    results_to_crawl = self._select_for_crawling(
        state.search_results,
        state.query,
        max_web=5,
        max_arxiv=3
    )
    
    # Initialize adaptive crawler with query-specific config
    crawler_config = self._get_crawler_config(state.query, state.research_type)
    crawler = EnhancedAdaptiveCrawler(**crawler_config)
    
    # Crawl each source type separately for optimization
    enriched_results = []
    
    for source_type, results in self._group_by_source(results_to_crawl).items():
        crawled = await crawler.crawl_search_results(
            results,
            state.query,
            source_type=source_type
        )
        enriched_results.extend(crawled)
    
    # Update state with enriched results
    state.search_results = enriched_results
    state.crawl_metadata = {
        'total_pages_crawled': sum(r.get('pages_crawled', 0) for r in crawled.values()),
        'average_confidence': np.mean([r.get('confidence', 0) for r in crawled.values()]),
        'strategy_used': crawler_config['strategy']
    }
    
    if state.dump_enabled and state.dump_path:
        self._dump_phase_data(state, "2a_crawling_complete")
    
    return state
```

#### 3.2 Dynamic Strategy Selection
```python
def _get_crawler_config(self, query: str, research_type: str) -> Dict:
    """Select crawling strategy based on query characteristics."""
    
    # Use embedding strategy for complex/conceptual queries
    if any(term in query.lower() for term in ['how', 'why', 'explain', 'understand']):
        return {
            'strategy': 'embedding',
            'embedding_model': 'sentence-transformers/all-MiniLM-L6-v2',
            'confidence_threshold': 0.8,
            'max_pages': 15 if research_type == 'deep' else 8
        }
    
    # Use statistical strategy for specific technical queries
    else:
        return {
            'strategy': 'statistical',
            'confidence_threshold': 0.7,
            'max_pages': 10 if research_type == 'deep' else 5
        }
```

### Phase 4: Smart Selection & Optimization (Week 2-3)

#### 4.1 Intelligent URL Selection
```python
def _select_for_crawling(
    self, 
    results: List[SearchResult], 
    query: str,
    **limits
) -> List[Dict]:
    """Select most promising URLs for adaptive crawling."""
    
    # Score each result for crawl priority
    scored_results = []
    for result in results:
        score = self._calculate_crawl_priority(result, query)
        scored_results.append((score, result))
    
    # Sort by score and apply limits
    scored_results.sort(key=lambda x: x[0], reverse=True)
    
    selected = []
    source_counts = defaultdict(int)
    
    for score, result in scored_results:
        source = result.source
        limit = limits.get(f'max_{source}', 3)
        
        if source_counts[source] < limit:
            selected.append(result)
            source_counts[source] += 1
            
        if len(selected) >= sum(limits.values()):
            break
    
    return selected

def _calculate_crawl_priority(self, result: SearchResult, query: str) -> float:
    """Calculate priority score for crawling a result."""
    score = 0.0
    
    # Domain authority
    trusted_domains = ['arxiv.org', 'github.com', 'docs.python.org', 'pytorch.org']
    if any(domain in result.url for domain in trusted_domains):
        score += 0.3
    
    # Query term coverage in title/snippet
    query_terms = set(query.lower().split())
    content_terms = set((result.title + ' ' + result.snippet).lower().split())
    overlap = len(query_terms & content_terms) / len(query_terms)
    score += overlap * 0.4
    
    # Source type bonus
    source_weights = {'arxiv': 0.2, 'github': 0.15, 'stackoverflow': 0.15}
    score += source_weights.get(result.source, 0.1)
    
    return score
```

### Phase 5: arXiv Special Handling (Week 3)

#### 5.1 arXiv URL Converter
```python
def _convert_arxiv_url(self, pdf_url: str) -> str:
    """Convert arXiv PDF URL to ar5iv HTML URL."""
    # Extract paper ID from https://arxiv.org/pdf/2301.12345.pdf
    import re
    match = re.search(r'arxiv\.org/pdf/(\d+\.\d+)', pdf_url)
    if match:
        paper_id = match.group(1)
        return f"https://ar5iv.labs.arxiv.org/html/{paper_id}"
    return pdf_url

async def download_arxiv_pdf(self, pdf_url: str, save_dir: Path) -> Optional[Path]:
    """Download arXiv PDF for reference."""
    paper_id = self._extract_arxiv_id(pdf_url)
    if not paper_id:
        return None
    
    pdf_path = save_dir / f"{paper_id}.pdf"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(pdf_url) as response:
            if response.status == 200:
                pdf_path.write_bytes(await response.read())
                return pdf_path
    
    return None
```

### Phase 6: Enhanced Analysis (Week 3-4)

#### 6.1 Update Analysis with Crawled Content
```python
async def _analyze_results(self, state: ResearchState) -> ResearchState:
    """Analyze search results with crawled content."""
    
    # Prepare enhanced context
    results_with_content = []
    for result in state.search_results[:20]:
        result_data = {
            'title': result.title,
            'url': result.url,
            'snippet': result.snippet,
            'source': result.source
        }
        
        # Add crawled content if available
        if hasattr(result, 'crawled_content') and result.crawled_content:
            content = result.crawled_content
            result_data['has_full_content'] = True
            result_data['content_preview'] = content.get('extracted_text', '')[:1000]
            result_data['crawl_confidence'] = content.get('confidence', 0)
            result_data['pages_analyzed'] = content.get('pages_crawled', 0)
        
        results_with_content.append(result_data)
    
    # Enhanced prompt with crawled content
    prompt = f"""Analyze these search results with their crawled content:

Query: {state.query}
Search Results with Content: {json.dumps(results_with_content, indent=2)}
Crawl Statistics: {json.dumps(state.crawl_metadata, indent=2)}

You now have access to:
1. Original search snippets
2. Full crawled content from pages (when available)
3. Crawl confidence scores
4. Multiple pages per domain (via adaptive crawling)

Generate a comprehensive analysis considering the full content..."""
```

### Phase 7: Configuration & CLI (Week 4)

#### 7.1 CLI Options
```python
# Update CLI parser
parser.add_argument(
    "--crawl-strategy",
    choices=["embedding", "statistical", "none"],
    default="embedding",
    help="Adaptive crawling strategy (default: embedding)"
)

parser.add_argument(
    "--crawl-confidence",
    type=float,
    default=0.7,
    help="Confidence threshold for stopping crawl (0-1)"
)

parser.add_argument(
    "--max-crawl-pages",
    type=int,
    default=10,
    help="Maximum pages to crawl per source"
)

parser.add_argument(
    "--no-crawl",
    action="store_true",
    help="Disable adaptive crawling (faster, less comprehensive)"
)
```

#### 7.2 Configuration Options
```python
class ResearchConfig:
    # Existing fields...
    
    # Adaptive crawling options
    enable_crawling: bool = True
    crawl_strategy: str = "embedding"  # or "statistical"
    crawl_confidence_threshold: float = 0.7
    max_crawl_pages: int = 10
    crawl_timeout: int = 30  # seconds per source
    save_crawled_content: bool = True  # Save raw crawled data
```

## Expected Capabilities After Implementation

### 1. **Intelligent Content Discovery**
- Automatically follows relevant links from search results
- Stops crawling when sufficient information is found
- Avoids redundant or low-value pages

### 2. **Semantic Understanding**
- Uses embeddings to understand query intent
- Identifies conceptually related content
- Expands search beyond exact keyword matches

### 3. **Multi-Page Context**
- Crawls documentation hierarchies (e.g., Python docs)
- Follows "See also" and related links
- Builds comprehensive understanding from multiple pages

### 4. **Research Examples**

#### Before (Current Implementation):
```
Query: "How to implement RLHF for LLMs"
Result: Basic snippets mentioning RLHF, limited context
```

#### After (With Adaptive Crawling):
```
Query: "How to implement RLHF for LLMs"
Result: 
- Full tutorial from HuggingFace documentation
- Implementation details from multiple GitHub repos
- Academic paper insights from ar5iv HTML
- Related concepts (PPO, reward modeling) from crawled links
- Code examples with full context
```

### 5. **Performance Metrics**
- **Crawl Efficiency**: Stop at ~70% confidence instead of fixed page count
- **Content Quality**: Access to full articles vs 200-char snippets
- **Semantic Coverage**: Find related concepts not in original query
- **Time Investment**: +10-30s for dramatically better results

### 6. **Use Case Examples**

```bash
# Deep technical research with embedding strategy
python -m agents.web_agent_langgraph.cli \
  "How to implement distributed training in PyTorch" \
  --crawl-strategy embedding \
  --max-crawl-pages 15

# Quick factual lookup with statistical strategy  
python -m agents.web_agent_langgraph.cli \
  "pandas merge vs join performance" \
  --crawl-strategy statistical \
  --crawl-confidence 0.6

# Debug mode with full crawl dumps
python -m agents.web_agent_langgraph.cli \
  "AsyncIO event loop internals" \
  --dump-path ./crawl_debug \
  --save-crawled-content
```

## Implementation Timeline

- **Week 1**: Core infrastructure + basic integration
- **Week 2**: LangGraph workflow + smart selection
- **Week 3**: arXiv handling + enhanced analysis  
- **Week 4**: Polish, testing, documentation

## Dependencies

```txt
crawl4ai>=0.3.0
sentence-transformers>=2.2.0
numpy>=1.24.0
aiohttp>=3.8.0
beautifulsoup4>=4.12.0
```

## Risk Mitigation

1. **Performance**: Implement timeouts and concurrent limits
2. **Cost**: Cache crawled content, respect robots.txt
3. **Quality**: Validate crawled content before analysis
4. **Reliability**: Fallback to snippet-only mode on errors

This implementation will transform our agent from a "search summarizer" into a true "research assistant" that intelligently explores and understands web content.