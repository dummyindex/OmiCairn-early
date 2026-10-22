# Job Reviewer Agent

The Job Reviewer Agent is a quality assurance component that validates completed function blocks to ensure code quality and prevent placeholder implementations.

## Overview

The Job Reviewer Agent automatically reviews completed nodes in the analysis tree to detect:
- Generated code that fakes the analysis or uses placeholders (e.g., hardcoded results)
- Incomplete implementations
- Machine learning best practice violations
- Implementation mismatches with requirements
- **Output validation mismatches** (claims vs actual files)

### Enhanced Output Validation (NEW)

The Job Reviewer now performs rigorous output validation:
- Compares claimed outputs in stdout against actual files in the output directory
- Detects commented-out save operations (e.g., `# plt.savefig()`)
- Identifies when code prints success messages without actually creating files
- Validates that promised figures/files actually exist

## How It Works

### Integration with Orchestrator

The Job Reviewer is integrated into the Orchestrator Agent's execution flow:

1. When a node completes successfully, the orchestrator checks if the job reviewer is enabled
2. If the node's execution result contains an `ExecutionResult` object, the job reviewer is invoked
3. The reviewer analyzes the function block code, execution results, and output files
4. Review results are saved to the node's directory and used for planning decisions

### Execution Flow

```python
# In orchestrator_agent.py _handle_node_completion()
if self.job_reviewer and 'execution_result' in result:
    review_result = self.job_reviewer.review_function_block(
        node=node,
        function_block=node.function_block,
        execution_result=result.get('execution_result'),
        user_request=self.current_user_request,
        output_files=result.get('output_files', [])
    )
```

## Technical Implementation

### Node Executor Changes

To enable job review, the node executors were updated to return `ExecutionResult` objects:

```python
# NodeExecutor.execute_node() now returns:
def execute_node(...) -> Tuple[NodeState, Optional[str], Optional[ExecutionResult]]:
    # Execute function block
    result = self.executor_manager.execute(...)
    
    # Return state, output path, and execution result
    return NodeState.COMPLETED, str(outputs_dir), result
```

### Job Review Criteria

**IMPORTANT: Node-Specific Evaluation**

The Job Reviewer evaluates each node ONLY against its specific task description, NOT against the entire user request. Each node in the analysis tree has a specific responsibility, and the review verifies that the individual node completes its assigned task correctly.

For example:
- If a node's task is "Perform scFates pseudotime analysis", it will ONLY be evaluated on whether it correctly implements scFates
- It will NOT be penalized for not implementing other methods (DPT, Palantir, etc.) that may be mentioned in the overall user request
- The overall user request is provided for context only

The Job Reviewer evaluates code based on:

1. **Code Quality**
   - No placeholder implementations
   - No hardcoded mock data
   - Actual algorithmic implementation for the node's specific task

2. **Output Validation** (NEW)
   - Verifies claimed outputs actually exist
   - Detects commented-out save operations
   - Compares stdout claims against actual files
   - Ensures figures/plots are actually saved

3. **Machine Learning Best Practices** (Only for ML nodes)
   - Non-ML nodes (data loading, preprocessing, visualization) automatically get a perfect ML score
   - For ML nodes:
     - Proper data preprocessing
     - Model evaluation metrics
     - Cross-validation when appropriate
     - Feature engineering documentation

3. **Implementation Completeness**
   - The node's specific functionality implemented
   - Proper error handling
   - Output files generated as expected for this node's task

## Configuration

The Job Reviewer is initialized in MainAgent:

```python
agent = MainAgent(
    openai_api_key="your-key",
    # Job reviewer is automatically enabled when LLM service is available
)
```

## Output Files

When a node is reviewed, the following files are created in the node's directory:

- `agent_tasks/job_reviewer/review_result.json` - Structured review results
- `agent_tasks/job_reviewer/review_report.md` - Human-readable review report

## Review Result Structure

```json
{
  "passed": true,
  "concerns": [
    {
      "type": "placeholder",
      "severity": "warning",
      "description": "Function may contain placeholder code",
      "evidence": "# TODO: implement actual logic",
      "suggested_fix": "Implement the actual analysis logic"
    }
  ],
  "recommendations": {
    "improvements": ["Add input validation", "Include error handling"]
  },
  "ml_best_practices": {
    "applies_to_node": false,
    "has_train_test_split": null,
    "handles_data_leakage": null,
    "appropriate_validation": null,
    "hyperparameter_handling": null
  },
  "summary": "Code passed review with minor concerns"
}
```

## Rework Triggering

If the Job Reviewer identifies critical issues:

1. The review result indicates `should_trigger_rework = True`
2. The orchestrator generates a rework specification
3. The function creator receives enhanced requirements to address the issues
4. A new node is created with explicit instructions to avoid the identified problems

## Best Practices

1. **Enable Job Review for Production Pipelines**
   - Ensures code quality standards are met
   - Prevents placeholder implementations from being accepted

2. **Review Reports for Debugging**
   - Check review reports when nodes behave unexpectedly
   - Use concerns and recommendations to improve implementations

3. **Iterative Improvement**
   - Failed reviews provide specific feedback
   - Subsequent attempts receive enhanced requirements

## Troubleshooting

### Job Reviewer Not Running

If the job reviewer is not being invoked:

1. Check that the LLM service is properly initialized
2. Verify that nodes are completing successfully (failed nodes are not reviewed)
3. Ensure the orchestrator is receiving ExecutionResult objects from node execution

### Review Results Not Saved

If review files are missing:

1. Check node directory permissions
2. Verify the `agent_tasks` directory exists
3. Check logs for save_reports_to_directory errors

## Testing

Run the job reviewer tests to verify functionality:

```bash
# Run the job reviewer tests
python -m pytest tests/agents/test_job_reviewer_complete.py -v
```

## Technical Details

### Enhanced Execution Context

The Job Reviewer now receives comprehensive execution context:

```python
{
    "node_id": "...",
    "execution_success": true,
    "output_files": [],  # From execution result
    "actual_output_files": ["file1.csv", "figures/plot.png"],  # Actual files in directory
    "actual_figures": ["figures/plot.png"],  # Actual figure files
    "output_claims_in_stdout": ["Saved to file.png", ...],  # Claims detected in stdout
    "has_suspicious_patterns": false,  # Detects "placeholder", "todo", etc.
    "shows_computation": true  # Detects computation indicators
}
```

This enhanced context enables the reviewer to:
- Compare what the code claims to save vs what actually exists
- Detect placeholder patterns and incomplete implementations
- Validate that computational work was actually performed

## Future Enhancements

- Configurable review criteria per domain
- Custom review rules via configuration
- Integration with code quality metrics
- Automated fix suggestions for common issues