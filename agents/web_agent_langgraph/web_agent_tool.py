"""Web Agent Tool for Bug Fixer Integration.

This module provides a tool interface for the web agent that can be used
by the bug fixer to research errors and find solutions.
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from .langgraph_agent import LangGraphResearchAgent
from constants import DEFAULT_OPENAI_MODEL
from .schemas import (
    ResearchConfig, 
    ResearchResult, 
    ResearchType,
    ResearchStatus
)

logger = logging.getLogger(__name__)


class WebAgentTool:
    """Web agent tool for bug fixer integration."""
    
    def __init__(
        self,
        model_name: str = DEFAULT_OPENAI_MODEL,
        embedding_model: str = "text-embedding-3-small",
        output_dir: Optional[Path] = None,
        enable_crawling: bool = True,
        crawl_limit: int = 5,
        timeout_seconds: int = 90
    ):
        """Initialize web agent tool.
        
        Args:
            model_name: LLM model to use
            embedding_model: Embedding model for crawling
            output_dir: Base output directory
            enable_crawling: Whether to enable content crawling
            crawl_limit: Maximum pages to crawl
            timeout_seconds: Maximum time allowed for research (default: 90s)
        """
        self.model_name = model_name
        self.embedding_model = embedding_model
        self.output_dir = output_dir or Path("web_agent_outputs")
        self.enable_crawling = enable_crawling
        self.crawl_limit = crawl_limit
        self.timeout_seconds = timeout_seconds
        self.agent = None
        
    async def _ensure_agent(self):
        """Ensure agent is initialized."""
        if self.agent is None:
            self.agent = LangGraphResearchAgent(
                model_name=self.model_name,
                output_dir=self.output_dir
            )
            
    async def research_error(
        self,
        error_message: str,
        context: Dict[str, Any],
        output_folder: Path,
        research_type: str = "quick"
    ) -> Dict[str, Any]:
        """Research an error using the web agent.
        
        Args:
            error_message: The error message to research
            context: Additional context (code, library, etc.)
            output_folder: Folder to save outputs to
            research_type: Type of research (quick/detailed/deep)
            
        Returns:
            Dictionary with research results for bug fixer
        """
        start_time = datetime.now()
        logger.info(f"Starting web agent research for error: {error_message[:100]}...")
        logger.info(f"Research type: {research_type}, Timeout: {self.timeout_seconds}s")
        
        await self._ensure_agent()
        
        # Create output folder
        output_folder.mkdir(parents=True, exist_ok=True)
        
        # Build research query
        query_parts = [f"Error: {error_message}"]
        
        if context.get("library"):
            query_parts.append(f"Library: {context['library']}")
            
        if context.get("function"):
            query_parts.append(f"Function: {context['function']}")
            
        if context.get("code_snippet"):
            query_parts.append(f"Code context: {context['code_snippet'][:200]}...")
            
        query = " | ".join(query_parts)
        
        # Configure research
        type_map = {
            "quick": ResearchType.QUICK,
            "detailed": ResearchType.DETAILED,
            "deep": ResearchType.DEEP
        }
        
        config = ResearchConfig(
            query=query,
            research_type=type_map.get(research_type, ResearchType.QUICK),
            enable_crawling=self.enable_crawling,
            crawl_limit=self.crawl_limit,
            save_to_file=str(output_folder / "research_report.md"),
            timeout=self.timeout_seconds
        )
        
        # Track partial state for timeout handling
        partial_state = {
            'search_completed': False,
            'search_results': [],
            'crawl_completed': False,
            'analysis_completed': False,
            'partial_findings': []
        }
        
        # Conduct research with timeout
        try:
            # Create a task to track progress
            research_task = asyncio.create_task(self.agent.conduct_research(config))
            
            # Use asyncio timeout
            result = await asyncio.wait_for(
                research_task,
                timeout=self.timeout_seconds
            )
            
            if result.success:
                # Save outputs
                report_path = output_folder / "research_report.md"
                json_path = output_folder / "research_data.json"
                
                # Save markdown report
                with open(report_path, 'w') as f:
                    f.write(result.report)
                
                # Save JSON data
                research_data = {
                    "timestamp": datetime.now().isoformat(),
                    "error_message": error_message,
                    "context": context,
                    "query": query,
                    "research_type": research_type,
                    "findings": self._extract_findings(result),
                    "solutions": self._extract_solutions(result),
                    "code_examples": self._extract_code_examples(result),
                    "sources": result.sources,
                    "confidence": result.metadata.get("confidence_score", 0.5),
                    "cost": result.cost_estimate,
                    "duration": result.duration_seconds
                }
                
                with open(json_path, 'w') as f:
                    json.dump(research_data, f, indent=2, default=str)
                
                # Log timing
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(f"Web agent research completed successfully in {duration:.1f}s")
                logger.info(f"Cost: ${result.cost_estimate:.4f}, Confidence: {research_data['confidence']:.2f}")
                
                # Return structured data for bug fixer
                return {
                    "success": True,
                    "report_path": str(report_path),
                    "json_path": str(json_path),
                    "findings": research_data["findings"],
                    "solutions": research_data["solutions"],
                    "code_examples": research_data["code_examples"],
                    "confidence": research_data["confidence"],
                    "sources": research_data["sources"][:3],  # Top 3 sources
                    "duration_seconds": duration
                }
            else:
                duration = (datetime.now() - start_time).total_seconds()
                logger.warning(f"Web agent research failed after {duration:.1f}s: {result.error}")
                return {
                    "success": False,
                    "error": result.error,
                    "findings": [],
                    "solutions": [],
                    "code_examples": [],
                    "duration_seconds": duration
                }
                
        except asyncio.TimeoutError:
            duration = (datetime.now() - start_time).total_seconds()
            logger.warning(f"Web agent research timed out after {duration:.1f}s - summarizing partial findings")
            
            # Try to get partial state from the agent
            partial_findings = []
            partial_solutions = []
            
            # Create a basic summary of what was found before timeout
            timeout_summary = f"Research timed out after {self.timeout_seconds}s. "
            
            # Check if we have the agent's current state
            if hasattr(self.agent, 'current_state') and self.agent.current_state:
                state = self.agent.current_state
                if hasattr(state, 'search_results') and state.search_results:
                    timeout_summary += f"Found {len(state.search_results)} search results. "
                    # Extract basic findings from search results
                    for result in state.search_results[:3]:
                        partial_findings.append({
                            "finding": f"{result.title} - {result.snippet[:100]}...",
                            "relevance": "medium"
                        })
                if hasattr(state, 'analysis') and state.analysis:
                    timeout_summary += "Partial analysis completed. "
                    if hasattr(state.analysis, 'key_findings'):
                        for finding in state.analysis.key_findings[:3]:
                            partial_findings.append({
                                "finding": finding,
                                "relevance": "high"
                            })
            
            # Add timeout-specific suggestions
            partial_solutions.append({
                "solution": "Research timed out - try searching for the specific error message directly",
                "type": "recommendation"
            })
            partial_solutions.append({
                "solution": f"Consider checking the {context.get('library', 'library')} documentation directly",
                "type": "recommendation"
            })
            
            # Save partial findings
            try:
                research_data = {
                    "timestamp": datetime.now().isoformat(),
                    "error_message": error_message,
                    "context": context,
                    "query": query,
                    "research_type": research_type,
                    "findings": partial_findings,
                    "solutions": partial_solutions,
                    "code_examples": [],
                    "sources": [],
                    "confidence": 0.3,  # Low confidence due to timeout
                    "cost": 0.0,
                    "duration": duration,
                    "status": "timeout",
                    "summary": timeout_summary
                }
                
                json_path = output_folder / "research_data.json"
                with open(json_path, 'w') as f:
                    json.dump(research_data, f, indent=2, default=str)
                
                # Create a basic report
                report_path = output_folder / "research_report.md"
                report_content = f"""# Research Report: {query}

