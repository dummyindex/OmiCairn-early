# Claude Code SDK Bug Fixer Guide

## Overview

The Claude Code SDK Bug Fixer is an alternative debugging implementation that leverages the Claude Code SDK alongside the existing Claude LLM implementation. The SDK provides built-in multi-turn conversation handling, tool management, and automatic context optimization, simplifying the implementation.

> Note: code snippets in this guide are illustrative pseudocode; some option names (e.g. `tool_restrictions`,
> `workspace_exploration`, `workspace_path`) are not part of the actual claude-code-sdk API. See
> `agents/claude_code_sdk_bug_fixer.py` for the implementation actually used.

## Architecture

### Design Philosophy

**Minimal Context Approach**: Instead of pre-loading extensive context, the SDK implementation provides only essential information and lets Claude Code explore the workspace independently through its built-in tools.

**Core Principle**: 
- Provide node name and error message
- Let SDK discover workspace structure
- SDK handles file exploration and modification
- Framework re-reads results after SDK completion

### Implementation Structure

```python
# agents/claude_code_sdk_bug_fixer.py
from claude_code_sdk import query, ClaudeCodeOptions, Message
import asyncio
from pathlib import Path

class ClaudeCodeSDKBugFixer:
    """Minimal SDK-based bug fixer implementation"""
    
    async def fix_error(self, node_name, error_message, working_dir):
        prompt = f"""
        I need help fixing an error in a function block.
        
        Function Block: {node_name}
        Error: {error_message}
        
        The workspace contains:
        - function_block.py: The main code to fix
        - requirements.txt: Python dependencies
        
        Please explore the workspace and fix the error.
        """
        
        # Let SDK handle everything
        result = await query(
            prompt, 
            workspace_path=working_dir,
            options=ClaudeCodeOptions(tool_restrictions=["file"])
        )
        
        return result
```

## Key Features

### 1. Simplified Implementation
- **~100 lines of code** vs 500+ for manual Claude LLM implementation
- **SDK handles complexity**: Multi-turn conversations, context optimization, tool management
- **No prompt engineering**: SDK manages conversation flow internally
- **Built-in optimization**: Automatic stdout/stderr length management

### 2. Automatic Workspace Exploration
- SDK discovers file structure independently
- No need to pre-load file contents
- Intelligent context building based on actual exploration
- Dynamic understanding of project structure

### 3. Direct File Modification
- SDK modifies files directly in workspace
- Framework re-reads modified files after completion
- No need for complex file handling logic
- Immediate effect of changes

### 4. Tool Management
- **Restricted to file operations** for security
- No bash/web tools to prevent security issues
- Built-in file operations (read, write, create, delete)
- Intelligent tool selection based on task

## Usage

### Integration with Main Agent

```python
from agents.main_agent import MainAgent

# Use Claude Code SDK bug fixer
agent = MainAgent(
    bug_fixer_type="claude_code_sdk",  # Specify SDK type
    enable_interactive_debug=True
)

result = agent.run_analysis(
    input_data_path="data.h5ad",
    user_request="Perform trajectory analysis",
    output_dir="results/"
)
```

### Direct SDK Bug Fixer Usage

```python
from agents.claude_code_sdk_bug_fixer import ClaudeCodeSDKBugFixer
import asyncio

async def fix_bug_example():
    bug_fixer = ClaudeCodeSDKBugFixer()
    
    result = await bug_fixer.fix_error(
        node_name="pseudotime_analysis",
        error_message="AttributeError: module 'palantir' has no attribute 'run'",
        working_dir=Path("/workspace/node_12345")
    )
    
    print(f"Success: {result.success}")
    print(f"Modified files: {result.modified_files}")

# Run async function
asyncio.run(fix_bug_example())
```

### Configuration Options

```python
from claude_code_sdk import ClaudeCodeOptions

# Configure SDK options
options = ClaudeCodeOptions(
    tool_restrictions=["file"],        # Only allow file operations
    max_turns=10,                      # Maximum conversation turns
    workspace_exploration=True,         # Enable workspace exploration
    auto_context_optimization=True     # Optimize context automatically
)

result = await query(prompt, workspace_path=workspace, options=options)
```

## Implementation Benefits

### 1. Development Efficiency
- **Faster Implementation**: SDK handles complex conversational logic
- **Less Maintenance**: Fewer custom prompts and response parsing
- **Built-in Best Practices**: SDK incorporates proven debugging patterns
- **Automatic Updates**: SDK improvements benefit all users

### 2. Better Performance
- **Optimized Context**: SDK manages context length automatically
- **Intelligent Exploration**: Only reads relevant files
- **Efficient Conversations**: Built-in turn optimization
- **Reduced Token Usage**: Smart context management

### 3. Enhanced Reliability
- **Tested SDK**: Battle-tested conversational patterns
- **Error Handling**: Built-in error recovery and retry logic
- **Consistent Behavior**: Predictable responses across different scenarios
- **Tool Safety**: Restricted tool access for security

