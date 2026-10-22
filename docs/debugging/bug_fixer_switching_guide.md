# Bug Fixer Switching Guide

## Available Bug Fixer Types

The OmiCairn Agent framework supports three types of bug fixers:

1. **Standard (GPT-based)**: `bug_fixer_type="standard"`
2. **Claude LLM**: `bug_fixer_type="claude"`
3. **Claude Code SDK**: `bug_fixer_type="claude_code_sdk"`

## How to Switch Bug Fixers

### Method 1: Configuration Parameter

When initializing the MainAgent:

```python
from agents.main_agent import MainAgent

# Use GPT-based bug fixer (default)
agent = MainAgent(
    bug_fixer_type="standard",
    openai_api_key="your-openai-key"
)

# Use Claude LLM multi-turn bug fixer
agent = MainAgent(
    bug_fixer_type="claude",
    claude_api_key="your-anthropic-key"
)

# Use Claude Code SDK bug fixer
agent = MainAgent(
    bug_fixer_type="claude_code_sdk",
    claude_api_key="your-anthropic-key"
)
```

### Method 2: Environment Variables

Set environment variables before running:

```bash
# For GPT-based bug fixer
export BUG_FIXER_TYPE="standard"
export OPENAI_API_KEY="your-openai-key"

# For Claude LLM bug fixer
export BUG_FIXER_TYPE="claude"
export ANTHROPIC_API_KEY="your-anthropic-key"

# For Claude Code SDK bug fixer
export BUG_FIXER_TYPE="claude_code_sdk"
export ANTHROPIC_API_KEY="your-anthropic-key"
```

### Method 3: In Scripts

For benchmark scripts or test runs:

```python
# Example: run_pseudotime_benchmark.py
if __name__ == "__main__":
    # Choose your bug fixer type
    bug_fixer_type = "standard"  # or "claude" or "claude_code_sdk"
    
    agent = MainAgent(
        bug_fixer_type=bug_fixer_type,
        # ... other parameters
    )
```

## Bug Fixer Comparison

> Note: the `unified` bug fixer is the current default; the `standard` and `claude` types described here are legacy
> options. Success rates and costs were not systematically benchmarked in this early research version.

| Feature | Standard (GPT) | Claude LLM | Claude Code SDK |
|---------|----------------|------------|------------------|
| **Model** | GPT-4/GPT-3.5 | Claude 3 | Claude (via SDK) |
| **Implementation** | ~300 lines | ~500 lines | ~100 lines |
| **Context Management** | Manual | Manual, sophisticated | Automatic by SDK |
| **Multi-turn Support** | Yes | Yes, advanced | Yes, built-in |
| **Tool Usage** | JSON actions | JSON actions | Direct SDK tools |
| **Output Truncation** | Manual | Manual | Automatic |
| **Web Search** | No | No | No (future) |
| **History Context** | Yes | Yes | No (future) |

## Recommendations

### Use Standard (GPT) Bug Fixer When:
- You have OpenAI API access
- Cost is less of a concern
- Working with general Python errors

### Use Claude LLM Bug Fixer When:
- You need sophisticated multi-turn conversations
- Complex debugging scenarios
- Better context understanding required
- You have Anthropic API access

### Use Claude Code SDK Bug Fixer When:
- Token efficiency is critical
- Simple file-based fixes needed
- You want minimal implementation complexity
- You have Claude Code CLI installed

## Example: Running Benchmarks with Different Bug Fixers

```python
# run_comparison_benchmark.py
import asyncio
from agents.main_agent import MainAgent
import time

async def run_benchmark_with_bug_fixer(bug_fixer_type: str):
    """Run benchmark with specified bug fixer."""
    print(f"\n{'='*60}")
    print(f"Running benchmark with {bug_fixer_type} bug fixer")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    
    agent = MainAgent(
        bug_fixer_type=bug_fixer_type,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        claude_api_key=os.getenv("ANTHROPIC_API_KEY"),
        max_debug_trials=3
    )
    
    # Run your analysis
    result = await agent.process_request(
        request="Your analysis request here",
        input_dir="path/to/input",
        output_dir="path/to/output"
    )
    
    duration = time.time() - start_time
    
    print(f"\nCompleted in {duration:.1f} seconds")
    print(f"Success: {result.get('success', False)}")
    
    return result

# Compare all three bug fixers
async def main():
    for bug_fixer in ["standard", "claude", "claude_code_sdk"]:
        await run_benchmark_with_bug_fixer(bug_fixer)

if __name__ == "__main__":
    asyncio.run(main())
```

## Troubleshooting

### Standard Bug Fixer Issues
- **No API Key**: Set `OPENAI_API_KEY` environment variable
- **Rate Limits**: Implement exponential backoff
- **Model Access**: Ensure you have GPT-4 access for better results

### Claude LLM Bug Fixer Issues
- **No API Key**: Set `ANTHROPIC_API_KEY` environment variable
- **High Token Usage**: Consider Claude Code SDK for efficiency
- **Complex Errors**: May need multiple attempts

### Claude Code SDK Bug Fixer Issues
- **CLI Not Found**: Install with `npm install -g @anthropic-ai/claude-code`
- **No History Context**: Currently starts fresh each attempt
- **API Errors**: May struggle without documentation access

## Best Practices

1. **Start with Standard**: For general debugging, start with the standard GPT bug fixer
2. **Upgrade to Claude LLM**: For complex multi-file issues
3. **Use SDK for Efficiency**: When token costs are a concern
4. **Monitor Success Rates**: Track which bug fixer works best for your use cases
5. **Combine Approaches**: Use different bug fixers for different error types
