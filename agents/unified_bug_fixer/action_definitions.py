"""Action definitions for bug fixer actions.

This module contains structured definitions of all available actions,
making it easy to maintain and extend action documentation.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ActionParameter:
    """Definition of an action parameter."""
    name: str
    description: str
    required: bool = True
    example: Any = None


@dataclass
class ActionDefinition:
    """Complete definition of an action."""
    name: str
    category: str
    description: str
    parameters: List[ActionParameter] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    returns: str = ""
    when_to_use: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    host_side: bool = False  # Whether action runs on host (not in container)


# Define all actions with their documentation
ACTION_DEFINITIONS = {
    # Research and Analysis Actions
    'research_online': ActionDefinition(
        name='research_online',
        category='Research and Analysis',
        description='Search the web for solutions to errors and coding problems',
        host_side=True,
        parameters=[
            ActionParameter(
                name='query',
                description='The error message or problem to research',
                required=True,
                example='pip resolution-too-deep squidpy dependencies'
            ),
            ActionParameter(
                name='research_type',
                description='Type of research: "quick" (default), "detailed", or "deep"',
                required=False,
                example='detailed'
            )
        ],
        when_to_use=[
            'Dependency resolution errors (e.g., "resolution-too-deep")',
            'API usage errors (AttributeError, module has no attribute)',
            'Package version conflicts',
            'Complex errors that need online solutions'
        ],
        examples=[
            {
                "type": "research_online",
                "params": {
                    "query": "pip resolution-too-deep squidpy dependencies",
                    "research_type": "detailed"
                },
                "explanation": "Researching dependency resolution issues for Squidpy",
                "confidence": 0.9
            }
        ],
        returns='Research findings, solutions, code examples, and confidence score'
    ),
    
    # File Operations
    'read_file': ActionDefinition(
        name='read_file',
        category='File Operations',
        description='Read a TEXT file\'s contents (NOT for binary files!)',
        parameters=[
            ActionParameter(
                name='path',
                description='Path to the text file to read',
                required=True,
                example='code.py'
            ),
            ActionParameter(
                name='max_lines',
                description='Maximum number of lines to read (default: 1000)',
                required=False,
                example=500
            )
        ],
        limitations=[
            'Only reads TEXT files (Python, R, CSV, JSON, TXT, etc.)',
            'CANNOT read binary files (h5ad, h5, pickle, parquet, etc.)',
            'Limited to 1000 lines by default (use max_lines parameter to adjust)',
            'Implemented using Unix \'head\' command internally'
        ],
        examples=[
            {
                "type": "read_file",
                "params": {"path": "code.py", "max_lines": 500},
                "explanation": "Reading Python code (max 500 lines)",
                "confidence": 0.9
            }
        ],
        returns='content (text only), line_count, truncated (if over limit), error (if binary)'
    ),
    
    'write_file': ActionDefinition(
        name='write_file',
        category='File Operations',
        description='Write content to a file',
        parameters=[
            ActionParameter(
                name='path',
                description='Path where the file should be written',
                required=True,
                example='filename.py'
            ),
            ActionParameter(
                name='content',
                description='Content to write to the file',
                required=True,
                example='file content here'
            )
        ],
        examples=[
            {
                "type": "write_file",
                "params": {"path": "filename.py", "content": "file content here"},
                "explanation": "Writing fixed code",
                "confidence": 0.8
            }
        ],
        returns='success/error, path, bytes_written'
    ),
    
    # Command Execution
    'execute_command': ActionDefinition(
        name='execute_command',
        category='Command Execution',
        description='Run SIMPLE shell commands ONLY',
        parameters=[
            ActionParameter(
                name='command',
                description='Shell command to execute',
                required=True,
                example='ls -la'
            )
        ],
        when_to_use=[
            'Simple shell commands: ls, pwd, cd, echo',
            'Package inspection: pip list, pip show package_name',
            'Simple file operations: cp, mv, rm'
        ],
        limitations=[
            'ONLY use for simple shell commands',
            'NEVER use for Python code - use write_and_run instead'
        ],
        examples=[
            {
                "type": "execute_command",
                "params": {"command": "ls -la"},
                "explanation": "List files",
                "confidence": 0.9
            },
            {
                "type": "execute_command",
                "params": {"command": "pwd"},
                "explanation": "Check current directory",
                "confidence": 0.95
            },
            {
                "type": "execute_command",
                "params": {"command": "pip list | grep squidpy"},
                "explanation": "Check if squidpy installed",
                "confidence": 0.9
            }
        ],
        returns='stdout, stderr, exit_code'
    ),
    
    'write_and_run': ActionDefinition(
        name='write_and_run',
        category='Advanced Code Execution',
        description='Write multiple files and execute a script (REQUIRED for ALL Python code)',
        parameters=[
            ActionParameter(
                name='files',
                description='List of files to write',
                required=True,
                example=[{"path": "test.py", "content": "print('Hello')"}]
            ),
            ActionParameter(
                name='run_script',
                description='Command to run after writing files',
                required=True,
                example='python test.py'
            )
        ],
        when_to_use=[
            'ANY Python code execution',
            'Data exploration and analysis',
            'Complex multi-step operations',
            'Reading binary files (h5ad, pickle, etc.)'
        ],
        examples=[
            {
                "type": "write_and_run",
                "params": {
                    "files": [{"path": "test.py", "content": "print('Hello World')"}],
                    "run_script": "python test.py"
                },
                "explanation": "Simple test",
                "confidence": 0.9
            },
            {
                "type": "write_and_run",
                "params": {
                    "files": [{
                        "path": "explore.py",
                        "content": """import scanpy as sc
