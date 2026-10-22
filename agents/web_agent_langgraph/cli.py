"""CLI for LangGraph research agent."""

import asyncio
import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .langgraph_agent import LangGraphResearchAgent
from .search_tools import SearchTools
from .schemas import ResearchConfig, ResearchType


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="LangGraph Research Agent CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick research
  python -m agents.web_agent_langgraph.cli "Python asyncio tutorial"
  
  # Search only (no LLM)
  python -m agents.web_agent_langgraph.cli --search-only "Python pandas DataFrame"
  
  # Research with process dump
  python -m agents.web_agent_langgraph.cli "Machine learning basics" \\
    --dump-path ./research_process --type detailed
  
  # Error research
  python -m agents.web_agent_langgraph.cli --error "AttributeError: NoneType" \\
    --context '{"library": "pandas"}'
"""
    )
    
    # Query
    parser.add_argument(
        "query",
        nargs="?",
        help="Research query"
    )
    
    # Mode
    parser.add_argument(
        "--search-only",
        action="store_true",
        help="Only perform search without LLM analysis"
    )
    
    parser.add_argument(
        "--error",
        help="Research a specific error"
    )
    
    parser.add_argument(
        "--context",
        help="Error context (JSON)"
    )
    
    # Research options
    parser.add_argument(
        "--type",
        choices=["quick", "detailed", "deep"],
        default="quick",
        help="Research type (default: quick)"
    )
    
    parser.add_argument(
        "--dump-path",
        help="Path to dump process data"
    )
    
    # Crawling options
    parser.add_argument(
        "--no-crawl",
        action="store_true",
        help="Disable content crawling (faster but less comprehensive)"
    )
    
    parser.add_argument(
        "--crawl-limit",
        type=int,
        default=None,
        help="Maximum number of pages to crawl (default: varies by type)"
    )
    
    # Output
    parser.add_argument(
        "--output", "-o",
        help="Save report to file"
    )
    
    parser.add_argument(
        "--json",
        help="Save as JSON"
    )
    
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Minimal output"
    )
    
    return parser


async def run_search_only(query: str, args: argparse.Namespace) -> int:
    """Run search-only mode without LLM."""
    tools = SearchTools()
    
    if not args.quiet:
        print(f"Searching for: {query}")
        print("Mode: Search only (no LLM)\n")
    
    # Search all sources
    results = tools.search_all_sources(query, max_per_source=5)
    
    # Generate report
    report = tools.generate_search_report(query, results)
    
    if not args.quiet:
        print(f"Found {report['total_results']} results\n")
        
        # Show results by source
        for source, items in report['results_by_source'].items():
            print(f"\n{source.upper()} ({len(items)} results):")
            for item in items[:3]:  # Show top 3 per source
                print(f"  - {item['title']}")
                print(f"    {item['url']}")
                print(f"    {item['snippet'][:100]}...")
    
    # Save outputs
    if args.output:
        # Save as JSON for search-only
        output_path = Path(args.output)
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        if not args.quiet:
            print(f"\nSearch report saved to: {output_path}")
    
    return 0


async def run_llm_research(args: argparse.Namespace) -> int:
    """Run full LLM research."""
    agent = LangGraphResearchAgent(model_name="gpt-4o-mini")
    
    if args.error:
        # Error research
        context = None
        if args.context:
            try:
                context = json.loads(args.context)
            except json.JSONDecodeError:
                print(f"Error: Invalid JSON context", file=sys.stderr)
                return 1
        
        if not args.quiet:
            print(f"Researching error: {args.error}")
            print("Mode: LLM-powered research\n")
        
        result = await agent.conduct_research_for_error(args.error, context)
        
    else:
        # Normal research
        if not args.query:
            print("Error: Query required", file=sys.stderr)
            return 1
        
        type_map = {
            "quick": ResearchType.QUICK,
            "detailed": ResearchType.DETAILED,
            "deep": ResearchType.DEEP
        }
        
        config = ResearchConfig(
            query=args.query,
            research_type=type_map[args.type],
            save_to_file=args.output
        )
        
        # Add dump path if provided
        if args.dump_path:
            config.dump_path = args.dump_path
        
        # Configure crawling
        if args.no_crawl:
            config.enable_crawling = False
        if args.crawl_limit:
            config.crawl_limit = args.crawl_limit
        
        if not args.quiet:
            print(f"Researching: {args.query}")
            print(f"Type: {args.type}")
            print("Mode: LLM-powered research")
            if args.dump_path:
                print(f"Dumping process to: {args.dump_path}")
            print()
        
        result = await agent.conduct_research(config)
    
    # Handle results
    if result.success:
        if not args.quiet:
            print("="*80)
            print(result.report)
            print("="*80)
            print(f"\nCompleted in {result.duration_seconds:.1f}s")
            print(f"Cost: ${result.cost_estimate:.4f}")
            
            if result.sources:
                print(f"\nSources ({len(result.sources)}):")
                for source in result.sources[:5]:
                    print(f"  - {source.get('title', 'Source')}")
                    print(f"    {source.get('url', 'N/A')}")
        
        # Save outputs
        if args.json:
            json_path = Path(args.json)
            with open(json_path, 'w') as f:
                json.dump(result.to_dict(), f, indent=2)
            if not args.quiet:
                print(f"\nJSON saved to: {json_path}")
        
        return 0
    else:
        print(f"Research failed: {result.error}", file=sys.stderr)
        return 1


async def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    try:
        if args.search_only:
            # Search-only mode
            query = args.query or " ".join(sys.argv[2:])
            if not query:
                print("Error: Query required for search", file=sys.stderr)
                return 1
            return await run_search_only(query, args)
        else:
            # LLM research mode
            return await run_llm_research(args)
            
    except KeyboardInterrupt:
        print("\nCancelled", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))