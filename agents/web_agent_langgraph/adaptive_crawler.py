"""Adaptive web crawler using Crawl4AI for intelligent content extraction."""

import os
import re
import asyncio
from typing import List, Dict, Optional, Any
from pathlib import Path
import logging

from pydantic import BaseModel, Field

from utils import setup_logger

logger = setup_logger(__name__)


class CrawlConfig(BaseModel):
    """Configuration for adaptive crawling."""
    max_pages: int = Field(default=10, description="Maximum pages to crawl")
    confidence_threshold: float = Field(default=0.7, description="Confidence threshold to stop crawling")
    use_semantic_chunking: bool = Field(default=True, description="Use semantic chunking for better analysis")
    chunk_size: int = Field(default=512, description="Size of semantic chunks")
    chunk_overlap: int = Field(default=50, description="Overlap between chunks")
    timeout: int = Field(default=30, description="Timeout per page in seconds")
    
    # OpenAI embedding config
    embedding_model: str = Field(default="text-embedding-3-small", description="OpenAI embedding model")


class CrawlResult(BaseModel):
    """Result from crawling a URL."""
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    chunks: Optional[List[str]] = None
    error: Optional[str] = None
    pages_crawled: int = 1
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EnhancedAdaptiveCrawler:
    """Enhanced adaptive crawler with Crawl4AI integration."""
    
    def __init__(self, config: Optional[CrawlConfig] = None):
        """Initialize crawler with configuration."""
        self.config = config or CrawlConfig()
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            logger.warning("OpenAI API key not found for embeddings")
    
    async def crawl_single_url(self, url: str, query: str) -> CrawlResult:
        """Crawl a single URL and extract content."""
        try:
            # Imported lazily so the package can be used without crawl4ai
            # installed when crawling is disabled.
            from crawl4ai import AsyncWebCrawler

            async with AsyncWebCrawler(verbose=False) as crawler:
                # Crawl the page with basic configuration
                result = await crawler.arun(
                    url=url,
                    timeout=self.config.timeout,
                    bypass_cache=True,
                    screenshot=False,
                    wait_for="body"
                )
                
                if result.success:
                    # Extract content
                    content = str(result.markdown) if result.markdown else ""
                    
                    # Extract title from HTML
                    title = "Untitled"
                    if result.html:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(result.html, 'html.parser')
                        title_tag = soup.find('title')
                        if title_tag:
                            title = title_tag.text.strip()
                    
                    return CrawlResult(
                        url=url,
                        title=title,
                        content=content[:50000],  # Limit content size
                        metadata={
                            'word_count': len(content.split()),
                            'has_content': len(content) > 100,
                            'status_code': result.status_code if hasattr(result, 'status_code') else 200
                        }
                    )
                else:
                    error_msg = "Unknown error"
                    if hasattr(result, 'error_message'):
                        error_msg = result.error_message
                    elif hasattr(result, 'status_code'):
                        error_msg = f"HTTP {result.status_code}"
                    
                    return CrawlResult(
                        url=url,
                        error=f"Crawl failed: {error_msg}"
                    )
                    
        except Exception as e:
            logger.error(f"Error crawling {url}: {e}")
            return CrawlResult(url=url, error=str(e))
    
    async def crawl_search_results(
        self, 
        search_results: List[Dict[str, str]], 
        query: str,
        source_type: str = "web",
        max_concurrent: int = 3
    ) -> Dict[str, CrawlResult]:
        """Crawl multiple search results with concurrency control."""
        crawled_content = {}
        
        # Convert arXiv URLs to ar5iv if needed
        processed_results = []
        for result in search_results:
            url = result['url']
            if source_type == "arxiv" and "arxiv.org/pdf/" in url:
                url = self._convert_arxiv_to_ar5iv(url)
                logger.info(f"Converted arXiv PDF to ar5iv HTML: {url}")
            processed_results.append({**result, 'url': url})
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def crawl_with_semaphore(result: Dict[str, str]) -> tuple:
            async with semaphore:
                crawl_result = await self.crawl_single_url(result['url'], query)
                return result['original_url'] if 'original_url' in result else result['url'], crawl_result
        
        # Crawl all URLs concurrently
        tasks = [crawl_with_semaphore(result) for result in processed_results[:self.config.max_pages]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for item in results:
            if isinstance(item, Exception):
                logger.error(f"Crawl task failed: {item}")
            else:
                original_url, crawl_result = item
                crawled_content[original_url] = crawl_result
        
        return crawled_content
    
    def _convert_arxiv_to_ar5iv(self, arxiv_url: str) -> str:
        """Convert arXiv PDF URL to ar5iv HTML URL."""
        # Extract paper ID from https://arxiv.org/pdf/2301.12345.pdf
        match = re.search(r'arxiv\.org/pdf/(\d+\.\d+)', arxiv_url)
        if match:
            paper_id = match.group(1)
            return f"https://ar5iv.labs.arxiv.org/html/{paper_id}"
        return arxiv_url
    
    async def download_arxiv_pdf(self, pdf_url: str, save_dir: Path) -> Optional[Path]:
        """Download arXiv PDF for reference."""
        try:
            import aiohttp
            
            # Extract paper ID
            match = re.search(r'arxiv\.org/pdf/(\d+\.\d+)', pdf_url)
            if not match:
                return None
            
            paper_id = match.group(1)
            pdf_path = save_dir / f"arxiv_{paper_id}.pdf"
            
            # Create directory if needed
            save_dir.mkdir(parents=True, exist_ok=True)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(pdf_url, timeout=60) as response:
                    if response.status == 200:
                        content = await response.read()
                        pdf_path.write_bytes(content)
                        logger.info(f"Downloaded arXiv PDF: {pdf_path}")
                        return pdf_path
                    else:
                        logger.error(f"Failed to download PDF: HTTP {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error downloading arXiv PDF: {e}")
            return None
    
    def calculate_content_quality(self, crawl_result: CrawlResult, query: str) -> float:
        """Calculate quality score for crawled content."""
        if crawl_result.error or not crawl_result.content:
            return 0.0
        
        score = 0.0
        content_lower = crawl_result.content.lower()
        query_terms = set(query.lower().split())
        
        # Term coverage (40%)
        covered_terms = sum(1 for term in query_terms if term in content_lower)
        term_coverage = covered_terms / len(query_terms) if query_terms else 0
        score += term_coverage * 0.4
        
        # Content length (20%)
        word_count = crawl_result.metadata.get('word_count', 0)
        if word_count > 100:
            length_score = min(1.0, word_count / 1000)
            score += length_score * 0.2
        
        # Has meaningful content (20%)
        if crawl_result.metadata.get('has_content', False):
            score += 0.2
        
        # Title relevance (20%)
        if crawl_result.title:
            title_lower = crawl_result.title.lower()
            title_coverage = sum(1 for term in query_terms if term in title_lower)
            title_score = title_coverage / len(query_terms) if query_terms else 0
            score += title_score * 0.2
        
        return min(1.0, score)