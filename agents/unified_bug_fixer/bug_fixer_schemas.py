"""JSON schemas for bug fixer actions that work with OpenAI's strict mode."""

# Schema that works with OpenAI's strict validation
# Uses a wrapper object with optional parameters
OPENAI_COMPATIBLE_ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": [
                "read_file", "write_file", "execute_command", "install_package",
                "update_function_block", "list_directory", "create_directory",
                "check_file_exists", "tail_file", "head_file", "grep_file"
            ],
            "description": "The type of action to perform"
        },
        "params": {
            "type": "object",
            "properties": {
                # File operation parameters
                "path": {
                    "type": "string", 
                    "description": "File or directory path"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for write_file)"
                },
                
                # Command execution
                "command": {
                    "type": "string",
                    "description": "Command to execute (for execute_command)"
                },
                
                # Package installation
                "package": {
                    "type": "string",
                    "description": "Package to install (for install_package)"
                },
                
                # Function block update
                "code": {
                    "type": "string",
                    "description": "Python/R code (for update_function_block)"
                },
                "requirements": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of requirements (for update_function_block)"
                },
                
                # File operations
                "lines": {
                    "type": "integer",
                    "description": "Number of lines to show (for head_file/tail_file)"
                },
                "pattern": {
                    "type": "string",
                    "description": "Search pattern (for grep_file)"
                }
            },
            "required": [],  # All fields are optional
            "additionalProperties": False
        },
        "explanation": {
            "type": "string",
            "description": "Detailed explanation of why this action is being taken"
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Confidence level in this action (0-1)"
        }
    },
    "required": ["type", "params", "explanation", "confidence"],
    "additionalProperties": False
}

# Alternative schema using nullable fields (if wrapper doesn't work well)
NULLABLE_FIELDS_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": [
                "read_file", "write_file", "execute_command", "install_package",
                "update_function_block", "list_directory", "create_directory",
                "check_file_exists", "tail_file", "head_file", "grep_file"
            ]
        },
        # All fields are nullable to satisfy OpenAI's requirement
        "path": {"type": ["string", "null"]},
        "content": {"type": ["string", "null"]},
        "command": {"type": ["string", "null"]},
        "package": {"type": ["string", "null"]},
        "code": {"type": ["string", "null"]},
        "requirements": {
            "type": ["array", "null"],
            "items": {"type": "string"}
        },
        "lines": {"type": ["integer", "null"]},
        "pattern": {"type": ["string", "null"]},
        "explanation": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1}
    },
    "required": [
        "type", "path", "content", "command", "package", 
        "code", "requirements", "lines", "pattern", 
        "explanation", "confidence"
    ],
    "additionalProperties": False
}

# Example of correct usage with wrapped schema:
# {
#     "type": "read_file",
#     "params": {
#         "path": "/workspace/test.py"
#     },
#     "explanation": "Reading the file to understand the error",
#     "confidence": 0.9
# }
#
# {
#     "type": "execute_command", 
#     "params": {
#         "command": "python --version"
#     },
#     "explanation": "Checking Python version",
#     "confidence": 0.8
# }