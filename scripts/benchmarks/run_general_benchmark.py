#!/usr/bin/env python3
"""General single-cell genomics benchmarks with configurable LLM models and debug parameters."""

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


def print_output_tree(tree_dir: Path, max_depth: int = 3, current_depth: int = 0, prefix: str = ""):
    """Print directory tree structure of outputs.
    
    Args:
        tree_dir: Directory to visualize
        max_depth: Maximum depth to traverse
        current_depth: Current recursion depth
        prefix: Prefix for tree visualization
    """
    if current_depth > max_depth or not tree_dir.exists():
        return
    
    # Get items in directory
    try:
        items = sorted(tree_dir.iterdir(), key=lambda x: (x.is_file(), x.name))
    except PermissionError:
        return
    
    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        current_prefix = "└── " if is_last else "├── "
        next_prefix = "    " if is_last else "│   "
        
        # Format the name with file size if it's a file
        if item.is_file():
            size = item.stat().st_size
            if size > 1024 * 1024:  # MB
                size_str = f" ({size / (1024 * 1024):.1f} MB)"
            elif size > 1024:  # KB
                size_str = f" ({size / 1024:.1f} KB)"
            else:
                size_str = f" ({size} bytes)"
            
            # Highlight important files
            if item.suffix == '.h5ad':
                display_name = f"📊 {item.name}{size_str}"
            elif item.suffix in ['.png', '.pdf', '.jpg']:
                display_name = f"📈 {item.name}{size_str}"
            elif item.suffix in ['.csv', '.tsv', '.txt']:
                display_name = f"📄 {item.name}{size_str}"
            elif item.suffix == '.json':
                display_name = f"🔧 {item.name}{size_str}"
            else:
                display_name = f"{item.name}{size_str}"
        else:
            # Directory
            display_name = f"📁 {item.name}/"
        
        print(f"{prefix}{current_prefix}{display_name}")
        
        # Recurse for directories
        if item.is_dir() and current_depth < max_depth:
            print_output_tree(item, max_depth, current_depth + 1, prefix + next_prefix)


def print_detailed_node_report(tree_data: dict, output_dir: Path):
    """Print detailed report for all nodes without hardcoded filters.
    
    Args:
        tree_data: The analysis tree data
        output_dir: Base output directory
    """
    print(f"\n{'='*60}")
    print("NODE EXECUTION DETAILS")
    print(f"{'='*60}")
    
    # Get tree ID from the data
    tree_id = tree_data.get('id', 'unknown')
    tree_dir = output_dir / tree_id if tree_id != 'unknown' else output_dir
    
    # Sort nodes by level (execution order) and then by name
    sorted_nodes = sorted(
        tree_data['nodes'].items(),
        key=lambda x: (x[1].get('level', 999), x[1]['function_block']['name'])
    )
    
    for idx, (node_id, node) in enumerate(sorted_nodes, 1):
        # Basic info
        fb = node['function_block']
        node_name = fb['name']
        state = node.get('state', 'pending')
        review_status = node.get('job_review_status', 'not_reviewed')
        debug_attempts = node.get('debug_attempts', 0)
        
        # Status icons
        exec_icon = {
            'completed': '✅',
            'failed': '❌',
            'pending': '⏳',
            'running': '🔄'
        }.get(state, '❓')
        
        review_icon = {
            'passed': '✅',
            'failed': '❌',
            'not_reviewed': '❓',
            'skipped': '⏭️'
        }.get(review_status, '❓')
        
        # Print node header
        print(f"\n{idx}. {node_name} (node_{node_id[:8]}...)")
        print(f"   Status: {exec_icon} {state.capitalize()} | Review: {review_icon} {review_status.replace('_', ' ').capitalize()}")
        
        # Add description if available
        if fb.get('description'):
            print(f"   Description: {fb['description'][:100]}...")
        
        # Debug info
        if debug_attempts > 0:
            print(f"   Debug: {debug_attempts} attempt{'s' if debug_attempts > 1 else ''}")
        
        # Check for outputs
        node_dir = tree_dir / "nodes" / f"node_{node_id}"
        outputs_dir = node_dir / "outputs"
        
        if outputs_dir.exists():
            try:
                output_files = list(outputs_dir.rglob("*"))
                if output_files:
                    # Categorize outputs
                    h5ad_files = [f for f in output_files if f.suffix == '.h5ad']
                    figure_files = [f for f in output_files if f.suffix in ['.png', '.pdf', '.jpg', '.svg']]
                    data_files = [f for f in output_files if f.suffix in ['.csv', '.tsv', '.txt']]
                    
                    print(f"   Outputs:")
                    if h5ad_files:
                        for f in h5ad_files[:3]:  # Show first 3
                            size_mb = f.stat().st_size / (1024 * 1024)
                            print(f"     📊 {f.name} ({size_mb:.1f} MB)")
                        if len(h5ad_files) > 3:
                            print(f"     ... and {len(h5ad_files) - 3} more h5ad files")
                    
                    if figure_files:
                        print(f"     📈 {len(figure_files)} figure{'s' if len(figure_files) > 1 else ''}")
                    
                    if data_files:
                        print(f"     📄 {len(data_files)} data file{'s' if len(data_files) > 1 else ''}")
                else:
                    print(f"   Outputs: None")
            except Exception as e:
                print(f"   Outputs: Error reading ({e})")
        elif state == 'completed':
            print(f"   Outputs: Directory not found")
        
        # Add error info if failed
        if state == 'failed' and node.get('error'):
            error_msg = str(node['error'])[:100]
            print(f"   Error: {error_msg}...")
    
    print(f"\n{'='*60}\n")


def analyze_output_quality(tree_data: dict, output_dir: Path) -> dict:
    """Analyze the quality and types of outputs produced.
    
    Args:
        tree_data: The analysis tree data
        output_dir: Base output directory
        
    Returns:
        Dictionary with output quality metrics
    """
    tree_id = tree_data.get('id', 'unknown')
    tree_dir = output_dir / tree_id if tree_id != 'unknown' else output_dir
    
    quality = {
        'total_output_files': 0,
        'h5ad_files': [],
        'figure_files': [],
        'data_files': [],
        'nodes_with_outputs': 0,
        'total_output_size_mb': 0,
        'output_by_node': {}
    }
    
    for node_id, node in tree_data['nodes'].items():
        node_name = node['function_block']['name']
        outputs_dir = tree_dir / "nodes" / f"node_{node_id}" / "outputs"
        
        if outputs_dir.exists():
            try:
                output_files = list(outputs_dir.rglob("*"))
                if output_files:
                    quality['nodes_with_outputs'] += 1
                    node_outputs = {
                        'h5ad': [],
                        'figures': [],
                        'data': [],
                        'other': []
                    }
                    
                    for f in output_files:
                        if f.is_file():
                            quality['total_output_files'] += 1
                            size_mb = f.stat().st_size / (1024 * 1024)
                            quality['total_output_size_mb'] += size_mb
                            
                            if f.suffix == '.h5ad':
                                quality['h5ad_files'].append(f.name)
                                node_outputs['h5ad'].append(f.name)
                            elif f.suffix in ['.png', '.pdf', '.jpg', '.svg']:
                                quality['figure_files'].append(f.name)
                                node_outputs['figures'].append(f.name)
                            elif f.suffix in ['.csv', '.tsv', '.txt']:
                                quality['data_files'].append(f.name)
                                node_outputs['data'].append(f.name)
                            else:
                                node_outputs['other'].append(f.name)
                    
                    quality['output_by_node'][node_name] = node_outputs
            except Exception:
                pass
    
    return quality


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


