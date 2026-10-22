#!/usr/bin/env python3
"""
Minimal cost benchmark script for paper evaluation.
Runs each benchmark task ONCE per model with configurable hyperparameters to minimize API costs.

Default hyperparameters (now configurable):
- Bug fixer max attempts: 4 (--max-trials)
- Bug fixer debug turns: 3 (--debug-turns)
- Single seed: 31 (--seed)
- Domain knowledge: enabled
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
import argparse

# Add the omicairn_agent_local directory to the Python path
omicairn_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, omicairn_path)

# Now import directly without the scripts.benchmarks prefix since we're in that directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_general_benchmark import (
    run_pseudotime_benchmark,
    run_clustering_benchmark, 
    run_cell_type_annotation_benchmark,
    run_spatial_analysis_case_1_benchmark,
    run_perturb_seq_benchmark,
    run_perturb_seq_v2_benchmark,
    run_perturb_Norman_analysis_benchmark
)

# Claude CLI is now natively supported in MainAgent
# No adapter needed

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Silence noisy loggers
for logger_name in ['urllib3', 'docker', 'requests', 'openai', 'httpx', 'httpcore', 'httpcore.http11']:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

# DEFAULT HYPERPARAMETERS FOR MINIMAL COST (now configurable)
DEFAULT_DEBUG_TURNS = 3  # Default debug turns to reduce cost
DEFAULT_MAX_TRIALS = 4   # Default bug fixer attempts
DEFAULT_SEED = 31        # Default seed for reproducibility
DEFAULT_MAX_ITERATIONS = 20  # Default planning iterations
DEFAULT_ENABLE_DOMAIN_KNOWLEDGE = True  # Default: use domain knowledge for better success rate

class MinimalBenchmarkRunner:
    """Minimal cost benchmark runner - single run per configuration."""
    
    def __init__(self, output_base_dir: str = "paper_benchmark_minimal", max_nodes: int = None, docker_execution_timeout: int = None,
                 debug_turns: int = None, max_trials: int = None, seed: int = None, max_iterations: int = None):
        self.output_base_dir = Path(output_base_dir)
        self.output_base_dir.mkdir(parents=True, exist_ok=True)
        self.results = []
        self.start_time = datetime.now()
        self.enable_domain_knowledge = None  # Will be set when running suite
        self.max_nodes = max_nodes  # Store max_nodes override
        self.docker_execution_timeout = docker_execution_timeout  # Store Docker timeout override
        # Store configurable parameters with defaults
        self.debug_turns = debug_turns if debug_turns is not None else DEFAULT_DEBUG_TURNS
        self.max_trials = max_trials if max_trials is not None else DEFAULT_MAX_TRIALS
        self.seed = seed if seed is not None else DEFAULT_SEED
        self.max_iterations = max_iterations if max_iterations is not None else DEFAULT_MAX_ITERATIONS
        
    def get_benchmark_functions(self) -> Dict[str, callable]:
        """Map benchmark types to their respective functions."""
        return {
            'pseudotime': run_pseudotime_benchmark,
            'clustering': run_clustering_benchmark,
            'annotation': run_cell_type_annotation_benchmark,
            'spatial': run_spatial_analysis_case_1_benchmark,  # Backward compatibility
            'spatial-case-1': run_spatial_analysis_case_1_benchmark,
            'perturb-seq': run_perturb_seq_benchmark,
            'perturb-seq-v2': run_perturb_seq_v2_benchmark,
            'perturb-norman-analysis': run_perturb_Norman_analysis_benchmark
        }
    
    def run_single_benchmark(self, benchmark_type: str, model: str, enable_domain_knowledge: bool = True, enable_claude_cli_websearch: bool = False) -> Dict[str, Any]:
        """Run a single benchmark with configurable hyperparameters."""
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Running {benchmark_type} with {model}")
        logger.info(f"Params: {self.debug_turns} turns, {self.max_trials} trials, seed {self.seed}")
        logger.info(f"{'='*60}")
        
        result = {
            'benchmark_type': benchmark_type,
            'model': model,
            'debug_turns': self.debug_turns,
            'max_trials': self.max_trials,
            'seed': self.seed,
            'domain_knowledge': enable_domain_knowledge,
            'success': False,
            'duration': 0.0,
            'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
            'error': None
        }
        
        try:
            start_time = time.time()
            
            # Check API key availability (skip for CLI models)
            if model.startswith('claude-cli'):
                # Claude CLI models don't need API keys
                logger.info(f"Using Claude CLI model: {model} (local Claude Code CLI)")
            elif model.startswith('claude'):
                if not os.getenv('CLAUDE_API_KEY'):
                    result['error'] = "CLAUDE_API_KEY not available"
                    logger.warning(f"Skipping {model}: No Claude API key")
                    return result
            else:
                if not os.getenv('OPENAI_API_KEY'):
                    result['error'] = "OPENAI_API_KEY not available"
                    logger.error("No OpenAI API key available")
                    return result
            
            
            # Generate unique suffix for this run
            config_id = f"minimal_{model.replace('-', '_')}_{benchmark_type}"
            if not enable_domain_knowledge:
                config_id += "_noDK"
            
            # Get the benchmark function
            benchmark_functions = self.get_benchmark_functions()
            benchmark_func = benchmark_functions[benchmark_type]
            
            # Run the benchmark with fixed parameters
            logger.info(f"Starting {benchmark_type} benchmark...")
            
            # For Claude CLI models, enable web agent if WebSearch is requested
            is_claude_cli = model.startswith('claude-cli-')
            web_agent_enabled = is_claude_cli and enable_claude_cli_websearch
            
            if is_claude_cli and enable_claude_cli_websearch:
                logger.info(f"Enabling WebSearch for Claude CLI model: {model}")
            elif is_claude_cli:
                logger.info(f"Claude CLI model detected but WebSearch disabled: {model}")
            
            # Pass the output directory directly to the benchmark function
            # Let run_general_benchmark.py handle all folder creation
            logger.info(f"Running benchmark with output_base_dir: {self.output_base_dir}")
            
            # Handle perturb-seq benchmarks specially (has dataset_name parameter)
            if benchmark_type in ['perturb-seq', 'perturb-seq-v2']:
                success = benchmark_func(
                    llm_model=model,
                    debug_turns=self.debug_turns,
                    max_debug_trials=self.max_trials,
                    enable_domain_knowledge=enable_domain_knowledge,
                    seed=self.seed,
                    output_suffix=config_id,
                    output_base_dir=str(self.output_base_dir),  # Pass base dir directly
                    enable_web_agent=web_agent_enabled,
                    dataset_name='all',  # Default to all datasets for comprehensive benchmark
                    max_nodes=self.max_nodes,
                    docker_execution_timeout=self.docker_execution_timeout,
                    max_iterations=self.max_iterations
                )
            else:
                success = benchmark_func(
                    llm_model=model,
                    debug_turns=self.debug_turns,
                    max_debug_trials=self.max_trials,
                    enable_domain_knowledge=enable_domain_knowledge,
                    seed=self.seed,
                    output_suffix=config_id,
                    output_base_dir=str(self.output_base_dir),  # Pass base dir directly
                    enable_web_agent=web_agent_enabled,
                    max_nodes=self.max_nodes,
                    docker_execution_timeout=self.docker_execution_timeout,
                    max_iterations=self.max_iterations
                )
            
            result['success'] = success
            result['duration'] = time.time() - start_time
            
            # Find and store output directory
            output_pattern = f"*{config_id}*"
            output_dirs = list(self.output_base_dir.glob(output_pattern))
            if output_dirs:
                result['output_dir'] = str(output_dirs[0])
                logger.info(f"Output saved to: {output_dirs[0]}")
            
            logger.info(f"✅ Completed {benchmark_type}/{model}: Success={success}, Duration={result['duration']:.1f}s")
            
        except Exception as e:
            result['error'] = str(e)
            result['duration'] = time.time() - start_time
            logger.error(f"❌ Failed {benchmark_type}/{model}: {e}")
            
        return result
    
    def run_minimal_suite(self, 
                         models: List[str] = None,
                         benchmark_types: List[str] = None,
                         enable_domain_knowledge: bool = True,
                         enable_claude_cli_websearch: bool = False) -> List[Dict[str, Any]]:
        """Run minimal benchmark suite - one run per model/task combination."""
        
        # Store the actual domain knowledge setting for metadata
        self.enable_domain_knowledge = enable_domain_knowledge
        
        # Default models - auto-detect all available when no models specified
        if models is None:
            models = []
            if os.getenv('OPENAI_API_KEY'):
                # Include all available OpenAI models
                models.extend(['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo', 'gpt-3.5-turbo'])
                # GPT-5 series (available as of August 2025)
                models.extend(['gpt-5', 'gpt-5-mini', 'gpt-5-nano'])
            if os.getenv('CLAUDE_API_KEY'):
                # Include all Claude models
                # Use full model IDs with dates for Claude models
                models.extend(['claude-3-5-haiku-20241022', 'claude-3-5-sonnet-20241022'])
            if not models:
                raise ValueError("No API keys available. Set OPENAI_API_KEY or CLAUDE_API_KEY")
        
        # Default benchmark types
        if benchmark_types is None:
            benchmark_types = ['pseudotime', 'clustering', 'annotation', 'spatial-case-1', 'perturb-seq', 'perturb-seq-v2', 'perturb-norman-analysis']
        
        # Calculate total runs
        total_runs = len(models) * len(benchmark_types)
        logger.info(f"\n{'='*60}")
        logger.info(f"MINIMAL COST BENCHMARK CONFIGURATION")
        logger.info(f"{'='*60}")
        logger.info(f"Models: {models}")
        logger.info(f"Benchmark types: {benchmark_types}")
        logger.info(f"Parameters:")
        logger.info(f"  - Debug turns: {self.debug_turns}")
        logger.info(f"  - Max trials: {self.max_trials}")
        logger.info(f"  - Seed: {self.seed}")
        logger.info(f"  - Domain knowledge: {enable_domain_knowledge}")
        logger.info(f"Total runs: {total_runs} (1 run per model/task)")
        logger.info(f"Estimated cost: ~${total_runs * 0.50:.2f} (assuming ~$0.50 per run)")
        logger.info(f"{'='*60}\n")
        
        # Track results from this suite run separately
        suite_results = []
        
        # Run benchmarks sequentially (no parallel to avoid rate limits)
        run_counter = 0
        for benchmark_type in benchmark_types:
            for model in models:
                run_counter += 1
                logger.info(f"\n[{run_counter}/{total_runs}] Running {benchmark_type} with {model}")
                
                result = self.run_single_benchmark(benchmark_type, model, enable_domain_knowledge, enable_claude_cli_websearch)
                self.results.append(result)  # Append to overall results
                suite_results.append(result)  # Also track for this suite run
                
                # Brief pause between runs to avoid rate limits
                if run_counter < total_runs:
                    time.sleep(2)
        
        return suite_results  # Return only results from this suite run
    
    def save_results(self, filename: str = None) -> Path:
        """Save minimal benchmark results."""
        if filename is None:
            timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
            filename = f"minimal_benchmark_results_{timestamp}.json"
        
        results_file = self.output_base_dir / filename
        
        # Calculate summary statistics
        total = len(self.results)
        successful = sum(1 for r in self.results if r['success'])
        
        summary_data = {
            'metadata': {
                'type': 'minimal_cost_benchmark',
                'start_time': self.start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'total_duration': sum(r['duration'] for r in self.results),
                'total_benchmarks': total,
                'successful_benchmarks': successful,
                'failed_benchmarks': total - successful,
                'success_rate': successful / total if total > 0 else 0,
                'parameters': {
                    'debug_turns': self.debug_turns,
                    'max_trials': self.max_trials,
                    'seed': self.seed,
                    'domain_knowledge': self.enable_domain_knowledge if self.enable_domain_knowledge is not None else DEFAULT_ENABLE_DOMAIN_KNOWLEDGE
                }
            },
            'results': self.results,
            'summary_by_model': self._summarize_by_model(),
            'summary_by_benchmark': self._summarize_by_benchmark()
        }
        
        with open(results_file, 'w') as f:
            json.dump(summary_data, f, indent=2)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Results saved to: {results_file}")
        logger.info(f"{'='*60}")
        
        return results_file
    
    def _summarize_by_model(self) -> Dict[str, Any]:
        """Generate summary statistics by model."""
        model_stats = {}
        for result in self.results:
            model = result['model']
            if model not in model_stats:
                model_stats[model] = {
                    'total': 0,
                    'successful': 0,
                    'failed': 0,
                    'total_duration': 0.0,
                    'benchmarks': []
                }
            
            model_stats[model]['total'] += 1
            model_stats[model]['total_duration'] += result['duration']
            model_stats[model]['benchmarks'].append(result['benchmark_type'])
            
            if result['success']:
                model_stats[model]['successful'] += 1
            else:
                model_stats[model]['failed'] += 1
        
        # Calculate success rates
        for model in model_stats:
            stats = model_stats[model]
            stats['success_rate'] = stats['successful'] / stats['total'] if stats['total'] > 0 else 0
            stats['avg_duration'] = stats['total_duration'] / stats['total'] if stats['total'] > 0 else 0
        
        return model_stats
    
    def _summarize_by_benchmark(self) -> Dict[str, Any]:
        """Generate summary statistics by benchmark type."""
        benchmark_stats = {}
        for result in self.results:
            benchmark = result['benchmark_type']
            if benchmark not in benchmark_stats:
                benchmark_stats[benchmark] = {
                    'total': 0,
                    'successful': 0,
                    'failed': 0,
                    'total_duration': 0.0,
                    'models': []
                }
            
            benchmark_stats[benchmark]['total'] += 1
            benchmark_stats[benchmark]['total_duration'] += result['duration']
            benchmark_stats[benchmark]['models'].append(result['model'])
            
            if result['success']:
                benchmark_stats[benchmark]['successful'] += 1
            else:
                benchmark_stats[benchmark]['failed'] += 1
        
        # Calculate success rates
        for benchmark in benchmark_stats:
            stats = benchmark_stats[benchmark]
            stats['success_rate'] = stats['successful'] / stats['total'] if stats['total'] > 0 else 0
            stats['avg_duration'] = stats['total_duration'] / stats['total'] if stats['total'] > 0 else 0
        
        return benchmark_stats
    
    def print_summary(self):
        """Print a summary of the benchmark results."""
        if not self.results:
            logger.info("No results to summarize")
            return
        
        total = len(self.results)
        successful = sum(1 for r in self.results if r['success'])
        total_duration = sum(r['duration'] for r in self.results)
        
        # Check if we ran with both DK settings
        dk_settings = set(r['domain_knowledge'] for r in self.results)
        
        print(f"\n{'='*60}")
        print("MINIMAL COST BENCHMARK SUMMARY")
        print(f"{'='*60}")
        print(f"Total benchmarks run: {total}")
        print(f"Successful: {successful}/{total} ({successful/total*100:.1f}%)")
        print(f"Total duration: {total_duration:.1f} seconds ({total_duration/60:.1f} minutes)")
        print(f"Average duration per benchmark: {total_duration/total:.1f} seconds")
        
        # Show domain knowledge settings used
        if len(dk_settings) > 1:
            print(f"Domain knowledge settings: BOTH (enabled and disabled)")
        elif True in dk_settings:
            print(f"Domain knowledge: ENABLED")
        else:
            print(f"Domain knowledge: DISABLED")
        
        # Summary by model
        print(f"\n{'='*60}")
        print("RESULTS BY MODEL:")
        print(f"{'='*60}")
        model_summary = self._summarize_by_model()
        
        # Check if we have both DK settings
        has_both_dk = len(dk_settings) > 1
        
        for model, stats in model_summary.items():
            print(f"\n{model}:")
            if has_both_dk:
                # Show separate stats for each DK setting
                with_dk = [r for r in self.results if r['model'] == model and r['domain_knowledge']]
                without_dk = [r for r in self.results if r['model'] == model and not r['domain_knowledge']]
                
                if with_dk:
                    success_with = sum(1 for r in with_dk if r['success'])
                    print(f"  With DK: {success_with}/{len(with_dk)} ({success_with/len(with_dk)*100:.1f}%)")
                
                if without_dk:
                    success_without = sum(1 for r in without_dk if r['success'])
                    print(f"  Without DK: {success_without}/{len(without_dk)} ({success_without/len(without_dk)*100:.1f}%)")
                
                print(f"  Overall: {stats['successful']}/{stats['total']} ({stats['success_rate']*100:.1f}%)")
            else:
                print(f"  Success rate: {stats['successful']}/{stats['total']} ({stats['success_rate']*100:.1f}%)")
            
            print(f"  Avg duration: {stats['avg_duration']:.1f}s")
            print(f"  Benchmarks: {', '.join(set(stats['benchmarks']))}")
        
        # Summary by benchmark type
        print(f"\n{'='*60}")
        print("RESULTS BY BENCHMARK TYPE:")
        print(f"{'='*60}")
        benchmark_summary = self._summarize_by_benchmark()
        for benchmark, stats in benchmark_summary.items():
            print(f"\n{benchmark}:")
            if has_both_dk:
                # Show separate stats for each DK setting
                with_dk = [r for r in self.results if r['benchmark_type'] == benchmark and r['domain_knowledge']]
                without_dk = [r for r in self.results if r['benchmark_type'] == benchmark and not r['domain_knowledge']]
                
                if with_dk:
                    success_with = sum(1 for r in with_dk if r['success'])
                    print(f"  With DK: {success_with}/{len(with_dk)} ({success_with/len(with_dk)*100:.1f}%)")
                
                if without_dk:
                    success_without = sum(1 for r in without_dk if r['success'])
                    print(f"  Without DK: {success_without}/{len(without_dk)} ({success_without/len(without_dk)*100:.1f}%)")
                
                print(f"  Overall: {stats['successful']}/{stats['total']} ({stats['success_rate']*100:.1f}%)")
            else:
                print(f"  Success rate: {stats['successful']}/{stats['total']} ({stats['success_rate']*100:.1f}%)")
            
            print(f"  Avg duration: {stats['avg_duration']:.1f}s")
            print(f"  Models tested: {', '.join(set(stats['models']))}")
        
        print(f"\n{'='*60}")
        # Estimate cost (each experiment costs ~$0.50)
        estimated_cost = total * 0.50
        print(f"Estimated total cost: ~${estimated_cost:.2f}")
        if has_both_dk:
            print(f"  (Includes both DK settings: {total//2} tasks × 2 settings)")
        print(f"{'='*60}\n")


def main():
    """Main entry point for minimal cost benchmark."""
    parser = argparse.ArgumentParser(description='Minimal cost benchmark for paper evaluation')
    
    # Remove choices to allow any model including claude-cli-*
    parser.add_argument('--models', nargs='+',
                       help='Models to benchmark (e.g., gpt-4o-mini, claude-cli-sonnet, etc.)')
    
    parser.add_argument('--benchmark-types', nargs='+',
                       choices=['pseudotime', 'clustering', 'annotation', 'spatial', 'spatial-case-1', 'perturb-seq', 'perturb-seq-v2', 'perturb-norman-analysis'],
                       help='Benchmark types to run (default: all)')
    
    parser.add_argument('--output-dir', type=str, default='paper_benchmark_minimal',
                       help='Output directory for results')
    
    parser.add_argument('--save-prefix', type=str,
                       help='Prefix for saved results file')
    
    parser.add_argument('--no-domain-knowledge', action='store_true',
                       help='Disable domain knowledge (default: enabled)')
    
    parser.add_argument('--both-dk-settings', action='store_true',
                       help='Run experiments both WITH and WITHOUT domain knowledge (doubles the number of experiments)')
    
    parser.add_argument('--enable-claude-cli-WebSearch', action='store_true',
                       help='Enable WebSearch tool for Claude CLI models (default: disabled)')
    
    parser.add_argument('--max-nodes', type=int, default=None,
                       help='Maximum number of nodes in the analysis tree (default: varies by benchmark type)')
    
    parser.add_argument('--docker-execution-timeout', type=int, default=None,
                       help='Docker execution timeout in seconds (default: 1800 = 30 minutes)')
    
    parser.add_argument('--debug-turns', type=int, default=None,
                       help=f'Number of debug turns per bug fixer session (default: {DEFAULT_DEBUG_TURNS})')
    
    parser.add_argument('--max-trials', type=int, default=None,
                       help=f'Maximum number of bug fixer sessions per node (default: {DEFAULT_MAX_TRIALS})')
    
    parser.add_argument('--seed', type=int, default=None,
                       help=f'Random seed for reproducibility (default: {DEFAULT_SEED})')
    
    parser.add_argument('--max-iterations', type=int, default=None,
                       help=f'Maximum planning iterations for orchestrator (default: {DEFAULT_MAX_ITERATIONS})')
    
    args = parser.parse_args()
    
    # Initialize runner
    runner = MinimalBenchmarkRunner(
        output_base_dir=args.output_dir, 
        max_nodes=args.max_nodes, 
        docker_execution_timeout=args.docker_execution_timeout,
        debug_turns=args.debug_turns,
        max_trials=args.max_trials,
        seed=args.seed,
        max_iterations=args.max_iterations
    )
    
    # Check if any models are Claude CLI models and patch if needed
    if args.models:
        has_cli_models = any(model.startswith('claude-cli') for model in args.models)
        if has_cli_models:
            logger.info("Using Claude CLI models with native MainAgent support...")
    
    # Run minimal benchmark suite
    try:
        if args.both_dk_settings:
            # Run experiments with both domain knowledge settings
            logger.info("Running experiments with BOTH domain knowledge settings...")
            
            # First run with domain knowledge enabled
            logger.info("\n" + "="*60)
            logger.info("PHASE 1: WITH domain knowledge")
            logger.info("="*60)
            results_with_dk = runner.run_minimal_suite(
                models=args.models,
                benchmark_types=args.benchmark_types,
                enable_domain_knowledge=True,
                enable_claude_cli_websearch=args.enable_claude_cli_WebSearch
            )
            
            # Then run with domain knowledge disabled
            logger.info("\n" + "="*60)
            logger.info("PHASE 2: WITHOUT domain knowledge")
            logger.info("="*60)
            results_without_dk = runner.run_minimal_suite(
                models=args.models,
                benchmark_types=args.benchmark_types,
                enable_domain_knowledge=False,
                enable_claude_cli_websearch=args.enable_claude_cli_WebSearch
            )
            
            # Combine results
            all_results = results_with_dk + results_without_dk
            runner.results = all_results  # Update runner's results for saving
            
        else:
            # Single run with specified domain knowledge setting
            results = runner.run_minimal_suite(
                models=args.models,
                benchmark_types=args.benchmark_types,
                enable_domain_knowledge=not args.no_domain_knowledge,
                enable_claude_cli_websearch=args.enable_claude_cli_WebSearch
            )
        
        # Save results
        if args.save_prefix:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{args.save_prefix}_{timestamp}.json"
        else:
            filename = None
        
        results_file = runner.save_results(filename)
        
        # Print summary
        runner.print_summary()
        
        print(f"\n✅ Minimal cost benchmark completed successfully!")
        print(f"📊 Results saved to: {results_file}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())