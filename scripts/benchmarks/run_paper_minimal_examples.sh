#!/usr/bin/env bash
# Example invocations of paper_benchmark_minimal.sh used during development of
# this early-stage research prototype.
#
# Requirements:
#   - Provide your own API keys (e.g. OPENAI_API_KEY, CLAUDE_API_KEY) in the
#     environment or in a local .env file (see .env.example). Never commit .env.
#   - Docker images built with docker/build.sh.
#
# Each block is independent; comment out the runs you do not need.
# Note: these benchmarks measure execution completion of the agent pipeline,
# not the scientific accuracy of the generated analyses.

set -euo pipefail

# Load variables from a local .env file if present
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

BENCH=./scripts/benchmarks/paper_benchmark_minimal.sh

# Clustering
$BENCH --tasks clustering --all-models --output-dir paper_benchmark_minimal/clustering
$BENCH --tasks clustering --all-models --output-dir paper_benchmark_minimal/clustering --no-domain-knowledge
$BENCH --tasks clustering --models claude-cli-sonnet claude-cli-haiku claude-cli-opus \
  --output-dir paper_benchmark_minimal/clustering --both-dk-settings

# Pseudotime
$BENCH --tasks pseudotime --all-models --output-dir paper_benchmark_minimal/pseudotime --both-dk-settings
$BENCH --tasks pseudotime --models claude-cli-sonnet claude-cli-haiku \
  --output-dir paper_benchmark_minimal/pseudotime --no-domain-knowledge

# Spatial transcriptomics (case 1)
$BENCH --tasks spatial-case-1 --models claude-cli-sonnet claude-cli-haiku claude-cli-opus \
  --output-dir paper_benchmark_minimal/spatial-case-1

# Perturb-seq
$BENCH --tasks perturb-norman-analysis --models claude-cli-sonnet claude-cli-haiku claude-cli-opus \
  --output-dir paper_benchmark_minimal/perturb-norman-analysis --no-domain-knowledge
$BENCH --tasks perturb-seq --models claude-cli-sonnet claude-cli-haiku claude-cli-opus --both-dk-settings
$BENCH --tasks perturb-seq-v2 --models claude-cli-sonnet claude-cli-haiku claude-cli-opus --both-dk-settings
