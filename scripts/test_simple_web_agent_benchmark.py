#!/usr/bin/env python3
"""Simple test to verify web agent integration with bug fixer."""

import os
import sys
import json
from pathlib import Path
import shutil
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.unified_bug_fixer import UnifiedBugFixer
from agents.orchestrator_agent import OrchestratorAgent
from agents.function_creator_agent import FunctionCreatorAgent
from llm_service import OpenAIService
from analysis_tree_management import AnalysisTreeManager, NodeExecutor
from job_executors import ExecutorManager
from models import (
    AnalysisTree, AnalysisNode, NodeState, 
    NewFunctionBlock, FunctionBlockType
)
from utils import setup_logger

logger = setup_logger(__name__)


def test_simple_pseudotime():
    """Test a simple pseudotime workflow with web agent."""
    
    print("\n" + "="*80)
    print("SIMPLE PSEUDOTIME TEST WITH WEB AGENT")
    print("="*80 + "\n")
    
    # Check API key
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        print("Error: OPENAI_API_KEY not set")
        return False
    
    # Create output directory
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = Path(f"test_outputs/simple_pseudotime_{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create input directory
    input_dir = output_dir / "input"
    input_dir.mkdir()
    
    # Copy test data
    zebrafish_path = Path("test_data/zebrafish.h5ad")
    if not zebrafish_path.exists():
        print(f"Error: {zebrafish_path} not found!")
        return False
        
    shutil.copy(zebrafish_path, input_dir / "zebrafish.h5ad")
    print(f"✓ Copied zebrafish data to {input_dir}")
    
    # Initialize services
    print("\nInitializing services...")
    llm_service = OpenAIService(api_key=openai_key, model="gpt-4o-mini")
    tree_manager = AnalysisTreeManager(output_dir)
    executor_manager = ExecutorManager()
    
    # Initialize bug fixer with web agent
    print("Initializing bug fixer with web agent...")
    bug_fixer = UnifiedBugFixer(
        model_name="gpt-4o-mini",
        api_key=openai_key,
        max_turns=5,
        enable_web_agent=True
    )
    
    if bug_fixer.web_agent_tool:
        print("✓ Web agent tool initialized")
    else:
        print("✗ Web agent tool failed to initialize")
    
    # Create simple analysis tree
    tree_id = f"simple_test_{timestamp}"
    tree = AnalysisTree(
        id=tree_id,
        user_request="Run basic pseudotime analysis using scanpy DPT",
        input_data={"zebrafish": str(input_dir / "zebrafish.h5ad")}
    )
    
    # Create a single node for pseudotime
    node = AnalysisNode(
        id="node_pseudotime",
        name="Run DPT Pseudotime",
        description="Run diffusion pseudotime using scanpy",
        function_block=NewFunctionBlock(
            name="run_dpt_pseudotime",
            type=FunctionBlockType.PYTHON,
            code="""
import scanpy as sc
import pandas as pd
import matplotlib.pyplot as plt

def run(path_dict, params):
    # Load data
    adata = sc.read_h5ad(path_dict['zebrafish'])
    
    # Basic preprocessing if needed
    if 'X_pca' not in adata.obsm:
        sc.pp.normalize_total(adata)
        sc.pp.log1p(adata)
        sc.pp.highly_variable_genes(adata)
        sc.pp.pca(adata)
    
    # Compute neighbors if needed
    if 'neighbors' not in adata.uns:
        sc.pp.neighbors(adata)
    
    # Run DPT
    sc.tl.dpt(adata)
    
    # Create visualization
    if 'X_umap' not in adata.obsm:
        sc.tl.umap(adata)
    
    sc.pl.umap(adata, color='dpt_pseudotime', save='_dpt_pseudotime.png')
    
    # Save results
    adata.write_h5ad(path_dict['output_dir'] + '/adata_with_dpt.h5ad')
    
    # Return summary
    return {
        'n_cells': adata.n_obs,
        'pseudotime_computed': True,
        'min_pseudotime': float(adata.obs['dpt_pseudotime'].min()),
        'max_pseudotime': float(adata.obs['dpt_pseudotime'].max())
    }
""",
            requirements=["scanpy", "pandas", "matplotlib"],
            input_data_assets=["zebrafish"],
            output_data_assets=["adata_with_dpt.h5ad"]
        )
    )
    
    tree.add_node(node)
    tree_manager.save_tree(tree)
    
    # Execute the node
    print("\nExecuting pseudotime analysis...")
    node_executor = NodeExecutor(tree_manager, executor_manager)
    
    try:
        result = node_executor.execute_node(tree_id, node.id)
        
        if result['success']:
            print("✓ Execution succeeded!")
            print(f"  Output: {result.get('output', {})}")
        else:
            print("✗ Execution failed!")
            print(f"  Error: {result.get('error', 'Unknown error')}")
            
            # Simulate bug fixing with web agent
            if 'error' in result and bug_fixer:
                print("\nAttempting to fix with bug fixer + web agent...")
                
                # Get working directory for the node
                node_dir = output_dir / tree_id / "nodes" / node.id
                node_dir.mkdir(parents=True, exist_ok=True)
                
                fix_result = bug_fixer.fix_bug(
                    node_name=node.name,
                    error_message=result['error'],
                    working_directory=node_dir,
                    stdout=result.get('stdout', ''),
                    stderr=result.get('stderr', ''),
                    attempt_number=1
                )
                
                print(f"\nBug fix result:")
                print(f"  Success: {fix_result.get('success', False)}")
                print(f"  Actions taken: {len(fix_result.get('actions_taken', []))}")
                
                # Check for web agent outputs
                web_agent_dir = node_dir / "web_agent_research"
                if web_agent_dir.exists():
                    print("\n✓ Web agent research found!")
                    
                    # Read research data
                    research_data_path = web_agent_dir / "attempt_1" / "research_data.json"
                    if research_data_path.exists():
                        with open(research_data_path) as f:
                            research_data = json.load(f)
                            
                        print(f"  Findings: {len(research_data.get('findings', []))}")
                        print(f"  Solutions: {len(research_data.get('solutions', []))}")
                        print(f"  Confidence: {research_data.get('confidence', 0):.2f}")
                        print(f"  Cost: ${research_data.get('cost', 0):.4f}")
                        
                        # Show findings
                        if research_data.get('findings'):
                            print("\n  Key findings:")
                            for finding in research_data['findings'][:3]:
                                print(f"    - {finding.get('finding', 'N/A')}")
                                
    except Exception as e:
        print(f"✗ Error during execution: {e}")
        logger.error(f"Execution error: {e}", exc_info=True)
        
    # Create summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "tree_id": tree_id,
        "output_dir": str(output_dir),
        "web_agent_enabled": bug_fixer.web_agent_tool is not None
    }
    
    summary_path = output_dir / "test_summary.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
        
    print(f"\n✓ Test summary saved to: {summary_path}")
    
    return True


if __name__ == "__main__":
    success = test_simple_pseudotime()
    sys.exit(0 if success else 1)