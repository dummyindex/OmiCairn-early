# Unified Bug Fixer Guide

## Overview

The Unified Bug Fixer is an LLM-agnostic debugging system that supports both OpenAI and Anthropic models with multi-turn action-based debugging. It consolidates the functionality of previous bug fixing implementations into a single, modular system.

## Architecture

### Core Components

```
unified_bug_fixer/
├── __init__.py
├── base_bug_fixer.py          # Abstract base class
├── unified_bug_fixer.py       # Main implementation
├── debug_session.py           # Debug session manager
├── action_executor.py         # Container action execution
├── prompt_templates.py        # Unified prompts
└── enhanced_debug_session.py  # Enhanced session management
```

### Key Design Principles

1. **LLM-Agnostic Interface**: Configure via model name (e.g., "gpt-4", "claude-3-opus")
2. **Action-Based Debugging**: Multi-turn conversations with container actions
3. **Unified Prompt System**: Consistent prompts across different models
4. **Flexible Provider System**: Easy to add new LLM providers
5. **Session Management**: Maintains debugging state across turns

## Supported Models

### OpenAI Models
- `gpt-4-turbo-preview` - Latest GPT-4 Turbo
- `gpt-4-0125-preview` - GPT-4 Turbo snapshot
- `gpt-4` - Standard GPT-4
- `gpt-3.5-turbo` - Latest GPT-3.5 Turbo
- `gpt-3.5-turbo-0125` - GPT-3.5 Turbo with reduced pricing

### Anthropic Models
- `claude-opus-4-20250514` - Claude Opus 4
- `claude-sonnet-4-20250514` - Claude Sonnet 4
- `claude-3-7-sonnet-20250219` - Claude Sonnet 3.7
- `claude-3-5-sonnet-20241022` - Claude 3.5 Sonnet
- `claude-3-5-haiku-20241022` - Claude 3.5 Haiku
- `claude-3-haiku-20240307` - Claude 3 Haiku

## Usage

### Basic Initialization

```python
from agents.unified_bug_fixer import UnifiedBugFixer

# OpenAI model
bug_fixer = UnifiedBugFixer(
    model_name="gpt-4-turbo-preview",
    max_turns=5,
    enable_web_agent=True
)

# Claude model
bug_fixer = UnifiedBugFixer(
    model_name="claude-3-5-sonnet-20241022",
    max_turns=5,
    enable_web_agent=True
)
```

### Integration with Main Agent

```python
from agents.main_agent import MainAgent

agent = MainAgent(
    openai_api_key="your-key",
    bug_fixer_type="unified",           # Use unified bug fixer
    bug_fixer_model="gpt-4-turbo",     # Specify model
    enable_interactive_debug=True       # Enable in-container debugging
)
```

### Direct Bug Fixing

```python
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

## Key Features

### 1. Multi-Turn Debugging Sessions
The bug fixer operates in turns within the container:

#### Turn Structure
- **Turn 1**: Exploration - Lists files, checks environment
- **Turn 2**: Code Analysis - Reads code files, analyzes errors
- **Turn 3-4**: Fix Implementation - Writes corrected code, installs packages
- **Turn 5**: Validation - Tests fixes, verifies functionality

### 2. Action-Based Container Access
Available actions for debugging:
- **read_file**: Access files in `/workspace` (required: path)
- **write_file**: Modify code files directly (required: path, content)
- **execute_command**: Run Python code or shell commands (required: command)
- **list_directory**: Explore file structure (optional: path)
- **install_package**: Install Python/R packages (required: package)
- **update_function_block**: Update and re-execute code (required: code; optional: requirements, language)
- **head_file/tail_file**: View file portions (required: path; optional: lines)
- **grep_file**: Search in files (required: path, pattern)
- **check_file_exists**: Check file existence (required: path)
- **create_directory**: Create directories (required: path)

All actions include comprehensive field validation before execution.

### 3. Web Agent Integration
For complex errors, automatically conducts web research:
- Triggered for AttributeError, ModuleNotFoundError, etc.
- Searches documentation, Stack Overflow, GitHub
- 90-second timeout with partial results on timeout
- Research findings guide fix implementation

### 4. Conversation History Persistence
Maintains context across debugging attempts:
- Previous attempts are summarized in prompts
- Key actions and findings are preserved
- Avoids repeating the same mistakes

### 5. Enhanced Error Context
Provides comprehensive debugging context:
- Full error tracebacks
- Code context around errors
- Environment information
- Data structure exploration

## Implementation Details

### Wrapped JSON Schema for OpenAI Compatibility

The bug fixer uses a wrapped JSON schema to satisfy OpenAI's strict validation requirements:

```python
# Action format with wrapped parameters
{
    "type": "update_function_block",
    "params": {
        "code": "def run(path_dict, params): ...",
        "requirements": ["pandas", "numpy"],
        "language": "python"
    },
    "explanation": "Fixing import error by adding required packages",
    "confidence": 0.85
}
```

This wrapped format:
- Allows all action types to share the same schema
- Makes all parameter fields optional within the `params` object
- Satisfies OpenAI's requirement that all properties be in the required array
- Is automatically unwrapped by EnhancedDebugSessionV2 before execution

### Field Validation

Before executing any action, the ActionExecutor validates:
1. **Required fields**: Each action type has specific required fields
2. **Empty values**: Empty strings and whitespace-only values are rejected
3. **Type validation**: 
   - `language` must be 'python' or 'r' for update_function_block
   - `lines` must be a positive integer for head_file/tail_file
4. **Clear error messages**: Missing fields are clearly listed in error responses

### Session Management

The enhanced debug session manages the debugging lifecycle:

```python
class EnhancedDebugSession:
    def __init__(self, container, working_dir, bug_fixer, max_turns=5):
        self.container = container
        self.working_dir = working_dir
        self.bug_fixer = bug_fixer
        self.max_turns = max_turns
        self.conversation_history = []
        
    def run_debug_session(self, error_context):
        for turn in range(self.max_turns):
            # Get LLM response with actions
            response = self.bug_fixer.get_debug_actions(
                error_context=error_context,
                conversation_history=self.conversation_history
            )
            
            # Execute actions in container
            results = self.execute_actions(response.actions)
            
            # Update conversation history
            self.conversation_history.append({
                'turn': turn + 1,
                'actions': response.actions,
                'results': results
            })
            
            # Check if fix was successful
            if self.test_fix():
                return {'success': True, 'turn_count': turn + 1}
                
        return {'success': False, 'turn_count': self.max_turns}
