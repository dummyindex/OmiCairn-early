# OpenAI JSON Schema Requirements

## OpenAI's Strict Validation Rules

When using `response_format` with `type: "json_schema"` and `"strict": true`, OpenAI enforces:

1. **All properties must be in required array**: Every property defined in the schema MUST be listed in the `required` array at that level.

2. **No conditional logic**: The following JSON Schema features are NOT supported:
   - `anyOf`, `oneOf`, `allOf` 
   - `if/then/else` conditionals
   - `dependencies` or `dependentSchemas`
   - `$ref` references

3. **additionalProperties must be false**: Every object in the schema must explicitly set `"additionalProperties": false`.

4. **No pattern properties**: Cannot use `patternProperties` or regex-based property names.

## The Problem

Our bug fixer needs different parameters for different action types:
- `read_file` needs: `path`
- `execute_command` needs: `command`
- `write_file` needs: `path`, `content`
- `update_function_block` needs: `code`, `requirements`

But OpenAI requires ALL properties to be in the required array, which would force every action to include irrelevant fields.

## Our Solution: Wrapped Parameters

We use a wrapper object pattern where all action-specific parameters go inside a `params` object:

```json
{
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["read_file", "write_file", "execute_command", ...]
        },
        "params": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "command": {"type": "string"},
                "package": {"type": "string"},
                "code": {"type": "string"},
                "requirements": {"type": "array", "items": {"type": "string"}},
                "lines": {"type": "integer"},
                "pattern": {"type": "string"}
            },
            "required": [],  // Empty - all fields optional
            "additionalProperties": false
        },
        "explanation": {"type": "string"},
        "confidence": {"type": "number"}
    },
    "required": ["type", "params", "explanation", "confidence"],
    "additionalProperties": false
}
```

## Example Actions

### Read File
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

### Execute Command
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

### Update Function Block
```json
{
    "type": "update_function_block",
    "params": {
        "code": "def run(path_dict, params):\n    pass",
        "requirements": ["pandas", "numpy"],
        "language": "python"
    },
    "explanation": "Fixing the import error",
    "confidence": 0.8
}
```

## Alternative Approaches Considered

1. **Nullable fields**: Make all fields nullable and required, but this creates confusion.
2. **Separate schemas per action**: Use discriminated unions, but OpenAI doesn't support `oneOf`.
3. **Disable strict mode**: Loses validation guarantees.
4. **Text parsing only**: Works but loses structure and reliability.

## Current Status

As of now, we've implemented the wrapped parameter approach and updated:
- JSON schema definition
- Action parsing logic to handle wrapped format
- Prompt templates with examples
- Unit tests for the new format

The system can still fall back to text parsing if JSON mode fails.