**Status**: Timed out after {self.timeout_seconds}s

## Summary

{timeout_summary}

## Partial Findings

"""
                for finding in partial_findings:
                    report_content += f"- {finding['finding']}\n"
                
                report_content += "\n## Recommendations\n\n"
                for solution in partial_solutions:
                    report_content += f"- {solution['solution']}\n"
                
                with open(report_path, 'w') as f:
                    f.write(report_content)
                
            except Exception as e:
                logger.error(f"Failed to save partial results: {e}")
            
            return {
                "success": False,
                "error": f"Research timed out after {self.timeout_seconds} seconds (partial results saved)",
                "findings": partial_findings,
                "solutions": partial_solutions,
                "code_examples": [],
                "duration_seconds": duration,
                "partial": True
            }
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Web agent research failed after {duration:.1f}s: {e}")
            return {
                "success": False,
                "error": str(e),
                "findings": [],
                "solutions": [],
                "code_examples": [],
                "duration_seconds": duration
            }
            
    def _extract_findings(self, result: ResearchResult) -> List[Dict[str, Any]]:
        """Extract key findings from research result."""
        findings = []
        
        # Check if metadata contains structured findings
        if result.metadata and 'final_report' in result.metadata:
            report_data = result.metadata['final_report']
            if 'detailed_findings' in report_data:
                for finding in report_data['detailed_findings'][:5]:
                    findings.append({
                        "finding": finding.get('finding', ''),
                        "relevance": finding.get('confidence', 'medium')
                    })
                return findings
        
        # Fallback to parsing from report text
        if result.report:
            lines = result.report.split('\n')
            in_findings = False
            
            for line in lines:
                if "Detailed Findings" in line:
                    in_findings = True
                    continue
                elif in_findings and line.startswith("- **"):
                    # Extract finding
                    finding = line.replace("- **", "").replace("**", "").strip()
                    findings.append({
                        "finding": finding,
                        "relevance": "high" if "error" in finding.lower() else "medium"
                    })
                elif in_findings and line.startswith("##"):
                    break
                    
        return findings[:5]  # Top 5 findings
        
    def _extract_solutions(self, result: ResearchResult) -> List[Dict[str, Any]]:
        """Extract potential solutions from research."""
        solutions = []
        
        # Check if metadata contains structured recommendations
        if result.metadata and 'final_report' in result.metadata:
            report_data = result.metadata['final_report']
            if 'recommendations' in report_data:
                for rec in report_data['recommendations'][:5]:
                    solutions.append({
                        "solution": rec,
                        "type": "recommendation"
                    })
        
        # Fallback to parsing recommendations from report
        if not solutions and result.report:
            lines = result.report.split('\n')
            in_recommendations = False
            
            for line in lines:
                if "Recommendations" in line:
                    in_recommendations = True
                    continue
                elif in_recommendations and line.startswith("- "):
                    solution = line.replace("- ", "").strip()
                    solutions.append({
                        "solution": solution,
                        "type": "recommendation"
                    })
                    
        # Add specific fixes from sources
        for source in result.sources:
            if "stackoverflow" in source.get("url", "").lower():
                solutions.append({
                    "solution": f"Check solution at: {source['url']}",
                    "type": "stackoverflow"
                })
                
        return solutions[:5]  # Top 5 solutions
        
    def _extract_code_examples(self, result: ResearchResult) -> List[Dict[str, str]]:
        """Extract code examples from research."""
        examples = []
        
        # Check if metadata contains structured code examples
        if result.metadata and 'final_report' in result.metadata:
            report_data = result.metadata['final_report']
            if 'code_examples' in report_data:
                for example in report_data['code_examples'][:3]:
                    examples.append({
                        "code": example.get('code', ''),
                        "language": example.get('language', 'python'),
                        "description": example.get('description', '')
                    })
                return examples
        
        # Fallback to parsing from report
        if result.report:
            lines = result.report.split('\n')
            in_code = False
            current_code = []
            current_lang = "python"
            
            for line in lines:
                if line.startswith("```"):
                    if in_code:
                        # End of code block
                        if current_code:
                            examples.append({
                                "code": '\n'.join(current_code),
                                "language": current_lang
                            })
                        current_code = []
                        in_code = False
                    else:
                        # Start of code block
                        in_code = True
                        lang = line.replace("```", "").strip()
                        current_lang = lang if lang else "python"
                elif in_code:
                    current_code.append(line)
                    
        return examples[:3]  # Top 3 examples
        
    async def research_library_usage(
        self,
        library: str,
        function: str,
        output_folder: Path,
        research_type: str = "quick"
    ) -> Dict[str, Any]:
        """Research how to use a specific library function.
        
        Args:
            library: Library name
            function: Function or feature to research
            output_folder: Folder to save outputs to
            research_type: Type of research
            
        Returns:
            Dictionary with research results
        """
        query = f"How to use {library} {function} with examples and best practices"
        
        context = {
            "library": library,
            "function": function,
            "type": "usage_research"
        }
        
        # Use error research with custom query
        return await self.research_error(
            error_message=query,
            context=context,
            output_folder=output_folder,
            research_type=research_type
        )