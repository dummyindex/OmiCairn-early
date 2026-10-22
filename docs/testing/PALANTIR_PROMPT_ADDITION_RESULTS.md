# Palantir Prompt Addition Results

## Summary

Successfully added palantir-specific usage information to the function creator and bug fixer prompts, which resolved the import errors and improved code generation.

## Changes Made

### 1. Function Creator Agent
Added detailed palantir usage example to the system prompt:
```python
PALANTIR USAGE (Python pseudotime analysis):
Palantir is a Python package for pseudotime analysis. Here's how to use it correctly:
import palantir
pr_res = palantir.core.run_palantir(
    adata,
    early_cell=start_cell,
    num_waypoints=500,
    knn=30,
    use_early_cell_as_start=True
)
adata.obs['palantir_pseudotime'] = pr_res.pseudotime
IMPORTANT: Never use "from palantir import palantir" or "import palantir.palantir". The correct import is just "import palantir".
```

### 2. Bug Fixer Agent
Added palantir-specific fixes section:
```
PALANTIR SPECIFIC FIXES:
If you see errors related to palantir imports or usage:
- CORRECT: import palantir
- INCORRECT: from palantir import palantir
- INCORRECT: import palantir.palantir
- Usage: pr_res = palantir.core.run_palantir(adata, early_cell=start_cell, num_waypoints=500, knn=30)
- The result has attributes: pseudotime, entropy, branch_probs
- Store results: adata.obs['palantir_pseudotime'] = pr_res.pseudotime
```

## Results

### Before Palantir Prompts
- **Error**: `ImportError: cannot import name 'palantir' from 'palantir'`
- Generated incorrect imports: `from palantir import palantir`
- Test failed immediately on palantir nodes

### After Palantir Prompts
- ✓ Correct imports: `import palantir`
- ✓ Correct API usage: `palantir.core.run_palantir(...)`
- ✓ Correct result extraction: `pr_res.pseudotime`
- Test progresses further but encounters other issues

## Remaining Challenges

1. **Function Block Modularity**: LLM still tends to combine multiple pseudotime methods in one node
   - Example: DPT + PAGA + Palantir all in one function block
   - Violates "one task per function block" principle

2. **Preprocessing Redundancy**: Nodes sometimes repeat preprocessing steps unnecessarily
   - Running normalize_total and log1p multiple times
   - Warning: "adata.X seems to be already log-transformed"

3. **Import Errors**: Still some confusion with scipy.stats vs sklearn.metrics
   - kendalltau and spearmanr are in scipy.stats, not sklearn.metrics
   - Bug fixer successfully corrects this

## Effectiveness

Informal observations from our development runs (not a systematic benchmark):
- After the prompt addition, the palantir import errors no longer occurred in these runs
- The bug fixer was no longer needed to fix palantir import errors in these runs

## Recommendations

1. **Continue Iterative Refinement**: The approach works - domain-specific knowledge in prompts helps significantly

2. **Add More Package Examples**: Consider adding similar usage examples for:
   - scFates
   - CellRank
   - Other commonly misused packages

3. **Strengthen Modularity Enforcement**: Add more examples showing one method per node

4. **Pre-install Packages**: Consider adding palantir, cellrank to Docker image to reduce installation time

## Conclusion

Adding domain-specific knowledge to prompts is an effective way to improve LLM code generation for specialized bioinformatics packages. In the palantir example, providing correct import patterns and API usage examples removed the import errors observed in our informal development runs.