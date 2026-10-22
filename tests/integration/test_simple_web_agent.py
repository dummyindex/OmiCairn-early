#!/usr/bin/env python3
"""Simple direct test of web agent for DPT error."""

import asyncio
from agents.web_agent_langgraph.langgraph_agent import LangGraphResearchAgent

async def test_simple():
    """Test web agent directly."""
    
    agent = LangGraphResearchAgent(
        model_name="gpt-4o-mini",
        embedding_model="text-embedding-3-small",
        enable_crawling=True,
        crawl_limit=3
    )
    
    query = """
    I'm getting this error in scanpy when trying to use DPT pseudotime:
    
    KeyError: 'Could not find key dpt_pseudotime in .var_names or .obs.columns.'
    
    My code:
    sc.tl.dpt(adata)
    sc.pl.umap(adata, color="dpt_pseudotime")
    
    WARNING: No root cell found. To compute pseudotime, pass the index or expression vector of a root cell
    """
    
    print("Running web agent research...")
    result = await agent.research(query)
    
    print("\n" + "="*80)
    print("RESEARCH RESULT")
    print("="*80)
    
    print(f"\nStatus: {result.status}")
    print(f"\nReport:\n{result.report}")
    
    if result.metadata:
        print(f"\nMetadata keys: {list(result.metadata.keys())}")

if __name__ == "__main__":
    asyncio.run(test_simple())