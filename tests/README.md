# Tests

This directory contains the tests of an **early-stage research prototype**. Coverage is uneven, and many files are
manual diagnostic or exploratory scripts written during development. Some may be out of date with the current code.

## Running

```bash
# From the repository root
pip install -r requirements.txt
pytest tests/ -m "not llm_required and not benchmark"
```

`tests/conftest.py` puts the repository root on `sys.path`.

## Layout

| Directory | Contents | Needs |
|-----------|----------|-------|
| `tests/*.py`, `tests/unit/` | Unit and mock-based tests of models, agents and utilities | nothing external |
| `tests/agents/` | Agent tests (mock LLM job-reviewer tests; scVelo pipeline smoke test skips without data/Docker) | `test_main_agent_simple.py` needs Docker and test data |
| `tests/code_agent/`, `tests/bug_fixer/` | Bug-fixer tests (mostly mocked LLM responses) | some need `OPENAI_API_KEY` |
| `tests/integration/` | Integration and exploratory scripts | Docker images (`docker/build.sh`), API keys, test data |
| `tests/domain_fb/` | Docker-based tests of the example pseudotime function blocks | Docker, test data |
| `tests/benchmarks/` | Benchmark drivers (execution-completion heuristics, not accuracy) | API keys, Docker, test data |
| `tests/llm_required/`, `tests/misc/`, `tests/creator/` | Manual scripts that call real LLM APIs and/or Docker. **Excluded from default pytest collection** (see `pytest.ini`); run them directly with `python`. | API keys, Docker |

Mock-based tests use scripted LLM/executor responses; they check plumbing and must not be read as evidence of
LLM or bug-fixer efficacy.

## Test data

Tests that need data read it from `$TEST_DATA_DIR` (default: `test_data/` relative to the working directory),
e.g. `test_data/zebrafish.h5ad` or `test_data/pbmc3k_processed.h5ad`. These datasets are not shipped with this
repository; use any public single-cell dataset in AnnData format (e.g. the 10x PBMC 3k dataset via
`scanpy.datasets.pbmc3k_processed()`).

## Cleaning outputs

```bash
bash tests/clean_test_outputs.sh
```
