#!/usr/bin/env python3
"""General single-cell genomics benchmarks with configurable LLM models and debug parameters.

Pass/fail criteria in this module are smoke-level execution heuristics (node counts,
outputs produced), not accuracy benchmarks.
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
import logging
import time
import json

# Add the omicairn_agent_local directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agents.main_agent import MainAgent
from models import NodeState, JobReviewStatus

# Set up logging - ensure we don't capture DEBUG logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure root logger is not at DEBUG level
logging.getLogger().setLevel(logging.INFO)

# Silence noisy loggers
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('docker').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('openai').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)  # Silence HTTP connection details
logging.getLogger('httpcore.http11').setLevel(logging.WARNING)  # Silence HTTP/1.1 protocol details
logging.getLogger('omicairn_agent.llm_service.openai_service').setLevel(logging.INFO)

# Test datasets are not shipped; set TEST_DATA_DIR (default: <repo>/test_data). See tests/README.md.
TEST_DATA_DIR = Path(os.environ.get(
    "TEST_DATA_DIR",
    Path(__file__).resolve().parent.parent.parent / "test_data"
))


def analyze_node_statistics(tree_data: dict) -> dict:
    """Analyze node statistics including execution status and job review status.
    
    Returns dict with detailed statistics.
    """
    from models import NodeState, JobReviewStatus
    
    # Initialize counters
    stats = {
        'total_nodes': len(tree_data['nodes']),
        # Execution status
        'execution': {
            'completed': 0,
            'failed': 0,
            'pending': 0,
            'running': 0
        },
        # Job review status
        'job_review': {
            'passed': 0,
            'failed': 0,
            'not_reviewed': 0,
            'skipped': 0,
            'needs_rework': 0
        },
        # Combined status
        'combined': {
            'completed_and_passed': 0,
            'completed_but_failed_review': 0,
            'completed_needs_rework': 0,
            'failed_execution': 0,
            'completed_not_reviewed': 0
        },
        # Debug stats
        'debug': {
            'total_attempts': 0,
            'nodes_with_debug': 0,
            'max_attempts_single_node': 0
        }
    }
    
    # Analyze each node
    for node_id, node in tree_data['nodes'].items():
        # Execution status
        state = node.get('state', NodeState.PENDING.value)
        if state == NodeState.COMPLETED.value:
            stats['execution']['completed'] += 1
        elif state == NodeState.FAILED.value:
            stats['execution']['failed'] += 1
        elif state == NodeState.PENDING.value:
            stats['execution']['pending'] += 1
        elif state == NodeState.RUNNING.value:
            stats['execution']['running'] += 1
        
        # Job review status
        review_status = node.get('job_review_status', JobReviewStatus.NOT_REVIEWED.value)
        if review_status == JobReviewStatus.PASSED.value:
            stats['job_review']['passed'] += 1
        elif review_status == JobReviewStatus.FAILED.value:
            stats['job_review']['failed'] += 1
        elif review_status == JobReviewStatus.NOT_REVIEWED.value:
            stats['job_review']['not_reviewed'] += 1
        elif review_status == JobReviewStatus.SKIPPED.value:
            stats['job_review']['skipped'] += 1
        
        # Check needs_rework
        if node.get('needs_rework', False):
            stats['job_review']['needs_rework'] += 1
        
        # Combined status analysis
        if state == NodeState.COMPLETED.value:
            if review_status == JobReviewStatus.PASSED.value:
                stats['combined']['completed_and_passed'] += 1
            elif review_status == JobReviewStatus.FAILED.value:
                stats['combined']['completed_but_failed_review'] += 1
                if node.get('needs_rework', False):
                    stats['combined']['completed_needs_rework'] += 1
            elif review_status == JobReviewStatus.NOT_REVIEWED.value:
                stats['combined']['completed_not_reviewed'] += 1
        elif state == NodeState.FAILED.value:
            stats['combined']['failed_execution'] += 1
        
        # Debug statistics
        debug_attempts = node.get('debug_attempts', 0)
        stats['debug']['total_attempts'] += debug_attempts
        if debug_attempts > 0:
            stats['debug']['nodes_with_debug'] += 1
            stats['debug']['max_attempts_single_node'] = max(
                stats['debug']['max_attempts_single_node'], 
                debug_attempts
            )
    
    # Calculate percentages
    total = stats['total_nodes']
    if total > 0:
        stats['execution']['success_rate'] = stats['execution']['completed'] / total * 100
        stats['job_review']['pass_rate'] = stats['job_review']['passed'] / total * 100
        stats['combined']['fully_successful_rate'] = stats['combined']['completed_and_passed'] / total * 100
    
    return stats


def print_node_statistics(stats: dict):
    """Print formatted node statistics."""
    print(f"\n{'='*60}")
    print("NODE STATISTICS SUMMARY")
    print(f"{'='*60}")
    
    print(f"\nTotal Nodes: {stats['total_nodes']}")
    
    print("\n📊 EXECUTION STATUS:")
    print(f"  ✅ Completed: {stats['execution']['completed']} ({stats['execution'].get('success_rate', 0):.1f}%)")
    print(f"  ❌ Failed: {stats['execution']['failed']}")
    print(f"  ⏳ Pending: {stats['execution']['pending']}")
    print(f"  🔄 Running: {stats['execution']['running']}")
    
    print("\n📋 JOB REVIEW STATUS:")
    print(f"  ✅ Passed Review: {stats['job_review']['passed']} ({stats['job_review'].get('pass_rate', 0):.1f}%)")
    print(f"  ❌ Failed Review: {stats['job_review']['failed']}")
    print(f"  🔄 Needs Rework: {stats['job_review']['needs_rework']}")
    print(f"  ⏭️  Skipped: {stats['job_review']['skipped']}")
    print(f"  ❓ Not Reviewed: {stats['job_review']['not_reviewed']}")
    
    print("\n🎯 COMBINED STATUS:")
    print(f"  ✅✅ Completed + Passed Review: {stats['combined']['completed_and_passed']} ({stats['combined'].get('fully_successful_rate', 0):.1f}%)")
    print(f"  ✅❌ Completed but Failed Review: {stats['combined']['completed_but_failed_review']}")
    print(f"  ✅🔄 Completed but Needs Rework: {stats['combined']['completed_needs_rework']}")
    print(f"  ✅❓ Completed but Not Reviewed: {stats['combined']['completed_not_reviewed']}")
    print(f"  ❌❌ Failed Execution: {stats['combined']['failed_execution']}")
    
    print("\n🔧 DEBUG STATISTICS:")
    print(f"  Total Debug Attempts: {stats['debug']['total_attempts']}")
    print(f"  Nodes Requiring Debug: {stats['debug']['nodes_with_debug']}")
    print(f"  Max Attempts (single node): {stats['debug']['max_attempts_single_node']}")
    if stats['debug']['nodes_with_debug'] > 0:
        avg_attempts = stats['debug']['total_attempts'] / stats['debug']['nodes_with_debug']
        print(f"  Average Attempts per Debugged Node: {avg_attempts:.1f}")
    
    print(f"{'='*60}\n")


def run_pseudotime_benchmark(llm_model: str = "gpt-4o-mini", debug_turns: int = 10, max_debug_trials: int = 3):
    """Run pseudotime benchmark with configurable LLM model and debug parameters.
    
    Args:
        llm_model: The LLM model to use (default: gpt-4o-mini)
        debug_turns: Number of debug turns per bug fixer session (default: 10)
        max_debug_trials: Maximum number of bug fixer sessions per node (default: 3)
    """
    
    user_request = """
    Perform comprehensive single-cell pseudotime analysis using multiple advanced methods:
    
    1. **Data Preprocessing**:
       - Load and preprocess the zebrafish dataset if not already processed
       - Ensure proper QC, normalization, and dimensionality reduction
       - Generate UMAP embedding for visualization
    
    2. **Multiple Pseudotime Methods**:
       **DPT + PAGA (Scanpy)**:
       - Compute diffusion maps and DPT pseudotime using sc.tl.dpt()
       - Use PAGA for trajectory structure inference
       - Store result in adata.obs['dpt_pseudotime']
       
       **Palantir**:
       - Use Palantir for pseudotime and trajectory inference
       - Handle potential API changes in recent versions
       - Store result in adata.obs['palantir_pseudotime']
       
       **scFates**:
       - Learn trajectory tree structure using scFates
       - Compute pseudotime along inferred trajectories
       - Handle potential API updates (tl.tree vs tl.curve)
       - Store in adata.obs['scfates_pseudotime']

       **DTFLOW**:
       - Use DTFLOW for pseudotime inference from embeddings
       - Store result in adata.obs['dtflow_pseudotime'] only if DTFLOW itself ran; if it is unavailable, store an approximation under a key naming the method actually used (e.g. adata.obs['rwr_pseudotime']) and say so in the report
    
    3. **Comprehensive Analysis**:
       - Compute correlation metrics (Kendall, Spearman, MAE) between all methods
       - Store metrics in adata.uns['pseudotime_metrics']
       - Generate UMAP plots colored by each pseudotime method
       - Create comparison plots showing method correlations
       - Save method-specific intermediate results
    
    4. **Visualization and Results**:
       - Generate comprehensive pseudotime comparison plots
       - Create method performance comparison charts
       - Save all intermediate and final results with clear naming
       - Export final processed dataset with all pseudotime annotations

       **CellRank**:
       - Use CellRank with PseudotimeKernel or VelocityKernel
       - Compute absorption probabilities and transition matrix
       - Create visualization plots with CellRank
       
    Note: This analysis may encounter API changes or compatibility issues with different 
    trajectory inference packages. The bug fixer should help resolve any method-specific errors.
    """
    
    # Input data path
    input_data = TEST_DATA_DIR / "zebrafish.h5ad"
    
    # Output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("test_outputs") / f"enhanced_pseudotime_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*80}")
    print("ENHANCED PSEUDOTIME BENCHMARK")
    print(f"{'='*80}")
    print(f"Input data: {input_data}")
    print(f"Output directory: {output_dir}")
    print(f"Started at: {datetime.now()}")
    print(f"LLM Model: {llm_model}")
    print(f"Bug fixer turns per session: {debug_turns}")
    print(f"Max bug fixer sessions per node: {max_debug_trials}")
    print(f"Max nodes: 15")
    print(f"Web agent: DISABLED")
    print(f"{'='*80}\n")
    
    # Log LLM configuration
    logger.info(f"Initializing MainAgent with LLM model: {llm_model}")
    logger.info(f"Bug fixer will use {debug_turns} debug turns per session")
    logger.info(f"Max debug sessions per node: {max_debug_trials}")
    
    try:
        # Initialize the main agent with modified settings
        agent = MainAgent(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            bug_fixer_type="unified",
            bug_fixer_model=llm_model,  # Use the specified LLM model for bug fixer
            llm_model=llm_model,  # Use the specified LLM model for main agent
            enable_interactive_debug=True,
            enable_web_agent=False,  # Disable web agent as requested
            log_llm_to_stdout=False,  # Keep logs in agent subfolders, not stdout
            enable_domain_knowledge=True,  # Keep domain knowledge for API fixes
            domain_knowledge_domains=["single_cell_genomics", "cell_type_annotation"],  # Specify relevant domains
            bug_fixer_max_turns=debug_turns  # Pass the configurable debug turns
        )
        
        logger.info(f"MainAgent initialized with:")
        logger.info(f"  - LLM model: {llm_model}")
        logger.info(f"  - Bug fixer model: {llm_model}")
        logger.info(f"  - Bug fixer max turns per session: {debug_turns}")
        logger.info(f"  - Max debug sessions per node: {max_debug_trials}")
        
        print("Main agent initialized with requested configuration:")
        print(f"✅ LLM Model: {llm_model}")
        print(f"✅ Bug fixer turns per session: {debug_turns}")
        print(f"✅ Max bug fixer sessions per node: {max_debug_trials}")
        print("✅ Web agent: DISABLED as requested")
        print("✅ Max nodes: 15 (configured via max_nodes)")
        print("✅ Interactive debugging: Full container access")
        print("✅ Knowledge inheritance: Complete action history between attempts")
        print("✅ Real function validation: Actual execution testing")
        print("")
        print("Configuration details:")
        print(f"  - LLM model: {llm_model} for all agents")
        print(f"  - Bug fixer: {debug_turns} turns per session, max {max_debug_trials} sessions per node")
        print(f"  - Total possible debugging: {debug_turns * max_debug_trials} actions per node")
        print("  - Max nodes: 15 to limit tree complexity")
        print("  - Web agent: Disabled to rely on local debugging only")
        print("  - Domain knowledge: Enabled for API guidance")
        print("")
        
        # Run the analysis with requested parameters
        result = agent.run_analysis(
            input_data_path=str(input_data),
            user_request=user_request,
            output_dir=str(output_dir),
            max_nodes=15,  # Reduced from 25 as requested
            max_debug_trials=max_debug_trials,  # Use the proper max_debug_trials parameter
            max_iterations=20  # Keep extended iteration limit
        )
        
        print(f"\n{'='*80}")
        print("ENHANCED ANALYSIS COMPLETE - EVALUATING RESULTS")
        print(f"{'='*80}\n")
        
        # Analyze results with enhanced metrics
        import json
        tree_id = result.get('tree_id')
        if not tree_id:
            print(f"❌ ERROR: Analysis failed - no tree_id in result")
            print(f"Result: {result}")
            return
            
        tree_file = output_dir / tree_id / "analysis_tree.json"
        if tree_file.exists():
            with open(tree_file, 'r') as f:
                tree_data = json.load(f)
            
            # Enhanced node analysis
            total_nodes = len(tree_data['nodes'])
            completed_nodes = sum(1 for n in tree_data['nodes'].values() if n['state'] == 'completed')
            failed_nodes = sum(1 for n in tree_data['nodes'].values() if n['state'] == 'failed')
            
            # Debug statistics
            total_debug_attempts = sum(n.get('debug_attempts', 0) for n in tree_data['nodes'].values())
            nodes_with_debug = sum(1 for n in tree_data['nodes'].values() if n.get('debug_attempts', 0) > 0)
            web_research_uses = 0  # Count would need to be tracked in tree data
            
            print(f"Enhanced Node Statistics:")
            print(f"  Total nodes: {total_nodes}")
            print(f"  Completed: {completed_nodes}")
            print(f"  Failed: {failed_nodes}")
            print(f"  Success rate: {completed_nodes/total_nodes*100:.1f}%")
            print(f"  Nodes requiring debug: {nodes_with_debug}")
            print(f"  Total debug attempts: {total_debug_attempts}")
            print(f"  Average debug attempts per failing node: {total_debug_attempts/max(nodes_with_debug, 1):.1f}")
            
            # Analyze pseudotime method results
            pseudotime_methods = []
            method_results = {}
            method_debug_stats = {}
            
            pseudotime_keywords = ['dpt', 'diffusion', 'palantir', 'scfates', 'cellrank', 'dtflow', 'paga', 'trajectory', 'pseudotime']
            
            for node_id, node in tree_data['nodes'].items():
                node_name = node['function_block']['name'].lower()
                is_pseudotime_node = any(keyword in node_name for keyword in pseudotime_keywords)
                
                if is_pseudotime_node:
                    method_debug_stats[node_name] = {
                        'state': node['state'],
                        'debug_attempts': node.get('debug_attempts', 0),
                        'node_id': node_id
                    }
                    
                    if node['state'] == 'completed':
                        pseudotime_methods.append(node_name)
                        if node.get('output_data_id'):
                            output_path = Path(node['output_data_id'])
                            if output_path.exists():
                                files = [f.name for f in output_path.glob('*')]
                                method_results[node_name] = {
                                    'files': files,
                                    'h5ad_files': [f for f in files if f.endswith('.h5ad')],
                                    'output_path': str(output_path)
                                }
            
            print(f"\nPseudotime Method Analysis:")
            print(f"  Pseudotime nodes attempted: {len(method_debug_stats)}")
            print(f"  Pseudotime methods completed: {len(pseudotime_methods)}")
            print(f"  Completion rate for pseudotime: {len(pseudotime_methods)/max(len(method_debug_stats), 1)*100:.1f}%")
            
            print(f"\nMethod-specific Debug Statistics:")
            for method, stats in method_debug_stats.items():
                status_icon = "✅" if stats['state'] == 'completed' else "❌" if stats['state'] == 'failed' else "⏳"
                print(f"  {status_icon} {method}: {stats['state']} (debug attempts: {stats['debug_attempts']})")
            
            # Analyze output quality
            total_h5ad_outputs = sum(len(result['h5ad_files']) for result in method_results.values())
            unique_output_names = set()
            for result in method_results.values():
                unique_output_names.update(result['files'])
            
            print(f"\nOutput Quality Analysis:")
            print(f"  Methods with outputs: {len(method_results)}")
            print(f"  Total h5ad output files: {total_h5ad_outputs}")
            print(f"  Unique output filenames: {len(unique_output_names)}")
            
            print(f"\nDetailed Method Results:")
            for method, result in method_results.items():
                print(f"  {method}:")
                print(f"    Output files: {len(result['files'])}")
                print(f"    H5AD files: {len(result['h5ad_files'])}")
                print(f"    Location: {result['output_path']}")
            
            # Enhanced success criteria adjusted for 15 node limit
            enhanced_success = (
                completed_nodes >= 10 and           # Adjusted for 15 node limit
                len(pseudotime_methods) >= 2 and    # At least 2 pseudotime methods
                failed_nodes <= 5 and              # Reasonable failure tolerance
                total_debug_attempts <= 50 and     # Allow more attempts with 10 turns
                total_h5ad_outputs >= 2            # Quality output generation
            )
            
            print(f"\n{'='*80}")
            print("ENHANCED PSEUDOTIME BENCHMARK EVALUATION:")
            print(f"{'='*80}")
            
            if enhanced_success:
                print("🎉 ENHANCED PSEUDOTIME BENCHMARK PASSED")
                print("(Pass criteria are execution-completion heuristics: node counts, methods completed,")
                print(" debug attempts and h5ad outputs. They do not assess scientific accuracy.)")
            else:
                print("⚠️ ENHANCED BENCHMARK NEEDS IMPROVEMENT")
                improvement_areas = []
                if completed_nodes < 10:
                    improvement_areas.append("Overall completion rate below target (need 10+ nodes)")
                if len(pseudotime_methods) < 2:
                    improvement_areas.append("Insufficient pseudotime method diversity (need 2+ methods)")
                if failed_nodes > 5:
                    improvement_areas.append("Too many failed nodes (max 5 allowed)")
                if total_debug_attempts > 50:
                    improvement_areas.append("Too many debug attempts (max 50)")
                if total_h5ad_outputs < 2:
                    improvement_areas.append("Output generation quality needs work (need 2+ h5ad files)")
                
                for area in improvement_areas:
                    print(f"  ❌ {area}")
            
            # Save comprehensive results
            enhanced_results = {
                "timestamp": timestamp,
                "benchmark_type": f"enhanced_pseudotime_{debug_turns}_turns_15_nodes_no_web_{llm_model}",
                "success": enhanced_success,
                "configuration": {
                    "llm_model": llm_model,
                    "bug_fixer_turns": debug_turns,  # Configurable
                    "web_agent_enabled": False,  # Disabled as requested
                    "max_nodes": 15,  # Limited as requested
                    "max_debug_trials": max_debug_trials
                },
                "note": "'success' reflects execution-completion heuristics, not scientific accuracy",
                "statistics": {
                    "total_nodes": total_nodes,
                    "completed_nodes": completed_nodes,
                    "failed_nodes": failed_nodes,
                    "success_rate": completed_nodes/total_nodes*100,
                    "pseudotime_methods_attempted": len(method_debug_stats),
                    "pseudotime_methods_completed": len(pseudotime_methods),
                    "pseudotime_success_rate": len(pseudotime_methods)/max(len(method_debug_stats), 1)*100,
                    "total_debug_attempts": total_debug_attempts,
                    "nodes_requiring_debug": nodes_with_debug,
                    "debug_efficiency": total_debug_attempts/max(nodes_with_debug, 1),
                    "h5ad_outputs_generated": total_h5ad_outputs
                },
                "pseudotime_methods": {
                    "completed": pseudotime_methods,
                    "debug_stats": method_debug_stats,
                    "output_results": method_results
                },
                "enhanced_features": [
                    f"Bug fixer with {debug_turns} turns per session",
                    f"Max {max_debug_trials} debug sessions per node",
                    "Web agent disabled",
                    "Max nodes 15"
                ],
                "output_quality": {
                    "unique_filenames": list(unique_output_names),
                    "methods_with_outputs": len(method_results),
                    "total_output_files": len(unique_output_names)
                }
            }
            
            results_file = output_dir / "enhanced_pseudotime_benchmark_results.json"
            with open(results_file, "w") as f:
                json.dump(enhanced_results, f, indent=2)
            
            print(f"\nDetailed results saved to: {results_file}")
            return enhanced_success
            
        else:
            print("❌ No analysis tree found")
            return False
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_clustering_benchmark(llm_model: str = "gpt-4o-mini", debug_turns: int = 10, max_debug_trials: int = 3):
    """Run clustering benchmark with configurable LLM model and debug parameters.
    
    Args:
        llm_model: The LLM model to use (default: gpt-4o-mini)
        debug_turns: Number of debug turns per bug fixer session (default: 10)
        max_debug_trials: Maximum number of bug fixer sessions per node (default: 3)
    """
    
    user_request = """
    Perform comprehensive single-cell clustering analysis using multiple methods:
    
    1. **Data Preprocessing**:
       - Load and preprocess the zebrafish dataset
       - Perform quality control (filter cells and genes)
       - Normalize and log-transform the data
       - Identify highly variable genes
       - Scale the data
    
    2. **Dimensionality Reduction**:
       - Perform PCA (Principal Component Analysis)
       - Generate UMAP embedding for visualization
       - Generate t-SNE embedding for comparison
    
    3. **Multiple Clustering Methods**:
       **Leiden Clustering**:
       - Apply Leiden algorithm with multiple resolutions (0.5, 1.0, 1.5)
       - Store results in adata.obs['leiden_res_0.5'], etc.
       
       **Louvain Clustering**:
       - Apply Louvain algorithm with multiple resolutions
       - Store results in adata.obs['louvain_res_0.5'], etc.
       
       **K-means Clustering**:
       - Apply k-means with different k values (5, 10, 15, 20)
       - Store results in adata.obs['kmeans_k5'], etc.
       
       **Hierarchical Clustering**:
       - Perform hierarchical clustering on PC space
       - Cut dendrogram at different heights
       - Store results in adata.obs['hierarchical_h1'], etc.
    
    4. **Cluster Evaluation**:
       - Calculate silhouette scores for each clustering
       - Compute ARI between different clustering methods
       - Calculate modularity scores
       - Store metrics in adata.uns['clustering_metrics']
    
    5. **Visualization**:
       - Generate UMAP plots colored by each clustering method
       - Create comparison plots showing clustering concordance
       - Generate cluster quality heatmaps
       - Save all plots in organized subdirectories
    
    6. **Cluster Characterization**:
       - Find marker genes for each cluster (using rank_genes_groups)
       - Generate dotplots and heatmaps of top markers
       - Export marker gene lists as CSV files
    """
    
    # Input data path
    input_data = TEST_DATA_DIR / "zebrafish.h5ad"
    
    # Output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("test_outputs") / f"clustering_benchmark_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*80}")
    print("CLUSTERING BENCHMARK")
    print(f"{'='*80}")
    print(f"Input data: {input_data}")
    print(f"Output directory: {output_dir}")
    print(f"Started at: {datetime.now()}")
    print(f"LLM Model: {llm_model}")
    print(f"Bug fixer turns per session: {debug_turns}")
    print(f"Max bug fixer sessions per node: {max_debug_trials}")
    print(f"Max nodes: 15")
    print(f"Web agent: DISABLED")
    print(f"{'='*80}\n")
    
    # Log LLM configuration
    logger.info(f"Initializing MainAgent with LLM model: {llm_model}")
    logger.info(f"Bug fixer will use {debug_turns} debug turns per session")
    logger.info(f"Max debug sessions per node: {max_debug_trials}")
    
    try:
        # Initialize the main agent
        agent = MainAgent(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            bug_fixer_type="unified",
            bug_fixer_model=llm_model,
            llm_model=llm_model,
            enable_interactive_debug=True,
            enable_web_agent=False,
            log_llm_to_stdout=False,
            enable_domain_knowledge=True,
            domain_knowledge_domains=["single_cell_genomics", "cell_type_annotation"],
            bug_fixer_max_turns=debug_turns
        )
        
        # Run the analysis
        result = agent.run_analysis(
            input_data_path=str(input_data),
            user_request=user_request,
            output_dir=str(output_dir),
            max_nodes=15,
            max_debug_trials=max_debug_trials,
            max_iterations=20
        )
        
        print(f"\n{'='*80}")
        print("CLUSTERING ANALYSIS COMPLETE - EVALUATING RESULTS")
        print(f"{'='*80}\n")
        
        # Analyze results
        tree_id = result.get('tree_id')
        if not tree_id:
            print(f"❌ ERROR: Analysis failed - no tree_id in result")
            return False
            
        tree_file = output_dir / tree_id / "analysis_tree.json"
        if tree_file.exists():
            with open(tree_file, 'r') as f:
                tree_data = json.load(f)
            
            # Analyze node statistics including job review status
            stats = analyze_node_statistics(tree_data)
            print_node_statistics(stats)
            
            # Extract values for later use
            total_nodes = stats['total_nodes']
            completed_nodes = stats['execution']['completed']
            failed_nodes = stats['execution']['failed']
            
            # Check for clustering-specific nodes
            clustering_keywords = ['leiden', 'louvain', 'kmeans', 'hierarchical', 'cluster']
            clustering_nodes = []
            
            for node_id, node in tree_data['nodes'].items():
                node_name = node['function_block']['name'].lower()
                if any(keyword in node_name for keyword in clustering_keywords):
                    clustering_nodes.append({
                        'name': node['function_block']['name'],
                        'state': node['state'],
                        'debug_attempts': node.get('debug_attempts', 0)
                    })
            
            print(f"\nClustering Method Analysis:")
            print(f"  Clustering nodes found: {len(clustering_nodes)}")
            for node in clustering_nodes:
                status = "✅" if node['state'] == 'completed' else "❌"
                print(f"  {status} {node['name']} (debug attempts: {node['debug_attempts']})")
            
            # Success criteria
            success = (
                completed_nodes >= 8 and
                len(clustering_nodes) >= 2 and
                failed_nodes <= 5
            )
            
            print(f"\n{'='*80}")
            print("CLUSTERING BENCHMARK EVALUATION:")
            print(f"{'='*80}")
            
            if success:
                print("🎉 CLUSTERING BENCHMARK PASSED")
            else:
                print("⚠️ CLUSTERING BENCHMARK NEEDS IMPROVEMENT")
            
            return success
            
        else:
            print("❌ No analysis tree found")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_cell_type_annotation_general_benchmark(llm_model: str = "gpt-4o-mini", debug_turns: int = 10, max_debug_trials: int = 3):
    """Run general cell type annotation benchmark with configurable LLM model and debug parameters.
    
    Args:
        llm_model: The LLM model to use (default: gpt-4o-mini)
        debug_turns: Number of debug turns per bug fixer session (default: 10)
        max_debug_trials: Maximum number of bug fixer sessions per node (default: 3)
    """
    
    user_request = """
    Perform comprehensive single-cell type annotation using Python-based methods:
    
    IMPORTANT: First, research and identify all available Python packages for cell type annotation.
    Common methods include but are not limited to: CellTypist, scType, CellAssign, SingleCellNet,
    SCINA, Garnett (Python wrapper), scPred, CHETAH, scmap, and others.
    
    1. **Method Discovery Phase**:
       - Search for and list all available Python packages for cell type annotation
       - Identify which methods work without reference data (unsupervised)
       - Identify which methods require reference datasets
       - Document installation requirements for each method
    
    2. **Data Preprocessing**:
       - Load the annotation benchmark dataset
       - Check if data is already normalized/scaled
       - Compute necessary embeddings (PCA, UMAP) if not present
       - Perform clustering if needed for some methods
    
    3. **Reference-free Methods** (prioritize these):
       - Marker-based scoring approaches
       - Unsupervised clustering with marker enrichment
       - Methods that use built-in marker databases
       
    4. **Reference-based Methods** (if references available):
       - Methods requiring external reference datasets
       - Transfer learning approaches
       - Supervised classification methods
    
    5. **For Each Available Method**:
       - Install required packages
       - Apply the method with appropriate parameters
       - Store results in adata.obs[f'{method_name}_celltype']
       - Record confidence scores if available
       - Handle errors gracefully if method fails
    
    6. **Annotation Evaluation**:
       - Compare annotations across all successful methods
       - Calculate concordance metrics between methods
       - Identify consensus cell types
       - Store comparison metrics in adata.uns['annotation_comparison']
    
    7. **Visualization & Export**:
       - UMAP plots colored by each annotation method
       - Comparison heatmaps showing method agreement
       - Export comprehensive annotation table with all methods
       - Generate method comparison report
    
    Note: Focus on Python methods only for this benchmark. Prioritize methods that
    can work with the available data without requiring external references.
    """
    
    # Input data path - use the specified annotation benchmark dataset
    input_data = TEST_DATA_DIR / "annotation-benchmark-task2-Liu.h5ad"
    
    # Output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("test_outputs") / f"cell_type_annotation_benchmark_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*80}")
    print("CELL TYPE ANNOTATION BENCHMARK")
    print(f"{'='*80}")
    print(f"Input data: {input_data}")
    print(f"Output directory: {output_dir}")
    print(f"Started at: {datetime.now()}")
    print(f"LLM Model: {llm_model}")
    print(f"Bug fixer turns per session: {debug_turns}")
    print(f"Max bug fixer sessions per node: {max_debug_trials}")
    print(f"Max nodes: 15")
    print(f"Web agent: DISABLED")
    print(f"{'='*80}\n")
    
    # Log LLM configuration
    logger.info(f"Initializing MainAgent with LLM model: {llm_model}")
    logger.info(f"Bug fixer will use {debug_turns} debug turns per session")
    logger.info(f"Max debug sessions per node: {max_debug_trials}")
    
    try:
        # Initialize the main agent
        agent = MainAgent(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            bug_fixer_type="unified",
            bug_fixer_model=llm_model,
            llm_model=llm_model,
            enable_interactive_debug=True,
            enable_web_agent=False,
            log_llm_to_stdout=False,
            enable_domain_knowledge=True,
            domain_knowledge_domains=["single_cell_genomics", "cell_type_annotation"],
            bug_fixer_max_turns=debug_turns
        )
        
        # Run the analysis
        result = agent.run_analysis(
            input_data_path=str(input_data),
            user_request=user_request,
            output_dir=str(output_dir),
            max_nodes=15,
            max_debug_trials=max_debug_trials,
            max_iterations=20
        )
        
        print(f"\n{'='*80}")
        print("CELL TYPE ANNOTATION ANALYSIS COMPLETE - EVALUATING RESULTS")
        print(f"{'='*80}\n")
        
        # Analyze results
        tree_id = result.get('tree_id')
        if not tree_id:
            print(f"❌ ERROR: Analysis failed - no tree_id in result")
            return False
            
        tree_file = output_dir / tree_id / "analysis_tree.json"
        if tree_file.exists():
            with open(tree_file, 'r') as f:
                tree_data = json.load(f)
            
            # Analyze node statistics including job review status  
            stats = analyze_node_statistics(tree_data)
            print_node_statistics(stats)
            
            # Extract values for later use
            total_nodes = stats['total_nodes']
            completed_nodes = stats['execution']['completed']
            failed_nodes = stats['execution']['failed']
            
            # Check for annotation-specific nodes
            annotation_keywords = ['singler', 'sctype', 'marker', 'annotation', 'celltype', 'cell_type', 'cellassign', 'scanvi']
            annotation_nodes = []
            
            for node_id, node in tree_data['nodes'].items():
                node_name = node['function_block']['name'].lower()
                if any(keyword in node_name for keyword in annotation_keywords):
                    annotation_nodes.append({
                        'name': node['function_block']['name'],
                        'state': node['state'],
                        'debug_attempts': node.get('debug_attempts', 0)
                    })
            
            print(f"\nAnnotation Method Analysis:")
            print(f"  Annotation nodes found: {len(annotation_nodes)}")
            for node in annotation_nodes:
                status = "✅" if node['state'] == 'completed' else "❌"
                print(f"  {status} {node['name']} (debug attempts: {node['debug_attempts']})")
            
            # Success criteria (more lenient due to method availability)
            success = (
                completed_nodes >= 6 and
                len(annotation_nodes) >= 1 and
                failed_nodes <= 7
            )
            
            print(f"\n{'='*80}")
            print("CELL TYPE ANNOTATION BENCHMARK EVALUATION:")
            print(f"{'='*80}")
            
            if success:
                print("🎉 CELL TYPE ANNOTATION BENCHMARK PASSED")
            else:
                print("⚠️ CELL TYPE ANNOTATION BENCHMARK NEEDS IMPROVEMENT")
            
            return success
            
        else:
            print("❌ No analysis tree found")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_analysis_benchmark(
    user_request: str,
    input_folder: str,
    llm_model: str = "gpt-4o-mini",
    debug_turns: int = 10,
    max_debug_trials: int = 3
):
    """Run a general analysis benchmark with custom user request and input folder.
    
    Args:
        user_request: The analysis request to execute
        input_folder: Path to folder containing input files
        llm_model: The LLM model to use (default: gpt-4o-mini)
        debug_turns: Number of debug turns per bug fixer session (default: 10)
        max_debug_trials: Maximum number of bug fixer sessions per node (default: 3)
    """
    
    # Validate input folder exists
    input_path = Path(input_folder)
    if not input_path.exists():
        print(f"\n❌ ERROR: Input folder not found: {input_folder}")
        return False
    
    if not input_path.is_dir():
        print(f"\n❌ ERROR: Input path is not a directory: {input_folder}")
        return False
    
    # List files in input folder
    input_files = list(input_path.glob("*"))
    if not input_files:
        print(f"\n❌ ERROR: No files found in input folder: {input_folder}")
        return False
    
    # Output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("test_outputs") / f"analysis_benchmark_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*80}")
    print("CUSTOM ANALYSIS BENCHMARK")
    print(f"{'='*80}")
    print(f"Input folder: {input_folder}")
    print(f"Files in input folder ({len(input_files)}):")
    for f in input_files[:10]:  # Show first 10 files
        if f.is_file():
            print(f"  - {f.name} ({f.stat().st_size:,} bytes)")
    if len(input_files) > 10:
        print(f"  ... and {len(input_files) - 10} more files")
    print(f"\nOutput directory: {output_dir}")
    print(f"Started at: {datetime.now()}")
    print(f"LLM Model: {llm_model}")
    print(f"Bug fixer turns per session: {debug_turns}")
    print(f"Max bug fixer sessions per node: {max_debug_trials}")
    print(f"\nUser Request:")
    print("-" * 40)
    # Handle Unicode encoding issues by replacing problematic characters
    try:
        print(user_request)
    except UnicodeEncodeError:
        # Clean the string of problematic Unicode characters
        clean_request = user_request.encode('utf-8', errors='replace').decode('utf-8')
        print(clean_request)
    print("-" * 40)
    print(f"{'='*80}\n")
    
    # Clean user request of any problematic Unicode characters
    user_request = user_request.encode('utf-8', errors='replace').decode('utf-8')
    
    # Log configuration
    logger.info(f"Initializing MainAgent for custom analysis")
    logger.info(f"Input folder: {input_folder}")
    logger.info(f"LLM model: {llm_model}")
    logger.info(f"Debug configuration: {debug_turns} turns, max {max_debug_trials} trials")
    
    try:
        # Initialize the main agent
        agent = MainAgent(
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            bug_fixer_type="unified",
            bug_fixer_model=llm_model,
            llm_model=llm_model,
            enable_interactive_debug=True,
            enable_web_agent=False,
            log_llm_to_stdout=False,
            enable_domain_knowledge=True,
            domain_knowledge_domains=["single_cell_genomics", "cell_type_annotation"],
            bug_fixer_max_turns=debug_turns
        )
        
        # Run the analysis with the input folder
        result = agent.run_analysis(
            input_data_path=str(input_folder),  # Pass the folder path
            user_request=user_request,
            output_dir=str(output_dir),
            max_nodes=15,
            max_debug_trials=max_debug_trials,
            max_iterations=20
        )
        
        print(f"\n{'='*80}")
        print("ANALYSIS COMPLETE - EVALUATING RESULTS")
        print(f"{'='*80}\n")
        
        # Analyze results
        tree_id = result.get('tree_id')
        if not tree_id:
            print(f"❌ ERROR: Analysis failed - no tree_id in result")
            return False
        
        tree_file = output_dir / tree_id / "analysis_tree.json"
        if tree_file.exists():
            with open(tree_file, 'r') as f:
                tree_data = json.load(f)
            
            # Analyze node statistics
            stats = analyze_node_statistics(tree_data)
            print_node_statistics(stats)
            
            # Extract values for evaluation
            total_nodes = stats['total_nodes']
            completed_nodes = stats['execution']['completed']
            failed_nodes = stats['execution']['failed']
            job_review_passed = stats['job_review']['passed']
            
            # Check for root node execution (should always pass for folder input)
            root_nodes = [n for n in tree_data['nodes'].values() 
                         if n['function_block']['name'] == 'load_input_data']
            root_success = len(root_nodes) > 0 and root_nodes[0]['state'] == 'completed'
            
            print(f"\nAnalysis Summary:")
            print(f"  Root node (data loading): {'✅ Success' if root_success else '❌ Failed'}")
            print(f"  Total nodes created: {total_nodes}")
            print(f"  Successful executions: {completed_nodes}")
            print(f"  Job review passed: {job_review_passed}")
            
            # Success criteria (lenient since user request is variable)
            success = (
                root_success and  # Root node must succeed for folder input
                completed_nodes >= 3 and  # At least some analysis happened
                total_nodes <= 15  # Stayed within node limit
            )
            
            print(f"\n{'='*80}")
            print("ANALYSIS BENCHMARK EVALUATION:")
            print(f"{'='*80}")
            
            if success:
                print("🎉 ANALYSIS BENCHMARK PASSED")
                print(f"Successfully processed input folder with {len(input_files)} files")
                print(f"Completed {completed_nodes} analysis nodes")
                if job_review_passed > 0:
                    print(f"✅ {job_review_passed} nodes passed quality review")
            else:
                print("⚠️ ANALYSIS BENCHMARK NEEDS IMPROVEMENT")
                if not root_success:
                    print("  ❌ Failed to load input data from folder")
                if completed_nodes < 3:
                    print(f"  ❌ Too few completed nodes ({completed_nodes} < 3)")
            
            return success
            
        else:
            print("❌ No analysis tree found")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_cell_type_annotation_benchmark(llm_model: str = "gpt-4o-mini", debug_turns: int = 10, max_debug_trials: int = 3):
    """Run specific cell type annotation benchmark using CellTypist and other Python-based methods.
    
    Args:
        llm_model: The LLM model to use (default: gpt-4o-mini)
        debug_turns: Number of debug turns per bug fixer session (default: 10)
        max_debug_trials: Maximum number of bug fixer sessions per node (default: 3)
    """
    
    # TODO: add scType (R) later when R fb is tested thoroughly.
    user_request = """
    Perform cell type annotation on PBMC3K dataset using specific Python-based annotation methods.
    
    Please implement the following workflow with these EXACT steps:
    
    1. **Data Preprocessing** (Essential foundation):
       - Load the PBMC3K raw data
       - Filter cells: Keep cells with 200-2500 genes
       - Filter genes: Keep genes expressed in at least 3 cells
       - Calculate mitochondrial gene percentage and filter cells with <5% mitochondrial genes
       - Normalize data using scanpy.pp.normalize_total with target_sum=1e4
       - Log transform the data using scanpy.pp.log1p
       - Find highly variable genes using scanpy.pp.highly_variable_genes
       - Keep only highly variable genes for downstream analysis
       - Scale the data using scanpy.pp.scale with max_value=10
    
    2. **Dimensionality Reduction** (Required for visualization):
       - Compute PCA with 50 components using scanpy.tl.pca
       - Compute neighborhood graph using scanpy.pp.neighbors with n_neighbors=10
       - Compute UMAP embedding using scanpy.tl.umap
       - Perform Leiden clustering using scanpy.tl.leiden
    
    3. **CellTypist Annotation**:
       - Install CellTypist package (pip install celltypist)
       - Import celltypist
       - Download and use the 'Immune_All_Low.pkl' model
       - Run CellTypist prediction on the preprocessed data
       - Store predictions in adata.obs['celltypist_cell_type']
       - Store confidence scores in adata.obs['celltypist_confidence']
       - Generate UMAP visualization colored by CellTypist predictions
    
    4. **Marker-based Annotation** (Manual approach):
       - Define PBMC marker genes:
         * CD14+ Monocytes: ['CD14', 'LYZ']
         * FCGR3A+ Monocytes: ['FCGR3A', 'MS4A7']
         * Dendritic Cells: ['FCER1A', 'CST3']
         * B cells: ['MS4A1', 'CD79A']
         * CD4 T cells: ['IL7R', 'CD4']
         * CD8 T cells: ['CD8A', 'CD8B']
         * NK cells: ['GNLY', 'NKG7']
         * Megakaryocytes: ['PPBP']
       - Calculate expression scores for each marker set
       - Assign cell types based on highest marker expression
       - Store in adata.obs['marker_cell_type']
    
    6. **Comparison and Consensus**:
       - Create comparison matrix of all annotation methods
       - Calculate agreement scores between methods
       - Generate consensus annotation using majority vote
       - Store consensus in adata.obs['consensus_cell_type']
       - Create confusion matrices comparing methods
    
    7. **Visualization and Export**:
       - Generate UMAP plots for each annotation method
       - Create a summary plot comparing all methods side by side
       - Export annotated dataset with all annotations
       - Generate annotation summary statistics
       - Save all plots to output directory
    
    IMPORTANT: Each step should be a separate node in the analysis tree. Focus on implementing
    the methods that work reliably in Python (CellTypist and marker-based). Handle package
    installation failures gracefully.
    """
    
    # Input data path - use pbmc3k_raw.h5ad as specified
    input_data = TEST_DATA_DIR / "pbmc3k_raw.h5ad"
    
    # Output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("test_outputs") / f"cell_type_annotation_benchmark_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*80}")
    print("CELL TYPE ANNOTATION BENCHMARK (SPECIFIC METHODS)")
    print(f"{'='*80}")
    print(f"LLM Model: {llm_model}")
    print(f"Debug Turns: {debug_turns}")
    print(f"Max Debug Trials: {max_debug_trials}")
    print(f"Input data: {input_data}")
    print(f"Output directory: {output_dir}")
    print(f"Timestamp: {timestamp}")
    
    # Check if input data exists
    if not input_data.exists():
        print(f"\nERROR: Input data not found at {input_data}")
        return False
    
    try:
        # Initialize the main agent
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            print("\nERROR: OPENAI_API_KEY environment variable not set")
            return False
        
        agent = MainAgent(
            openai_api_key=api_key,
            bug_fixer_type="unified",
            bug_fixer_model=llm_model,
            llm_model=llm_model,
            enable_interactive_debug=True,
            enable_web_agent=False,
            log_llm_to_stdout=False,
            enable_domain_knowledge=True,
            domain_knowledge_domains=["single_cell_genomics", "cell_type_annotation"],
            bug_fixer_max_turns=debug_turns
        )
        
        # Run the analysis
        result = agent.run_analysis(
            input_data_path=str(input_data),
            user_request=user_request,
            output_dir=str(output_dir),
            max_iterations=25,
            max_debug_trials=max_debug_trials,
            max_nodes=20
        )
        
        # Analyze results
        print(f"\n{'='*80}")
        print("BENCHMARK RESULTS:")
        print(f"{'='*80}")
        
        tree_id = result.get('tree_id')
        if not tree_id:
            print(f"❌ ERROR: Analysis failed - no tree_id in result")
            print(f"Result: {result}")
            return False
            
        tree_dir = output_dir / tree_id
        
        # Check if tree was created
        if not tree_dir.exists():
            print("ERROR: Analysis tree directory not found")
            return False
        
        # Load and analyze the tree data
        tree_json_path = tree_dir / "analysis_tree.json"
        if tree_json_path.exists():
            with open(tree_json_path, 'r') as f:
                tree_data = json.load(f)
            
            # Print node statistics
            stats = analyze_node_statistics(tree_data)
            print("\nNode Statistics:")
            print(f"  Total nodes: {stats['total_nodes']}")
            print(f"  Completed: {stats['execution']['completed']}")
            print(f"  Failed: {stats['execution']['failed']}")
            print(f"  Job review passed: {stats['job_review']['passed']}")
            print(f"  Job review failed: {stats['job_review']['failed']}")
            
            # Extract values for later use
            total_nodes = stats['total_nodes']
            completed_nodes = stats['execution']['completed']
            failed_nodes = stats['execution']['failed']
            
            # Check for annotation-specific nodes
            annotation_keywords = ['celltypist', 'marker', 'annotation', 'celltype', 'cell_type', 
                                 'sctype', 'consensus', 'comparison', 'preprocessing', 'pca', 'umap']
            annotation_nodes = []
            
            for node_id, node in tree_data['nodes'].items():
                node_name = node['function_block']['name'].lower()
                if any(keyword in node_name for keyword in annotation_keywords):
                    annotation_nodes.append({
                        'name': node['function_block']['name'],
                        'state': node['state'],
                        'debug_attempts': node.get('debug_attempts', 0)
                    })
            
            print(f"\nAnnotation Method Analysis:")
            print(f"  Annotation-related nodes found: {len(annotation_nodes)}")
            for node in annotation_nodes:
                status = "✅" if node['state'] == 'completed' else "❌"
                print(f"  {status} {node['name']} (debug attempts: {node['debug_attempts']})")
            
            # Success criteria
            success = (
                completed_nodes >= 10 and  # At least 10 nodes completed (preprocessing + methods)
                len(annotation_nodes) >= 5 and  # At least 5 annotation-related nodes
                failed_nodes <= 5  # Allow some failures
            )
            
            print(f"\n{'='*80}")
            print("CELL TYPE ANNOTATION BENCHMARK EVALUATION:")
            print(f"  Completed nodes: {completed_nodes}/20 target")
            print(f"  Annotation nodes: {len(annotation_nodes)}/5 minimum")
            print(f"  Failed nodes: {failed_nodes}/5 maximum allowed")
            print(f"  Overall: {'✅ PASSED' if success else '❌ FAILED'}")
            print(f"{'='*80}\n")
            
            return success
        else:
            print("ERROR: analysis_tree.json not found")
            return False
            
    except Exception as e:
        print(f"\nERROR during benchmark execution: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run single-cell genomics benchmarks with configurable parameters")
    parser.add_argument(
        "--benchmark-type",
        type=str,
        choices=["pseudotime", "clustering", "annotation", "annotation-general", "analysis"],
        default="pseudotime",
        dest="benchmark_type",
        help="Type of benchmark to run (default: pseudotime)"
    )
    parser.add_argument(
        "--llm-model", 
        type=str, 
        default="gpt-4o-mini",
        dest="llm_model",
        help="LLM model to use (default: gpt-4o-mini)"
    )
    parser.add_argument(
        "--debug-turns", 
        type=int, 
        default=10,
        dest="debug_turns",
        help="Number of debug turns per bug fixer session (default: 10)"
    )
    parser.add_argument(
        "--max-debug-trials", 
        type=int, 
        default=3,
        dest="max_debug_trials",
        help="Maximum number of bug fixer sessions per node (default: 3)"
    )
    
    # Arguments specific to 'analysis' benchmark type
    parser.add_argument(
        "--analysis-user-req",
        type=str,
        dest="analysis_user_req",
        help="User request for analysis benchmark (required when benchmark-type=analysis)"
    )
    parser.add_argument(
        "--input-folder",
        type=str,
        dest="input_folder",
        help="Input folder path for analysis benchmark (required when benchmark-type=analysis)"
    )
    
    args = parser.parse_args()
    
    # Validate parameters
    if args.debug_turns < 1:
        print("Error: debug-turns must be at least 1")
        sys.exit(1)
    if args.max_debug_trials < 1:
        print("Error: max-debug-trials must be at least 1")
        sys.exit(1)
    
    # Validate analysis-specific arguments
    if args.benchmark_type == "analysis":
        if not args.analysis_user_req:
            print("Error: --analysis-user-req is required when benchmark-type=analysis")
            sys.exit(1)
        if not args.input_folder:
            print("Error: --input-folder is required when benchmark-type=analysis")
            sys.exit(1)
    
    # Log the configuration
    logger.info(f"Starting {args.benchmark_type} benchmark with:")
    logger.info(f"  - Benchmark Type: {args.benchmark_type}")
    logger.info(f"  - LLM Model: {args.llm_model}")
    logger.info(f"  - Debug Turns per session: {args.debug_turns}")
    logger.info(f"  - Max Debug Sessions per node: {args.max_debug_trials}")
    if args.benchmark_type == "analysis":
        logger.info(f"  - Input Folder: {args.input_folder}")
        logger.info(f"  - User Request: {args.analysis_user_req[:100]}...")  # Log first 100 chars
    
    # Run the appropriate benchmark
    if args.benchmark_type == "pseudotime":
        success = run_pseudotime_benchmark(
            llm_model=args.llm_model, 
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials
        )
        benchmark_name = "PSEUDOTIME"
    elif args.benchmark_type == "clustering":
        success = run_clustering_benchmark(
            llm_model=args.llm_model, 
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials
        )
        benchmark_name = "CLUSTERING"
    elif args.benchmark_type == "annotation-general":
        success = run_cell_type_annotation_general_benchmark(
            llm_model=args.llm_model, 
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials
        )
        benchmark_name = "CELL TYPE ANNOTATION (GENERAL)"
    elif args.benchmark_type == "annotation":
        success = run_cell_type_annotation_benchmark(
            llm_model=args.llm_model, 
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials
        )
        benchmark_name = "CELL TYPE ANNOTATION"
    elif args.benchmark_type == "analysis":
        success = run_analysis_benchmark(
            user_request=args.analysis_user_req,
            input_folder=args.input_folder,
            llm_model=args.llm_model,
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials
        )
        benchmark_name = "CUSTOM ANALYSIS"
    else:
        print(f"Error: Unknown benchmark type: {args.benchmark_type}")
        sys.exit(1)
    
    print(f"\n{'='*80}")
    if success:
        print(f"🎉 {benchmark_name} BENCHMARK COMPLETED SUCCESSFULLY")
        print(f"The enhanced bug fixer with {args.debug_turns} turns per session")
        print(f"and up to {args.max_debug_trials} sessions per node")
        print(f"completed the {args.benchmark_type} run (execution completion, not an accuracy assessment)")
        print(f"LLM Model used: {args.llm_model}")
    else:
        print(f"⚠️ {benchmark_name} BENCHMARK NEEDS WORK")
        print("Consider investigating specific failure modes.")
        print(f"Configuration: {args.llm_model} model")
        print(f"Debug settings: {args.debug_turns} turns per session, max {args.max_debug_trials} sessions per node")
        print("Note: Web agent was disabled.")
    print(f"{'='*80}")
    sys.exit(0 if success else 1)