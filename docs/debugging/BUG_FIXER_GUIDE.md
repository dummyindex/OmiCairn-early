# Bug Fixer Guide

## Overview

The Bug Fixer is an **action-based debugging system** that automatically fixes errors in function blocks using **pure LLM-driven actions** with **no hardcoded pattern-matching solutions**. It operates directly within the same Docker container where the job is executing, using multi-turn debugging with optional web agent research capabilities.

## Architecture

### Current Default: Interactive Executor
By default (when `enable_interactive_debug=True`), the system uses:
- **InteractiveNodeExecutor**: Orchestrates node execution with debugging support
- **InteractiveExecutor**: Manages in-container debugging sessions
- **InContainerDebugSession**: Runs bug fixing logic inside the container
- **ContainerActionHandler**: Translates bug fixer actions to container commands

### Legacy Mode (To Be Removed)
The external bug fixing approach (where MainAgent fixes code outside containers) is deprecated and will be removed in future versions.

## Action-Based Debugging Philosophy

The bug fixer follows a **pure action-based approach**:

### Core Principles
1. **No Hardcoded Solutions**: Zero pattern-matching rules or preset fixes
2. **LLM-Driven Analysis**: All debugging decisions made by analyzing specific error context
3. **Dynamic Action Selection**: LLM determines which actions to take based on error analysis
4. **Validated Actions**: All operations go through structured, type-validated action schema
5. **Iterative Problem Solving**: Multi-turn debugging with LLM learning from each action result

### Available Actions
All actions include comprehensive field validation:
- `read_file`: Analyze code and configuration files (required: path)
- `write_file`: Modify specific files with targeted fixes (required: path, content)
- `execute_command`: Test imports, run diagnostics, check package availability (required: command)
- `install_package`: Install missing dependencies (required: package)
- `update_function_block`: Update entire function block with code and requirements (required: code; optional: requirements, language)
- `list_directory`: Explore workspace structure (optional: path)
- `grep_file`: Search for specific patterns in files (required: path, pattern)
- `head_file`/`tail_file`: Preview file contents or check logs (required: path; optional: lines)

### Why Action-Based?
- **Adaptability**: Can handle any error type without needing predefined solutions
- **Transparency**: Every debugging step is explicit and logged
- **Reliability**: Actions are validated and error-checked
- **Extensibility**: New action types can be added without changing core logic

## How It Works

**Key Innovation**: With InteractiveExecutor, the bug fixer operates INSIDE the same container as the failing job, allowing it to:
- Access the exact runtime environment
- See all installed packages and dependencies
- Modify code files directly in `/workspace`
- Re-execute the function block immediately after fixes
- Maintain the same file system state throughout debugging

## Key Components

### 1. Base Bug Fixer (`agents/base_bug_fixer.py`)
- Abstract base class defining the bug fixer interface
- Provides common error extraction utilities
- Ensures compatibility across different bug fixer implementations

### 2. Unified Bug Fixer (`agents/unified_bug_fixer/`)
- **Action-Based Implementation**: Uses only structured actions (read_file, write_file, execute_command, etc.)
- **No Pattern Matching**: Zero hardcoded solutions - all debugging decisions made by LLM
- **Dynamic Strategy**: LLM analyzes each error and determines appropriate action sequence
- **Multi-Model Support**: Compatible with OpenAI and Claude models
- **Web Research Integration**: Can research errors online and apply findings through actions
- **Multi-Turn Debugging**: Configurable retry limits with iterative problem solving
- **Wrapped JSON Schema**: Uses wrapped parameters format for OpenAI JSON mode compatibility
- **Field Validation**: All actions validated for required fields before execution

### 3. In-Container Execution
- Bug fixer runs inside the same Docker container as the job
- Modifies `/workspace/function_block.py` directly
- Has access to all installed packages and runtime state
- Changes persist for subsequent execution attempts

### 4. Web Agent Integration (`agents/web_agent_langgraph/`)
- Researches errors using web search and documentation
- Provides suggested fixes and code examples
- 90-second timeout with partial results on timeout

## Required Files and Structure

