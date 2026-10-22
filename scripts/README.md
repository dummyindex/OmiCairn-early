# Scripts Directory

Benchmark drivers, example invocations and developer analysis utilities for this early-stage research prototype.
Most scripts need API keys (see `../.env.example`), the Docker images built with `docker/build.sh`, and input data
under `test_data/` (not shipped; see `tests/README.md`).

## benchmarks/
- `run_general_benchmark.py` - Runs the main agent end to end on predefined single-cell tasks (pseudotime,
  clustering, cell-type annotation, spatial transcriptomics, Perturb-seq) or a custom request.
- `paper_benchmark_minimal.sh` / `paper_benchmark_minimal_cost.py` - Runs each task once per model with fixed
  default hyperparameters (see `README_MINIMAL_BENCHMARK.md`).
- `paper_benchmark_comprehensive.py` / `.sh` - Parameter-sweep benchmark runner.
- `run_paper_minimal_examples.sh` - Example invocations of `paper_benchmark_minimal.sh`.
- `run_single_pseudotime.sh` - Single low-cost pseudotime run.
- `perturb_benchmark_request.md` - Perturb-seq task description.

The benchmark "success" flags measure execution completion (nodes and outputs produced), not the scientific
accuracy of the generated analyses.

## tests/
- `test_cli_clustering.sh` - Example CLI clustering run.

## analysis/
- `analyze_expensive_requests.py` - LLM request cost analysis from debug logs
- `detailed_token_analysis.py` - Token usage analysis (reads `$TEST_OUTPUTS_DIR`, default `test_outputs/`)
- `visualize_token_usage.py` - Token usage visualization

## Top level
- `test_simple_web_agent_benchmark.py`, `test_web_agent_direct.py` - Manual web-agent demos (need `OPENAI_API_KEY`).

## Usage

Run from the project root, for example:

```bash
python scripts/benchmarks/run_general_benchmark.py --help
bash scripts/benchmarks/run_single_pseudotime.sh
python scripts/analysis/analyze_expensive_requests.py
```
