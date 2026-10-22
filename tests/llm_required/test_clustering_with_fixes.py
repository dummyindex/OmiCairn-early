#!/usr/bin/env python
"""Test clustering benchmark with enhanced bug fixer."""

import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path  
sys.path.insert(0, str(Path(__file__).parent))

from omicairn_agent_local.agents.main_agent import MainAgent

def run_clustering_test():
    """Run clustering benchmark with the enhanced bug fixer."""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"omicairn_agent_local/test_outputs/clustering_fixed_{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ No OpenAI API key found")
        return False
    
    agent = MainAgent(openai_api_key=api_key)
    
    # Find test data
    test_data = None
    for path in [
        Path("omicairn_agent_local/test_data/zebrafish.h5ad"),
        Path("omicairn_agent_local/test_outputs/clustering_openai_20250804_010410/test_data/zebrafish.h5ad"),
    ]:
        if path.exists():
            test_data = path
            break
    
    if not test_data:
        print("❌ No test data found")
        return False
    
    print(f"\n{'='*80}")
    print("CLUSTERING BENCHMARK TEST WITH ENHANCED BUG FIXER")
    print(f"{'='*80}")
    print(f"✅ Test data: {test_data}")
    print(f"📁 Output: {output_dir}")
    print("\nRequest: Complete a comprehensive clustering benchmark")
    print(f"{'='*80}\n")
    
    # Clustering benchmark request
    request = """Complete a comprehensive clustering benchmark on this single-cell dataset:

1. Apply dimensionality reduction (PCA and UMAP)
2. Compare multiple clustering algorithms (KMeans, Leiden, Agglomerative)
3. Calculate clustering metrics (ARI, NMI, silhouette score) using 'Cell_type' as ground truth
4. Visualize clustering results with proper plots
5. Generate comparison report

Requirements:
- Use Cell_type column as ground truth for metrics
- Create visualization figures for each clustering method
- Save all metrics to CSV files
- Create a summary report"""
    
    result = agent.run_analysis(
        input_data_path=test_data,
        user_request=request,
        output_dir=str(output_dir),
        max_nodes=10,  # Allow more nodes for comprehensive analysis
        max_children=3,
        max_iterations=5,
        max_debug_trials=3,  # Allow multiple fix attempts
        generation_mode="only_new",
        llm_model="gpt-4o-mini",
        verbose=True
    )
    
    # Check results
    tree_id = result['tree_id']
    nodes_dir = output_dir / tree_id / "nodes"
    
    success_count = 0
    failed_count = 0
    fixed_count = 0
    
    if nodes_dir.exists():
        for node_dir in sorted(nodes_dir.iterdir()):
            if node_dir.is_dir():
                # Check node status
                status_file = node_dir / "status.json"
                if status_file.exists():
                    import json
                    with open(status_file) as f:
                        status = json.load(f)
                        if status.get('state') == 'COMPLETED':
                            success_count += 1
                            
                            # Check if it was fixed
                            bug_fixer_dir = node_dir / "agent_tasks" / "bug_fixer"
                            if bug_fixer_dir.exists() and list(bug_fixer_dir.glob("*.json")):
                                fixed_count += 1
                                print(f"✅ Fixed and completed: {node_dir.name}")
                            else:
                                print(f"✅ Completed: {node_dir.name}")
                        else:
                            failed_count += 1
                            print(f"❌ Failed: {node_dir.name}")
    
    print(f"\n{'='*80}")
    print("RESULTS SUMMARY")
    print(f"{'='*80}")
    print(f"Total nodes: {success_count + failed_count}")
    print(f"Successful: {success_count}")
    print(f"Failed: {failed_count}")
    print(f"Fixed by bug fixer: {fixed_count}")
    print(f"Success rate: {success_count / (success_count + failed_count) * 100:.1f}%")
    
    # Check for specific improvements
    improvements = []
    
    # Check if scanpy scatter errors were fixed
    for node_dir in nodes_dir.iterdir() if nodes_dir.exists() else []:
        if node_dir.is_dir():
            code_file = node_dir / "function_block" / "code.py"
            if code_file.exists():
                with open(code_file) as f:
                    code = f.read()
                    # Check for correct visualizations
                    if 'sc.pl.pca' in code or 'sc.pl.umap' in code:
                        improvements.append("✅ Using correct scanpy visualization methods")
                        break
                    elif 'plt.scatter' in code and 'adata.obsm' in code:
                        improvements.append("✅ Using matplotlib for PCA visualization")
                        break
    
    # Check if Cell_type is used correctly
    for node_dir in nodes_dir.iterdir() if nodes_dir.exists() else []:
        if node_dir.is_dir():
            code_file = node_dir / "function_block" / "code.py"
            if code_file.exists():
                with open(code_file) as f:
                    code = f.read()
                    if "'Cell_type'" in code and 'metrics' in code.lower():
                        improvements.append("✅ Using Cell_type column for ground truth metrics")
                        break
    
    if improvements:
        print(f"\n{'='*80}")
        print("IMPROVEMENTS DETECTED")
        print(f"{'='*80}")
        for improvement in improvements:
            print(improvement)
    
    return success_count > 0 and fixed_count > 0

if __name__ == "__main__":
    success = run_clustering_test()
    
    if success:
        print("\n✅ TEST PASSED: Bug fixer successfully handled clustering errors")
        sys.exit(0)
    else:
        print("\n❌ TEST FAILED: Bug fixer needs more improvements")
        sys.exit(1)