### Function Block Structure
```
node_directory/
├── code.py              # Main function code (required)
├── requirements.txt     # Python dependencies
├── config.json         # Function block configuration
└── web_agent_research/ # Web agent research results (auto-created)
    └── attempt_N/
        ├── research_report.md
        └── research_data.json
```

### Key File: `code.py`
The main function code must follow this structure:
```python
def run(path_dict, params):
    """Main function entry point.
    
    Args:
        path_dict: Dictionary with 'input_dir' and 'output_dir'
        params: Dictionary of parameters from config
    """
    # Read input
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    
    # Process data
    # ...
    
    # Write output
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
```

## How Bug Fixing Works

### 1. Error Detection
- Function block execution fails with non-zero exit code
- Container captures error message, stdout, and stderr
- Container remains running (doesn't exit)
- Bug fixer is invoked INSIDE the same container

### 2. In-Container Bug Fixing Process
The bug fixer runs within the container's Python environment:
```python
# Container's execution flow
try:
    # Initial execution attempt
    from function_block import run
    run(path_dict, params)
except Exception as e:
    # Bug fixer invoked here - INSIDE container
    bug_fixer = UnifiedBugFixer()
    fixed_code = bug_fixer.fix_error({
        'function_block': current_code,
        'error_message': str(e),
        'stdout': captured_stdout,
        'stderr': captured_stderr
    })
    
    # Write fixed code to /workspace/function_block.py
    with open('/workspace/function_block.py', 'w') as f:
        f.write(fixed_code)
    
    # Re-import and retry execution
    del sys.modules['function_block']
    from function_block import run
    run(path_dict, params)
```

### 3. Web Agent Research (if enabled)
- Triggered for complex errors (AttributeError, ModuleNotFoundError, etc.)
- Runs in parallel process to avoid blocking
- Searches web, GitHub, Stack Overflow for solutions
- Timeout: 90 seconds (configurable)
- Results passed back to bug fixer for implementation

### 4. Multi-Turn Debugging Actions

#### Action Format (Wrapped JSON Schema)
When using OpenAI models with JSON mode, actions use a wrapped format:
```json
{
    "type": "update_function_block",
    "params": {
        "code": "def run(path_dict, params): ...",
        "requirements": ["pandas", "numpy"]
    },
    "explanation": "Fixing import error",
    "confidence": 0.85
}
```

This format:
- Wraps all action-specific parameters in a `params` object
- Makes all parameters optional to satisfy OpenAI's schema requirements
- Is automatically unwrapped before execution
- Includes explanation and confidence for transparency

#### Available Actions
Since the bug fixer runs inside the container, it can:
- **Read files**: Access any file in `/workspace`
- **Write files**: Modify `/workspace/function_block.py` (Python) or `/workspace/function_block.R` (R)
- **Execute commands**: Run Python/R code to test fixes
- **Check packages**: 
  - Python: `pip list`
  - R: `Rscript -e "installed.packages()[,'Package']"`
- **Install packages**: 
  - Python: Add missing dependencies with `pip install`
  - R: Must update requirements in function block (cannot install directly)
- **Test imports**: Verify modules/libraries are available

### 5. Fix Persistence
- Modified code remains in `/workspace/function_block.py`
- Requirements updates persist in `/workspace/requirements.txt`
- Installed packages remain available
- Next execution attempt uses the fixed code

## Configuration

### Initialize with Interactive Debugging (Default)
```python
from agents.main_agent import MainAgent

# Default configuration uses InteractiveExecutor
agent = MainAgent(
    openai_api_key="your-key",
    bug_fixer_type="unified",
    bug_fixer_model="gpt-4o-mini",
    enable_interactive_debug=True  # Default: True
)
```

### Direct Bug Fixer Usage (Advanced)
```python
from agents.unified_bug_fixer import UnifiedBugFixer

bug_fixer = UnifiedBugFixer(
    model_name="gpt-4o-mini",      # LLM model
    max_turns=5,                    # Max debugging turns
    enable_web_agent=True           # Enable web research
)
```

### Web Agent Settings
- **Model**: gpt-4o-mini (cost-optimized)
- **Timeout**: 90 seconds
- **Crawl limit**: 3 pages
- **Search sources**: Web, GitHub, Stack Overflow (ArXiv optional)

## Common Error Patterns and Fixes

### 1. Module Attribute Errors
```python
# Error: AttributeError: module 'palantir' has no attribute 'pseudotime'
# Fix: Use correct API - palantir.core.run_palantir()
```

### 2. Missing Dependencies
```python
# Error: ModuleNotFoundError: No module named 'scfates'
# Fix: Add to requirements.txt and install
```

### 3. File I/O Errors
```python
# Error: FileNotFoundError
# Fix: Create output directory before writing
os.makedirs(path_dict['output_dir'], exist_ok=True)
```

## Timing and Performance

### Web Agent Research
- Quick research: ~40-60 seconds
- Detailed research: ~60-90 seconds
- Timeout handling: Saves partial results

### Bug Fixing Session
- Per turn: 5-15 seconds
- Total session: 30-120 seconds
- With web research: +40-90 seconds

## Debug Logs

### Session Logs Location
```
agent_tasks/unified_bug_fixer/
├── node_name/
│   └── attempt_N/
│       ├── session_log.json    # Complete session history
│       ├── conversation.json   # LLM conversation
│       └── actions.json        # Executed actions
```

### Log Contents
- Timestamp and duration
- All actions executed
- Files modified
- Success/failure status
- Cost and token usage

## Best Practices

### 1. Error Messages
- Provide complete error traceback
- Include relevant stdout/stderr
- Specify the failing function name

### 2. Code Structure
- Keep `code.py` as the main file
- Use clear function signatures
- Follow the `run(path_dict, params)` pattern

### 3. Dependencies
- List all requirements in `requirements.txt`
- Use specific versions when needed
- Avoid conflicting dependencies

### 4. Web Agent Research
- Most effective for API usage errors
- Less effective for logic errors
- Timeout results still provide useful hints

## Troubleshooting

### Bug Fixer Only Lists Directories
- **Cause**: Prompt confusion about file names
- **Fix**: Updated prompts to check `code.py` first

### Web Agent Timeout
- **Cause**: Complex searches or slow crawling
- **Fix**: Reduced timeout to 90s, saves partial results

### No Code Modifications
- **Cause**: Bug fixer not trusting web agent findings
- **Fix**: Enhanced prompts to implement suggestions

### Container Permission Warnings
- **Cause**: The execution containers currently run as the root user
- **Note**: LLM-generated code and commands execute inside these containers. Run this prototype only on trusted
  data and hosts, without production credentials, or configure a non-root user in the Dockerfiles

## Example Usage

```python
# Fix a bug in pseudotime analysis
result = bug_fixer.fix_bug(
    node_name="pseudotime_analysis",
    error_message="AttributeError: module 'palantir' has no attribute 'pseudotime'",
    working_directory=Path("/path/to/node"),
    stdout="Processing started...",
    stderr="AttributeError at line 18",
    attempt_number=1
)

# Check results
if result['success']:
    print(f"Fixed in {result['turn_count']} turns")
    print(f"Files modified: {result['files_modified']}")
else:
    print(f"Failed after {result['turn_count']} turns")
    print(f"Error: {result.get('explanation', 'Unknown')}")
```

## Integration with Main Agent

When using the default configuration (`enable_interactive_debug=True`):

1. **MainAgent** creates an **InteractiveNodeExecutor**
2. **InteractiveNodeExecutor** uses **InteractiveExecutor** for nodes
3. On failure, **InteractiveExecutor** invokes bug fixing inside the container
4. The container stays running between debug attempts
5. After fixes, execution resumes in the same container

Key benefits:
- No container restart between attempts
- Preserved package installations
- Access to actual runtime state
- Faster debugging cycles

### Execution Flow
1. Container starts and stays running
2. Function block execution attempted
3. On failure: Bug fixer runs inside container
4. Code is modified in-place
5. Re-execution in same container
6. Process repeats up to `max_debug_trials` times

### Future Direction
The legacy external bug fixing (where MainAgent modifies files outside containers) will be removed. All bug fixing will use the InteractiveExecutor approach for better reliability and performance.