"""Action schemas and allowed actions for different agents."""

# Action schemas define the structure and validation rules for each action
ACTION_SCHEMAS = {
    'list_directory': {
        'required': [],
        'optional': ['path'],
        'defaults': {'path': '.'},
        'description': 'List files and directories in a path'
    },
    'read_file': {
        'required': ['path'],
        'optional': ['max_lines'],
        'defaults': {'max_lines': 1000},
        'description': 'Read content from a file'
    },
    'write_file': {
        'required': ['path', 'content'],
        'optional': [],
        'defaults': {},
        'description': 'Write content to a file'
    },
    'execute_command': {
        'required': ['command'],
        'optional': [],
        'defaults': {},
        'description': 'Execute a shell command'
    },
    'check_file_exists': {
        'required': ['path'],
        'optional': [],
        'defaults': {},
        'description': 'Check if a file or directory exists'
    },
    'head_file': {
        'required': ['path'],
        'optional': ['lines'],
        'defaults': {'lines': 20},
        'description': 'Read first N lines of a file'
    },
    'tail_file': {
        'required': ['path'],
        'optional': ['lines'],
        'defaults': {'lines': 20},
        'description': 'Read last N lines of a file'
    },
    'grep_file': {
        'required': ['path', 'pattern'],
        'optional': [],
        'defaults': {},
        'description': 'Search for pattern in a file'
    },
    'create_directory': {
        'required': ['path'],
        'optional': [],
        'defaults': {},
        'description': 'Create a directory'
    },
    'install_package': {
        'required': ['package'],
        'optional': [],
        'defaults': {},
        'description': 'Install a Python/R package'
    },
    'update_function_block': {
        'required': ['code'],
        'optional': ['requirements', 'language', 'confidence'],
        'defaults': {'requirements': [], 'language': 'python', 'confidence': 0.5},
        'description': 'Update the function block code and requirements'
    },
    'list_previous_nodes': {
        'required': [],
        'optional': [],
        'defaults': {},
        'description': 'List available previous nodes and their outputs'
    },
    'retrieve_previous_node_file': {
        'required': ['node_index', 'filename'],
        'optional': [],
        'defaults': {},
        'description': 'Retrieve a file from a previous node'
    },
    'retrieve_previous_node_files': {
        'required': ['files'],
        'optional': [],
        'defaults': {},
        'description': 'Retrieve multiple files from previous nodes'
    },
    # New actions for output collector
    'tree_directory': {
        'required': ['path'],
        'optional': ['max_depth'],
        'defaults': {'max_depth': 3},
        'description': 'Show directory tree structure'
    },
    'find_files': {
        'required': ['pattern'],
        'optional': ['path', 'type'],
        'defaults': {'path': '.', 'type': 'all'},
        'description': 'Find files matching pattern'
    },
    'copy_file': {
        'required': ['source', 'destination'],
        'optional': [],
        'defaults': {},
        'description': 'Copy a file to another location'
    },
    'move_file': {
        'required': ['source', 'destination'],
        'optional': [],
        'defaults': {},
        'description': 'Move a file to another location'
    },
    'get_file_info': {
        'required': ['path'],
        'optional': [],
        'defaults': {},
        'description': 'Get file metadata (size, modified time, etc.)'
    },
    'write_and_run': {
        'required': ['files', 'run_script'],
        'optional': ['description'],
        'defaults': {'description': None},
        'description': 'Write multiple files and execute a run script - avoids one-liner syntax issues'
    }
}

# Allowed actions for bug fixer agent
ALLOWED_ACTIONS_BUG_FIXER = {
    'list_directory',
    'read_file',
    'write_file',
    'execute_command',
    'check_file_exists',
    'head_file',
    'tail_file',
    'grep_file',
    'create_directory',
    'install_package',
    'update_function_block',
    'list_previous_nodes',
    'retrieve_previous_node_file',
    'retrieve_previous_node_files',
    'write_and_run'  # New action to avoid one-liner syntax issues
}

# Allowed actions for output collector agent
ALLOWED_ACTIONS_OUTPUT_COLLECTOR = {
    'list_directory',
    'read_file',
    'execute_command',
    'check_file_exists',
    'head_file',
    'tail_file',
    'grep_file',
    'create_directory',
    'tree_directory',
    'find_files',
    'copy_file',
    'move_file',
    'get_file_info'
}