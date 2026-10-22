#!/usr/bin/env python3
"""Test web agent for DPT error research."""

import asyncio
import os
from pathlib import Path
from agents.web_agent_langgraph.web_agent_tool import WebAgentTool

async def test_dpt_research():
    """Test researching DPT pseudotime error."""
    
    # Initialize web agent with small crawl settings
    web_agent = WebAgentTool(
        model_name="gpt-4o-mini",
        embedding_model="text-embedding-3-small",
        enable_crawling=True,
        crawl_limit=3
    )
    
    # Example error encountered during development
    error_message = """KeyError: 'Could not find key dpt_pseudotime in .var_names or .obs.columns.'

WARNING: No root cell found. To compute pseudotime, pass the index or expression vector of a root cell, one of:
    adata.uns['iroot'] = root_cell_index
    adata.var['xroot'] = adata[root_cell_name, :].X
WARNING: Trying to run `tl.dpt` without prior call of `tl.diffmap`. Falling back to `tl.diffmap` with default parameters."""
    
    context = {
        "library": "scanpy",
        "function": "sc.tl.dpt",
        "code_snippet": """
# Pseudotime Analysis using DPT
sc.tl.dpt(adata)

# Visualization
sc.pl.umap(adata, color="dpt_pseudotime", save="_pseudotime_umap.png", show=False)
"""
    }
    
    output_folder = Path("test_outputs/web_agent_dpt_test")
    output_folder.mkdir(parents=True, exist_ok=True)
    
    print("Researching DPT error with web agent...")
    result = await web_agent.research_error(
        error_message=error_message,
        context=context,
        output_folder=output_folder,
        research_type="detailed"  # Get thorough research
    )
    
    print("\n" + "="*80)
    print("RESEARCH RESULTS")
    print("="*80)
    
    print(f"\nSuccess: {result.get('success', False)}")
    print(f"Confidence: {result.get('confidence', 0)}")
    print(f"Cost: ${result.get('cost', 0):.4f}")
    
    print("\n### Findings:")
    for finding in result.get('findings', []):
        print(f"- {finding['finding']}")
    
    print("\n### Solutions:")
    for solution in result.get('solutions', []):
        print(f"- {solution['solution']}")
    
    print("\n### Code Examples:")
    for example in result.get('code_examples', []):
        print(f"\n```{example['language']}")
        print(example['code'])
        print("```")
    
    # Save full result
    import json
    with open(output_folder / "full_result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\nFull results saved to: {output_folder}")

if __name__ == "__main__":
    asyncio.run(test_dpt_research())