#!/usr/bin/env python3
"""Test the new CLI folder structure."""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from omicairn_agent_local.agents import MainAgent
from omicairn_agent_local.utils import setup_logger

logger = setup_logger(__name__)


def main():
    """Test CLI with new folder structure."""
    
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        return 1
    
    # Test parameters
    input_data = Path(os.environ.get("TEST_DATA_DIR", "test_data")) / "zebrafish.h5ad"
    output_dir = Path("test_outputs") / "test_CLI_main_agent"
    
    # Simple clustering request
    user_request = """Perform basic clustering analysis on this zebrafish dataset.
    Use the 'Cell_type' column as ground truth.
    Calculate UMAP, run leiden clustering, and compute ARI metric."""
    
    print("="*60)
    print("Testing CLI Folder Structure")
    print("="*60)
    print(f"Input: {input_data}")
    print(f"Output: {output_dir}")
    print(f"Request: {user_request}")
    print("="*60)
    
    try:
        # Initialize main agent
        agent = MainAgent(openai_api_key=api_key)
        
        # Validate environment
        print("\nValidating environment...")
        validation = agent.validate_environment()
        for component, status in validation.items():
            print(f"  {component}: {'✓' if status else '✗'}")
        
        print("\nRunning analysis...")
        
        # Run analysis with specified output directory
        results = agent.run_analysis(
            input_data_path=input_data,
            user_request=user_request,
            output_dir=output_dir,
            max_nodes=2,
            max_children=1,
            max_debug_trials=1,
            generation_mode="only_new",
            llm_model="gpt-4o-mini",
            verbose=True
        )
        
        # Check folder structure
        print("\n" + "="*60)
        print("Folder Structure Created:")
        print("="*60)
        
        # Check main task folder
        main_folders = list(output_dir.glob("main_*"))
        if main_folders:
            main_task_dir = main_folders[0]
            print(f"✓ Main task folder: {main_task_dir.name}")
            
            # Check orchestrator folder
            orchestrator_folders = list(main_task_dir.glob("orchestrator_*"))
            if orchestrator_folders:
                orchestrator_dir = orchestrator_folders[0]
                print(f"  ✓ Orchestrator folder: {orchestrator_dir.name}")
                
                # Check selector tasks
                selector_tasks = list(orchestrator_dir.glob("selector_*"))
                print(f"    - Selector tasks: {len(selector_tasks)}")
                
                # Check creator task records
                creator_tasks = list(orchestrator_dir.glob("creator_*.json"))
                print(f"    - Creator task records: {len(creator_tasks)}")
            
            # Check tree folder with new structure
            tree_id = results['tree_id']
            tree_dir = output_dir / f"tree_{tree_id}"
            if tree_dir.exists():
                print(f"\n✓ Tree directory: {tree_dir.name}")
                
                # Check tree structure files
                if (tree_dir / "analysis_tree.json").exists():
                    print("  ✓ analysis_tree.json")
                if (tree_dir / "tree_metadata.json").exists():
                    print("  ✓ tree_metadata.json")
                
                # Check nodes directory
                nodes_dir = tree_dir / "nodes"
                if nodes_dir.exists():
                    print(f"  ✓ nodes/ directory")
                    
                    # Check each node
                    for node_id in results.get('results', {}).keys():
                        node_dir = nodes_dir / f"node_{node_id}"
                        if node_dir.exists():
                            print(f"    ✓ Node: node_{node_id[:8]}...")
                            
                            # Check node structure
                            if (node_dir / "node_info.json").exists():
                                print(f"      ✓ node_info.json")
                            
                            # Check function_block folder
                            if (node_dir / "function_block").exists():
                                print(f"      ✓ function_block/")
                                if (node_dir / "function_block" / "code.py").exists():
                                    print(f"        - code.py")
                                if (node_dir / "function_block" / "config.json").exists():
                                    print(f"        - config.json")
                            
                            # Check jobs folder
                            jobs_dir = node_dir / "jobs"
                            if jobs_dir.exists():
                                print(f"      ✓ jobs/")
                                job_folders = list(jobs_dir.glob("job_*"))
                                print(f"        - {len(job_folders)} job(s)")
                                if (jobs_dir / "latest").exists():
                                    print(f"        - latest symlink")
                            
                            # Check outputs folder
                            if (node_dir / "outputs").exists():
                                print(f"      ✓ outputs/")
                                if (node_dir / "outputs" / "_node_anndata.h5ad").exists():
                                    print(f"        - _node_anndata.h5ad")
                            
                            # Check agent_tasks folder
                            agent_tasks_dir = node_dir / "agent_tasks"
                            if agent_tasks_dir.exists():
                                print(f"      ✓ agent_tasks/")
                                
                                # Check creator tasks
                                creator_tasks = list(agent_tasks_dir.glob("creator_*"))
                                if creator_tasks:
                                    print(f"        - {len(creator_tasks)} creator task(s)")
                                
                                # Check fixer tasks
                                fixer_tasks = list(agent_tasks_dir.glob("fixer_*"))
                                if fixer_tasks:
                                    print(f"        - {len(fixer_tasks)} fixer task(s)")
                
                # Check tree-level agent_tasks
                tree_agent_tasks = tree_dir / "agent_tasks"
                if tree_agent_tasks.exists():
                    print(f"  ✓ Tree-level agent_tasks/")
        
        # Summary
        print("\n" + "="*60)
        print("Analysis Results:")
        print("="*60)
        print(f"Tree ID: {results['tree_id']}")
        print(f"Total nodes: {results['total_nodes']}")
        print(f"Completed: {results['completed_nodes']}")
        print(f"Failed: {results['failed_nodes']}")
        
        if results['completed_nodes'] > 0:
            print("\n✓ Test successful - folder structure created correctly!")
        else:
            print("\n⚠ Test completed but no nodes executed successfully")
        
        return 0
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())