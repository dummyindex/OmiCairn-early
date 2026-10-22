"""Action schema for bug fixer that works with text parsing.

Since OpenAI's strict JSON mode requires ALL properties to be in the required array,
which doesn't work for our use case where different actions need different fields,
we use text parsing for bug fixer actions while keeping JSON mode for other uses.
"""

# Action type definitions for validation
ACTION_TYPES = [
    "read_file", "write_file", "execute_command", "install_package",
    "update_function_block", "list_directory", "create_directory",
    "check_file_exists", "tail_file", "head_file", "grep_file"
]

# Required fields for each action type
REQUIRED_FIELDS = {
    'read_file': ['path'],
    'write_file': ['path', 'content'],
    'execute_command': ['command'],
    'list_directory': [],  # path is optional, defaults to '.'
    'create_directory': ['path'],
    'install_package': ['package'],
    'check_file_exists': ['path'],
    'tail_file': ['path'],  # lines is optional
    'head_file': ['path'],  # lines is optional
    'grep_file': ['path', 'pattern'],
    'update_function_block': ['code']  # requirements and language are optional
}

# Example action format for prompts
ACTION_FORMAT_EXAMPLES = """
## Action Format

When you need to perform an action, format it as a JSON block:

```json
{
    "type": "action_name",
    "params": {
        "parameter1": "value1",
        "parameter2": "value2"
    },
    "explanation": "Why you are taking this action",
    "confidence": 0.8
}
```

### Examples:

**Read File:**
```json
{
    "type": "read_file",
    "params": {
        "path": "/workspace/test.py"
    },
    "explanation": "Reading the file to understand the error",
    "confidence": 0.9
}
```

**Execute Command:**
```json
{
    "type": "execute_command",
    "params": {
        "command": "python --version"
    },
    "explanation": "Checking Python version",
    "confidence": 0.9
}
```

**Update Function Block:**
```json
{
    "type": "update_function_block",
    "params": {
        "code": "def run(path_dict, params):\\n    pass",
        "requirements": ["pandas", "numpy"],
        "language": "python"
    },
    "explanation": "Fixing the import error",
    "confidence": 0.8
}
```
"""