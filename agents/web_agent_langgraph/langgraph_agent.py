"""LangGraph-based research agent with JSON structured outputs."""

import os
import json
import asyncio
from typing import Dict, Any, List, Optional, Annotated
from datetime import datetime
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from langchain_community.callbacks.manager import get_openai_callback
from .cost_aware_callback import get_cost_aware_callback
from constants import DEFAULT_OPENAI_MODEL, ENV_OPENAI_API_KEY

from .models import (
    ResearchState, SearchResult, ResearchReport,
    ResearchPlan, ResearchAnalysis, ResearchPhase
)
from .search_tools import SearchTools
from .research_interface import ResearchInterface
from .schemas import ResearchConfig, ResearchResult, ResearchStatus
from utils import setup_logger

logger = setup_logger(__name__)


class LangGraphResearchAgent(ResearchInterface):
    """Research agent using LangGraph with structured JSON outputs."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = DEFAULT_OPENAI_MODEL,
        output_dir: Optional[Path] = None,
        temperature: float = 0.0
    ):
        """Initialize LangGraph research agent.
        
        Args:
            api_key: OpenAI API key
            model_name: Model to use (default: gpt-4o-mini)
            output_dir: Directory for saving outputs
            temperature: LLM temperature
        """
        self.api_key = api_key or os.getenv(ENV_OPENAI_API_KEY)
        if not self.api_key:
            raise ValueError("OpenAI API key required")
            
        self.model_name = model_name
        self.temperature = temperature
        self.output_dir = output_dir or Path("research_outputs")
        self.output_dir.mkdir(exist_ok=True)
        
        # Create log directory
        self.log_dir = Path("agent_tasks/langgraph_research_logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize LLM with JSON mode
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            api_key=self.api_key
        ).bind(response_format={"type": "json_object"})
        
        # Initialize search tools with crawling
        self.search_tools = SearchTools(enable_crawling=True)
        
        # Build the graph
        self.graph = self._build_graph()
        
        # Track current state for timeout handling
        self.current_state = None
        
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow.
        
        Returns:
            Configured StateGraph
        """
        # Create the graph
        workflow = StateGraph(ResearchState)
        
        # Add nodes
        workflow.add_node("plan", self._plan_research)
        workflow.add_node("search", self._execute_searches)
        workflow.add_node("crawl", self._crawl_content)
        workflow.add_node("analyze", self._analyze_results)
        workflow.add_node("synthesize", self._synthesize_report)
        workflow.add_node("save", self._save_state)
        
        # Add edges
        workflow.set_entry_point("plan")
        workflow.add_edge("plan", "search")
        workflow.add_edge("search", "crawl")
        workflow.add_edge("crawl", "analyze")
        workflow.add_edge("analyze", "synthesize")
        workflow.add_edge("synthesize", "save")
        workflow.add_edge("save", END)
        
        return workflow.compile()
    
    async def _plan_research(self, state: ResearchState) -> ResearchState:
        """Plan the research strategy.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with research plan
        """
        self.current_state = state  # Track for timeout handling
        state.current_phase = ResearchPhase.PLANNING
        
        if state.dump_enabled and state.dump_path:
            self._dump_phase_data(state, "1_planning_start")
        
        prompt = f"""You are a research planning assistant. Create a research plan for the following query.

Query: {state.query}
Research Type: {state.research_type}

Generate a JSON response with the following structure:
{{
    "main_query": "the main research query",
    "sub_queries": ["list", "of", "specific", "search", "queries"],
    "search_strategy": "description of search strategy",
    "expected_sources": ["web", "arxiv", "github", "stackoverflow"]
}}

Focus on creating 3-5 specific search queries that will find relevant information."""
        
        try:
            # Use our cost-aware callback for accurate pricing
            with get_cost_aware_callback(model_name=self.model_name) as cb:
                response = await self.llm.ainvoke([
                    SystemMessage(content="You are a research planning assistant. Always respond with valid JSON."),
                    HumanMessage(content=prompt)
                ])
                
                # Update costs from response
                cb.update_from_response(response, self.model_name)
                
                # Parse JSON response
                plan_data = json.loads(response.content)
                state.research_plan = ResearchPlan(**plan_data)
                state.search_queries = state.research_plan.sub_queries
                
                # Update state with accurate costs
                state.total_cost += cb.total_cost
                state.total_tokens += cb.total_tokens
                
                logger.info(f"Created research plan with {len(state.search_queries)} queries")
                
        except Exception as e:
            logger.error(f"Planning error: {e}")
            state.errors.append(f"Planning error: {str(e)}")
            # Fallback to simple search
            state.search_queries = [state.query]
            
        if state.dump_enabled and state.dump_path:
            self._dump_phase_data(state, "1_planning_complete")
            
        return state
    
    async def _execute_searches(self, state: ResearchState) -> ResearchState:
        """Execute web searches without LLM.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with search results
        """
        self.current_state = state  # Track for timeout handling
        state.current_phase = ResearchPhase.SEARCHING
        
        if state.dump_enabled and state.dump_path:
            self._dump_phase_data(state, "2_searching_start")
        
        all_results = []
        
        # Execute searches for each query
        for query in state.search_queries[:5]:  # Limit to 5 queries
            logger.info(f"Searching for: {query}")
            results = self.search_tools.search_all_sources(
                query, 
                max_per_source=state.max_search_results
            )
            all_results.extend(results)
        
        # Remove duplicates based on URL
        seen_urls = set()
        unique_results = []
        for result in all_results:
            if result.url not in seen_urls:
                seen_urls.add(result.url)
                unique_results.append(result)
                
        state.search_results = unique_results
        logger.info(f"Found {len(unique_results)} unique search results")
        
        if state.dump_enabled and state.dump_path:
            self._dump_phase_data(state, "2_searching_complete")
            
        return state
    
    async def _crawl_content(self, state: ResearchState) -> ResearchState:
        """Crawl content from search results.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with crawled content
        """
        state.current_phase = ResearchPhase.CRAWLING
        
        if state.dump_enabled and state.dump_path:
            self._dump_phase_data(state, "2a_crawling_start")
        
        if not state.enable_crawling or not state.search_results:
            logger.info("Crawling disabled or no search results")
            return state
        
        # Select top results to crawl based on research type
        crawl_limits = {
            'quick': 3,
            'detailed': 5,
            'deep': 8
        }
        crawl_top_n = crawl_limits.get(state.research_type, 5)
        
        # Use search_and_crawl method to enrich results
        logger.info(f"Crawling top {crawl_top_n} results for enhanced content")
        
        # Convert SearchResult objects to dict format
        search_input = []
        for result in state.search_results[:crawl_top_n]:
            search_input.append({
                'url': result.url,
                'title': result.title,
                'snippet': result.snippet,
                'source': result.source
            })
        
        # Crawl the content
        crawled_content = await self.search_tools.crawler.crawl_search_results(
            search_input,
            state.query,
            source_type='mixed'
        )
        
        # Update search results with crawled content
        crawled_count = 0
        total_content_length = 0
        
        for result in state.search_results:
            if result.url in crawled_content:
                crawl_result = crawled_content[result.url]
                if crawl_result.content:
                    result.crawled_content = crawl_result.content
                    result.crawl_metadata = crawl_result.metadata
                    result.content_quality_score = self.search_tools.crawler.calculate_content_quality(
                        crawl_result, state.query
                    )
                    crawled_count += 1
                    total_content_length += len(crawl_result.content)
                elif crawl_result.error:
                    result.crawl_error = crawl_result.error
        
        # Update crawl metadata
        state.crawl_metadata = {
            'total_crawled': crawled_count,
            'total_content_chars': total_content_length,
            'average_quality_score': sum(
                r.content_quality_score for r in state.search_results 
                if r.content_quality_score is not None
            ) / max(1, crawled_count)
        }
        
        logger.info(f"Crawled {crawled_count} pages, total content: {total_content_length} chars")
        
        if state.dump_enabled and state.dump_path:
            self._dump_phase_data(state, "2a_crawling_complete")
        
        return state
    
    async def _analyze_results(self, state: ResearchState) -> ResearchState:
        """Analyze search results with LLM.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with analysis
        """
        self.current_state = state  # Track for timeout handling
        state.current_phase = ResearchPhase.ANALYZING
        
        if state.dump_enabled and state.dump_path:
            self._dump_phase_data(state, "3_analyzing_start")
        
        # Prepare results summary with crawled content
        results_summary = []
        for result in state.search_results[:20]:  # Limit to top 20
            result_data = {
                'title': result.title,
                'url': result.url,
                'snippet': result.snippet,
                'source': result.source
            }
            
            # Add crawled content if available
            if result.crawled_content:
                result_data['has_full_content'] = True
                result_data['content_preview'] = result.crawled_content[:1500]  # First 1500 chars
                result_data['content_length'] = len(result.crawled_content)
                result_data['quality_score'] = result.content_quality_score
            elif result.crawl_error:
                result_data['crawl_failed'] = True
                result_data['crawl_error'] = result.crawl_error
                
            results_summary.append(result_data)
        
        # Add crawl statistics to prompt
        crawl_stats = state.crawl_metadata or {}
        
        prompt = f"""Analyze these search results with crawled content for the research query: {state.query}

Crawl Statistics:
- Total pages crawled: {crawl_stats.get('total_crawled', 0)}
- Total content extracted: {crawl_stats.get('total_content_chars', 0)} characters
- Average quality score: {crawl_stats.get('average_quality_score', 0):.2f}

Search Results with Content:
{json.dumps(results_summary, indent=2)}

You now have access to:
1. Original search snippets
2. Full crawled content (when available)
3. Content quality scores
4. Actual page content, not just summaries

Generate a JSON response with the following structure:
{{
    "key_findings": ["list", "of", "key", "findings"],
    "relevant_urls": ["most", "relevant", "URLs"],
    "gaps_identified": ["information", "gaps", "if", "any"],
    "confidence_score": 0.8
}}

Focus on extracting the most important information from the FULL CONTENT (not just snippets) and identifying the most relevant sources based on actual content quality."""
        
        try:
            # Use our cost-aware callback for accurate pricing
            with get_cost_aware_callback(model_name=self.model_name) as cb:
                response = await self.llm.ainvoke([
                    SystemMessage(content="You are a research analyst. Always respond with valid JSON."),
                    HumanMessage(content=prompt)
                ])
                
                # Update costs from response
                cb.update_from_response(response, self.model_name)
                
                # Parse JSON response
                analysis_data = json.loads(response.content)
                state.analysis = ResearchAnalysis(**analysis_data)
                
                # Update state with accurate costs
                state.total_cost += cb.total_cost
                state.total_tokens += cb.total_tokens
                
                logger.info(f"Analysis complete with confidence: {state.analysis.confidence_score}")
                
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            state.errors.append(f"Analysis error: {str(e)}")
            
        if state.dump_enabled and state.dump_path:
            self._dump_phase_data(state, "3_analyzing_complete")
            
        return state
    
    async def _synthesize_report(self, state: ResearchState) -> ResearchState:
        """Synthesize final research report.
        
        Args:
            state: Current state
            
        Returns:
            Updated state with final report
        """
        state.current_phase = ResearchPhase.SYNTHESIZING
        
        if state.dump_enabled and state.dump_path:
            self._dump_phase_data(state, "4_synthesizing_start")
        
        # Prepare context
        context = {
            'query': state.query,
            'key_findings': state.analysis.key_findings if state.analysis else [],
            'search_results': [
                {
                    'title': r.title,
                    'url': r.url,
                    'snippet': r.snippet
                } for r in state.search_results[:10]
            ]
        }
        
        prompt = f"""Create a comprehensive research report based on the following information:

Query: {state.query}
Context: {json.dumps(context, indent=2)}

Generate a JSON response with the following structure:
{{
    "query": "{state.query}",
    "summary": "executive summary of findings",
    "detailed_findings": [
        {{"finding": "specific finding", "source": "source URL", "confidence": "high/medium/low"}}
    ],
    "code_examples": [
        {{"description": "what the code does", "code": "actual code", "language": "python/javascript/etc"}}
    ],
    "recommendations": ["actionable", "recommendations"],
    "sources": [
        {{"title": "source title", "url": "source URL", "relevance": "high/medium/low"}}
    ],
    "limitations": ["research", "limitations"],
    "confidence_score": 0.8
}}

Ensure all findings are supported by the search results."""
        
        try:
            # Use our cost-aware callback for accurate pricing
            with get_cost_aware_callback(model_name=self.model_name) as cb:
                response = await self.llm.ainvoke([
                    SystemMessage(content="You are a research report writer. Always respond with valid JSON."),
                    HumanMessage(content=prompt)
                ])
                
                # Update costs from response
                cb.update_from_response(response, self.model_name)
                
                # Parse JSON response
                report_data = json.loads(response.content)
                
                # Add metadata
                report_data['metadata'] = {
                    'research_type': state.research_type,
                    'total_sources_searched': len(state.search_results),
                    'duration_seconds': (datetime.now() - state.start_time).total_seconds(),
                    'model_used': self.model_name
                }
                
                state.final_report = ResearchReport(**report_data)
                
                # Update state with accurate costs
                state.total_cost += cb.total_cost
                state.total_tokens += cb.total_tokens
                
                logger.info("Research report synthesized")
                
        except Exception as e:
            logger.error(f"Synthesis error: {e}")
            state.errors.append(f"Synthesis error: {str(e)}")
            # Create minimal report
            state.final_report = ResearchReport(
                query=state.query,
                summary="Research failed due to errors",
                confidence_score=0.0
            )
            
        state.current_phase = ResearchPhase.COMPLETE
        state.end_time = datetime.now()
        
        if state.dump_enabled and state.dump_path:
            self._dump_phase_data(state, "4_synthesizing_complete")
            
        return state
    
    async def _save_state(self, state: ResearchState) -> ResearchState:
        """Save the final state and logs.
        
        Args:
            state: Current state
            
        Returns:
            State (unchanged)
        """
        if state.dump_enabled and state.dump_path:
            self._dump_phase_data(state, "5_final_state")
            
        # Save to log directory
        self._save_research_log(state)
        
        return state
    
    def _dump_phase_data(self, state: ResearchState, phase_name: str) -> None:
        """Dump current state data to file.
        
        Args:
            state: Current state
            phase_name: Name of the phase
        """
        if not state.dump_path:
            return
            
        dump_dir = Path(state.dump_path)
        dump_dir.mkdir(parents=True, exist_ok=True)
        
        # Create phase file
        phase_file = dump_dir / f"{phase_name}.json"
        
        # Prepare data
        data = {
            'phase': phase_name,
            'timestamp': datetime.now().isoformat(),
            'current_phase': state.current_phase.value,
            'query': state.query,
            'search_queries': state.search_queries,
            'search_results_count': len(state.search_results),
            'errors': state.errors,
            'cost_so_far': state.total_cost,
            'tokens_so_far': state.total_tokens
        }
        
        # Add phase-specific data
        if state.research_plan:
            data['research_plan'] = state.research_plan.model_dump(mode='json')
        if state.analysis:
            data['analysis'] = state.analysis.model_dump(mode='json')
        if state.final_report:
            data['final_report'] = state.final_report.model_dump(mode='json')
            
        # Save
        with open(phase_file, 'w') as f:
            json.dump(data, f, indent=2)
            
        logger.debug(f"Dumped phase data: {phase_file}")
    
    def _save_research_log(self, state: ResearchState) -> None:
        """Save research log.
        
        Args:
            state: Final state
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            query_slug = state.query[:50].replace(" ", "_").replace("/", "_")
            
            # Save JSON log
            log_file = self.log_dir / f"research_{timestamp}_{query_slug}.json"
            log_data = {
                'timestamp': datetime.now().isoformat(),
                'query': state.query,
                'research_type': state.research_type,
                'duration_seconds': (state.end_time - state.start_time).total_seconds() if state.end_time else 0,
                'total_cost': state.total_cost,
                'total_tokens': state.total_tokens,
                'search_results_count': len(state.search_results),
                'errors': state.errors,
                'final_report': state.final_report.model_dump(mode='json') if state.final_report else None
            }
            
            with open(log_file, 'w') as f:
                json.dump(log_data, f, indent=2, default=str)
                
            # Save markdown report
            if state.final_report:
                md_file = log_file.with_suffix('.md')
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(self._format_report_as_markdown(state))
                    
            logger.info(f"Research log saved: {log_file}")
            
        except Exception as e:
            logger.error(f"Failed to save log: {e}")
    
    def _format_report_as_markdown(self, state: ResearchState) -> str:
        """Format research report as markdown.
        
        Args:
            state: Research state
            
        Returns:
            Markdown formatted report
        """
        report = state.final_report
        if not report:
            return "# No Report Generated"
            
        md = f"""# Research Report: {report.query}

