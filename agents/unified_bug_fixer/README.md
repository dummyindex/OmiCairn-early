# Unified Bug Fixer

## Overview

The Unified Bug Fixer is an **action-based debugging system** that uses **pure LLM-driven actions** with **no hardcoded pattern-matching solutions**. It automatically fixes errors in function blocks by operating directly within Docker containers using structured debugging actions.

## Core Principles

### 🎯 Action-Based Architecture
- **No Pattern Matching**: Zero hardcoded solutions or preset fixes
- **Pure LLM Analysis**: All debugging decisions made by analyzing specific error context
- **Structured Actions**: All operations executed through validated action schema
- **Dynamic Strategy**: LLM adapts debugging approach based on each unique error

### 🔧 Available Actions

| Action | Purpose | Example |
|--------|---------|---------|
| `read_file` | Analyze code and logs | `{"type": "read_file", "path": "function_block.py"}` |
| `write_file` | Modify specific files | `{"type": "write_file", "path": "code.py", "content": "..."}` |
| `write_and_run` | **PREFERRED** - Execute Python properly | `{"type": "write_and_run", "files": [{"path": "test.py", "content": "print('hello')"}], "run_script": "python test.py"}` |
| `execute_command` | Simple shell commands ONLY | `{"type": "execute_command", "command": "ls -la"}` |
| `install_package` | Install dependencies | `{"type": "install_package", "package": "pandas==2.0.0"}` |
| `update_function_block` | Update entire block | `{"type": "update_function_block", "code": "...", "requirements": [...]}` |
| `list_directory` | Explore structure | `{"type": "list_directory", "path": "/workspace"}` |
| `grep_file` | Search patterns | `{"type": "grep_file", "path": "*.py", "pattern": "import"}` |

## Components

### 1. ActionExecutor (`action_executor.py`)
- Validates and executes all debugging actions
- Ensures type safety and error handling
- Supports both Python and R function blocks
- Returns structured results for LLM analysis

### 2. EnhancedDebugSession (`enhanced_debug_session.py`)
- Orchestrates multi-turn debugging sessions
- Analyzes LLM responses and extracts actions
- Implements stringent fix detection (no false positives)
- Integrates with web agent for error research

### 3. UnifiedBugFixer (`unified_bug_fixer.py`)
- Main entry point for bug fixing requests
- Supports OpenAI and Claude models
- Configurable retry limits and session parameters
- Returns detailed debugging reports

## Action Execution Flow

```
1. Error Analysis
   ↓ LLM analyzes error logs and context
2. Action Planning  
   ↓ LLM determines which actions needed
3. Action Execution
   ↓ Actions run in container with validation
4. Result Analysis
   ↓ LLM evaluates results and plans next steps
5. Iterative Debugging
   ↓ Process repeats until fixed or max turns
```

## Example Action Sequence

```json
[
  {
    "type": "read_file", 
    "path": "function_block.py"
  },
  {
    "type": "write_and_run", 
    "files": [{"path": "check_version.py", "content": "import scanpy\nprint(scanpy.__version__)"}],
    "run_script": "python check_version.py"
  },
  {
    "type": "install_package", 
    "package": "scanpy==1.9.3"
  },
  {
    "type": "update_function_block",
    "code": "def run(path_dict, params):\n    import scanpy as sc\n    ...",
    "requirements": ["scanpy==1.9.3", "pandas", "numpy"],
    "language": "python"
  }
]
```

## Key Benefits

### 🚀 Adaptability
- Handles any error type without predefined solutions
- LLM determines optimal debugging strategy for each case
- No maintenance of hardcoded fix patterns

### 🔍 Transparency  
- Every debugging step is explicit and logged
- Action execution results available for analysis
- Clear audit trail of all debugging operations

### 🛡️ Reliability
- All actions validated before execution
- Structured error handling and reporting
- Container isolation prevents system contamination

### 📈 Extensibility
- New action types can be added without changing core logic
- Action schema ensures type safety and consistency
- Easy to extend for new debugging capabilities

## Usage

```python
from agents.unified_bug_fixer import UnifiedBugFixer

# Initialize bug fixer
bug_fixer = UnifiedBugFixer(
    llm_service=openai_service,
    max_turns=5,
    enable_web_agent=True
)

# Fix function block errors
result = bug_fixer.fix_bug(
    node_name="my_function_block",
    error_message=error,
    working_directory=Path("/workspace"),
    max_turns=5
)
```

## Testing

Run the comprehensive test suite:

```bash
# Unit tests of the action executor and bug fixer (mocked LLM)
python -m pytest tests/code_agent/ tests/test_bug_fixer_action_results.py

# Bug fixer integration
python -m pytest tests/integration/test_bug_fixer_*.py
```

## Configuration

The bug fixer behavior can be configured through:

- `max_turns`: Maximum debugging iterations (default: 5)
- `enable_web_agent`: Enable web research for errors (default: False)
- `model_name` / `llm_service`: LLM model (or pre-initialized service) for debugging analysis
- `timeout`: Timeout in seconds for bug fixer execution

This action-based approach ensures the bug fixer can adapt to any error scenario without requiring predefined solutions or pattern matching rules.