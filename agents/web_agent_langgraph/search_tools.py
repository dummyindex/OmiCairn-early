"""Search tools that work without LLM calls."""

import json
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import aiohttp
from bs4 import BeautifulSoup
try:
    from ddgs import DDGS
except ImportError:
    # Fallback to old package name
    from duckduckgo_search import DDGS

from .models import SearchResult
from .adaptive_crawler import EnhancedAdaptiveCrawler, CrawlConfig, CrawlResult
from utils import setup_logger

logger = setup_logger(__name__)


class SearchTools:
    """Web search and fetch tools that don't require LLM."""
    
    def __init__(self, enable_crawling: bool = True):
        """Initialize search tools."""
        self.ddgs = DDGS()
        self.session = None
        self.enable_crawling = enable_crawling
        if enable_crawling:
            self.crawler = EnhancedAdaptiveCrawler()
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    def search_web(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Search the web using DuckDuckGo.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of SearchResult objects
        """
        results = []
        try:
            for r in self.ddgs.text(query, max_results=max_results):
                result = SearchResult(
                    title=r.get('title', ''),
                    url=r.get('href', ''),
                    snippet=r.get('body', ''),
                    source='web'
                )
                results.append(result)
                
            logger.info(f"Web search for '{query}' returned {len(results)} results")
            
        except Exception as e:
            logger.error(f"Web search error: {e}")
            
        return results
    
    def search_arxiv(self, query: str, max_results: int = 3) -> List[SearchResult]:
        """Search arXiv for academic papers.
        
        Args:
            query: Search query
            max_results: Maximum results
            
        Returns:
            List of SearchResult objects
        """
        results = []
        try:
            import arxiv
            
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance
            )
            
            for paper in search.results():
                result = SearchResult(
                    title=paper.title,
                    url=paper.pdf_url,
                    snippet=f"Authors: {', '.join(str(a) for a in paper.authors[:3])}. "
                           f"Abstract: {paper.summary[:200]}...",
                    source='arxiv'
                )
                results.append(result)
                
            logger.info(f"ArXiv search for '{query}' returned {len(results)} results")
            
        except Exception as e:
            logger.error(f"ArXiv search error: {e}")
            
        return results
    
    def search_github(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Search GitHub for code examples.
        
        Args:
            query: Search query
            max_results: Maximum results
            
        Returns:
            List of SearchResult objects
        """
        results = []
        try:
            github_query = f"site:github.com {query}"
            
            for r in self.ddgs.text(github_query, max_results=max_results):
                url = r.get('href', '')
                if 'github.com' in url:
                    result = SearchResult(
                        title=r.get('title', ''),
                        url=url,
                        snippet=r.get('body', ''),
                        source='github'
                    )
                    results.append(result)
                    
            logger.info(f"GitHub search for '{query}' returned {len(results)} results")
            
        except Exception as e:
            logger.error(f"GitHub search error: {e}")
            
        return results
    
    def search_stackoverflow(self, query: str, max_results: int = 5) -> List[SearchResult]:
        """Search Stack Overflow for solutions.
        
        Args:
            query: Search query
            max_results: Maximum results
            
        Returns:
            List of SearchResult objects
        """
        results = []
        try:
            so_query = f"site:stackoverflow.com {query}"
            
            for r in self.ddgs.text(so_query, max_results=max_results):
                url = r.get('href', '')
                if 'stackoverflow.com' in url:
                    result = SearchResult(
                        title=r.get('title', ''),
                        url=url,
                        snippet=r.get('body', ''),
                        source='stackoverflow'
                    )
                    results.append(result)
                    
            logger.info(f"Stack Overflow search for '{query}' returned {len(results)} results")
            
        except Exception as e:
            logger.error(f"Stack Overflow search error: {e}")
            
        return results
    
    async def fetch_webpage_content(self, url: str, max_length: int = 5000) -> Optional[str]:
        """Fetch and extract text content from a webpage.
        
        Args:
            url: URL to fetch
            max_length: Maximum content length
            
        Returns:
            Extracted text content or None if failed
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        try:
            async with self.session.get(url, timeout=10) as response:
                if response.status != 200:
                    logger.warning(f"Failed to fetch {url}: HTTP {response.status}")
                    return None
                    
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                    
                # Get text
                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = ' '.join(chunk for chunk in chunks if chunk)
                
                # Limit length
                if len(text) > max_length:
                    text = text[:max_length] + "..."
                    
                logger.info(f"Fetched {len(text)} chars from {url}")
                return text
                
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None
    
    async def fetch_multiple_pages(self, urls: List[str], max_pages: int = 3) -> Dict[str, str]:
        """Fetch multiple web pages concurrently.
        
        Args:
            urls: List of URLs to fetch
            max_pages: Maximum number of pages to fetch
            
        Returns:
            Dictionary mapping URL to content
        """
        # Limit URLs
        urls = urls[:max_pages]
        
        tasks = [self.fetch_webpage_content(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        content_map = {}
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                content_map[url] = f"Error: {str(result)}"
            elif result:
                content_map[url] = result
            else:
                content_map[url] = "Failed to fetch content"
                
        logger.info(f"Fetched {len(content_map)} pages")
        return content_map
    
    def search_all_sources(self, query: str, max_per_source: int = 3, include_arxiv: bool = False) -> List[SearchResult]:
        """Search all available sources.
        
        Args:
            query: Search query
            max_per_source: Max results per source
            include_arxiv: Whether to include arXiv search (default: False)
            
        Returns:
            Combined list of SearchResult objects
        """
        all_results = []
        
        # Search each source
        all_results.extend(self.search_web(query, max_per_source))
        
        # ArXiv is now optional - only for academic/theoretical queries
        if include_arxiv:
            all_results.extend(self.search_arxiv(query, max_per_source))
            
        all_results.extend(self.search_github(query, max_per_source))
        all_results.extend(self.search_stackoverflow(query, max_per_source))
        
        logger.info(f"Total search results for '{query}': {len(all_results)}")
        return all_results
    
    def generate_search_report(self, query: str, results: List[SearchResult]) -> Dict[str, Any]:
        """Generate a search report without LLM.
        
        Args:
            query: Original query
            results: Search results
            
        Returns:
            Search report dictionary
        """
        # Group by source
        by_source = {}
        for result in results:
            if result.source not in by_source:
                by_source[result.source] = []
            by_source[result.source].append({
                'title': result.title,
                'url': result.url,
                'snippet': result.snippet
            })
        
        report = {
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'total_results': len(results),
            'results_by_source': by_source,
            'all_urls': [r.url for r in results],
            'sources_searched': list(by_source.keys())
        }
        
        return report
    
    async def search_and_crawl(
        self, 
        query: str, 
        max_per_source: int = 3,
        crawl_top_n: int = 5
    ) -> List[SearchResult]:
        """Search all sources and crawl top results.
        
        Args:
            query: Search query
            max_per_source: Max results per source
            crawl_top_n: Number of top results to crawl
            
        Returns:
            List of SearchResult objects with crawled content
        """
        # First, get search results
        results = self.search_all_sources(query, max_per_source)
        
        if not self.enable_crawling or not results:
            return results
        
        # Select top results to crawl
        results_to_crawl = results[:crawl_top_n]
        
        # Convert to dict format for crawler
        crawl_input = []
        for result in results_to_crawl:
            crawl_input.append({
                'url': result.url,
                'title': result.title,
                'snippet': result.snippet,
                'source': result.source
            })
        
        # Crawl the URLs
        logger.info(f"Crawling {len(crawl_input)} URLs for query: {query}")
        crawled_content = await self.crawler.crawl_search_results(
            crawl_input,
            query,
            source_type='mixed'
        )
        
        # Update results with crawled content
        for i, result in enumerate(results):
            if result.url in crawled_content:
                crawl_result = crawled_content[result.url]
                if crawl_result.content:
                    result.crawled_content = crawl_result.content
                    result.crawl_metadata = crawl_result.metadata
                    result.content_quality_score = self.crawler.calculate_content_quality(
                        crawl_result, query
                    )
                    logger.info(f"Enriched result {i+1}: {result.title[:50]}... (quality: {result.content_quality_score:.2f})")
                elif crawl_result.error:
                    result.crawl_error = crawl_result.error
        
        return results