**Generated**: {datetime.now().isoformat()}  
**Duration**: {(state.end_time - state.start_time).total_seconds():.1f}s  
**Cost**: ${state.total_cost:.4f}  
**Confidence**: {report.confidence_score:.2f}

## Summary

{report.summary}

## Detailed Findings

"""
        
        for finding in report.detailed_findings:
            md += f"- **{finding.get('finding', 'N/A')}**\n"
            md += f"  - Source: {finding.get('source', 'N/A')}\n"
            md += f"  - Confidence: {finding.get('confidence', 'N/A')}\n\n"
            
        if report.code_examples:
            md += "\n## Code Examples\n\n"
            for example in report.code_examples:
                md += f"### {example.get('description', 'Code')}\n\n"
                md += f"```{example.get('language', 'python')}\n"
                md += f"{example.get('code', '')}\n"
                md += "```\n\n"
                
        if report.recommendations:
            md += "\n## Recommendations\n\n"
            for rec in report.recommendations:
                md += f"- {rec}\n"
                
        if report.sources:
            md += "\n## Sources\n\n"
            for source in report.sources:
                md += f"- [{source.get('title', 'Source')}]({source.get('url', '#')})"
                md += f" (Relevance: {source.get('relevance', 'N/A')})\n"
                
        if report.limitations:
            md += "\n## Limitations\n\n"
            for limitation in report.limitations:
                md += f"- {limitation}\n"
                
        return md
    
    async def conduct_research(self, config: ResearchConfig) -> ResearchResult:
        """Conduct research using LangGraph.
        
        Args:
            config: Research configuration
            
        Returns:
            Research result
        """
        self.validate_config(config)
        
        # Create initial state
        state = ResearchState(
            query=config.query,
            research_type=config.research_type.value,
            max_search_results=3,  # Limit for cost
            dump_enabled=False,  # Can be enabled via config
            dump_path=None
        )
        
        # Enable dumping if requested
        if hasattr(config, 'dump_path') and config.dump_path:
            state.dump_enabled = True
            state.dump_path = config.dump_path
            
        # Configure crawling
        if hasattr(config, 'enable_crawling'):
            state.enable_crawling = config.enable_crawling
        if hasattr(config, 'crawl_limit'):
            state.crawl_limit = config.crawl_limit
            
        try:
            # Run the graph
            final_state_dict = await self.graph.ainvoke(state)
            
            # Convert dict back to ResearchState if needed
            if isinstance(final_state_dict, dict):
                final_state = ResearchState(**final_state_dict)
            else:
                final_state = final_state_dict
            
            # Convert to ResearchResult
            report = final_state.final_report
            if report:
                result = ResearchResult(
                    query=config.query,
                    report=self._format_report_as_markdown(final_state),
                    sources=[
                        {'title': s.get('title', ''), 'url': s.get('url', '')}
                        for s in report.sources
                    ],
                    metadata={
                        'research_type': config.research_type.value,
                        'confidence_score': report.confidence_score,
                        'total_search_results': len(final_state.search_results),
                        'final_report': report.model_dump(mode='json') if hasattr(report, 'model_dump') else report.dict()
                    },
                    status=ResearchStatus.COMPLETED,
                    start_time=final_state.start_time,
                    end_time=final_state.end_time,
                    duration_seconds=(final_state.end_time - final_state.start_time).total_seconds(),
                    cost_estimate=final_state.total_cost
                )
            else:
                # Failed
                result = ResearchResult(
                    query=config.query,
                    report="Research failed",
                    sources=[],
                    metadata={},
                    status=ResearchStatus.FAILED,
                    error="; ".join(final_state.errors) if hasattr(final_state, 'errors') and final_state.errors else "Unknown error",
                    start_time=final_state.start_time if hasattr(final_state, 'start_time') else datetime.now(),
                    end_time=final_state.end_time if hasattr(final_state, 'end_time') else datetime.now()
                )
                
            # Save if requested
            if config.save_to_file:
                self._save_report(result, config.save_to_file)
                
            return result
            
        except Exception as e:
            logger.error(f"Research failed: {e}")
            return ResearchResult(
                query=config.query,
                report="",
                sources=[],
                metadata={},
                status=ResearchStatus.FAILED,
                error=str(e)
            )
    
    async def conduct_research_for_error(
        self,
        error_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ResearchResult:
        """Conduct research for an error.
        
        Args:
            error_message: Error message
            context: Additional context
            
        Returns:
            Research result
        """
        # Build error-specific query
        query = f"How to fix Python error: {error_message}"
        if context:
            if 'library' in context:
                query += f" in {context['library']}"
                
        from .schemas import ResearchType
        config = ResearchConfig(
            query=query,
            research_type=ResearchType.DETAILED
        )
        
        result = await self.conduct_research(config)
        result.metadata['error_context'] = {
            'original_error': error_message,
            'context': context or {}
        }
        
        return result
    
    def validate_config(self, config: ResearchConfig) -> bool:
        """Validate configuration."""
        if not config.query:
            raise ValueError("Query cannot be empty")
        return True
    
    def _save_report(self, result: ResearchResult, filename: str) -> None:
        """Save report to file."""
        # Handle absolute paths vs relative paths
        path = Path(filename)
        if path.is_absolute() or filename.startswith('./') or filename.startswith('../'):
            output_path = path
        else:
            output_path = self.output_dir / filename
            
        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        output_path.write_text(result.report, encoding='utf-8')
        
        # Save metadata
        meta_path = output_path.with_suffix('.json')
        with open(meta_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)
            
        logger.info(f"Report saved to: {output_path}")