### 4. Simplified Architecture
- **Async-First Design**: Modern async/await patterns
- **Clean Integration**: Minimal framework changes required
- **Clear Separation**: SDK handles conversation, framework handles orchestration
- **Easy Testing**: Mockable SDK interactions

## Comparison with Manual Implementation

### Manual Claude LLM Implementation
```python
# Complex conversation management
class ClaudeBugFixerAgent:
    def __init__(self):
        self.conversation_history = []
        self.action_executor = ContainerActionHandler()
        self.prompt_builder = PromptBuilder()
        # ... 500+ lines of conversation logic
    
    def fix_bug(self):
        # Build complex prompts
        # Manage conversation turns
        # Parse responses
        # Execute actions
        # Handle errors
        # ... extensive implementation
```

### SDK Implementation
```python
# Simple SDK delegation
class ClaudeCodeSDKBugFixer:
    async def fix_error(self, node_name, error_message, working_dir):
        prompt = f"Fix error in {node_name}: {error_message}"
        return await query(prompt, workspace_path=working_dir)
        # SDK handles everything else
```

## Integration Points

### 1. Main Agent Integration
- Modified `main_agent.py` to support `bug_fixer_type="claude_code_sdk"`
- Added async handling with `asyncio.run()` for SDK calls
- Fixed undefined variables and requirements handling
- Preserved backward compatibility with existing bug fixers

### 2. File System Integration
- SDK works directly with workspace files
- Framework re-reads modified files after SDK completion
- No complex file synchronization needed
- Clean separation of concerns

### 3. Error Handling
- SDK provides structured error information
- Framework maps SDK results to internal format
- Graceful fallback to other bug fixers if needed
- Comprehensive logging of SDK interactions

## Testing and Validation

### Test Structure
Dedicated tests for the SDK bug fixer are not yet included in this early research version (planned: unit tests,
integration tests and a comparison against the manual implementation).

### Performance Metrics
Not systematically benchmarked in this early research version.

### Validation Approach
1. **Unit Testing**: Mock SDK responses for consistent testing
2. **Integration Testing**: Full workflow with real workspace
3. **Benchmark Comparison** (planned): Side-by-side with manual implementation
4. **Edge Case Testing**: Error scenarios and recovery

## Migration Guide

### From Manual Claude Bug Fixer

**Before**:
```python
agent = MainAgent(bug_fixer_type="claude")
```

**After**:
```python
agent = MainAgent(bug_fixer_type="claude_code_sdk")
```

### Backward Compatibility
- **Existing Implementation Preserved**: Manual Claude bug fixer remains available
- **No Breaking Changes**: Current functionality unchanged
- **Gradual Migration**: Projects can migrate at their own pace
- **Feature Parity**: SDK implementation provides equivalent debugging capability

## Configuration and Environment

### Required Dependencies
```bash
pip install claude-code-sdk
```

### Environment Variables
```bash
ANTHROPIC_API_KEY=your_api_key  # Required for Claude access
CLAUDE_CODE_SDK_OPTIONS=file   # Tool restrictions (optional)
```

### Workspace Requirements
- **Working Directory**: Must be accessible to SDK
- **File Permissions**: SDK needs read/write access
- **Structure**: Standard function block layout expected

## Troubleshooting

### Common Issues

1. **SDK Import Error**
   ```bash
   # Solution: Install SDK
   pip install claude-code-sdk
   ```

2. **Async Runtime Error**
   ```python
   # Problem: Running async code in sync context
   # Solution: Use asyncio.run()
   result = asyncio.run(bug_fixer.fix_error(...))
   ```

3. **Workspace Access Issues**
   ```bash
   # Problem: SDK cannot access workspace
   # Solution: Check file permissions and paths
   chmod 755 /workspace
   ```

4. **Tool Restriction Errors**
   ```python
   # Problem: SDK trying to use restricted tools
   # Solution: Configure tool restrictions properly
   options = ClaudeCodeOptions(tool_restrictions=["file"])
   ```

## Future Enhancements

### Planned Features
1. **Enhanced Tool Support**: More debugging tools as they become available
2. **Custom Tool Integration**: Framework-specific tools for SDK
3. **Performance Monitoring**: Built-in metrics and analytics
4. **Smart Caching**: Cache common debugging patterns

### SDK Evolution
- **Regular Updates**: Benefit from ongoing SDK improvements
- **New Capabilities**: Access to new debugging features automatically
- **Community Contributions**: Leverage broader ecosystem developments
- **Best Practice Integration**: Automatic adoption of proven techniques

## Conclusion

The Claude Code SDK Bug Fixer is an alternative debugging backend with less custom code, relying on the SDK's
built-in conversation and tool handling. It is part of an early research prototype and has not been benchmarked
against the other bug fixers.