import os

# List files
print('Files in input:')
for f in os.listdir('/workspace/input'):
    print(f'  {f}')

# Load h5ad
adata = sc.read_h5ad('/workspace/input/_node_anndata.h5ad')
print(f'\\nShape: {adata.shape}')
n_obs = len(adata.obs.columns)
print(f'Obs columns ({n_obs}):')
if n_obs <= 15:
    print(f'  {list(adata.obs.columns)}')
else:
    print(f'  First 15: {list(adata.obs.columns)[:15]}')
    print(f'  ... and {n_obs - 15} more')"""
                    }],
                    "run_script": "python explore.py"
                },
                "explanation": "Exploring h5ad structure with smart display",
                "confidence": 0.95
            }
        ],
        returns='stdout, stderr, exit_code, files_written'
    ),
    
    # Package Management
    'install_package': ActionDefinition(
        name='install_package',
        category='Package Management',
        description='Install a Python package',
        parameters=[
            ActionParameter(
                name='package',
                description='Package name with optional version',
                required=True,
                example='numpy==1.21.0'
            )
        ],
        examples=[
            {
                "type": "install_package",
                "params": {"package": "numpy==1.21.0"},
                "explanation": "Installing specific numpy version",
                "confidence": 0.85
            }
        ],
        returns='success/error, installation log'
    ),
    
    # Directory Operations
    'list_directory': ActionDefinition(
        name='list_directory',
        category='Directory Operations',
        description='List directory contents',
        parameters=[
            ActionParameter(
                name='path',
                description='Path to directory to list',
                required=True,
                example='.'
            ),
            ActionParameter(
                name='recursive',
                description='Whether to list recursively',
                required=False,
                example=False
            )
        ],
        examples=[
            {
                "type": "list_directory",
                "params": {"path": ".", "recursive": False},
                "explanation": "List current directory",
                "confidence": 0.95
            }
        ],
        returns='files, directories, error (if path doesn\'t exist)'
    ),
    
    'create_directory': ActionDefinition(
        name='create_directory',
        category='Directory Operations',
        description='Create a new directory',
        parameters=[
            ActionParameter(
                name='path',
                description='Path of directory to create',
                required=True,
                example='outputs/figures'
            )
        ],
        examples=[
            {
                "type": "create_directory",
                "params": {"path": "outputs/figures"},
                "explanation": "Create output directory",
                "confidence": 0.9
            }
        ],
        returns='success/error'
    ),
    
    # File Inspection
    'check_file_exists': ActionDefinition(
        name='check_file_exists',
        category='File Inspection',
        description='Check if file exists',
        parameters=[
            ActionParameter(
                name='path',
                description='Path to check',
                required=True,
                example='requirements.txt'
            )
        ],
        examples=[
            {
                "type": "check_file_exists",
                "params": {"path": "requirements.txt"},
                "explanation": "Check if requirements file exists",
                "confidence": 0.95
            }
        ],
        returns='exists (boolean), is_file, is_directory, size'
    ),
    
    'head_file': ActionDefinition(
        name='head_file',
        category='File Inspection',
        description='Read first N lines of a file',
        parameters=[
            ActionParameter(
                name='path',
                description='Path to file',
                required=True,
                example='large_file.csv'
            ),
            ActionParameter(
                name='lines',
                description='Number of lines to read',
                required=False,
                example=20
            )
        ],
        examples=[
            {
                "type": "head_file",
                "params": {"path": "large_file.csv", "lines": 20},
                "explanation": "Preview CSV file",
                "confidence": 0.9
            }
        ],
        returns='content, line_count'
    ),
    
    'tail_file': ActionDefinition(
        name='tail_file',
        category='File Inspection',
        description='Read last N lines of a file',
        parameters=[
            ActionParameter(
                name='path',
                description='Path to file',
                required=True,
                example='error.log'
            ),
            ActionParameter(
                name='lines',
                description='Number of lines to read',
                required=False,
                example=50
            )
        ],
        examples=[
            {
                "type": "tail_file",
                "params": {"path": "error.log", "lines": 50},
                "explanation": "Check end of log file",
                "confidence": 0.9
            }
        ],
        returns='content, line_count'
    ),
    
    'grep_file': ActionDefinition(
        name='grep_file',
        category='File Inspection',
        description='Search for pattern in file',
        parameters=[
            ActionParameter(
                name='path',
                description='Path to file to search',
                required=True,
                example='code.py'
            ),
            ActionParameter(
                name='pattern',
                description='Pattern to search for',
                required=True,
                example='def run'
            )
        ],
        examples=[
            {
                "type": "grep_file",
                "params": {"path": "code.py", "pattern": "def run"},
                "explanation": "Find run function",
                "confidence": 0.9
            }
        ],
        returns='matches (list of matching lines with line numbers)'
    ),
    
    # Function Block Management
    'update_function_block': ActionDefinition(
        name='update_function_block',
        category='Function Block Management',
        description='Update the entire function block code and requirements',
        parameters=[
            ActionParameter(
                name='code',
                description='Complete function block code',
                required=True,
                example='def run(path_dict, params):\\n    # Fixed code here'
            ),
            ActionParameter(
                name='requirements',
                description='List of required packages',
                required=False,
                example=['numpy', 'pandas']
            ),
            ActionParameter(
                name='language',
                description='Programming language (python or r)',
                required=False,
                example='python'
            )
        ],
        limitations=[
            'This action IMMEDIATELY re-executes the code after updating!'
        ],
        examples=[
            {
                "type": "update_function_block",
                "params": {
                    "code": "def run(path_dict, params):\\n    # Fixed code here",
                    "requirements": ["numpy", "pandas"],
                    "language": "python"
                },
                "explanation": "Fix and re-run function block",
                "confidence": 0.8
            }
        ],
        returns='success/error, execution results (stdout, stderr, exit_code)'
    ),
    
    # Previous Nodes Access
    'list_previous_nodes': ActionDefinition(
        name='list_previous_nodes',
        category='Previous Nodes Access',
        description='List available previous nodes',
        parameters=[],
        examples=[
            {
                "type": "list_previous_nodes",
                "params": {},
                "explanation": "Check available upstream nodes",
                "confidence": 0.95
            }
        ],
        returns='list of nodes with their output files'
    ),
    
    'retrieve_previous_node_file': ActionDefinition(
        name='retrieve_previous_node_file',
        category='Previous Nodes Access',
        description='Get a file from a previous node',
        parameters=[
            ActionParameter(
                name='node_index',
                description='Index of the previous node',
                required=True,
                example=1
            ),
            ActionParameter(
                name='filename',
                description='Name of the file to retrieve',
                required=True,
                example='outputs/processed.h5ad'
            )
        ],
        examples=[
            {
                "type": "retrieve_previous_node_file",
                "params": {"node_index": 1, "filename": "outputs/processed.h5ad"},
                "explanation": "Get processed data from node 1",
                "confidence": 0.9
            }
        ],
        returns='success/error, destination path'
    ),
    
    'retrieve_previous_node_files': ActionDefinition(
        name='retrieve_previous_node_files',
        category='Previous Nodes Access',
        description='Get multiple files from previous nodes',
        parameters=[
            ActionParameter(
                name='files',
                description='List of files to retrieve',
                required=True,
                example=[
                    {"node_index": 1, "filename": "data_file.ext"},
                    {"node_index": 2, "filename": "results.csv"}
                ]
            )
        ],
        examples=[
            {
                "type": "retrieve_previous_node_files",
                "params": {
                    "files": [
                        {"node_index": 1, "filename": "data_file.ext"},
                        {"node_index": 2, "filename": "results.csv"}
                    ]
                },
                "explanation": "Getting multiple files from different nodes",
                "confidence": 0.9
            }
        ],
        returns='retrieved_count, failed_count, retrieved_files, failed_files'
    ),
}


def get_action_definition(action_name: str) -> Optional[ActionDefinition]:
    """Get the definition for a specific action.
    
    Args:
        action_name: Name of the action
        
    Returns:
        ActionDefinition if found, None otherwise
    """
    return ACTION_DEFINITIONS.get(action_name)


def get_actions_by_category() -> Dict[str, List[ActionDefinition]]:
    """Group actions by their categories.
    
    Returns:
        Dictionary mapping category names to list of actions
    """
    categories = {}
    for action_def in ACTION_DEFINITIONS.values():
        if action_def.category not in categories:
            categories[action_def.category] = []
        categories[action_def.category].append(action_def)
    return categories


def format_action_documentation(action_def: ActionDefinition) -> str:
    """Format a single action definition into documentation string.
    
    Args:
        action_def: Action definition to format
        
    Returns:
        Formatted documentation string
    """
    doc_parts = []
    
    # Action name and description
    doc_parts.append(f"- {action_def.name}: {action_def.description}")
    
    # Host-side indicator
    if action_def.host_side:
        doc_parts.append("  (runs on HOST, not in container)")
    
    # Parameters
    if action_def.parameters:
        doc_parts.append("  Parameters:")
        for param in action_def.parameters:
            req_str = "required" if param.required else "optional"
            if param.example:
                doc_parts.append(f"    - {param.name} ({req_str}): {param.description}")
            else:
                doc_parts.append(f"    - {param.name} ({req_str}): {param.description}")
    
    # When to use
    if action_def.when_to_use:
        doc_parts.append("  \n  When to use:")
        for use_case in action_def.when_to_use:
            doc_parts.append(f"    - {use_case}")
    
    # Limitations
    if action_def.limitations:
        doc_parts.append("  \n  ⚠️ CRITICAL LIMITATIONS:")
        for limitation in action_def.limitations:
            doc_parts.append(f"    - {limitation}")
    
    # Examples
    if action_def.examples:
        doc_parts.append("  \n  Example:")
        for example in action_def.examples[:1]:  # Show first example
            import json
            example_str = json.dumps(example, indent=2)
            # Indent each line of the example
            indented_example = '\n'.join('  ' + line for line in example_str.split('\n'))
            doc_parts.append(indented_example)
    
    # Return value
    if action_def.returns:
        doc_parts.append(f"  → Returns: {action_def.returns}")
    
    return '\n'.join(doc_parts)