def run_pseudotime_benchmark(llm_model: str = "gpt-4o-mini", debug_turns: int = 10, max_debug_trials: int = 3, 
                            enable_domain_knowledge: bool = True, seed: int = 31, output_suffix: str = None,
                            output_base_dir: str = "test_outputs", enable_web_agent: bool = False, max_nodes: int = None,
                            docker_execution_timeout: int = None, max_iterations: int = None):
    """Run pseudotime benchmark with configurable LLM model and debug parameters.
    
    Args:
        llm_model: The LLM model to use (default: gpt-4o-mini)
        debug_turns: Number of debug turns per bug fixer session (default: 10)
        max_debug_trials: Maximum number of bug fixer sessions per node (default: 3)
        enable_domain_knowledge: Whether to enable domain knowledge (default: True)
        output_suffix: Optional suffix for output directory to ensure uniqueness in parallel runs
        seed: Random seed for reproducibility (default: 31)
        output_base_dir: Base directory for outputs (default: test_outputs)
        enable_web_agent: Enable web agent for online research (default: False)
        max_nodes: Maximum number of nodes in the analysis tree (default: None)
        docker_execution_timeout: Docker execution timeout in seconds (default: None)
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
    trajectory inference packages. The enhanced bug fixer with web research should help 
    resolve any method-specific errors.
    """
    
    # Input data path
    input_data = Path(__file__).parent.parent.parent / "test_data" / "zebrafish.h5ad"
    
    # Output directory with unique suffix to prevent collisions in parallel runs
    import uuid
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Build suffix components
    suffix_parts = []
    if output_suffix:
        suffix_parts.append(output_suffix)
    if enable_web_agent:
        suffix_parts.append("webAgent")
    
    # Check if output_base_dir already contains the benchmark type to avoid duplication
    base_dir_path = Path(output_base_dir)
    if base_dir_path.name == "pseudotime":
        # Already in a pseudotime subdirectory, don't add another prefix
        if suffix_parts:
            output_dir = base_dir_path / f"{timestamp}_{'_'.join(suffix_parts)}"
        else:
            # Generate a unique ID if no suffix provided
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"{timestamp}_{unique_id}"
    else:
        # Not in a subdirectory, use the old behavior with prefix
        if suffix_parts:
            output_dir = base_dir_path / f"pseudotime_{timestamp}_{'_'.join(suffix_parts)}"
        else:
            # Generate a unique ID if no suffix provided
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"pseudotime_{timestamp}_{unique_id}"
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
    print(f"Max nodes: {max_nodes if max_nodes is not None else 15}")
    print(f"Web agent: {'ENABLED' if enable_web_agent else 'DISABLED'}")
    print(f"{'='*80}\n")
    
    # Log LLM configuration
    logger.info(f"Initializing MainAgent with LLM model: {llm_model}")
    logger.info(f"Bug fixer will use {debug_turns} debug turns per session")
    logger.info(f"Max debug sessions per node: {max_debug_trials}")
    
    try:
        # Determine which API key to use based on model name
        openai_api_key = None
        claude_api_key = None
        
        if llm_model.startswith('claude'):
            claude_api_key = os.getenv("CLAUDE_API_KEY")
            if not claude_api_key:
                raise ValueError(f"CLAUDE_API_KEY environment variable required for model {llm_model}")
            logger.info(f"Using Claude API for model {llm_model}")
        else:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                raise ValueError(f"OPENAI_API_KEY environment variable required for model {llm_model}")
            logger.info(f"Using OpenAI API for model {llm_model}")
        
        # Initialize the main agent for pseudotime analysis
        agent = MainAgent(
            openai_api_key=openai_api_key,
            claude_api_key=claude_api_key,
            bug_fixer_type="unified",
            bug_fixer_model=llm_model,  # Use the specified LLM model for bug fixer
            llm_model=llm_model,  # Use the specified LLM model for main agent
            enable_web_agent=enable_web_agent,  # Configurable web agent
            log_llm_to_stdout=False,  # Keep logs in agent subfolders, not stdout
            enable_domain_knowledge=enable_domain_knowledge,  # Configurable domain knowledge
            domain_knowledge_domains=["single_cell_genomics", "pseudotime_implementation", "function_block_faq"] if enable_domain_knowledge else None,  # Pseudotime-specific domains
            bug_fixer_max_turns=debug_turns,  # Pass the configurable debug turns
            llm_seed=seed,  # Pass the configurable seed
            docker_execution_timeout=docker_execution_timeout  # Pass the Docker execution timeout
        )
        
        logger.info(f"MainAgent initialized with:")
        logger.info(f"  - LLM model: {llm_model}")
        logger.info(f"  - Bug fixer model: {llm_model}")
        logger.info(f"  - Web agent enabled: {enable_web_agent}")
        logger.info(f"  - Bug fixer max turns per session: {debug_turns}")
        logger.info(f"  - Max debug sessions per node: {max_debug_trials}")
        
        print("Main agent initialized with requested configuration:")
        print(f"✅ LLM Model: {llm_model}")
        print(f"✅ Bug fixer turns per session: {debug_turns}")
        print(f"✅ Max bug fixer sessions per node: {max_debug_trials}")
        print(f"Web agent: {'ENABLED' if enable_web_agent else 'DISABLED'}")
        print(f"✅ Max nodes: {max_nodes if max_nodes is not None else 15} (configured via max_nodes)")
        print("")
        print("Configuration details:")
        print(f"  - LLM model: {llm_model} for all agents")
        print(f"  - Bug fixer: {debug_turns} turns per session, max {max_debug_trials} sessions per node")
        print(f"  - Total possible debugging: {debug_turns * max_debug_trials} actions per node")
        print(f"  - Max nodes: {max_nodes if max_nodes is not None else 15}")
        print(f"  - Web agent: {'enabled' if enable_web_agent else 'disabled'}")
        print(f"  - Domain knowledge: {'enabled' if enable_domain_knowledge else 'disabled'}")
        print("")
        
        # Run the analysis with requested parameters
        result = agent.run_analysis(
            input_data_path=str(input_data),
            user_request=user_request,
            output_dir=str(output_dir),
            max_nodes=max_nodes if max_nodes is not None else 15,  # Use override or default to 15
            max_debug_trials=max_debug_trials,  # Use the proper max_debug_trials parameter
            max_iterations=max_iterations if max_iterations is not None else 20  # Use provided or default
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
            
            # Use new general statistics functions
            stats = analyze_node_statistics(tree_data)
            print_node_statistics(stats)
            
            # Print detailed node report
            print_detailed_node_report(tree_data, output_dir)
            
            # Analyze output quality
            quality = analyze_output_quality(tree_data, output_dir)
            
            print(f"\n{'='*60}")
            print("OUTPUT QUALITY ANALYSIS")
            print(f"{'='*60}")
            print(f"Total output files: {quality['total_output_files']}")
            print(f"Total size: {quality['total_output_size_mb']:.1f} MB")
            print(f"Nodes with outputs: {quality['nodes_with_outputs']}/{stats['total_nodes']}")
            print(f"H5AD files: {len(quality['h5ad_files'])}")
            print(f"Figure files: {len(quality['figure_files'])}")
            print(f"Data files: {len(quality['data_files'])}")
            
            # Print directory tree
            print(f"\n{'='*60}")
            print("OUTPUT DIRECTORY STRUCTURE")
            print(f"{'='*60}")
            tree_dir = output_dir / tree_id
            print(f"📁 {tree_dir.name}/")
            print_output_tree(tree_dir, max_depth=3, current_depth=0, prefix="")
            
            # Extract values for evaluation
            completed_nodes = stats['execution']['completed']
            failed_nodes = stats['execution']['failed']
            total_nodes = stats['total_nodes']
            
            # Generic success criteria based on actual performance
            enhanced_success = (
                completed_nodes >= 10 and                      # Good completion rate
                quality['nodes_with_outputs'] >= 5 and         # Actual outputs produced
                len(quality['h5ad_files']) >= 2 and           # Data files generated
                stats['job_review']['passed'] >= 5 and        # Quality checks passed
                failed_nodes <= 5                             # Reasonable failure rate
            )
            
            print(f"\n{'='*80}")
            print("ENHANCED PSEUDOTIME BENCHMARK EVALUATION:")
            print(f"{'='*80}")
            
            if enhanced_success:
                print("🎉 ENHANCED PSEUDOTIME BENCHMARK PASSED")
                print("\nCapabilities demonstrated:")
                print(f"✅ Completed {completed_nodes} nodes successfully")
                print(f"✅ Generated {len(quality['h5ad_files'])} H5AD data files")
                print(f"✅ {quality['nodes_with_outputs']} nodes produced outputs")
                print(f"✅ {stats['job_review']['passed']} nodes passed quality review")
                print(f"✅ Bug fixer ({debug_turns} turns) handled errors effectively")
                print(f"✅ Total output size: {quality['total_output_size_mb']:.1f} MB")
            else:
                print("⚠️ ENHANCED BENCHMARK NEEDS IMPROVEMENT")
                improvement_areas = []
                if completed_nodes < 10:
                    improvement_areas.append(f"Overall completion rate below target ({completed_nodes} < 10 nodes)")
                if quality['nodes_with_outputs'] < 5:
                    improvement_areas.append(f"Too few nodes with outputs ({quality['nodes_with_outputs']} < 5)")
                if len(quality['h5ad_files']) < 2:
                    improvement_areas.append(f"Insufficient data files generated ({len(quality['h5ad_files'])} < 2)")
                if stats['job_review']['passed'] < 5:
                    improvement_areas.append(f"Too few quality reviews passed ({stats['job_review']['passed']} < 5)")
                if failed_nodes > 5:
                    improvement_areas.append(f"Too many failed nodes ({failed_nodes} > 5)")
                
                for area in improvement_areas:
                    print(f"  ❌ {area}")
            
            # Save comprehensive results
            enhanced_results = {
                "timestamp": timestamp,
                "benchmark_type": f"pseudotime_{llm_model}_{debug_turns}turns_{max_debug_trials}trials",
                "success": enhanced_success,
                "configuration": {
                    "llm_model": llm_model,
                    "bug_fixer_turns": debug_turns,
                    "max_debug_trials": max_debug_trials,
                    "web_agent_enabled": enable_web_agent,
                    "max_nodes": max_nodes if max_nodes is not None else 15,
                    "enable_domain_knowledge": enable_domain_knowledge,
                    "docker_execution_timeout": docker_execution_timeout
                },
                "note": "'success' reflects execution completion heuristics (node/file counts), not scientific accuracy",
                "node_statistics": stats,
                "output_quality": {
                    "total_files": quality['total_output_files'],
                    "total_size_mb": quality['total_output_size_mb'],
                    "nodes_with_outputs": quality['nodes_with_outputs'],
                    "h5ad_files": len(quality['h5ad_files']),
                    "figure_files": len(quality['figure_files']),
                    "data_files": len(quality['data_files']),
                    "output_by_node": quality['output_by_node']
                },
                "enhanced_features": [
                    f"Bug fixer with {debug_turns} turns per session",
                    f"Max {max_debug_trials} debug sessions per node",
                    f"Web agent {'enabled' if enable_web_agent else 'disabled'}",
                    f"Max nodes {max_nodes if max_nodes is not None else 15}"
                ]
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


def run_clustering_benchmark(llm_model: str = "gpt-4o-mini", debug_turns: int = 10, max_debug_trials: int = 3,
                            enable_domain_knowledge: bool = True, seed: int = 31, output_suffix: str = None,
                            output_base_dir: str = "test_outputs", enable_web_agent: bool = False, max_nodes: int = None,
                            docker_execution_timeout: int = 600, max_iterations: int = None):
    """Run clustering benchmark with configurable LLM model and debug parameters.
    
    Args:
        llm_model: The LLM model to use (default: gpt-4o-mini)
        debug_turns: Number of debug turns per bug fixer session (default: 10)
        max_debug_trials: Maximum number of bug fixer sessions per node (default: 3)
        enable_domain_knowledge: Whether to enable domain knowledge (default: True)
        seed: Random seed for reproducibility (default: 31)
        output_suffix: Optional suffix for output directory to ensure uniqueness in parallel runs
        output_base_dir: Base directory for outputs (default: test_outputs)
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
    input_data = Path(__file__).parent.parent.parent / "test_data" / "zebrafish.h5ad"
    
    # Output directory with unique suffix to prevent collisions in parallel runs
    import uuid
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Check if output_base_dir already contains the benchmark type to avoid duplication
    base_dir_path = Path(output_base_dir)
    if base_dir_path.name == "clustering":
        # Already in a clustering subdirectory, don't add another prefix
        if output_suffix:
            output_dir = base_dir_path / f"{timestamp}_{output_suffix}"
        else:
            # Generate a unique ID if no suffix provided
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"{timestamp}_{unique_id}"
    else:
        # Not in a subdirectory, use the old behavior with prefix
        if output_suffix:
            output_dir = base_dir_path / f"clustering_{timestamp}_{output_suffix}"
        else:
            # Generate a unique ID if no suffix provided
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"clustering_{timestamp}_{unique_id}"
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
    print(f"Max nodes: {max_nodes if max_nodes is not None else 15}")
    print(f"Web agent: {'ENABLED' if enable_web_agent else 'DISABLED'}")
    print(f"{'='*80}\n")
    
    # Log LLM configuration
    logger.info(f"Initializing MainAgent with LLM model: {llm_model}")
    logger.info(f"Bug fixer will use {debug_turns} debug turns per session")
    logger.info(f"Max debug sessions per node: {max_debug_trials}")
    
    try:
        # Determine which API key to use based on model name
        openai_api_key = None
        claude_api_key = None
        
        if llm_model.startswith('claude'):
            claude_api_key = os.getenv("CLAUDE_API_KEY")
            if not claude_api_key:
                raise ValueError(f"CLAUDE_API_KEY environment variable required for model {llm_model}")
            logger.info(f"Using Claude API for model {llm_model}")
        else:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                raise ValueError(f"OPENAI_API_KEY environment variable required for model {llm_model}")
            logger.info(f"Using OpenAI API for model {llm_model}")
        
        # Initialize the main agent for clustering analysis
        agent = MainAgent(
            openai_api_key=openai_api_key,
            claude_api_key=claude_api_key,
            bug_fixer_type="unified",
            bug_fixer_model=llm_model,
            llm_model=llm_model,
            enable_web_agent=enable_web_agent,
            log_llm_to_stdout=False,
            enable_domain_knowledge=enable_domain_knowledge,
            domain_knowledge_domains=["single_cell_genomics", "function_block_faq"] if enable_domain_knowledge else None,
            bug_fixer_max_turns=debug_turns,
            llm_seed=seed,
            docker_execution_timeout=docker_execution_timeout
        )
        
        # Run the analysis
        result = agent.run_analysis(
            input_data_path=str(input_data),
            user_request=user_request,
            output_dir=str(output_dir),
            max_nodes=max_nodes if max_nodes is not None else 15,
            max_debug_trials=max_debug_trials,
            max_iterations=max_iterations if max_iterations is not None else 20
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
            
            # Use new general statistics functions
            stats = analyze_node_statistics(tree_data)
            print_node_statistics(stats)
            
            # Print detailed node report
            print_detailed_node_report(tree_data, output_dir)
            
            # Analyze output quality
            quality = analyze_output_quality(tree_data, output_dir)
            
            print(f"\n{'='*60}")
            print("OUTPUT QUALITY ANALYSIS")
            print(f"{'='*60}")
            print(f"Total output files: {quality['total_output_files']}")
            print(f"Total size: {quality['total_output_size_mb']:.1f} MB")
            print(f"Nodes with outputs: {quality['nodes_with_outputs']}/{stats['total_nodes']}")
            print(f"H5AD files: {len(quality['h5ad_files'])}")
            print(f"Figure files: {len(quality['figure_files'])}")
            print(f"Data files: {len(quality['data_files'])}")
            
            # Print directory tree
            print(f"\n{'='*60}")
            print("OUTPUT DIRECTORY STRUCTURE")
            print(f"{'='*60}")
            tree_dir = output_dir / tree_id
            print(f"📁 {tree_dir.name}/")
            print_output_tree(tree_dir, max_depth=3, current_depth=0, prefix="")
            
            # Extract values for evaluation
            completed_nodes = stats['execution']['completed']
            failed_nodes = stats['execution']['failed']
            
            # Generic success criteria
            success = (
                completed_nodes >= 8 and
                quality['nodes_with_outputs'] >= 4 and
                len(quality['h5ad_files']) >= 1 and
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


def run_cell_type_annotation_general_benchmark(llm_model: str = "gpt-4o-mini", debug_turns: int = 10, max_debug_trials: int = 3,
                                               enable_domain_knowledge: bool = True, seed: int = 31, output_suffix: str = None,
                                               output_base_dir: str = "test_outputs", enable_web_agent: bool = False, max_nodes: int = None,
                                               max_iterations: int = None, docker_execution_timeout: int = None):
    """Run general cell type annotation benchmark with configurable LLM model and debug parameters.
    
    Args:
        llm_model: The LLM model to use (default: gpt-4o-mini)
        debug_turns: Number of debug turns per bug fixer session (default: 10)
        max_debug_trials: Maximum number of bug fixer sessions per node (default: 3)
        enable_domain_knowledge: Whether to enable domain knowledge (default: True)
        seed: Random seed for reproducibility (default: 31)
        output_base_dir: Base directory for outputs (default: test_outputs)
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
    input_data = Path(__file__).parent.parent.parent / "test_data" / "annotation-benchmark-task2-Liu.h5ad"
    
    # Output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Check if output_base_dir already contains the benchmark type to avoid duplication
    base_dir_path = Path(output_base_dir)
    if base_dir_path.name == "annotation":
        # Already in an annotation subdirectory, don't add another prefix
        if output_suffix:
            output_dir = base_dir_path / f"{timestamp}_{output_suffix}"
        else:
            # Generate a unique ID if no suffix provided
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"{timestamp}_{unique_id}"
    else:
        # Not in a subdirectory, use the old behavior with prefix
        if output_suffix:
            output_dir = base_dir_path / f"annotation_{timestamp}_{output_suffix}"
        else:
            # Generate a unique ID if no suffix provided
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"annotation_{timestamp}_{unique_id}"
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
    print(f"Max nodes: {max_nodes if max_nodes is not None else 15}")
    print(f"Web agent: {'ENABLED' if enable_web_agent else 'DISABLED'}")
    print(f"{'='*80}\n")
    
    # Log LLM configuration
    logger.info(f"Initializing MainAgent with LLM model: {llm_model}")
    logger.info(f"Bug fixer will use {debug_turns} debug turns per session")
    logger.info(f"Max debug sessions per node: {max_debug_trials}")
    
    try:
        # Determine which API key to use based on model name
        openai_api_key = None
        claude_api_key = None
        
        if llm_model.startswith('claude'):
            claude_api_key = os.getenv("CLAUDE_API_KEY")
            if not claude_api_key:
                raise ValueError(f"CLAUDE_API_KEY environment variable required for model {llm_model}")
            logger.info(f"Using Claude API for model {llm_model}")
        else:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                raise ValueError(f"OPENAI_API_KEY environment variable required for model {llm_model}")
            logger.info(f"Using OpenAI API for model {llm_model}")
        
        # Initialize the main agent
        agent = MainAgent(
            openai_api_key=openai_api_key,
            claude_api_key=claude_api_key,
            bug_fixer_type="unified",
            bug_fixer_model=llm_model,
            llm_model=llm_model,
            enable_web_agent=enable_web_agent,
            log_llm_to_stdout=False,
            enable_domain_knowledge=enable_domain_knowledge,
            domain_knowledge_domains=["single_cell_genomics", "cell_type_annotation"] if enable_domain_knowledge else None,
            bug_fixer_max_turns=debug_turns,
            llm_seed=seed,
            docker_execution_timeout=docker_execution_timeout
        )
        
        # Run the analysis
        result = agent.run_analysis(
            input_data_path=str(input_data),
            user_request=user_request,
            output_dir=str(output_dir),
            max_nodes=max_nodes if max_nodes is not None else 15,
            max_debug_trials=max_debug_trials,
            max_iterations=max_iterations if max_iterations is not None else 20
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
            
            # Use new general statistics functions  
            stats = analyze_node_statistics(tree_data)
            print_node_statistics(stats)
            
            # Print detailed node report
            print_detailed_node_report(tree_data, output_dir)
            
            # Analyze output quality
            quality = analyze_output_quality(tree_data, output_dir)
            
            print(f"\n{'='*60}")
            print("OUTPUT QUALITY ANALYSIS")
            print(f"{'='*60}")
            print(f"Total output files: {quality['total_output_files']}")
            print(f"Total size: {quality['total_output_size_mb']:.1f} MB")
            print(f"Nodes with outputs: {quality['nodes_with_outputs']}/{stats['total_nodes']}")
            print(f"H5AD files: {len(quality['h5ad_files'])}")
            print(f"Figure files: {len(quality['figure_files'])}")
            print(f"Data files: {len(quality['data_files'])}")
            
            # Print directory tree
            print(f"\n{'='*60}")
            print("OUTPUT DIRECTORY STRUCTURE")
            print(f"{'='*60}")
            tree_dir = output_dir / tree_id
            print(f"📁 {tree_dir.name}/")
            print_output_tree(tree_dir, max_depth=3, current_depth=0, prefix="")
            
            # Extract values for evaluation
            completed_nodes = stats['execution']['completed']
            failed_nodes = stats['execution']['failed']
            
            # Generic success criteria (more lenient for annotation)
            success = (
                completed_nodes >= 6 and
                quality['nodes_with_outputs'] >= 3 and
                len(quality['h5ad_files']) >= 1 and
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
    max_debug_trials: int = 3,
    domain_knowledge_domains: list = None,
    enable_domain_knowledge: bool = True,
    seed: int = 31,
    max_nodes: int = None,
    output_base_dir: str = "test_outputs",
    max_iterations: int = None,
    enable_web_agent: bool = False,
    docker_execution_timeout: int = None
):
    """Run a general analysis benchmark with custom user request and input folder.
    
    Args:
        user_request: The analysis request to execute
        input_folder: Path to folder containing input files
        llm_model: The LLM model to use (default: gpt-4o-mini)
        debug_turns: Number of debug turns per bug fixer session (default: 10)
        max_debug_trials: Maximum number of bug fixer sessions per node (default: 3)
        domain_knowledge_domains: List of domain knowledge to include (default: ["single_cell_genomics", "cell_type_annotation"])
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
    output_dir = Path(output_base_dir) / f"analysis_{timestamp}"
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
        # Determine which API key to use based on model name
        openai_api_key = None
        claude_api_key = None
        
        if llm_model.startswith('claude'):
            claude_api_key = os.getenv("CLAUDE_API_KEY")
            if not claude_api_key:
                raise ValueError(f"CLAUDE_API_KEY environment variable required for model {llm_model}")
            logger.info(f"Using Claude API for model {llm_model}")
        else:
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                raise ValueError(f"OPENAI_API_KEY environment variable required for model {llm_model}")
            logger.info(f"Using OpenAI API for model {llm_model}")
        
        # Initialize the main agent
        agent = MainAgent(
            openai_api_key=openai_api_key,
            claude_api_key=claude_api_key,
            bug_fixer_type="unified",
            bug_fixer_model=llm_model,
            llm_model=llm_model,
            enable_web_agent=enable_web_agent,
            log_llm_to_stdout=False,
            enable_domain_knowledge=enable_domain_knowledge,
            domain_knowledge_domains=domain_knowledge_domains if enable_domain_knowledge else None,
            bug_fixer_max_turns=debug_turns,
            llm_seed=seed,
            docker_execution_timeout=docker_execution_timeout
        )
        
        # Run the analysis with the input folder
        result = agent.run_analysis(
            input_data_path=str(input_folder),  # Pass the folder path
            user_request=user_request,
            output_dir=str(output_dir),
            max_nodes=max_nodes if max_nodes is not None else 15,
            max_debug_trials=max_debug_trials,
            max_iterations=max_iterations if max_iterations is not None else 20
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
            
            # Use new general statistics functions
            stats = analyze_node_statistics(tree_data)
            print_node_statistics(stats)
            
            # Print detailed node report
            print_detailed_node_report(tree_data, output_dir)
            
            # Analyze output quality
            quality = analyze_output_quality(tree_data, output_dir)
            
            print(f"\n{'='*60}")
            print("OUTPUT QUALITY ANALYSIS")
            print(f"{'='*60}")
            print(f"Total output files: {quality['total_output_files']}")
            print(f"Total size: {quality['total_output_size_mb']:.1f} MB")
            print(f"Nodes with outputs: {quality['nodes_with_outputs']}/{stats['total_nodes']}")
            print(f"H5AD files: {len(quality['h5ad_files'])}")
            print(f"Figure files: {len(quality['figure_files'])}")
            print(f"Data files: {len(quality['data_files'])}")
            
            # Print directory tree
            print(f"\n{'='*60}")
            print("OUTPUT DIRECTORY STRUCTURE")
            print(f"{'='*60}")
            tree_dir = output_dir / tree_id
            print(f"📁 {tree_dir.name}/")
            print_output_tree(tree_dir, max_depth=3, current_depth=0, prefix="")
            
            # Extract values for evaluation
            total_nodes = stats['total_nodes']
            completed_nodes = stats['execution']['completed']
            failed_nodes = stats['execution']['failed']
            job_review_passed = stats['job_review']['passed']
            
            # Check for root node execution (should always pass for folder input)
            root_nodes = [n for n in tree_data['nodes'].values() 
                         if n['function_block']['name'] == 'load_input_data']
            root_success = len(root_nodes) > 0 and root_nodes[0]['state'] == 'completed'
            
            # Success criteria (lenient since user request is variable)
            success = (
                root_success and  # Root node must succeed for folder input
                completed_nodes >= 3 and  # At least some analysis happened
                quality['nodes_with_outputs'] >= 2 and  # At least 2 nodes produced outputs
                total_nodes <= 15  # Stayed within node limit
            )
            
            print(f"\n{'='*80}")
            print("ANALYSIS BENCHMARK EVALUATION:")
            print(f"{'='*80}")
            
            if success:
                print("🎉 ANALYSIS BENCHMARK PASSED")
                print(f"Successfully processed input folder with {len(input_files)} files")
                print(f"Completed {completed_nodes}/{total_nodes} analysis nodes")
                print(f"Nodes with outputs: {quality['nodes_with_outputs']}")
                if job_review_passed > 0:
                    print(f"✅ {job_review_passed} nodes passed quality review")
                print(f"Total output size: {quality['total_output_size_mb']:.1f} MB")
            else:
                print("⚠️ ANALYSIS BENCHMARK NEEDS IMPROVEMENT")
                if not root_success:
                    print("  ❌ Failed to load input data from folder")
                if completed_nodes < 3:
                    print(f"  ❌ Too few completed nodes ({completed_nodes} < 3)")
                if quality['nodes_with_outputs'] < 2:
                    print(f"  ❌ Too few nodes with outputs ({quality['nodes_with_outputs']} < 2)")
            
            # Save comprehensive results
            analysis_results = {
                "timestamp": timestamp,
                "benchmark_type": f"analysis_{llm_model}_{debug_turns}turns_{max_debug_trials}trials",
                "success": success,
                "configuration": {
                    "llm_model": llm_model,
                    "bug_fixer_turns": debug_turns,
                    "max_debug_trials": max_debug_trials,
                    "max_nodes": max_nodes if max_nodes is not None else 15,
                    "input_folder": str(input_folder),
                    "input_files_count": len(input_files)
                },
                "node_statistics": stats,
                "output_quality": {
                    "total_files": quality['total_output_files'],
                    "total_size_mb": quality['total_output_size_mb'],
                    "nodes_with_outputs": quality['nodes_with_outputs'],
                    "h5ad_files": len(quality['h5ad_files']),
                    "figure_files": len(quality['figure_files']),
                    "data_files": len(quality['data_files'])
                }
            }
            
            results_file = output_dir / "analysis_benchmark_results.json"
            with open(results_file, "w") as f:
                json.dump(analysis_results, f, indent=2)
            
            print(f"\nDetailed results saved to: {results_file}")
            return success
            
        else:
            print("❌ No analysis tree found")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_cell_type_annotation_benchmark(llm_model: str = "gpt-4o-mini", debug_turns: int = 10, max_debug_trials: int = 3,
                                       enable_domain_knowledge: bool = True, seed: int = 31, output_suffix: str = None,
                                       output_base_dir: str = "test_outputs", enable_web_agent: bool = False, max_nodes: int = None,
                                       docker_execution_timeout: int = None, max_iterations: int = None):
    """Run specific cell type annotation benchmark using CellTypist and other Python-based methods.
    
    Args:
        llm_model: The LLM model to use (default: gpt-4o-mini)
        debug_turns: Number of debug turns per bug fixer session (default: 10)
        max_debug_trials: Maximum number of bug fixer sessions per node (default: 3)
        enable_domain_knowledge: Whether to enable domain knowledge (default: True)
        seed: Random seed for reproducibility (default: 31)
        output_suffix: Optional suffix for output directory to ensure uniqueness in parallel runs
        output_base_dir: Base directory for outputs (default: test_outputs)
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
    input_data = Path(__file__).parent.parent.parent / "test_data" / "pbmc3k_raw.h5ad"
    
    # Output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Check if output_base_dir already contains the benchmark type to avoid duplication
    base_dir_path = Path(output_base_dir)
    if base_dir_path.name == "annotation":
        # Already in an annotation subdirectory, don't add another prefix
        if output_suffix:
            output_dir = base_dir_path / f"{timestamp}_{output_suffix}"
        else:
            # Generate a unique ID if no suffix provided
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"{timestamp}_{unique_id}"
    else:
        # Not in a subdirectory, use the old behavior with prefix
        if output_suffix:
            output_dir = base_dir_path / f"annotation_{timestamp}_{output_suffix}"
        else:
            # Generate a unique ID if no suffix provided
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"annotation_{timestamp}_{unique_id}"
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
            enable_web_agent=enable_web_agent,
            log_llm_to_stdout=False,
            enable_domain_knowledge=enable_domain_knowledge,
            domain_knowledge_domains=["single_cell_genomics", "cell_type_annotation"] if enable_domain_knowledge else None,
            bug_fixer_max_turns=debug_turns,
            llm_seed=seed,
            docker_execution_timeout=docker_execution_timeout
        )
        
        # Run the analysis
        result = agent.run_analysis(
            input_data_path=str(input_data),
            user_request=user_request,
            output_dir=str(output_dir),
            max_iterations=max_iterations if max_iterations is not None else 25,
            max_debug_trials=max_debug_trials,
            max_nodes=max_nodes if max_nodes is not None else 20
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
            
            # Use new general statistics functions
            stats = analyze_node_statistics(tree_data)
            print_node_statistics(stats)
            
            # Print detailed node report
            print_detailed_node_report(tree_data, output_dir)
            
            # Analyze output quality
            quality = analyze_output_quality(tree_data, output_dir)
            
            print(f"\n{'='*60}")
            print("OUTPUT QUALITY ANALYSIS")
            print(f"{'='*60}")
            print(f"Total output files: {quality['total_output_files']}")
            print(f"Total size: {quality['total_output_size_mb']:.1f} MB")
            print(f"Nodes with outputs: {quality['nodes_with_outputs']}/{stats['total_nodes']}")
            print(f"H5AD files: {len(quality['h5ad_files'])}")
            print(f"Figure files: {len(quality['figure_files'])}")
            print(f"Data files: {len(quality['data_files'])}")
            
            # Print directory tree
            print(f"\n{'='*60}")
            print("OUTPUT DIRECTORY STRUCTURE")
            print(f"{'='*60}")
            tree_dir = output_dir / tree_id
            print(f"📁 {tree_dir.name}/")
            print_output_tree(tree_dir, max_depth=3, current_depth=0, prefix="")
            
            # Extract values for evaluation
            completed_nodes = stats['execution']['completed']
            failed_nodes = stats['execution']['failed']
            
            # Success criteria
            success = (
                completed_nodes >= 10 and  # At least 10 nodes completed
                quality['nodes_with_outputs'] >= 5 and  # At least 5 nodes with outputs
                len(quality['h5ad_files']) >= 2 and  # At least 2 h5ad files
                failed_nodes <= 5  # Allow some failures
            )
            
            # Count annotation nodes (nodes with 'annotation' or 'celltypist' in their name)
            annotation_nodes = [n for n in tree_data['nodes'].values() 
                              if 'annotation' in n['function_block']['name'].lower() or 
                              'celltypist' in n['function_block']['name'].lower()]
            
            print(f"\n{'='*80}")
            print("CELL TYPE ANNOTATION BENCHMARK EVALUATION:")
            print(f"  Completed nodes: {completed_nodes} (>= 10 required)")
            print(f"  Annotation nodes: {len(annotation_nodes)} (informational)")
            print(f"  Failed nodes: {failed_nodes} (<= 5 allowed)")
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


def run_spatial_analysis_case_1_benchmark(llm_model: str = "gpt-4o-mini", debug_turns: int = 10, max_debug_trials: int = 3,
                                          enable_domain_knowledge: bool = True, seed: int = 31, output_suffix: str = None,
                                          output_base_dir: str = "test_outputs", enable_web_agent: bool = False, max_nodes: int = None,
                                          docker_execution_timeout: int = None, max_iterations: int = None):
    """Run spatial transcriptomics analysis benchmark - Case 1.
    
    Args:
        llm_model: The LLM model to use (default: gpt-4o-mini)
        debug_turns: Number of debug turns per bug fixer session (default: 10)
        max_debug_trials: Maximum number of bug fixer sessions per node (default: 3)
        enable_domain_knowledge: Whether to enable domain knowledge (default: True)
        seed: Random seed for reproducibility (default: 31)
        output_suffix: Optional suffix for output directory to ensure uniqueness in parallel runs
        output_base_dir: Base directory for outputs (default: test_outputs)
    """
    
    user_request = """Goal:
Process a spatial transcriptomics AnnData file (cell2loc_result.h5ad), perform clustering analysis using Scanpy, 
create spatial visualizations using Squidpy, then carry out metabolic pathway and biological process analysis 
using GSEApy and GOATOOLS. Save all results and figures.

Required Analysis Steps:

1. **Data Loading and Setup**
   - Load the spatial transcriptomics data (cell2loc_result.h5ad)
   - Ensure gene names are unique
   - Set up figure directories for output

2. **Scanpy Analysis Pipeline**
   - Apply Zheng17 preprocessing recipe for initial QC and normalization
   - Perform PCA dimensionality reduction
   - Build neighborhood graph (n_neighbors=15, n_pcs=50)
   - Perform Leiden clustering (resolution=1.0)
   - Compute UMAP embedding
   - Store workflow parameters in adata.uns
   - Generate UMAP visualization colored by Leiden clusters

3. **Squidpy Spatial Visualizations**
   - Create spatial scatter plots colored by Leiden clusters
   - If AUCell scores or abundance columns exist in adata.obs, create spatial plots for each
   - Use appropriate colormaps and scaling for visualization
   - Save all figures to the designated output directory

4. **Metabolic and Biological Process Analysis**

   A) **Cluster-level Metabolic Pathway Enrichment**
      - Perform differential expression analysis between clusters using Wilcoxon test
      - Extract top marker genes for each cluster (p-value < 0.05, top 300 genes)
      - Use GSEApy's Enrichr functionality with Reactome_2022 and KEGG_2021_Human databases
      - Filter results for metabolic pathways
      - Save enrichment results to CSV

   B) **Per-cell Hallmark Metabolism Scores**
      - Calculate single-sample GSEA (ssGSEA) scores for metabolic hallmark gene sets
      - Focus on: GLYCOLYSIS, OXIDATIVE_PHOSPHORYLATION, FATTY_ACID_METABOLISM
      - Add scores to adata.obs
      - Generate UMAP and spatial visualizations colored by metabolism scores

   C) **GO Biological Process Enrichment**
      - Use GOATOOLS to perform GO enrichment analysis
      - Focus on metabolic process terms
      - Analyze marker genes from each cluster
      - Generate enrichment plots and save results

   D) **Optional: Flux Analysis with COBRApy**
      - If metabolic model is available, perform flux balance analysis
      - Analyze glycolysis and other metabolic pathways
      - Export flux results

5. **Output Requirements**
   - Save processed AnnData object with all annotations
   - Save all figures to designated output directory
   - Export enrichment results as CSV/TSV files
   - Generate summary statistics
   - Ensure all visualizations have proper labels and legends

IMPORTANT NOTES:
- Each major step should be a separate node in the analysis tree
- Handle package installation and dependency issues gracefully
- Ensure proper error handling for missing data or failed computations
- Use matplotlib backend appropriate for headless execution
- Create output directories before saving files
- Verify all API calls against library documentation"""
    
    # Input data path
    input_folder = Path(__file__).parent.parent.parent / "test_data" / "spatial_analysis_input"
    
    # Check if input folder exists (never substitute non-spatial data)
    if not input_folder.exists() or not (input_folder / "cell2loc_result.h5ad").exists():
        logger.error(f"Spatial input {input_folder / 'cell2loc_result.h5ad'} does not exist")
        return False
    
    # Output directory - simple approach without detection
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir_path = Path(output_base_dir)
    
    # Always create a subdirectory for this benchmark's results
    if output_suffix:
        output_dir = base_dir_path / f"spatial_case_1_{timestamp}_{output_suffix}"
    else:
        # Generate a unique ID if no suffix provided
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        output_dir = base_dir_path / f"spatial_case_1_{timestamp}_{unique_id}"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*80}")
    print("SPATIAL TRANSCRIPTOMICS ANALYSIS BENCHMARK - CASE 1")
    print(f"{'='*80}")
    print(f"Input folder: {input_folder}")
    print(f"Output directory: {output_dir}")
    print(f"Started at: {datetime.now()}")
    print(f"LLM Model: {llm_model}")
    print(f"Bug fixer turns per session: {debug_turns}")
    print(f"Max bug fixer sessions per node: {max_debug_trials}")
    print(f"Max nodes: {max_nodes if max_nodes is not None else 15}")
    print(f"Web agent: {'ENABLED' if enable_web_agent else 'DISABLED'}")
    print(f"{'='*80}\n")
    
    # Log LLM configuration
    logger.info(f"Initializing MainAgent for spatial analysis benchmark")
    logger.info(f"LLM model: {llm_model}")
    logger.info(f"Bug fixer configuration: {debug_turns} turns, max {max_debug_trials} trials")
    
    # Call run_analysis_benchmark_with_output_dir to use the exact output directory
    # We need to bypass the default directory creation in run_analysis_benchmark
    # So we'll call the MainAgent directly here instead
    
    logger.info(f"Initializing MainAgent for custom analysis")
    logger.info(f"Input folder: {input_folder}")
    logger.info(f"LLM model: {llm_model}")
    logger.info(f"Debug configuration: {debug_turns} turns, max {max_debug_trials} trials")
    
    # Determine which API key to use
    openai_api_key = os.getenv('OPENAI_API_KEY')
    claude_api_key = os.getenv('CLAUDE_API_KEY')
    
    if llm_model.startswith('gpt') or llm_model.startswith('o1'):
        if not openai_api_key:
            logger.error("OpenAI API key not found for model: %s", llm_model)
            return False
        logger.info(f"Using OpenAI API for model {llm_model}")
        agent = MainAgent(
            openai_api_key=openai_api_key,
            llm_model=llm_model,
            bug_fixer_model=llm_model,
            enable_web_agent=enable_web_agent,
            enable_output_collector=True,
            enable_domain_knowledge=enable_domain_knowledge,
            domain_knowledge_domains=["single_cell_genomics", "function_block_faq", "sc_spatial_case_1"] if enable_domain_knowledge else None,
            bug_fixer_max_turns=debug_turns,
            llm_seed=seed,
            docker_execution_timeout=docker_execution_timeout
        )
    elif llm_model.startswith('claude'):
        if not claude_api_key:
            logger.error("Claude API key not found for model: %s", llm_model)
            return False
        logger.info(f"Using Claude API for model {llm_model}")
        agent = MainAgent(
            claude_api_key=claude_api_key,
            llm_model=llm_model,
            bug_fixer_model=llm_model,
            enable_web_agent=enable_web_agent,
            enable_output_collector=True,
            enable_domain_knowledge=enable_domain_knowledge,
            domain_knowledge_domains=["single_cell_genomics", "function_block_faq", "sc_spatial_case_1"] if enable_domain_knowledge else None,
            bug_fixer_max_turns=debug_turns,
            llm_seed=seed,
            docker_execution_timeout=docker_execution_timeout
        )
    else:
        logger.error(f"Unknown model type: {llm_model}")
        return False
    
    try:
        # Run the analysis with the exact output directory we created
        result = agent.run_analysis(
            input_data_path=str(input_folder),
            user_request=user_request,
            output_dir=str(output_dir),  # Use the exact directory we created
            max_nodes=max_nodes if max_nodes is not None else 15,
            max_debug_trials=max_debug_trials,
            max_iterations=max_iterations if max_iterations is not None else 20
        )
        
        print(f"\n{'='*80}")
        print("SPATIAL ANALYSIS COMPLETE - EVALUATING RESULTS")
        print(f"{'='*80}\n")
        
        # Check if analysis succeeded
        if result.get('tree_id'):
            print(f"✅ Analysis completed successfully")
            print(f"📁 Output directory: {output_dir}")
            print(f"🌳 Tree ID: {result['tree_id']}")
            
            # Check for completed nodes
            tree_file = output_dir / f"{result['tree_id']}" / "analysis_tree.json"
            if tree_file.exists():
                import json
                with open(tree_file, 'r') as f:
                    tree_data = json.load(f)
                
                completed_nodes = sum(1 for node in tree_data.get('nodes', {}).values() 
                                    if node.get('state') == 'completed')
                total_nodes = len(tree_data.get('nodes', {}))
                
                print(f"📊 Nodes: {completed_nodes}/{total_nodes} completed")
                
                if completed_nodes >= 3:
                    print(f"✅ BENCHMARK SUCCESS: Spatial analysis completed with {completed_nodes} nodes")
                    return True
                else:
                    print(f"⚠️ BENCHMARK PARTIAL: Only {completed_nodes} nodes completed")
                    return False
        else:
            print(f"❌ ERROR: Analysis failed - no tree_id in result")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: Benchmark failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_spatial_analysis_case_2_benchmark(llm_model: str = "gpt-4o-mini", debug_turns: int = 10, max_debug_trials: int = 3,
                                          enable_domain_knowledge: bool = True, seed: int = 31, output_suffix: str = None,
                                          output_base_dir: str = "test_outputs", enable_web_agent: bool = False, max_nodes: int = None,
                                          docker_execution_timeout: int = None, max_iterations: int = None):
    """Run spatial transcriptomics analysis benchmark - Case 2 (Visium intestinal development).
    
    Args:
        llm_model: The LLM model to use (default: gpt-4o-mini)
        debug_turns: Number of debug turns per bug fixer session (default: 10)
        max_debug_trials: Maximum number of bug fixer sessions per node (default: 3)
        enable_domain_knowledge: Whether to enable domain knowledge (default: True)
        seed: Random seed for reproducibility (default: 31)
        output_suffix: Optional suffix for output directory to ensure uniqueness in parallel runs
        output_base_dir: Base directory for outputs (default: test_outputs)
    """
    
    user_request = """Reproduction Task: Visium-only results from "Spatiotemporal analysis of human intestinal development at single-cell resolution" (Cell, 2021)
Data you'll use (already downloaded from cellxgene)

Visium Spatial Gene Expression V1, Homo sapiens:
Adult colon: A1, A2
Fetal colon: A3, A4 (≈19 PCW), A8 (≈12 PCW), A9
Fetal ileum/TI: A6 (≈12 PCW), A7
Each Visium 6.5 mm capture area contains ~4,992 spots; verify counts from tissue_positions.csv. 
10x Genomics

Environment & conventions

Python (Scanpy ≥1.9 + Squidpy) or R (Seurat v4). Use SCTransform (or Seurat's sctransform) per paper; PCA→UMAP; Louvain clustering at resolution = 0.5 for each slide. Save all intermediate AnnData/Seurat objects.

Do not use external scRNA-seq for deconvolution; all deliverables must be computed from these Visium slides alone (gene overlays, unsupervised clusters, spatial statistics, distance-based trends).

Core figure/analysis deliverables (Visium-only)
D1. Unsupervised spot clustering & spatial maps (Figure 2A, Visium side)

For each of: A6 (12 PCW TI), A8 (12 PCW colon), A4 (19 PCW colon), A1 (adult colon)
(i) UMAP of spot transcriptomes; (ii) H&E-overlayed cluster map on tissue.
Acceptance: UMAP shows clear clusters; spatial maps form layered/ring-like patterns along tissue depth. Save .png for each slide and a 2×2 composite panel mirroring Figure 2A (left two columns).

D2. Single-gene landmark validations on Adult A1 (Figure 2B, genes only)

H&E with spot overlays for: PTPRC/CD45 (lymphoid follicle), RET (myenteric plexus).
Optional: show a simple crypt-top colonocyte proxy (e.g., BEST4/OTOP2) and a myofibroblast proxy (e.g., MYH11/ACTA2) as single-gene overlays (since we're not using references).
Acceptance: spots align with expected anatomic regions on A1. Provide magnified insets.

D3. Depth/Distance analysis (Figure 2C–D, Visium-only variant)

Adult A1:
(i) Compute a distance score for each spot relative to the muscularis mucosa. Do this by drawing a polyline boundary on the H&E (manual annotation is fine) and computing signed distances: submucosa negative, mucosa positive.
(ii) Identify distance-varying genes by smoothing each gene across distance (e.g., LOESS/GAM) and selecting significantly varying genes (FDR < 0.05).
(iii) Heatmap of distance-smoothed expression for top 200 distance-varying genes, clustered into mucosa-enriched vs submucosa-enriched modules, plus a distance-color bar overlay.

Fetal slides: replicate (i–ii) on A8 (12 PCW colon) and A4 (19 PCW colon) and show line/area plots for select genes illustrating developmental differences (e.g., split muscularis layers apparent at 19 PCW but not 12 PCW).
Acceptance: one A1 heatmap with two broad gene clusters; two fetal line-plots; a figure inset showing the distance map on H&E.

D4. Receptor–ligand spatial co-localization overlays (Supp. Fig S6E, Visium genes)

On Adult A1: co-overlay CEACAM1/CEACAM5; on Adult A1 and Fetal A6 (12 PCW TI): LRP1/HSPG2.
Produce two-channel spot overlays (or two panels) with H&E and smoothed expression contours; add a spatial co-occurrence metric (e.g., Squidpy co_occurrence or Moran's I cross-variogram) with a short caption.
Acceptance: clear, localized co-expression in relevant layers/regions; include a small bar chart of per-slide co-occurrence scores.

D5. Morphogen-module spot overlays (Supp. Fig S7B, Visium-only adaptation)

Using paper-defined morphogen gene sets (from Supplementary; if list not embedded in the object, recreate from figure legends/tables), compute per-spot module scores (mean-z of genes detected).
Slides: A4 (19 PCW colon) and A3 (12 PCW colon).
Deliver: two H&E-overlays for one selected module (e.g., pericyte/myofibroblast-derived module noted in S7B) showing contrasting spatial distributions across ages.
Acceptance: reproducible heatmaps showing expected compartmental localization differences between 12 PCW and 19 PCW colon.

Note: The paper originally integrates scRNA-seq for cell-type predictions and module discovery, but S7B also shows module score overlays on ST; you are reproducing just the ST overlay part with predefined gene sets.

D6. Quality control & summary table (per slide)

For each slide (A1, A2, A3, A4, A6, A7, A8, A9):

Spots on tissue, median UMIs/spot, genes/spot; % mitochondrial genes; #clusters at res=0.5; UMAP figure path; H&E overlay path.

Save a CSV summarizing all slides plus a PDF report (one page/slide with thumbnail panels).

File outputs (exact names)

visium_{slideID}.h5ad (or .rds) after SCTransform/PCA/UMAP/Louvain.

Figures:

D1 fig2A_like_{slideID}_umap.png, fig2A_like_{slideID}_spatial_clusters.png, plus fig2A_like_4panel.png

D2 fig2B_like_A1_PTPRC.png, fig2B_like_A1_RET.png, optional BEST4/OTOP2/MYH11/ACTA2

D3 fig2C_like_A1_distance_heatmap.png; fig2D_like_A8_profiles.png; fig2D_like_A4_profiles.png; include *_distance_inset.png

D4 S6E_like_A1_CEACAM1_CEACAM5.png; S6E_like_A1_LRP1_HSPG2.png; S6E_like_A6_LRP1_HSPG2.png plus *_cooccurrence.csv

D5 S7B_like_A4_moduleX.png; S7B_like_A3_moduleX.png

qc_summary.csv, qc_report.pdf.

Methods you should follow (brief)

Load & filter spots: keep tissue-covered spots; SCTransform normalize.

PCA/UMAP/Clustering: PCA → choose PCs by scree; Louvain (res = 0.5); UMAP.

H&E overlays: consistent spot size factor (≈1.6) across panels for comparability.

Single-gene maps (D2): log-normalize expression; Gaussian-smooth across spatial neighbors (Squidpy) for visualization; overlay on H&E.

Distance scoring (D3): annotate muscularis mucosa boundary; compute signed distance per spot; LOESS/GAM smoothing; FDR threshold on per-gene slope to select distance-varying genes; cluster genes, plot heatmap with GO terms optional (enrichment can be skipped).

Receptor–ligand overlays (D4): plot gene pairs listed above; compute spatial co-occurrence (neighbor graph with 6–8 nearest spots; report standardized statistic).

Morphogen modules (D5): use the paper's morphogen module gene lists to compute per-spot module scores and overlay.

Slide↔figure mapping (for reference/validation)

Figure 2A uses slides A6 (12 PCW TI), A8 (12 PCW colon), A4 (19 PCW colon), A1 (adult colon).

Figure 2B gene overlays and landmarks are from Adult A1.

Figure 2C–D distance/depth analyses: adult A1; fetal A8 (12 PCW colon) and A4 (19 PCW colon).

Supp. S6E receptor–ligand co-localization overlays: A1 (CEACAM1/5; LRP1/HSPG2) and A6 (LRP1/HSPG2).

Supp. S7B morphogen module ST overlays: A4 (top) and A3 (bottom; rotated).

What to hand in

All figures (PNGs) + composite PDFs for each deliverable (D1–D5).

qc_summary.csv and qc_report.pdf.

Reproducible code (scripts or notebooks) and a short README.md describing commands to regenerate all outputs."""
    
    # Input data path
    input_folder = Path(__file__).parent.parent.parent / "test_data" / "spatial_case_2"
    
    # Check if input folder exists
    if not input_folder.exists():
        logger.error(f"Input folder {input_folder} does not exist")
        return False
    
    # Output directory - simple approach without detection
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir_path = Path(output_base_dir)
    
    # Always create a subdirectory for this benchmark's results
    if output_suffix:
        output_dir = base_dir_path / f"spatial_case_2_{timestamp}_{output_suffix}"
    else:
        # Generate a unique ID if no suffix provided
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        output_dir = base_dir_path / f"spatial_case_2_{timestamp}_{unique_id}"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*80}")
    print("SPATIAL TRANSCRIPTOMICS ANALYSIS BENCHMARK - CASE 2 (VISIUM INTESTINAL DEVELOPMENT)")
    print(f"{'='*80}")
    print(f"Input folder: {input_folder}")
    print(f"Output directory: {output_dir}")
    print(f"Started at: {datetime.now()}")
    print(f"LLM Model: {llm_model}")
    print(f"Bug fixer turns per session: {debug_turns}")
    print(f"Max bug fixer sessions per node: {max_debug_trials}")
    print(f"Max nodes: {max_nodes if max_nodes is not None else 25}")
    print(f"Web agent: {'ENABLED' if enable_web_agent else 'DISABLED'}")
    print(f"{'='*80}\n")
    
    # Log LLM configuration
    logger.info(f"Initializing MainAgent for spatial analysis benchmark - Case 2")
    logger.info(f"LLM model: {llm_model}")
    logger.info(f"Bug fixer configuration: {debug_turns} turns, max {max_debug_trials} trials")
    
    # Determine which API key to use
    openai_api_key = os.getenv('OPENAI_API_KEY')
    claude_api_key = os.getenv('CLAUDE_API_KEY')
    
    if llm_model.startswith('gpt') or llm_model.startswith('o1'):
        if not openai_api_key:
            logger.error("OpenAI API key not found for model: %s", llm_model)
            return False
        logger.info(f"Using OpenAI API for model {llm_model}")
        agent = MainAgent(
            openai_api_key=openai_api_key,
            llm_model=llm_model,
            bug_fixer_model=llm_model,
            enable_web_agent=enable_web_agent,
            enable_output_collector=True,
            enable_domain_knowledge=enable_domain_knowledge,
            domain_knowledge_domains=["single_cell_genomics", "function_block_faq", "sc_spatial_case_1"] if enable_domain_knowledge else None,
            bug_fixer_max_turns=debug_turns,
            llm_seed=seed,
            docker_execution_timeout=docker_execution_timeout
        )
    elif llm_model.startswith('claude'):
        if not claude_api_key:
            logger.error("Claude API key not found for model: %s", llm_model)
            return False
        logger.info(f"Using Claude API for model {llm_model}")
        agent = MainAgent(
            claude_api_key=claude_api_key,
            llm_model=llm_model,
            bug_fixer_model=llm_model,
            enable_web_agent=enable_web_agent,
            enable_output_collector=True,
            enable_domain_knowledge=enable_domain_knowledge,
            domain_knowledge_domains=["single_cell_genomics", "function_block_faq", "sc_spatial_case_1"] if enable_domain_knowledge else None,
            bug_fixer_max_turns=debug_turns,
            llm_seed=seed,
            docker_execution_timeout=docker_execution_timeout
        )
    else:
        logger.error(f"Unknown model type: {llm_model}")
        return False
    
    try:
        # Run the analysis with the exact output directory we created
        result = agent.run_analysis(
            input_data_path=str(input_folder),
            user_request=user_request,
            output_dir=str(output_dir),  # Use the exact directory we created
            max_nodes=max_nodes if max_nodes is not None else 25,  # Higher default for complex spatial analysis
            max_debug_trials=max_debug_trials,
            max_iterations=max_iterations if max_iterations is not None else 25  # Higher default for complex workflow
        )
        
        print(f"\n{'='*80}")
        print("SPATIAL ANALYSIS CASE 2 COMPLETE - EVALUATING RESULTS")
        print(f"{'='*80}\n")
        
        # Check if analysis succeeded
        if result.get('tree_id'):
            print(f"✅ Analysis completed successfully")
            print(f"📁 Output directory: {output_dir}")
            print(f"🌳 Tree ID: {result['tree_id']}")
            
            # Check for completed nodes
            tree_file = output_dir / f"{result['tree_id']}" / "analysis_tree.json"
            if tree_file.exists():
                import json
                with open(tree_file, 'r') as f:
                    tree_data = json.load(f)
                
                completed_nodes = sum(1 for node in tree_data.get('nodes', {}).values() 
                                    if node.get('state') == 'completed')
                total_nodes = len(tree_data.get('nodes', {}))
                
                print(f"📊 Nodes: {completed_nodes}/{total_nodes} completed")
                
                if completed_nodes >= 5:
                    print(f"✅ BENCHMARK SUCCESS: Spatial analysis case 2 completed with {completed_nodes} nodes")
                    return True
                else:
                    print(f"⚠️ BENCHMARK PARTIAL: Only {completed_nodes} nodes completed")
                    return False
        else:
            print(f"❌ ERROR: Analysis failed - no tree_id in result")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR: Benchmark failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_perturb_seq_benchmark(llm_model: str = "gpt-4o-mini", debug_turns: int = 10, max_debug_trials: int = 3,
                              enable_domain_knowledge: bool = True, seed: int = 31, output_suffix: str = None,
                              output_base_dir: str = "test_outputs", enable_web_agent: bool = False,
                              dataset_name: str = "all", max_nodes: int = None,
                              docker_execution_timeout: int = None, max_iterations: int = None):
    """Run perturb-seq combinatorial perturbation prediction benchmark.
    
    Args:
        llm_model: The OpenAI model to use
        debug_turns: Number of debugging turns per bug fixer session
        max_debug_trials: Maximum debug attempts per node
        enable_domain_knowledge: Whether to use domain knowledge
        seed: Random seed for reproducibility
        output_suffix: Optional suffix for output directory
        output_base_dir: Base directory for outputs
        enable_web_agent: Whether to enable web agent for online research
        dataset_name: Which dataset(s) to use: 'norman', 'adamson', 'dixit', 
                     'replogle_k562_essential', 'replogle_rpe1_essential', or 'all'
    
    Returns:
        bool: True if benchmark ran successfully
    """
    # Define available datasets
    GEARS_DATASETS = {
        'norman': 'norman/norman/perturb_processed.h5ad',
        'adamson': 'adamson/adamson/perturb_processed.h5ad',
        'dixit': 'dixit/dixit/perturb_processed.h5ad',
        'replogle_k562_essential': 'replogle_k562_essential/replogle_k562_essential/perturb_processed.h5ad',
        'replogle_rpe1_essential': 'replogle_rpe1_essential/replogle_rpe1_essential/perturb_processed.h5ad'
    }
    
    # Load the request from markdown file
    request_file = Path(__file__).parent / "perturb_benchmark_request.md"
    
    if not request_file.exists():
        logger.error(f"Request file not found: {request_file}")
        return False
    
    with open(request_file, 'r') as f:
        user_request = f.read()
    
    # Determine which datasets to use
    base_data_dir = Path(__file__).parent.parent.parent / "test_data" / "gears_data"
    
    if dataset_name == "all":
        # Create a folder with all datasets for the agent to process
        datasets_to_use = GEARS_DATASETS
        logger.info(f"Running benchmark on ALL datasets: {list(datasets_to_use.keys())}")
        
        # For 'all' mode, we'll pass the gears_data directory
        input_data = base_data_dir
        
        # Update user request to emphasize processing all datasets
        user_request = user_request.replace(
            "Process each dataset independently",
            "IMPORTANT: Process ALL 5 datasets independently (Norman, Adamson, Dixit, Replogle K562, Replogle RPE1)"
        )
        
    elif dataset_name in GEARS_DATASETS:
        # Single dataset mode
        input_data = base_data_dir / GEARS_DATASETS[dataset_name]
        
        if not input_data.exists():
            logger.error(f"{dataset_name} dataset not found at {input_data}")
            logger.error("Please run the GEARS data download script first")
            return False
        
        logger.info(f"Running benchmark on single dataset: {dataset_name}")
        datasets_to_use = {dataset_name: GEARS_DATASETS[dataset_name]}
        
        # Update user request to focus on specific dataset
        user_request = user_request.replace(
            "Analyze ALL available GEARS datasets",
            f"Focus on the {dataset_name.upper()} dataset"
        )
    else:
        logger.error(f"Invalid dataset name: {dataset_name}")
        logger.error(f"Valid options: {list(GEARS_DATASETS.keys())} or 'all'")
        return False
    
    # Verify all required datasets exist
    for name, rel_path in datasets_to_use.items():
        dataset_path = base_data_dir / rel_path
        if not dataset_path.exists():
            logger.error(f"{name} dataset not found at {dataset_path}")
            logger.error("Please run the GEARS data download script first")
            return False
        else:
            logger.info(f"✅ Found {name} dataset at {dataset_path}")
    
    logger.info(f"Running perturb-seq benchmark with {llm_model}")
    logger.info(f"Input data: {input_data}")
    
    # Create output directory with timestamp and dataset info - consistent with other benchmarks
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_suffix = dataset_name if dataset_name != "all" else "all_datasets"
    base_dir_path = Path(output_base_dir)
    
    # Check if output_base_dir already contains the benchmark type to avoid duplication
    if base_dir_path.name == "perturb-seq" or base_dir_path.name == "perturb_seq":
        # Already in a perturb-seq subdirectory, don't add another prefix
        if output_suffix:
            output_dir = base_dir_path / f"{dataset_suffix}_{timestamp}_{output_suffix}"
        else:
            # Generate a unique ID if no suffix provided
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"{dataset_suffix}_{timestamp}_{unique_id}"
    else:
        # Not in a subdirectory, use the old behavior with prefix
        if output_suffix:
            output_dir = base_dir_path / f"perturb_seq_{dataset_suffix}_{timestamp}_{output_suffix}"
        else:
            # Generate a unique ID if no suffix provided
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"perturb_seq_{dataset_suffix}_{timestamp}_{unique_id}"
    
    # Initialize MainAgent
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable is not set")
        return False
    
    try:
        agent = MainAgent(
            openai_api_key=api_key,
            llm_model=llm_model,
            bug_fixer_model=llm_model,  # Use the same model for bug fixer
            bug_fixer_type="unified",
            bug_fixer_max_turns=debug_turns,  # Configurable debug turns
            llm_seed=seed,  # Random seed for reproducibility
            enable_output_collector=True,
            enable_domain_knowledge=enable_domain_knowledge,  # Configurable domain knowledge
            domain_knowledge_domains=["single_cell_genomics", "function_block_faq"] if enable_domain_knowledge else None,
            enable_web_agent=enable_web_agent,  # Configurable web agent
            docker_execution_timeout=docker_execution_timeout  # Pass the Docker execution timeout
        )
        
        # Run analysis
        logger.info("Starting perturb-seq analysis...")
        start_time = time.time()
        
        result = agent.run_analysis(
            input_data_path=str(input_data),
            user_request=user_request,
            output_dir=str(output_dir),
            max_iterations=max_iterations if max_iterations is not None else 20,  # Use provided or default
            max_debug_trials=max_debug_trials,  # Configurable max debug trials
            max_nodes=max_nodes if max_nodes is not None else 30,  # Use override or default to 30 for complex analysis
            max_children=4,
            capture_logs=True
        )
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        # Analyze results
        logger.info(f"Analysis completed in {elapsed_time:.2f} seconds")
        
        if result.get('tree_id'):
            tree_id = result['tree_id']
            tree_dir = output_dir / tree_id
            tree_file = tree_dir / "analysis_tree.json"
            
            if tree_file.exists():
                with open(tree_file, 'r') as f:
                    tree_data = json.load(f)
                
                # Analyze node statistics
                stats = analyze_node_statistics(tree_data)
                quality = analyze_output_quality(tree_data, output_dir)
                
                # Print summary
                print(f"\n{'='*60}")
                print(f"PERTURB-SEQ BENCHMARK RESULTS")
                print(f"{'='*60}")
                print(f"Dataset(s): {dataset_name.upper()}")
                print(f"LLM Model: {llm_model}")
                print(f"Debug Turns per Session: {debug_turns}")
                print(f"Max Debug Sessions: {max_debug_trials}")
                print(f"Domain Knowledge: {'ENABLED' if enable_domain_knowledge else 'DISABLED'}")
                print(f"Web Agent: {'ENABLED' if enable_web_agent else 'DISABLED'}")
                print(f"Random Seed: {seed}")
                print(f"Time Elapsed: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
                print(f"Output Directory: {output_dir}")
                print(f"Tree ID: {tree_id}")
                
                print(f"\n{'='*60}")
                print("NODE STATISTICS")
                print(f"{'='*60}")
                print(f"Total Nodes Created: {stats['total_nodes']}")
                print(f"\nExecution Status:")
                print(f"  - Completed: {stats['execution']['completed']} ({stats['execution'].get('success_rate', 0):.1f}%)")
                print(f"  - Failed: {stats['execution']['failed']}")
                print(f"  - Pending: {stats['execution']['pending']}")
                
                print(f"\nJob Review Status:")
                print(f"  - Passed: {stats['job_review']['passed']} ({stats['job_review'].get('pass_rate', 0):.1f}%)")
                print(f"  - Failed: {stats['job_review']['failed']}")
                print(f"  - Needs Rework: {stats['job_review']['needs_rework']}")
                print(f"  - Not Reviewed: {stats['job_review']['not_reviewed']}")
                
                print(f"\nDebug Statistics:")
                print(f"  - Nodes with Debug: {stats['debug']['nodes_with_debug']}")
                print(f"  - Total Debug Attempts: {stats['debug']['total_attempts']}")
                print(f"  - Max Attempts (single node): {stats['debug']['max_attempts_single_node']}")
                
                print(f"\n{'='*60}")
                print("OUTPUT QUALITY")
                print(f"{'='*60}")
                print(f"Total Output Files: {quality['total_output_files']}")
                print(f"Nodes with Outputs: {quality['nodes_with_outputs']}")
                print(f"Total Output Size: {quality['total_output_size_mb']:.2f} MB")
                print(f"H5AD Files Generated: {len(quality['h5ad_files'])}")
                print(f"Figure Files: {len(quality['figure_files'])}")
                print(f"Data Files (CSV/TSV): {len(quality['data_files'])}")
                
                # Print key outputs by node
                if quality['output_by_node']:
                    print(f"\n{'='*60}")
                    print("KEY OUTPUTS BY NODE")
                    print(f"{'='*60}")
                    for node_name, outputs in quality['output_by_node'].items():
                        has_outputs = any(outputs[k] for k in ['h5ad', 'figures', 'data'])
                        if has_outputs:
                            print(f"\n{node_name}:")
                            if outputs['h5ad']:
                                print(f"  📊 H5AD: {', '.join(outputs['h5ad'])}")
                            if outputs['figures']:
                                print(f"  📈 Figures: {len(outputs['figures'])} files")
                            if outputs['data']:
                                print(f"  📄 Data: {', '.join(outputs['data'][:3])}{'...' if len(outputs['data']) > 3 else ''}")
                
                # Print output tree structure
                print(f"\n{'='*60}")
                print("OUTPUT DIRECTORY STRUCTURE")
                print(f"{'='*60}")
                print_output_tree(tree_dir, max_depth=2)
                
                # Save benchmark results
                results_file = output_dir / f"benchmark_results_{llm_model.replace('-', '_')}.json"
                benchmark_results = {
                    'benchmark_type': 'perturb-seq',
                    'dataset_name': dataset_name,
                    'datasets_used': list(datasets_to_use.keys()),
                    'llm_model': llm_model,
                    'debug_turns': debug_turns,
                    'max_debug_trials': max_debug_trials,
                    'domain_knowledge_enabled': enable_domain_knowledge,
                    'web_agent_enabled': enable_web_agent,
                    'seed': seed,
                    'timestamp': timestamp,
                    'elapsed_time_seconds': elapsed_time,
                    'tree_id': tree_id,
                    'statistics': stats,
                    'output_quality': quality
                }
                
                with open(results_file, 'w') as f:
                    json.dump(benchmark_results, f, indent=2)
                
                logger.info(f"Benchmark results saved to {results_file}")
                
                # Determine success
                success_rate = stats['execution'].get('success_rate', 0)
                if success_rate > 50:  # At least 50% of nodes should complete
                    logger.info(f"✅ Perturb-seq benchmark completed successfully with {success_rate:.1f}% node success rate")
                    return True
                else:
                    logger.warning(f"⚠️ Perturb-seq benchmark completed with low success rate: {success_rate:.1f}%")
                    return False
            else:
                logger.error(f"Tree file not found: {tree_file}")
                return False
        else:
            logger.error("No tree ID in result")
            return False
            
    except Exception as e:
        logger.error(f"Error running perturb-seq benchmark: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def run_perturb_seq_v2_benchmark(llm_model: str = "gpt-4o-mini", debug_turns: int = 10, max_debug_trials: int = 3,
                                 enable_domain_knowledge: bool = True, seed: int = 31, output_suffix: str = None,
                                 output_base_dir: str = "test_outputs", enable_web_agent: bool = False,
                                 dataset_name: str = "all", max_nodes: int = None,
                                 docker_execution_timeout: int = None, max_iterations: int = None):
    """Run perturb-seq v2 benchmark using flattened GEARS data.
    
    This version uses the gears_data_flattened directory which has a simpler structure
    without nested subdirectories, making it easier for the agent to process.
    
    Args:
        llm_model: The OpenAI model to use
        debug_turns: Number of debugging turns per bug fixer session
        max_debug_trials: Maximum debug attempts per node
        enable_domain_knowledge: Whether to use domain knowledge
        seed: Random seed for reproducibility
        output_suffix: Optional suffix for output directory
        output_base_dir: Base directory for outputs
        enable_web_agent: Whether to enable web agent for online research
        dataset_name: Which dataset(s) to use: 'norman', 'adamson', 'dixit', 
                     'replogle_rpe1_essential', or 'all'
        max_nodes: Maximum number of nodes in the analysis tree
    
    Returns:
        bool: True if benchmark ran successfully
    """
    # Define available datasets in flattened structure
    GEARS_DATASETS = {
        'norman': 'norman/perturb_processed.h5ad',
        'adamson': 'adamson/perturb_processed.h5ad',
        'dixit': 'dixit/perturb_processed.h5ad',
        'replogle_rpe1_essential': 'replogle_rpe1_essential/perturb_processed.h5ad'
    }
    
    # Load the request from markdown file (same as v1)
    request_file = Path(__file__).parent / "perturb_benchmark_request.md"
    
    if not request_file.exists():
        logger.error(f"Request file not found: {request_file}")
        return False
    
    with open(request_file, 'r') as f:
        user_request = f.read()
    
    # Use gears_data_flattened instead of gears_data
    base_data_dir = Path(__file__).parent.parent.parent / "test_data" / "gears_data_flattened"
    
    if dataset_name == "all":
        # Use the entire flattened directory
        datasets_to_use = GEARS_DATASETS
        logger.info(f"Running benchmark on ALL datasets: {list(datasets_to_use.keys())}")
        input_data = base_data_dir
    else:
        # Use specific dataset
        if dataset_name not in GEARS_DATASETS:
            logger.error(f"Unknown dataset: {dataset_name}. Available: {list(GEARS_DATASETS.keys())}")
            return False
        
        # Point to specific dataset subdirectory
        datasets_to_use = {dataset_name: GEARS_DATASETS[dataset_name]}
        input_data = base_data_dir / dataset_name
        
        if not input_data.exists():
            logger.error(f"Dataset directory not found: {input_data}")
            return False
    
    # Check that the data exists
    if not base_data_dir.exists():
        logger.error(f"Data directory not found: {base_data_dir}")
        return False
    
    # Verify datasets exist
    for name, rel_path in datasets_to_use.items():
        dataset_path = base_data_dir / rel_path
        if not dataset_path.exists():
            logger.error(f"❌ Dataset not found: {dataset_path}")
            return False
        else:
            logger.info(f"✅ Found {name} dataset at {dataset_path}")
    
    logger.info(f"Running perturb-seq v2 benchmark with {llm_model}")
    logger.info(f"Input data: {input_data}")
    
    # Create output directory with timestamp and dataset info - consistent with other benchmarks
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dataset_suffix = dataset_name if dataset_name != "all" else "all_datasets"
    base_dir_path = Path(output_base_dir)
    
    # Check if output_base_dir already contains the benchmark type to avoid duplication
    if base_dir_path.name == "perturb-seq-v2" or base_dir_path.name == "perturb_seq_v2":
        # Already in a perturb-seq-v2 subdirectory, don't add another prefix
        if output_suffix:
            output_dir = base_dir_path / f"{dataset_suffix}_{timestamp}_{output_suffix}"
        else:
            # Generate a unique ID if no suffix provided
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"{dataset_suffix}_{timestamp}_{unique_id}"
    else:
        # Not in a subdirectory, use the old behavior with prefix
        if output_suffix:
            output_dir = base_dir_path / f"perturb_seq_v2_{dataset_suffix}_{timestamp}_{output_suffix}"
        else:
            # Generate a unique ID if no suffix provided
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"perturb_seq_v2_{dataset_suffix}_{timestamp}_{unique_id}"
    
    # Initialize MainAgent (same as v1 but with proper Claude support)
    # Determine which API key to use based on model name
    openai_api_key = None
    claude_api_key = None
    
    if llm_model.startswith('claude'):
        # Handle both regular Claude models and claude-cli models
        if llm_model.startswith('claude-cli'):
            # Claude CLI models use native support in MainAgent
            logger.info(f"Using Claude CLI model: {llm_model} (local Claude Code CLI)")
            # MainAgent handles claude-cli models natively, no API key needed
        else:
            claude_api_key = os.getenv("CLAUDE_API_KEY")
            if not claude_api_key:
                logger.error(f"CLAUDE_API_KEY environment variable required for model {llm_model}")
                return False
            logger.info(f"Using Claude API for model {llm_model}")
    else:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            logger.error(f"OPENAI_API_KEY environment variable required for model {llm_model}")
            return False
        logger.info(f"Using OpenAI API for model {llm_model}")
    
    try:
        agent = MainAgent(
            openai_api_key=openai_api_key,
            claude_api_key=claude_api_key,
            llm_model=llm_model,
            bug_fixer_model=llm_model,
            bug_fixer_type="unified",
            bug_fixer_max_turns=debug_turns,
            llm_seed=seed,
            enable_output_collector=True,
            enable_domain_knowledge=enable_domain_knowledge,
            domain_knowledge_domains=["single_cell_genomics", "function_block_faq"] if enable_domain_knowledge else None,
            enable_web_agent=enable_web_agent,
            docker_execution_timeout=docker_execution_timeout  # Pass the Docker execution timeout
        )
        
        # Run analysis
        logger.info("Starting perturb-seq v2 analysis...")
        start_time = time.time()
        
        result = agent.run_analysis(
            input_data_path=str(input_data),
            user_request=user_request,
            output_dir=str(output_dir),
            max_iterations=max_iterations if max_iterations is not None else 20,  # Use provided or default
            max_debug_trials=max_debug_trials,
            max_nodes=max_nodes if max_nodes is not None else 30,
            max_children=4,
            capture_logs=True
        )
        
        elapsed_time = time.time() - start_time
        logger.info(f"Perturb-seq v2 analysis completed in {elapsed_time:.2f} seconds")
        
        # Same result processing as v1
        if result:
            tree_id = result.get('tree_id')
            if tree_id:
                tree_file = output_dir / tree_id / "analysis_tree.json"
                if tree_file.exists():
                    with open(tree_file, 'r') as f:
                        tree_data = json.load(f)
                    
                    # Analyze results
                    stats = analyze_node_statistics(tree_data)
                    quality = analyze_output_quality(tree_data, output_dir)
                    
                    # Print results
                    print(f"\n{'='*80}")
                    print(f"PERTURB-SEQ V2 BENCHMARK RESULTS - {dataset_name.upper()}")
                    print(f"{'='*80}")
                    print(f"Model: {llm_model}")
                    print(f"Datasets: {', '.join(datasets_to_use.keys())}")
                    print(f"Elapsed Time: {elapsed_time:.2f} seconds")
                    
                    print_node_statistics(stats)
                    
                    # Print detailed node report
                    print_detailed_node_report(tree_data, output_dir)
                    
                    # Print debug statistics
                    if stats.get('debug'):
                        print(f"\n{'='*60}")
                        print("DEBUG STATISTICS")
                        print(f"{'='*60}")
                        print(f"Nodes with Debug Attempts: {stats['debug']['nodes_with_debug']}")
                        print(f"Total Debug Attempts: {stats['debug']['total_attempts']}")
                        print(f"Max Attempts (single node): {stats['debug']['max_attempts_single_node']}")
                        
                    # Save benchmark results
                    results_file = output_dir / f"benchmark_results_{llm_model.replace('-', '_')}.json"
                    benchmark_results = {
                        'benchmark_type': 'perturb-seq-v2',
                        'dataset_name': dataset_name,
                        'datasets_used': list(datasets_to_use.keys()),
                        'llm_model': llm_model,
                        'debug_turns': debug_turns,
                        'max_debug_trials': max_debug_trials,
                        'domain_knowledge_enabled': enable_domain_knowledge,
                        'web_agent_enabled': enable_web_agent,
                        'seed': seed,
                        'timestamp': timestamp,
                        'elapsed_time_seconds': elapsed_time,
                        'tree_id': tree_id,
                        'statistics': stats,
                        'output_quality': quality
                    }
                    
                    with open(results_file, 'w') as f:
                        json.dump(benchmark_results, f, indent=2)
                    
                    logger.info(f"Benchmark results saved to {results_file}")
                    
                    # Determine success
                    success_rate = stats['execution'].get('success_rate', 0)
                    if success_rate > 50:
                        logger.info(f"✅ Perturb-seq v2 benchmark completed successfully with {success_rate:.1f}% node success rate")
                        return True
                    else:
                        logger.warning(f"⚠️ Perturb-seq v2 benchmark completed with low success rate: {success_rate:.1f}%")
                        return False
                else:
                    logger.error(f"Tree file not found: {tree_file}")
                    return False
            else:
                logger.error("No tree ID in result")
                return False
        else:
            logger.error("Analysis failed to produce results")
            return False
            
    except Exception as e:
        logger.error(f"Error running perturb-seq v2 benchmark: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def run_perturb_Norman_analysis_benchmark(llm_model: str = "gpt-4o-mini", debug_turns: int = 10, max_debug_trials: int = 3,
                                          enable_domain_knowledge: bool = True, seed: int = 31, output_suffix: str = None,
                                          output_base_dir: str = "test_outputs", enable_web_agent: bool = False,
                                          max_nodes: int = None,
                                        docker_execution_timeout: int = None, max_iterations: int = None):
    """Run perturb-seq Norman comprehensive analysis benchmark.
    
    This benchmark performs a comprehensive analysis of the Norman et al. CRISPRa 
    perturbation dataset, including GI manifold reconstruction, synergy analysis,
    linear GI modeling, and recommender system imputation.
    
    Args:
        llm_model: The OpenAI or Claude model to use
        debug_turns: Number of debugging turns per bug fixer session
        max_debug_trials: Maximum debug attempts per node
        enable_domain_knowledge: Whether to use domain knowledge
        seed: Random seed for reproducibility
        output_suffix: Optional suffix for output directory
        output_base_dir: Base directory for outputs
        enable_web_agent: Whether to enable web agent for online research
        max_nodes: Maximum number of nodes in the analysis tree
    
    Returns:
        bool: True if benchmark ran successfully
    """
    # User request for comprehensive Norman analysis
    user_request = """Provide (i) the processed Perturb-seq data for the 287 single- and double-CRISPRa perturbations in K562 cells (~110k cells) with per-cell guide assignments and sample metadata, (ii) library/annotation files mapping each sgRNA pair and A/B cassette position to its target gene(s), and (iii) the fitness-map metadata linking the profiled gene pairs to their GI scores for reference; and deliver (1) a fully reproducible single-cell pipeline (QC → guide assignment → normalization → per-perturbation DE) that reconstructs the "GI manifold" UMAP and major clusters (e.g., G1 arrest, erythroid, granulocyte/megakaryocyte) from mean expression profiles, (2) replication of the CBL×CNN1 synergy analysis, including marker induction (e.g., hemoglobin genes) and single-cell progression from unperturbed → singles → double, (3) fitting and reporting the linear GI model (d_{ab}=c_1 d_a+c_2 d_b+e) across all pairs with (R^2), coefficients, and interaction classifications (buffering/epistasis vs. synergy/suppression), plus pathway orientation for the DUSP9–MAPK1–ETS2 trio, (4) the recommender-system imputation of GI scores using single-perturbation transcriptional "side information" with performance diagnostics, and (5) a concise report (figures matched to paper panels, tables for DE genes and model coefficients, and a README with exact software/environment) that reproduces the main results and scaling/down-sampling analyses.  
Figures-to-reproduce checklist. 
* #1 GI manifold (mean-profile UMAP; Fig. 2B) — Compute a per-perturbation mean log-normalized expression vector (singles and doubles), reduce (e.g., PCA→UMAP), plot one point per perturbation. Axes: UMAP-1 vs UMAP-2. Color: cluster ID from HDBSCAN (or leave gray for non-clustered). Label representative clusters (e.g., G1 arrest, erythroid, granulocyte/megakaryocyte). This mirrors the paper’s “UMAP projection of all single-gene and gene-pair Perturb-seq profiles,” where each dot is a mean expression profile and clusters are colored consistently. 

* #2 Marker overlays on the manifold (Fig. 3A) — On the same UMAP as #1, overlay per-perturbation marker panels (e.g., erythroid/granulocyte genes): color each dot by the mean Z-scored expression of the marker panel for that perturbation. Axes: UMAP-1 vs UMAP-2. Color scale: mean expression Z-score. 

* #3 Cell-cycle effects for cell-cycle gene targets (Fig. 2E–F) — For selected perturbations (CDKN1 family, PLK4/STIL, KIF18B/KIF2C, etc.), score each cell with S and G2/M signatures, assign a phase (G1/S/G2-M), then (a) plot deviation of the phase distribution vs control (bar/point chart; y: deviation) and (b) show the phase composition per perturbation (stacked bars across phases). Axes: (E) deviation vs perturbation; (F) categorical phase fractions. (Panel labels and examples shown alongside Fig. 2 caption.) 

* #4 Case study: CBL×CNN1 (Fig. 3C–D)
  • Heatmaps (3C): For CBL/ctrl, ctrl/CNN1, and CBL/CNN1, compute mean expression change vs unperturbed controls; plot gene-wise deviations (rows=genes, columns=perturbations). No axes beyond gene and condition labels; values are normalized expression differences. 
  • Single-cell UMAP (3D): UMAP on the cells from these three backgrounds; plot each cell, colored by genetic background (ctrl, single A, single B, double). Axes: UMAP-1 vs UMAP-2. (Paper shows a per-cell projection colored by background.) 
  • (Optional from scRNA-seq gene lists) ARCHS4 enrichment bar plot for genes most changed in the double (x: combined score; y: enriched cell types), if you also run gene-set enrichment on your DE list. 

* #5 Linear GI model from transcriptomes (Fig. 4A–B) — For each gene pair, fit the linear model on mean profiles of differentially expressed genes (d_{ab}=c_1 d_a+c_2 d_b+e) (predict the double from the two singles). Plot: (A) example prediction vs observed (scatter or bar of gene-level effects) to illustrate the model; (B) distribution of (R^2) across all pairs (histogram/box). Axes: (A) observed vs predicted effect size per gene; (B) (R^2) on y (or density), pairs on x (or histogram bins). (Avoid Fig. 4C; it correlates with fitness-based GI scores.) 

* #6 Trio logic with single-cell trajectories: DUSP9–MAPK1–ETS2 (Fig. 5A–C, G–H)
  • Model panels (5A–C): For each pair within the trio, show the fitted coefficients (bars) and/or predicted-vs-observed plots for the double; include the “double ≈ α·single1 + β·single2” summary on the figure. Axes: gene-effect (y) vs genes or predicted vs observed (scatter). 
  • Single-cell UMAP + principal curve (5G): UMAP of cells from DUSP9/ctrl, ctrl/MAPK1, and DUSP9/MAPK1; overlay a principal curve tracing the main phenotypic trajectory across backgrounds. Axes: UMAP-1 vs UMAP-2; curve shows the direction of variation. 
  • Gene expression along trajectory (5H): Order cells by position on the principal curve and plot a heatmap of median-filtered expression for DE genes along pseudotrajectory; annotate columns for each cell’s genetic background and rows for genes (include the targeted genes’ tracks). Axes: trajectory position (x) vs ordered cells; color: normalized expression. 

* (Optional) Single-cell manifold of all cells (Supp. Fig. S8) — Repeat #1 at single-cell resolution (UMAP of all cells, colored by perturbation/background). Axes: UMAP-1 vs UMAP-2. (Paper explicitly notes a per-cell version is shown in S8.) 
"""
    
    # Input data path - specific Norman GEARS data
    input_data = Path(__file__).parent.parent.parent / "test_data" / "perturb_norman_gears_data"
    
    # Check that the data exists
    if not input_data.exists():
        logger.error(f"Data directory not found: {input_data}")
        return False
    
    # Check for expected files
    expected_file = input_data / "Norman_perturb_processed.h5ad"
    if not expected_file.exists():
        logger.error(f"Expected data file not found: {expected_file}")
        return False
    
    logger.info(f"✅ Found Norman dataset at {expected_file}")
    file_size_mb = expected_file.stat().st_size / (1024 * 1024)
    logger.info(f"  File size: {file_size_mb:.1f} MB")
    
    logger.info(f"Running perturb Norman analysis benchmark with {llm_model}")
    logger.info(f"Input data: {input_data}")
    
    # Create output directory with timestamp - consistent with other benchmarks
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir_path = Path(output_base_dir)
    
    # Check if output_base_dir already contains the benchmark type to avoid duplication
    if base_dir_path.name == "perturb-norman-analysis" or base_dir_path.name == "perturb_norman_analysis":
        # Already in a perturb-norman-analysis subdirectory, don't add another prefix
        if output_suffix:
            output_dir = base_dir_path / f"{timestamp}_{output_suffix}"
        else:
            # Generate a unique ID if no suffix provided
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"{timestamp}_{unique_id}"
    else:
        # Not in a subdirectory, use the old behavior with prefix
        if output_suffix:
            output_dir = base_dir_path / f"perturb_norman_analysis_{timestamp}_{output_suffix}"
        else:
            # Generate a unique ID if no suffix provided
            import uuid
            unique_id = str(uuid.uuid4())[:8]
            output_dir = base_dir_path / f"perturb_norman_analysis_{timestamp}_{unique_id}"
    
    # Initialize MainAgent
    # Support both OpenAI and Claude models
    openai_api_key = None
    claude_api_key = None
    
    if llm_model.startswith('claude'):
        claude_api_key = os.getenv('CLAUDE_API_KEY')
        if not claude_api_key and not llm_model.startswith('claude-cli'):
            logger.error("CLAUDE_API_KEY environment variable is not set for Claude model")
            return False
    else:
        openai_api_key = os.getenv('OPENAI_API_KEY')
        if not openai_api_key:
            logger.error("OPENAI_API_KEY environment variable is not set")
            return False
    
    try:
        agent = MainAgent(
            openai_api_key=openai_api_key,
            claude_api_key=claude_api_key,
            llm_model=llm_model,
            bug_fixer_model=llm_model,
            bug_fixer_type="unified",
            bug_fixer_max_turns=debug_turns,
            llm_seed=seed,
            enable_output_collector=True,
            enable_domain_knowledge=enable_domain_knowledge,
            domain_knowledge_domains=["single_cell_genomics", "function_block_faq"] if enable_domain_knowledge else None,
            enable_web_agent=enable_web_agent,
            docker_execution_timeout=docker_execution_timeout  # Pass the Docker execution timeout
        )
        
        # Run analysis
        logger.info("Starting perturb Norman comprehensive analysis...")
        start_time = time.time()
        
        result = agent.run_analysis(
            input_data_path=str(input_data),
            user_request=user_request,
            output_dir=str(output_dir),
            max_iterations=max_iterations if max_iterations is not None else 20,  # Use provided or default
            max_debug_trials=max_debug_trials,
            max_nodes=max_nodes if max_nodes is not None else 40,  # More nodes for comprehensive analysis
            max_children=5,  # More children allowed for complex workflow
            capture_logs=True
        )
        
        elapsed_time = time.time() - start_time
        logger.info(f"Perturb Norman analysis completed in {elapsed_time:.2f} seconds")
        
        # Process results
        if result:
            tree_id = result.get('tree_id')
            if tree_id:
                tree_file = output_dir / tree_id / "analysis_tree.json"
                if tree_file.exists():
                    with open(tree_file, 'r') as f:
                        tree_data = json.load(f)
                    
                    # Analyze results
                    stats = analyze_node_statistics(tree_data)
                    quality = analyze_output_quality(tree_data, output_dir)
                    
                    # Print results
                    print(f"\n{'='*80}")
                    print(f"PERTURB NORMAN ANALYSIS BENCHMARK RESULTS")
                    print(f"{'='*80}")
                    print(f"Model: {llm_model}")
                    print(f"Elapsed Time: {elapsed_time:.2f} seconds")
                    
                    print_node_statistics(stats)
                    
                    # Print detailed node report
                    print_detailed_node_report(tree_data, output_dir)
                    
                    # Print debug statistics
                    if stats.get('debug'):
                        print(f"\n{'='*60}")
                        print("DEBUG STATISTICS")
                        print(f"{'='*60}")
                        print(f"Nodes with Debug Attempts: {stats['debug']['nodes_with_debug']}")
                        print(f"Total Debug Attempts: {stats['debug']['total_attempts']}")
                        print(f"Max Attempts (single node): {stats['debug']['max_attempts_single_node']}")
                    
                    # Print output quality
                    print(f"\n{'='*60}")
                    print("OUTPUT QUALITY")
                    print(f"{'='*60}")
                    print(f"Total Output Files: {quality['total_output_files']}")
                    print(f"Nodes with Outputs: {quality['nodes_with_outputs']}")
                    print(f"Total Output Size: {quality['total_output_size_mb']:.2f} MB")
                    print(f"H5AD Files Generated: {len(quality['h5ad_files'])}")
                    print(f"Figure Files: {len(quality['figure_files'])}")
                    print(f"Data Files (CSV/TSV): {len(quality['data_files'])}")
                    
                    # Save benchmark results
                    results_file = output_dir / f"benchmark_results_{llm_model.replace('-', '_')}.json"
                    benchmark_results = {
                        'benchmark_type': 'perturb-norman-analysis',
                        'llm_model': llm_model,
                        'debug_turns': debug_turns,
                        'max_debug_trials': max_debug_trials,
                        'domain_knowledge_enabled': enable_domain_knowledge,
                        'web_agent_enabled': enable_web_agent,
                        'seed': seed,
                        'timestamp': timestamp,
                        'elapsed_time_seconds': elapsed_time,
                        'tree_id': tree_id,
                        'statistics': stats,
                        'output_quality': quality
                    }
                    
                    with open(results_file, 'w') as f:
                        json.dump(benchmark_results, f, indent=2)
                    
                    logger.info(f"Benchmark results saved to {results_file}")
                    
                    # Determine success
                    success_rate = stats['execution'].get('success_rate', 0)
                    if success_rate > 50:
                        logger.info(f"✅ Perturb Norman analysis benchmark completed successfully with {success_rate:.1f}% node success rate")
                        return True
                    else:
                        logger.warning(f"⚠️ Perturb Norman analysis benchmark completed with low success rate: {success_rate:.1f}%")
                        return False
                else:
                    logger.error(f"Tree file not found: {tree_file}")
                    return False
            else:
                logger.error("No tree ID in result")
                return False
        else:
            logger.error("Analysis failed to produce results")
            return False
            
    except Exception as e:
        logger.error(f"Error running perturb Norman analysis benchmark: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run single-cell genomics benchmarks with configurable parameters")
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=None,
        dest="max_nodes",
        help="Maximum number of nodes in the analysis tree (default: varies by benchmark type)"
    )
    parser.add_argument(
        "--benchmark-type",
        type=str,
        choices=["pseudotime", "clustering", "annotation", "annotation-general", "analysis", "spatial-analysis-case-1", "perturb-seq", "perturb-seq-v2", "perturb-norman-analysis"],
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
    parser.add_argument(
        "--disable-domain-knowledge",
        action="store_true",
        dest="disable_domain_knowledge",
        help="Disable domain knowledge for ablation study (default: False, domain knowledge enabled)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=31,
        dest="seed",
        help="Random seed for reproducibility (default: 31)"
    )
    parser.add_argument(
        "--enable-web-agent",
        action="store_true",
        dest="enable_web_agent",
        help="Enable web agent for online research (default: False, disabled for cost/security)"
    )
    
    # Arguments specific to 'perturb-seq' benchmark type
    parser.add_argument(
        "--perturb-dataset",
        type=str,
        default="all",
        choices=["norman", "adamson", "dixit", "replogle_k562_essential", "replogle_rpe1_essential", "all"],
        dest="perturb_dataset",
        help="Dataset to use for perturb-seq benchmark (default: all)"
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
    
    # For individual benchmark runs, we'll let MainAgent handle the output directory structure
    # and save the configuration in the MainAgent's folder
    # This will be handled by the benchmark functions themselves
    
    # Log the configuration
    logger.info(f"Starting {args.benchmark_type} benchmark with:")
    logger.info(f"  - Benchmark Type: {args.benchmark_type}")
    logger.info(f"  - LLM Model: {args.llm_model}")
    logger.info(f"  - Debug Turns per session: {args.debug_turns}")
    logger.info(f"  - Max Debug Sessions per node: {args.max_debug_trials}")
    logger.info(f"  - Domain Knowledge: {'DISABLED' if args.disable_domain_knowledge else 'ENABLED'}")
    logger.info(f"  - Random Seed: {args.seed}")
    if args.benchmark_type == "analysis":
        logger.info(f"  - Input Folder: {args.input_folder}")
        logger.info(f"  - User Request: {args.analysis_user_req[:100]}...")  # Log first 100 chars
    
    # Run the appropriate benchmark
    if args.benchmark_type == "pseudotime":
        success = run_pseudotime_benchmark(
            llm_model=args.llm_model, 
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials,
            enable_domain_knowledge=not args.disable_domain_knowledge,
            seed=args.seed,
            enable_web_agent=args.enable_web_agent,
            max_nodes=args.max_nodes
        )
        benchmark_name = "PSEUDOTIME"
    elif args.benchmark_type == "clustering":
        success = run_clustering_benchmark(
            llm_model=args.llm_model, 
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials,
            enable_domain_knowledge=not args.disable_domain_knowledge,
            seed=args.seed,
            enable_web_agent=args.enable_web_agent,
            max_nodes=args.max_nodes
        )
        benchmark_name = "CLUSTERING"
    elif args.benchmark_type == "annotation-general":
        success = run_cell_type_annotation_general_benchmark(
            llm_model=args.llm_model, 
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials,
            enable_domain_knowledge=not args.disable_domain_knowledge,
            seed=args.seed,
            enable_web_agent=args.enable_web_agent,
            max_nodes=args.max_nodes
        )
        benchmark_name = "CELL TYPE ANNOTATION (GENERAL)"
    elif args.benchmark_type == "annotation":
        success = run_cell_type_annotation_benchmark(
            llm_model=args.llm_model, 
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials,
            enable_domain_knowledge=not args.disable_domain_knowledge,
            seed=args.seed,
            enable_web_agent=args.enable_web_agent,
            max_nodes=args.max_nodes
        )
        benchmark_name = "CELL TYPE ANNOTATION"
    elif args.benchmark_type == "analysis":
        success = run_analysis_benchmark(
            user_request=args.analysis_user_req,
            input_folder=args.input_folder,
            llm_model=args.llm_model,
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials,
            enable_domain_knowledge=not args.disable_domain_knowledge,
            seed=args.seed,
            enable_web_agent=args.enable_web_agent,
            max_nodes=args.max_nodes
        )
        benchmark_name = "CUSTOM ANALYSIS"
    elif args.benchmark_type == "spatial-analysis-case-1":
        success = run_spatial_analysis_case_1_benchmark(
            llm_model=args.llm_model,
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials,
            enable_domain_knowledge=not args.disable_domain_knowledge,
            seed=args.seed,
            enable_web_agent=args.enable_web_agent,
            max_nodes=args.max_nodes
        )
        benchmark_name = "SPATIAL TRANSCRIPTOMICS ANALYSIS - CASE 1"
    elif args.benchmark_type == "perturb-seq":
        success = run_perturb_seq_benchmark(
            llm_model=args.llm_model,
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials,
            enable_domain_knowledge=not args.disable_domain_knowledge,
            seed=args.seed,
            enable_web_agent=args.enable_web_agent,
            dataset_name=args.perturb_dataset,
            max_nodes=args.max_nodes
        )
        benchmark_name = f"PERTURB-SEQ ({args.perturb_dataset.upper()})"
    elif args.benchmark_type == "perturb-seq-v2":
        success = run_perturb_seq_v2_benchmark(
            llm_model=args.llm_model,
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials,
            enable_domain_knowledge=not args.disable_domain_knowledge,
            seed=args.seed,
            enable_web_agent=args.enable_web_agent,
            dataset_name=args.perturb_dataset,
            max_nodes=args.max_nodes
        )
        benchmark_name = f"PERTURB-SEQ-V2 ({args.perturb_dataset.upper()})"
    elif args.benchmark_type == "perturb-norman-analysis":
        success = run_perturb_Norman_analysis_benchmark(
            llm_model=args.llm_model,
            debug_turns=args.debug_turns,
            max_debug_trials=args.max_debug_trials,
            enable_domain_knowledge=not args.disable_domain_knowledge,
            seed=args.seed,
            enable_web_agent=args.enable_web_agent,
            max_nodes=args.max_nodes
        )
        benchmark_name = "PERTURB NORMAN ANALYSIS"
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
        print(f"Web agent: {'enabled' if args.enable_web_agent else 'disabled'}")
    print(f"{'='*80}")
    sys.exit(0 if success else 1)