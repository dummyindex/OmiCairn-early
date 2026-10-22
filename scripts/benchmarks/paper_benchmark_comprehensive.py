#!/usr/bin/env python3
"""
Comprehensive benchmarking script for technical paper evaluation.
Tests multiple LLM models, parameters, and benchmark types to generate data for paper figures.
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Any
import argparse

# Add the omicairn_agent_local directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scripts.benchmarks.run_general_benchmark import (
    run_pseudotime_benchmark,
    run_clustering_benchmark, 
    run_cell_type_annotation_benchmark,
    run_spatial_analysis_case_1_benchmark
)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Silence noisy loggers
for logger_name in ['urllib3', 'docker', 'requests', 'openai', 'httpx', 'httpcore', 'httpcore.http11']:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

class BenchmarkResult:
    """Container for benchmark result data."""
    def __init__(self, benchmark_type: str, model: str, debug_turns: int, max_trials: int, 
                 domain_knowledge: bool = True, seed: int = 31):
        self.benchmark_type = benchmark_type
        self.model = model
        self.debug_turns = debug_turns
        self.max_trials = max_trials
        self.domain_knowledge = domain_knowledge
        self.seed = seed
        self.success = False
        self.duration = 0.0
        self.timestamp = None
        self.output_dir = None
        self.config_id = None
        self.error = None
        self.node_stats = None
        self.output_quality = None
        self.raw_results = None
        self.agent_hyperparameters = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'benchmark_type': self.benchmark_type,
            'model': self.model,
            'debug_turns': self.debug_turns,
            'max_trials': self.max_trials,
            'domain_knowledge': self.domain_knowledge,
            'seed': self.seed,
            'success': self.success,
            'duration': self.duration,
            'timestamp': self.timestamp,
            'output_dir': str(self.output_dir) if self.output_dir else None,
            'error': self.error,
            'node_stats': self.node_stats,
            'output_quality': self.output_quality,
            'raw_results': self.raw_results,
            'agent_hyperparameters': self.agent_hyperparameters
        }

class ComprehensiveBenchmarkRunner:
    """Comprehensive benchmark runner for paper evaluation."""
    
    # Predefined seeds for reproducibility
    REPRODUCIBILITY_SEEDS = [31, 42, 123]  # Three different seeds for statistical analysis
    
    def __init__(self, output_base_dir: str = "paper_benchmark_outputs"):
        self.output_base_dir = Path(output_base_dir)
        self.output_base_dir.mkdir(parents=True, exist_ok=True)
        self.results: List[BenchmarkResult] = []
        self.start_time = datetime.now()
        
    def get_models_config(self) -> Dict[str, List[str]]:
        """Get available models for benchmarking."""
        return {
            'openai': ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo'],
            'claude': ['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022']  # If Claude API key available
        }
    
    def get_parameter_grid(self) -> List[Dict[str, Any]]:
        """Define parameter grid for systematic evaluation."""
        return [
            # Minimal debugging - fast iteration
            {'debug_turns': 3, 'max_trials': 2},
            {'debug_turns': 5, 'max_trials': 2}, 
            
            # Standard debugging - balanced
            {'debug_turns': 5, 'max_trials': 3},
            {'debug_turns': 10, 'max_trials': 3},
            
            # Extended debugging - thorough
            {'debug_turns': 10, 'max_trials': 5},
            {'debug_turns': 15, 'max_trials': 3},
        ]
    
    def get_benchmark_types(self) -> List[str]:
        """Get benchmark types to run."""
        return ['pseudotime', 'clustering', 'annotation', 'spatial-case-1']
    
    def run_single_benchmark(self, benchmark_type: str, model: str, debug_turns: int, max_trials: int,
                            domain_knowledge: bool = True, seed: int = 31) -> BenchmarkResult:
        """Run a single benchmark configuration."""
        result = BenchmarkResult(benchmark_type, model, debug_turns, max_trials, domain_knowledge, seed)
        result.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        logger.info(f"Starting {benchmark_type} benchmark with {model}, {debug_turns} turns, {max_trials} trials, "
                   f"domain_knowledge={domain_knowledge}, seed={seed}")
        
        try:
            start_time = time.time()
            
            # Set model-specific API key
            if model.startswith('claude'):
                if not os.getenv('CLAUDE_API_KEY'):
                    result.error = "CLAUDE_API_KEY not available"
                    return result
            else:
                if not os.getenv('OPENAI_API_KEY'):
                    result.error = "OPENAI_API_KEY not available" 
                    return result
            
            # Generate unique suffix for this configuration to prevent folder collisions
            config_id = f"{model.replace('-', '_').replace('.', '_')}_{debug_turns}t_{max_trials}m_s{seed}"
            if not domain_knowledge:
                config_id += "_noDK"
            result.config_id = config_id
            
            # Run the appropriate benchmark
            if benchmark_type == 'pseudotime':
                success = run_pseudotime_benchmark(
                    llm_model=model,
                    debug_turns=debug_turns,
                    max_debug_trials=max_trials,
                    enable_domain_knowledge=domain_knowledge,
                    seed=seed,
                    output_suffix=config_id,
                    output_base_dir=str(self.output_base_dir)
                )
            elif benchmark_type == 'clustering':
                success = run_clustering_benchmark(
                    llm_model=model,
                    debug_turns=debug_turns, 
                    max_debug_trials=max_trials,
                    enable_domain_knowledge=domain_knowledge,
                    seed=seed,
                    output_suffix=config_id,
                    output_base_dir=str(self.output_base_dir)
                )
            elif benchmark_type == 'annotation':
                success = run_cell_type_annotation_benchmark(
                    llm_model=model,
                    debug_turns=debug_turns,
                    max_debug_trials=max_trials,
                    enable_domain_knowledge=domain_knowledge,
                    seed=seed,
                    output_suffix=config_id,
                    output_base_dir=str(self.output_base_dir)
                )
            elif benchmark_type in ['spatial-case-1', 'spatial-analysis-case-1']:  # Support both names
                success = run_spatial_analysis_case_1_benchmark(
                    llm_model=model,
                    debug_turns=debug_turns,
                    max_debug_trials=max_trials,
                    enable_domain_knowledge=domain_knowledge,
                    seed=seed,
                    output_suffix=config_id,
                    output_base_dir=str(self.output_base_dir)
                )
            else:
                result.error = f"Unknown benchmark type: {benchmark_type}"
                return result
            
            result.success = success
            result.duration = time.time() - start_time
            
            # Extract additional metrics from the benchmark output directory
            self._extract_detailed_metrics(result)
            
            # Extract hyperparameters from agent_info.json if available
            self._extract_hyperparameters(result)
            
        except Exception as e:
            result.error = str(e)
            result.duration = time.time() - start_time
            logger.error(f"Benchmark failed: {e}")
        
        return result
    
    def _extract_detailed_metrics(self, result: BenchmarkResult):
        """Extract detailed metrics from benchmark output."""
        try:
            # Find the output directory of THIS configuration (matched on its unique
            # config_id suffix, not on modification time, so parallel runs are not mixed up)
            config_id = getattr(result, 'config_id', None)
            if not config_id:
                logger.warning("No config_id recorded; cannot attribute output directory")
                return
            # Output folders use underscores (e.g. spatial_case_1_<ts>_<id>), not the CLI name
            dir_prefix = {'spatial-case-1': 'spatial_case_1', 'spatial-analysis-case-1': 'spatial_case_1'}.get(
                result.benchmark_type, result.benchmark_type)
            output_pattern = f"{self.output_base_dir}/{dir_prefix}_*_{config_id}"
            from glob import glob
            dirs = sorted(glob(output_pattern), key=os.path.getmtime, reverse=True)
            if len(dirs) > 1:
                logger.warning(f"Multiple output dirs match {output_pattern}; using the most recent")
            
            if dirs:
                result.output_dir = Path(dirs[0])
                
                # Look for results JSON file
                for json_file in result.output_dir.glob("*_results.json"):
                    try:
                        with open(json_file, 'r') as f:
                            data = json.load(f)
                            result.node_stats = data.get('node_statistics')
                            result.output_quality = data.get('output_quality')
                            result.raw_results = data
                            break
                    except Exception as e:
                        logger.warning(f"Could not parse {json_file}: {e}")
        except Exception as e:
            logger.warning(f"Could not extract detailed metrics: {e}")
    
    def _extract_hyperparameters(self, result: BenchmarkResult):
        """Extract hyperparameters from agent_info.json files."""
        try:
            # Look for agent_info.json files in main task directories
            from glob import glob
            
            # Only look inside this configuration's own output directory
            if not result.output_dir:
                logger.warning("No output directory attributed; skipping hyperparameter extraction")
                return
            main_pattern = f"{result.output_dir}/**/main_*"
            main_dirs = sorted(glob(main_pattern, recursive=True), key=os.path.getmtime, reverse=True)
            
            for main_dir in main_dirs[:3]:  # Check the 3 most recent
                agent_info_file = Path(main_dir) / "agent_info.json"
                if agent_info_file.exists():
                    try:
                        with open(agent_info_file, 'r') as f:
                            agent_info = json.load(f)
                            
                        # Extract relevant hyperparameters
                        hyperparams = agent_info.get('hyperparameters', {})
                        
                        # Store additional hyperparameters not already captured
                        result.agent_hyperparameters = {
                            'llm_model': agent_info.get('llm_model'),
                            'bug_fixer_type': agent_info.get('bug_fixer_type'),
                            'enable_domain_knowledge': agent_info.get('enable_domain_knowledge'),
                            'domain_knowledge_domains': agent_info.get('domain_knowledge_domains'),
                            'llm_seed': agent_info.get('llm_seed'),
                            'bug_fixer_max_turns': agent_info.get('bug_fixer_max_turns'),
                            'enable_web_agent': agent_info.get('enable_web_agent'),
                            'enable_interactive_debug': agent_info.get('enable_interactive_debug'),
                            'max_debug_trials': hyperparams.get('max_debug_trials'),
                            'max_iterations': hyperparams.get('max_iterations'),
                            'tree_id': agent_info.get('tree_id'),
                            'created_at': agent_info.get('created_at')
                        }
                        
                        logger.debug(f"Extracted hyperparameters from {agent_info_file}")
                        break  # Use the first (most recent) match
                        
                    except Exception as e:
                        logger.warning(f"Could not parse {agent_info_file}: {e}")
                        
        except Exception as e:
            logger.warning(f"Could not extract hyperparameters: {e}")
    
    def run_comprehensive_benchmarks(self, 
                                   models: List[str] = None,
                                   benchmark_types: List[str] = None,
                                   parameter_sets: List[Dict] = None,
                                   test_domain_knowledge: bool = True,
                                   seeds: List[int] = None,
                                   parallel: bool = True,
                                   max_workers: int = 2) -> List[BenchmarkResult]:
        """Run comprehensive benchmarks across multiple configurations."""
        
        # Use defaults if not specified
        if models is None:
            available_models = self.get_models_config()
            models = []
            if os.getenv('OPENAI_API_KEY'):
                models.extend(available_models['openai'])
            if os.getenv('CLAUDE_API_KEY'):
                models.extend(available_models['claude'])
            if not models:
                raise ValueError("No API keys available. Set OPENAI_API_KEY or CLAUDE_API_KEY")
        
        if benchmark_types is None:
            benchmark_types = self.get_benchmark_types()
            
        if parameter_sets is None:
            parameter_sets = self.get_parameter_grid()
        
        if seeds is None:
            seeds = self.REPRODUCIBILITY_SEEDS
        
        # Determine domain knowledge configurations to test
        domain_knowledge_configs = [True]
        if test_domain_knowledge:
            domain_knowledge_configs = [True, False]  # Test both with and without domain knowledge
        
        # Generate all benchmark configurations
        configurations = []
        for benchmark_type in benchmark_types:
            for model in models:
                for params in parameter_sets:
                    for domain_knowledge in domain_knowledge_configs:
                        for seed in seeds:
                            configurations.append((
                                benchmark_type, model, params['debug_turns'], 
                                params['max_trials'], domain_knowledge, seed
                            ))
        
        logger.info(f"Running {len(configurations)} benchmark configurations")
        logger.info(f"Models: {models}")
        logger.info(f"Benchmark types: {benchmark_types}")
        logger.info(f"Parameter sets: {len(parameter_sets)}")
        logger.info(f"Domain knowledge ablation: {test_domain_knowledge}")
        logger.info(f"Seeds for reproducibility: {seeds}")
        logger.info(f"Domain knowledge configs: {domain_knowledge_configs}")
        
        if parallel and max_workers > 1:
            # Run benchmarks in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_config = {
                    executor.submit(self.run_single_benchmark, *config): config
                    for config in configurations
                }
                
                for future in as_completed(future_to_config):
                    config = future_to_config[future]
                    try:
                        result = future.result()
                        self.results.append(result)
                        logger.info(f"Completed: {config[0]}/{config[1]} - Success: {result.success}")
                    except Exception as e:
                        logger.error(f"Configuration {config} failed: {e}")
        else:
            # Run benchmarks sequentially
            for config in configurations:
                result = self.run_single_benchmark(*config)
                self.results.append(result)
                logger.info(f"Completed: {config[0]}/{config[1]} - Success: {result.success}")
        
        return self.results
    
    def save_results(self, filename: str = None) -> Path:
        """Save comprehensive benchmark results."""
        if filename is None:
            timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
            filename = f"comprehensive_benchmark_results_{timestamp}.json"
        
        results_file = self.output_base_dir / filename
        
        summary_data = {
            'metadata': {
                'start_time': self.start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'total_benchmarks': len(self.results),
                'successful_benchmarks': sum(1 for r in self.results if r.success),
                'failed_benchmarks': sum(1 for r in self.results if not r.success),
            },
            'results': [r.to_dict() for r in self.results],
            'summary_stats': self._generate_summary_stats()
        }
        
        with open(results_file, 'w') as f:
            json.dump(summary_data, f, indent=2)
        
        logger.info(f"Results saved to: {results_file}")
        return results_file
    
    def _generate_summary_stats(self) -> Dict[str, Any]:
        """Generate summary statistics across all benchmarks."""
        if not self.results:
            return {}
        
        stats = {
            'success_rates': {},
            'duration_stats': {},
            'model_performance': {},
            'benchmark_type_performance': {},
            'parameter_effects': {}
        }
        
        # Success rates by various dimensions
        total = len(self.results)
        successful = sum(1 for r in self.results if r.success)
        stats['success_rates']['overall'] = successful / total if total > 0 else 0
        
        # By model
        model_stats = {}
        for result in self.results:
            model = result.model
            if model not in model_stats:
                model_stats[model] = {'total': 0, 'successful': 0}
            model_stats[model]['total'] += 1
            if result.success:
                model_stats[model]['successful'] += 1
        
        for model, data in model_stats.items():
            stats['model_performance'][model] = {
                'success_rate': data['successful'] / data['total'] if data['total'] > 0 else 0,
                'total_runs': data['total'],
                'successful_runs': data['successful']
            }
        
        # By benchmark type
        benchmark_stats = {}
        for result in self.results:
            benchmark_type = result.benchmark_type
            if benchmark_type not in benchmark_stats:
                benchmark_stats[benchmark_type] = {'total': 0, 'successful': 0}
            benchmark_stats[benchmark_type]['total'] += 1
            if result.success:
                benchmark_stats[benchmark_type]['successful'] += 1
        
        for benchmark_type, data in benchmark_stats.items():
            stats['benchmark_type_performance'][benchmark_type] = {
                'success_rate': data['successful'] / data['total'] if data['total'] > 0 else 0,
                'total_runs': data['total'],
                'successful_runs': data['successful']
            }
        
        # Duration statistics
        durations = [r.duration for r in self.results if r.duration > 0]
        if durations:
            stats['duration_stats'] = {
                'mean_duration': sum(durations) / len(durations),
                'min_duration': min(durations),
                'max_duration': max(durations),
                'total_duration': sum(durations)
            }
        
        return stats
    
    def print_summary(self):
        """Print a summary of benchmark results."""
        if not self.results:
            print("No benchmark results available.")
            return
        
        print(f"\n{'='*80}")
        print("COMPREHENSIVE BENCHMARK RESULTS SUMMARY")
        print(f"{'='*80}")
        
        total = len(self.results)
        successful = sum(1 for r in self.results if r.success)
        failed = total - successful
        
        print(f"Total Benchmarks: {total}")
        print(f"Successful: {successful} ({successful/total*100:.1f}%)")
        print(f"Failed: {failed} ({failed/total*100:.1f}%)")
        
        # Model performance
        print(f"\n{'='*40}")
        print("MODEL PERFORMANCE")
        print(f"{'='*40}")
        
        model_stats = {}
        for result in self.results:
            model = result.model
            if model not in model_stats:
                model_stats[model] = {'total': 0, 'successful': 0, 'durations': []}
            model_stats[model]['total'] += 1
            if result.success:
                model_stats[model]['successful'] += 1
            if result.duration > 0:
                model_stats[model]['durations'].append(result.duration)
        
        for model, stats in model_stats.items():
            success_rate = stats['successful'] / stats['total'] * 100
            avg_duration = sum(stats['durations']) / len(stats['durations']) if stats['durations'] else 0
            print(f"{model:20s} | {stats['successful']:2d}/{stats['total']:2d} ({success_rate:5.1f}%) | Avg: {avg_duration:6.1f}s")
        
        # Benchmark type performance
        print(f"\n{'='*40}")
        print("BENCHMARK TYPE PERFORMANCE")
        print(f"{'='*40}")
        
        benchmark_stats = {}
        for result in self.results:
            benchmark_type = result.benchmark_type
            if benchmark_type not in benchmark_stats:
                benchmark_stats[benchmark_type] = {'total': 0, 'successful': 0, 'durations': []}
            benchmark_stats[benchmark_type]['total'] += 1
            if result.success:
                benchmark_stats[benchmark_type]['successful'] += 1
            if result.duration > 0:
                benchmark_stats[benchmark_type]['durations'].append(result.duration)
        
        for benchmark_type, stats in benchmark_stats.items():
            success_rate = stats['successful'] / stats['total'] * 100
            avg_duration = sum(stats['durations']) / len(stats['durations']) if stats['durations'] else 0
            print(f"{benchmark_type:20s} | {stats['successful']:2d}/{stats['total']:2d} ({success_rate:5.1f}%) | Avg: {avg_duration:6.1f}s")
        
        print(f"\n{'='*80}")


def main():
    """Main function for comprehensive benchmarking."""
    parser = argparse.ArgumentParser(description="Comprehensive benchmarking for technical paper")
    parser.add_argument('--models', nargs='+', 
                       choices=['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo', 
                                'claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022'],
                       help="Models to test (default: all available)")
    parser.add_argument('--benchmark-types', nargs='+',
                       choices=['pseudotime', 'clustering', 'annotation', 'spatial-case-1', 'spatial-analysis-case-1'],
                       help="Benchmark types to run (default: all)")
    parser.add_argument('--quick', action='store_true',
                       help="Run quick benchmark with minimal parameters")
    parser.add_argument('--output-dir', default='paper_benchmark_outputs',
                       help="Output directory for results")
    parser.add_argument('--parallel', action=argparse.BooleanOptionalAction, default=True,
                       help="Run benchmarks in parallel (use --no-parallel to run sequentially)")
    parser.add_argument('--max-workers', type=int, default=2,
                       help="Maximum parallel workers")
    parser.add_argument('--save-prefix', default='comprehensive_benchmark',
                       help="Prefix for saved results file")
    parser.add_argument('--test-domain-knowledge', action='store_true', default=True,
                       help="Test both with and without domain knowledge for ablation study")
    parser.add_argument('--no-domain-knowledge-ablation', dest='test_domain_knowledge', action='store_false',
                       help="Skip domain knowledge ablation (only test with domain knowledge)")
    parser.add_argument('--seeds', nargs='+', type=int, default=[31, 42, 123],
                       help="Seeds for reproducibility (default: 31 42 123)")
    
    args = parser.parse_args()
    
    # Check API keys
    has_openai = bool(os.getenv('OPENAI_API_KEY'))
    has_claude = bool(os.getenv('CLAUDE_API_KEY'))
    
    print(f"\n{'='*80}")
    print("COMPREHENSIVE BENCHMARK RUNNER FOR TECHNICAL PAPER")
    print(f"{'='*80}")
    print(f"Available API Keys:")
    print(f"  - OpenAI: {'✅' if has_openai else '❌'}")
    print(f"  - Claude: {'✅' if has_claude else '❌'}")
    
    if not (has_openai or has_claude):
        print("\n❌ ERROR: No API keys available. Set OPENAI_API_KEY or CLAUDE_API_KEY")
        sys.exit(1)
    
    # Initialize runner
    runner = ComprehensiveBenchmarkRunner(output_base_dir=args.output_dir)
    
    # Configure parameters based on quick mode
    if args.quick:
        parameter_sets = [
            {'debug_turns': 3, 'max_trials': 2},
            {'debug_turns': 5, 'max_trials': 2}
        ]
    else:
        parameter_sets = runner.get_parameter_grid()
    
    print(f"\nRunning with configuration:")
    print(f"  - Models: {args.models or 'all available'}")
    print(f"  - Benchmark types: {args.benchmark_types or 'all'}")
    print(f"  - Parameter sets: {len(parameter_sets)}")
    print(f"  - Domain knowledge ablation: {args.test_domain_knowledge}")
    print(f"  - Seeds: {args.seeds}")
    print(f"  - Parallel execution: {args.parallel}")
    print(f"  - Max workers: {args.max_workers}")
    print(f"  - Output directory: {args.output_dir}")
    
    # Run benchmarks
    try:
        results = runner.run_comprehensive_benchmarks(
            models=args.models,
            benchmark_types=args.benchmark_types,
            parameter_sets=parameter_sets,
            test_domain_knowledge=args.test_domain_knowledge,
            seeds=args.seeds,
            parallel=args.parallel,
            max_workers=args.max_workers
        )
        
        # Print summary
        runner.print_summary()
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{args.save_prefix}_{timestamp}.json"
        results_file = runner.save_results(filename)
        
        print(f"\n🎉 Comprehensive benchmarking completed!")
        print(f"📊 Results saved to: {results_file}")
        print(f"📈 Ready for visualization and analysis")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()