```

### Action Execution

Container actions are executed through the action executor:

```python
class ContainerActionHandler:
    def execute_action(self, action):
        if action.type == "read_file":
            return self.read_file(action.path)
        elif action.type == "write_file":
            return self.write_file(action.path, action.content)
        elif action.type == "execute_command":
            return self.execute_command(action.command)
        elif action.type == "list_directory":
            return self.list_directory(action.path)
```

### Prompt Templates

Unified prompts work across different LLM providers:

```python
SYSTEM_PROMPT = """
You are a debugging expert helping fix Python code errors. You have access to:
- read_file: Read any file in /workspace
- write_file: Modify files directly
- execute_command: Run commands to test and explore
- list_directory: Explore file structure

Always start by exploring the environment and understanding the error context.
Use micromamba run -n _omicairn_job python for Python commands.
"""

ERROR_CONTEXT_PROMPT = """
Error Details:
- Error: {error_message}
- File: {error_file}
- Line: {error_line}
- Working Directory: {working_dir}

Previous Attempts: {previous_attempts_summary}

Your task: Debug and fix this error using available actions.
"""
```

## Performance and Optimization

### Token Usage
- Optimized prompts reduce token consumption
- Action-based approach focuses on relevant information
- Context window management prevents token waste

### Success Rates
Success rates have not been systematically benchmarked in this early research version.

### Timing (informal observations, not benchmarked)
- **Average Session Duration**: 30-120 seconds
- **With Web Research**: +40-90 seconds
- **Per Turn**: 5-15 seconds

## Configuration Options

### Bug Fixer Settings
```python
bug_fixer = UnifiedBugFixer(
    model_name="gpt-4-turbo",          # LLM model
    max_turns=5,                       # Max debugging turns
    enable_web_agent=True,             # Enable web research
    timeout_seconds=300,               # Session timeout
    web_agent_timeout=90               # Web research timeout
)
```

### Environment Variables
- `OPENAI_API_KEY`: Required for OpenAI models
- `ANTHROPIC_API_KEY`: Required for Claude models
- `OMICAIRN_DEBUG_MODE`: Enable verbose logging

## Migration from Legacy Bug Fixers

### From GPT Bug Fixer
```python
# Old approach
from agents.bug_fixer_agent import GPTBugFixer
bug_fixer = GPTBugFixer(api_key="key")

# New approach
from agents.unified_bug_fixer import UnifiedBugFixer
bug_fixer = UnifiedBugFixer(model_name="gpt-4-turbo")
```

### From Claude Bug Fixer
```python
# Old approach
from agents.claude_bug_fixer_agent import ClaudeBugFixer
bug_fixer = ClaudeBugFixer(api_key="key")

# New approach
from agents.unified_bug_fixer import UnifiedBugFixer
bug_fixer = UnifiedBugFixer(model_name="claude-3-5-sonnet")
```

## Testing

### Unit Tests
```bash
pytest tests/code_agent/test_unified_bug_fixer.py -v
```

### Integration Tests
```bash
python tests/integration/test_bug_fixer_live.py  # requires an LLM API key and Docker
```

### Real-World Testing
```bash
pytest tests/domain_fb/scrnaq/test_palantir_debug.py -v  # Test with actual errors
```

## Troubleshooting

### Common Issues

1. **Model Not Found**
   - Check model name spelling
   - Ensure API keys are set
   - Verify model availability

2. **Container Permission Errors**
   - Use micromamba commands for Python
   - Check file permissions in container
   - Verify container is running

3. **Web Agent Timeouts**
   - Increase timeout settings
   - Check network connectivity
   - Review timeout logs

### Debug Logging

Enable detailed logging:
```python
import logging
logging.getLogger('unified_bug_fixer').setLevel(logging.DEBUG)
```

## Future Enhancements

1. **Additional LLM Providers**: Support for more models
2. **Caching**: Cache successful fixes for similar errors
3. **Learning System**: Learn from debugging patterns
4. **Parallel Debugging**: Debug multiple nodes simultaneously
5. **Advanced Actions**: More sophisticated container operations

## Conclusion

The Unified Bug Fixer provides a robust, flexible debugging system that works across different LLM providers while maintaining the advanced in-container debugging capabilities. It consolidates the best features from previous implementations while adding new capabilities for more effective error resolution.