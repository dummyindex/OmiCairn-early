#!/usr/bin/env python3
"""Test agent logging functionality with MainAgent."""

import os
import sys
from pathlib import Path
from datetime import datetime
import tempfile
import json
from dotenv import load_dotenv

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from omicairn_agent_local.agents import MainAgent
from omicairn_agent_local.utils import setup_logger
import scanpy as sc
import numpy as np

logger = setup_logger(__name__)


def create_test_data(output_path: Path):
    """Create synthetic test data for clustering."""
    n_obs = 500
    n_vars = 2000
    
    # Generate count matrix
    np.random.seed(42)
    X = np.random.negative_binomial(5, 0.3, size=(n_obs, n_vars))
    
    adata = sc.AnnData(X=X.astype(np.float32))
    adata.obs_names = [f'Cell_{i}' for i in range(n_obs)]
    adata.var_names = [f'Gene_{i}' for i in range(n_vars)]
    
    # Add some metadata
    adata.obs['cell_type'] = np.random.choice(['TypeA', 'TypeB', 'TypeC'], size=n_obs)
    adata.obs['batch'] = np.random.choice(['Batch1', 'Batch2'], size=n_obs)
    
    # Mark some genes as mitochondrial
    adata.var['mt'] = [name.startswith('MT-') for name in adata.var_names]
    
    adata.write(output_path)
    return adata


def check_agent_logging(output_dir: Path):
    """Check if agent logging files were created."""
    logging_results = {
        'nodes_found': 0,
        'agent_tasks_dirs': [],
        'log_files': [],
        'agents_logged': set()
    }
    
    # Find all node directories
    for tree_dir in output_dir.glob("*"):
        if not tree_dir.is_dir():
            continue
            
        nodes_dir = tree_dir / "nodes"
        if not nodes_dir.exists():
            continue
            
        for node_dir in nodes_dir.glob("node_*"):
            logging_results['nodes_found'] += 1
            
            # Check for agent_tasks directory
            agent_tasks_dir = node_dir / "agent_tasks"
            if agent_tasks_dir.exists():
                logging_results['agent_tasks_dirs'].append(str(agent_tasks_dir))
                
                # Check for agent subdirectories
                for agent_dir in agent_tasks_dir.iterdir():
                    if agent_dir.is_dir():
                        logging_results['agents_logged'].add(agent_dir.name)
                        
                        # Check for log files
                        for log_file in agent_dir.glob("*.json"):
                            logging_results['log_files'].append(str(log_file))
                            
                            # Read and verify log content
                            try:
                                with open(log_file) as f:
                                    log_data = json.load(f)
                                    print(f"\nFound log: {log_file.name}")
                                    print(f"  Agent: {log_data.get('agent')}")
                                    print(f"  Task type: {log_data.get('task_type')}")
                                    print(f"  Timestamp: {log_data.get('timestamp')}")
                            except Exception as e:
                                print(f"Error reading log {log_file}: {e}")
    
    return logging_results


def main():
    """Test agent logging with MainAgent."""
    
    print("="*80)
    print("AGENT LOGGING TEST")
    print("="*80)
    
    # Load environment variables from project root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded environment from {env_path}")
    else:
        print(f"Warning: .env file not found at {env_path}")
    
    # Get OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set in environment")
        print("Please set OPENAI_API_KEY environment variable or create a .env file")
        return 1
    
    print("Using OpenAI API key: set")
    
    # Create test data
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_data = temp_path / "test_data.h5ad"
        
        print(f"\nCreating test data at {test_data}")
        adata = create_test_data(test_data)
        print(f"Created test data: {adata.shape}")
        
        # Setup output directory
        output_dir = temp_path / "test_outputs" / f"agent_logging_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize MainAgent with API key
        print("\nInitializing MainAgent with OpenAI API...")
        agent = MainAgent(openai_api_key=api_key)
        
        # Run a simple analysis to trigger agent logging
        user_request = "Perform quality control by filtering cells with less than 200 genes"
        
        print(f"\nRunning analysis with request: {user_request}")
        print(f"Output directory: {output_dir}")
        
        try:
            results = agent.run_analysis(
                input_data_path=test_data,
                user_request=user_request,
                output_dir=output_dir,
                max_nodes=3,  # Limit nodes for quick test
                max_children=1,
                max_debug_trials=1,
                generation_mode="only_new",  # Force new generation to trigger logging
                verbose=True
            )
            
            print("\n" + "="*80)
            print("Analysis completed!")
            print(f"Output directory: {results['output_dir']}")
            print(f"Total nodes: {results.get('total_nodes', 0)}")
            print(f"Completed nodes: {results.get('completed_nodes', 0)}")
            
        except Exception as e:
            print(f"\nError during analysis: {e}")
            import traceback
            traceback.print_exc()
        
        # Check for agent logging
        print("\n" + "="*80)
        print("CHECKING AGENT LOGGING")
        print("="*80)
        
        logging_results = check_agent_logging(output_dir)
        
        print(f"\nLogging Summary:")
        print(f"  Nodes found: {logging_results['nodes_found']}")
        print(f"  Agent tasks dirs: {len(logging_results['agent_tasks_dirs'])}")
        print(f"  Agents logged: {logging_results['agents_logged']}")
        print(f"  Total log files: {len(logging_results['log_files'])}")
        
        if logging_results['log_files']:
            print("\n✅ Agent logging is working!")
            print(f"Found {len(logging_results['log_files'])} log files")
            
            # Show sample log files
            print("\nSample log files:")
            for log_file in logging_results['log_files'][:5]:
                print(f"  - {Path(log_file).name}")
        else:
            print("\n⚠️ No agent log files found")
            print("Agent logging may not be working correctly")
            
            # Debug: Show directory structure
            print("\nDirectory structure:")
            for p in output_dir.rglob("*"):
                if p.is_file():
                    print(f"  {p.relative_to(output_dir)}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())