"""Execute debugging actions in the container."""

import shlex
import sys
import os
import subprocess
import shutil
import requests
from typing import Dict, Any, Optional, List
from pathlib import Path

from utils import setup_logger
from .code_versioning import CodeVersionManager

logger = setup_logger(__name__)


class ActionExecutor:
    """DEPRECATED: Execute debugging actions in the container environment.
    
    WARNING: This class is deprecated and should not be used directly.
    Use the in-container debugging path with InteractiveExecutor instead.
    This standalone ActionExecutor lacks proper re-execution support.
    """
    
    # Base actions that are always available
    BASE_ACTIONS = {
        'read_file',
        'write_file',
        'execute_command',
        'list_directory',
        'create_directory',
        'install_package',
        'check_file_exists',
        'tail_file',
        'head_file',
        'grep_file',
        'update_function_block',
        'list_previous_nodes',
        'retrieve_previous_node_file',
        'write_and_run'
    }
    
    # Optional actions that require specific tools
    OPTIONAL_ACTIONS = {
        'research_online'  # Requires web_agent_tool
    }
    
    # Full set for backward compatibility
    ALLOWED_ACTIONS = BASE_ACTIONS | OPTIONAL_ACTIONS
    
    def __init__(self, workspace: Path, node_dir: Optional[Path] = None,
                 max_output_chars: int = 10000, max_output_lines: int = 1000,
                 interactive_executor: Optional[Any] = None, web_agent_tool: Optional[Any] = None):
        """Initialize action executor.
        
        Args:
            workspace: Working directory path
            node_dir: Node directory path for versioning (optional)
            max_output_chars: Maximum characters for command output (default: 10000)
            max_output_lines: Maximum lines for command output (default: 1000)
            interactive_executor: Optional InteractiveExecutor for delegation (optional)
        """
        # Raise deprecation error for standalone usage
        if interactive_executor is None:
            raise DeprecationWarning(
                "\n" + "="*80 + "\n" +
                "DEPRECATED: Standalone ActionExecutor is no longer supported!\n" +
                "\n" +
                "This class should only be used with an InteractiveExecutor for delegation.\n" +
                "The standalone ActionExecutor lacks proper re-execution support and\n" +
                "should not be used directly.\n" +
                "\n" +
                "Please use one of the following instead:\n" +
                "1. Enable interactive debugging (enable_interactive_debug=True) in MainAgent\n" +
                "2. Use InteractiveNodeExecutor for in-container debugging\n" +
                "3. Pass an interactive_executor parameter if you must use ActionExecutor\n" +
                "\n" +
                "The standalone ActionExecutor will be removed in a future version.\n" +
                "="*80
            )
        
        self.workspace = Path(workspace)
        self.node_dir = node_dir
        self.actions_log = []
        self.max_output_chars = max_output_chars
        self.max_output_lines = max_output_lines
        self.interactive_executor = interactive_executor
        self.web_agent_tool = web_agent_tool  # Store web agent tool
        
        # Initialize code version manager if node directory is provided
        self.version_manager = None
        if self.node_dir:
            self.version_manager = CodeVersionManager(self.node_dir)
        
        # Define required fields for each action type
        self.REQUIRED_FIELDS = {
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
            'update_function_block': ['code'],  # requirements and language are optional
            'list_previous_nodes': [],  # No required fields
            'retrieve_previous_node_file': ['node_index', 'filename'],
            'retrieve_previous_node_files': ['files'],  # List of {node_index, filename} dicts
            'research_online': ['query']  # research_type is optional
        }
        
        # Node context for accessing previous nodes (set by the executor)
        self.node_context = None
        
        # Build the list of actually available actions
        self.available_actions = self.BASE_ACTIONS.copy()
        
        # Add optional actions based on available tools
        if self.web_agent_tool is not None:
            self.available_actions.add('research_online')
    
    def get_available_actions(self) -> set:
        """Get the set of available actions based on configured tools."""
        return self.available_actions
    
    def get_actions_for_prompt(self) -> str:
        """Generate action documentation for prompt based on available actions."""
        sections = []
        
        # Add research section only if available
        if 'research_online' in self.available_actions:
            sections.append("""**Research and Analysis** (runs on HOST, not in container):
- research_online: Search the web for solutions to errors and coding problems
  Parameters:
    - query (required): The error message or problem to research
    - research_type (optional): "quick" (default), "detailed", or "deep"
  
  When to use:
    - Dependency resolution errors (e.g., "resolution-too-deep")
    - API usage errors (AttributeError, module has no attribute)
    - Package version conflicts
    - Complex errors that need online solutions
  
  Example:
  {"type": "research_online", "params": {"query": "pip resolution-too-deep squidpy dependencies", "research_type": "detailed"}, "explanation": "Researching dependency resolution issues for Squidpy", "confidence": 0.9}

""")
        
        # Always include base actions documentation
        sections.append("""**File Operations** (return text content):
- read_file: Read a TEXT file's contents (NOT for binary files!)
  ⚠️ CRITICAL LIMITATIONS:
  - Only reads TEXT files (Python, R, CSV, JSON, TXT, etc.)
  - CANNOT read binary files (h5ad, h5, pickle, parquet, etc.)
  - Limited to 1000 lines by default (use max_lines parameter to adjust)
  - Implemented using Unix 'head' command internally""")
        
        # Continue with other base actions...
        # (keeping existing documentation structure)
        
        return "".join(sections)
        
    def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single action and return result.
        
        Args:
            action: Action dictionary with 'type' and parameters
            
        Returns:
            Result dictionary with 'success' and output data
        """
        # Check if we have interactive_executor - should never reach here due to __init__
        if not self.interactive_executor:
            logger.error("CRITICAL: execute_action called on standalone ActionExecutor!")
            raise RuntimeError(
                "Standalone ActionExecutor is deprecated and should not be used. "
                "Please use in-container debugging with InteractiveExecutor."
            )
        
        action_type = action.get('type')
        
        # Enhanced logging with action details
        logger.info(f"Executing action: {action_type}")
        if action_type in ['read_file', 'write_file', 'head_file', 'tail_file', 'grep_file']:
            logger.info(f"  File: {action.get('path', 'N/A')}")
        elif action_type == 'execute_command':
            cmd = action.get('command', 'N/A')
            logger.info(f"  Command: {cmd[:100]}{'...' if len(cmd) > 100 else ''}")
        elif action_type == 'update_function_block':
            logger.info(f"  Language: {action.get('language', 'python')}")
            logger.info(f"  Confidence: {action.get('confidence', 'N/A')}")
            logger.info(f"  Requirements count: {len(action.get('requirements', []))}")
        elif action_type == 'install_package':
            logger.info(f"  Package: {action.get('package', 'N/A')}")
        elif action_type == 'research_online':
            query = action.get('query', 'N/A')
            logger.info(f"  Query: {query[:100]}{'...' if len(query) > 100 else ''}")
            logger.info(f"  Research type: {action.get('research_type', 'quick')}")
        
        if action_type not in self.ALLOWED_ACTIONS:
            error_msg = f'Unknown action type: {action_type}. Allowed: {", ".join(self.ALLOWED_ACTIONS)}'
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'action_type': action_type,
                'available_actions': self.ALLOWED_ACTIONS
            }
        
        # Validate required fields for the action
        validation_result = self._validate_action_fields(action)
        if not validation_result['valid']:
            logger.error(f"Action validation failed: {validation_result['error']}")
            return {
                'success': False,
                'error': validation_result['error'],
                'action_type': action_type,
                'missing_fields': validation_result.get('missing_fields', [])
            }
            
        # Log action
        self.actions_log.append(action)
        
        # Get handler method
        handler = getattr(self, f'_handle_{action_type}', None)
        if not handler:
            error_msg = f'No handler for action: {action_type}'
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'action_type': action_type
            }
            
        # Execute action with timing
        import time
        start_time = time.time()
        
        try:
            result = handler(action)
            
            # Add timing and action details to result
            execution_time = time.time() - start_time
            result['action_type'] = action_type
            result['execution_time'] = execution_time
            result['workspace'] = str(self.workspace)
            
            # Enhanced result logging
            if result.get('success'):
                logger.info(f"  ✓ Action completed in {execution_time:.3f}s")
                
                # Log specific results based on action type
                if action_type == 'read_file' and 'content' in result:
                    content_preview = result['content'][:200].replace('\n', '\\n')
                    logger.info(f"  Content preview: {content_preview}{'...' if len(result['content']) > 200 else ''}")
                
                elif action_type == 'execute_command':
                    if 'stdout' in result and result['stdout']:
                        stdout_preview = result['stdout'][:300].replace('\n', '\\n')
                        logger.info(f"  STDOUT: {stdout_preview}{'...' if len(result['stdout']) > 300 else ''}")
                    if 'stderr' in result and result['stderr']:
                        stderr_preview = result['stderr'][:300].replace('\n', '\\n')
                        logger.info(f"  STDERR: {stderr_preview}{'...' if len(result['stderr']) > 300 else ''}")
                    if 'return_code' in result:
                        logger.info(f"  Return code: {result['return_code']}")
                
                elif action_type == 'update_function_block':
                    logger.info(f"  Code file: {result.get('code_file', 'N/A')}")
                    logger.info(f"  Dependencies file: {result.get('dependencies_file', 'N/A')}")
                    logger.info(f"  Package count: {result.get('package_count', 0)}")
                
                elif action_type == 'list_directory':
                    if 'contents' in result:
                        logger.info(f"  Found {len(result['contents'])} items")
                        if result['contents']:
                            preview = ', '.join(result['contents'][:5])
                            if len(result['contents']) > 5:
                                preview += f", ... ({len(result['contents']) - 5} more)"
                            logger.info(f"  Contents: {preview}")
                            
            else:
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"  ✗ Action failed: {error_msg}")
                
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f'Handler exception: {str(e)}'
            logger.error(f"  ✗ {error_msg} (after {execution_time:.3f}s)")
            
            return {
                'success': False,
                'error': error_msg,
                'action_type': action_type,
                'execution_time': execution_time,
                'workspace': str(self.workspace),
                'exception': str(e)
            }
    
    def _validate_action_fields(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that an action has all required fields.
        
        Args:
            action: Action dictionary to validate
            
        Returns:
            Dictionary with 'valid' bool and optional 'error' and 'missing_fields'
        """
        action_type = action.get('type')
        
        if action_type not in self.REQUIRED_FIELDS:
            return {
                'valid': False,
                'error': f'Unknown action type for validation: {action_type}'
            }
        
        required_fields = self.REQUIRED_FIELDS[action_type]
        missing_fields = []
        
        for field in required_fields:
            value = action.get(field)
            # Check if field exists and is not None or empty string
            if value is None or (isinstance(value, str) and not value.strip()):
                missing_fields.append(field)
        
        if missing_fields:
            return {
                'valid': False,
                'error': f"Action '{action_type}' missing required fields: {', '.join(missing_fields)}",
                'missing_fields': missing_fields
            }
        
        # Additional validation for specific action types
        if action_type == 'update_function_block':
            # Validate language if provided
            language = action.get('language', 'python').lower()
            if language not in ['python', 'r']:
                return {
                    'valid': False,
                    'error': f"Invalid language '{language}' for update_function_block. Must be 'python' or 'r'"
                }
        
        elif action_type in ['head_file', 'tail_file']:
            # Validate lines is a positive integer if provided
            lines = action.get('lines')
            if lines is not None:
                try:
                    lines_int = int(lines)
                    if lines_int <= 0:
                        return {
                            'valid': False,
                            'error': f"Lines parameter must be positive, got {lines_int}"
                        }
                except (TypeError, ValueError):
                    return {
                        'valid': False,
                        'error': f"Lines parameter must be an integer, got {type(lines).__name__}"
                    }
        
        return {'valid': True}
            
    def _handle_read_file(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Read file contents with line limit."""
        path = action.get('path', '')
        max_lines = action.get('max_lines', 1000)  # Default 1000 lines
        
        # Handle None or empty path
        if not path:
            return {
                'success': False,
                'error': 'No file path provided'
            }
        
        # Handle absolute /workspace paths
        if path.startswith('/workspace/'):
            relative_path = path[11:]  # len('/workspace/') = 11
            file_path = self.workspace / relative_path
        elif path == '/workspace':
            # Can't read a directory
            return {
                'success': False,
                'error': 'Cannot read directory as file'
            }
        else:
            file_path = self.workspace / path
        
        if not file_path.exists():
            return {
                'success': False,
                'error': f'File not found: {path}'
            }
        
        # Check if it's a binary file
        binary_extensions = {'.h5ad', '.h5', '.hdf5', '.pkl', '.pickle', '.npy', '.npz', 
                           '.parquet', '.feather', '.arrow', '.db', '.sqlite', '.gz', 
                           '.zip', '.tar', '.bz2', '.xz', '.jpg', '.png', '.pdf', '.xlsx'}
        
        if file_path.suffix.lower() in binary_extensions:
            return {
                'success': False,
                'error': f'Cannot read binary file with read_file action. File type: {file_path.suffix}. Use execute_command with Python/R code to read this file type.',
                'path': str(file_path),
                'file_exists': True,
                'is_binary': True,
                'file_type': file_path.suffix
            }
            
        try:
            # Try to read as text with line limit
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = []
                line_count = 0
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"\n... (truncated after {max_lines} lines)")
                        # Continue counting remaining lines
                        remaining = sum(1 for _ in f)
                        total_lines = max_lines + remaining
                        break
                    lines.append(line.rstrip('\n'))
                    line_count += 1
                else:
                    # File had fewer lines than max_lines
                    total_lines = line_count
                
                content = '\n'.join(lines)
                
            return {
                'success': True,
                'content': content,
                'path': str(file_path),
                'file_size': file_path.stat().st_size,
                'line_count': min(total_lines, max_lines),
                'truncated': total_lines > max_lines,
                'max_lines': max_lines,
                'file_type': file_path.suffix or 'no extension'
            }
        except UnicodeDecodeError:
            return {
                'success': False,
                'error': f'File appears to be binary or uses non-UTF-8 encoding. Use execute_command with appropriate tools to read this file.',
                'path': str(file_path),
                'file_exists': True,
                'is_binary': True
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error reading file: {e}',
                'path': str(file_path),
                'file_exists': file_path.exists()
            }
            
    def _handle_write_file(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Write content to file."""
        path = action.get('path', '')
        content = action.get('content', '')
        
        # Handle None or empty path
        if not path:
            return {
                'success': False,
                'error': 'No file path provided'
            }
        
        # Handle absolute /workspace paths
        if path.startswith('/workspace/'):
            relative_path = path[11:]  # len('/workspace/') = 11
            file_path = self.workspace / relative_path
        else:
            file_path = self.workspace / path
        
        try:
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write content
            file_path.write_text(content)
            
            return {
                'success': True,
                'path': str(file_path),
                'bytes_written': len(content)
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error writing file: {e}'
            }
            
    def _handle_execute_command(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute shell command."""
        command = action.get('command', '')
        timeout = action.get('timeout', 30)
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.workspace,
                timeout=timeout
            )
            
            # Apply output limits
            stdout = result.stdout
            stderr = result.stderr
            stdout_truncated = False
            stderr_truncated = False
            
            # Truncate by character count
            if stdout and len(stdout) > self.max_output_chars:
                stdout = stdout[:self.max_output_chars] + f"\n... (truncated - output was {len(result.stdout)} chars)"
                stdout_truncated = True
                
            if stderr and len(stderr) > self.max_output_chars:
                stderr = stderr[:self.max_output_chars] + f"\n... (truncated - output was {len(result.stderr)} chars)"
                stderr_truncated = True
            
            # Truncate by line count
            if stdout:
                stdout_lines = stdout.split('\n')
                if len(stdout_lines) > self.max_output_lines:
                    stdout = '\n'.join(stdout_lines[:self.max_output_lines]) + f"\n... (truncated - output was {len(stdout_lines)} lines)"
                    stdout_truncated = True
                    
            if stderr:
                stderr_lines = stderr.split('\n')
                if len(stderr_lines) > self.max_output_lines:
                    stderr = '\n'.join(stderr_lines[:self.max_output_lines]) + f"\n... (truncated - output was {len(stderr_lines)} lines)"
                    stderr_truncated = True
            
            return {
                'success': True,
                'stdout': stdout,
                'stderr': stderr,
                'return_code': result.returncode,
                'command': command,
                'timeout_used': timeout,
                'stdout_lines': result.stdout.count('\n') + 1 if result.stdout else 0,
                'stderr_lines': result.stderr.count('\n') + 1 if result.stderr else 0,
                'stdout_truncated': stdout_truncated,
                'stderr_truncated': stderr_truncated,
                'original_stdout_size': len(result.stdout) if result.stdout else 0,
                'original_stderr_size': len(result.stderr) if result.stderr else 0
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': f'Command timed out after {timeout} seconds'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error executing command: {e}'
            }
            
    def _handle_list_directory(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """List directory contents."""
        path = action.get('path', '.')
        
        # Handle None path
        if path is None:
            path = '.'
        
        # Handle absolute /workspace paths
        if path == '/workspace' or path.startswith('/workspace/'):
            # In container context, /workspace maps to self.workspace
            if path == '/workspace':
                dir_path = self.workspace
            else:
                # Remove /workspace/ prefix and join with workspace
                relative_path = path[11:]  # len('/workspace/') = 11
                dir_path = self.workspace / relative_path
        else:
            # Regular relative path handling
            dir_path = self.workspace / path
        
        if not dir_path.exists():
            return {
                'success': False,
                'error': f'Directory not found: {path}'
            }
            
        if not dir_path.is_dir():
            return {
                'success': False,
                'error': f'Not a directory: {path}'
            }
            
        try:
            entries = []
            for entry in sorted(dir_path.iterdir()):
                entries.append({
                    'name': entry.name,
                    'type': 'directory' if entry.is_dir() else 'file',
                    'size': entry.stat().st_size if entry.is_file() else None
                })
                
            return {
                'success': True,
                'path': str(dir_path),
                'entries': entries
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error listing directory: {e}'
            }
            
    def _handle_create_directory(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Create directory."""
        path = action.get('path', '')
        
        # Handle None or empty path
        if not path:
            return {
                'success': False,
                'error': 'No directory path provided'
            }
        
        dir_path = self.workspace / path
        
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return {
                'success': True,
                'path': str(dir_path)
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error creating directory: {e}'
            }
            
    def _handle_install_package(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Install Python package."""
        package = action.get('package', '')
        
        if not package:
            return {
                'success': False,
                'error': 'No package specified'
            }
            
        try:
            # Use pip to install package
            # Pass arguments as a list (no shell) so the LLM-provided package string
            # cannot inject additional shell commands
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', *shlex.split(package)],
                capture_output=True,
                text=True,
                cwd=self.workspace,
                timeout=120  # 2 minute timeout for package installation
            )
            
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'return_code': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'error': 'Package installation timed out'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error installing package: {e}'
            }
            
    def _handle_check_file_exists(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Check if file or directory exists."""
        path = action.get('path', '')
        
        # Handle None or empty path
        if not path:
            return {
                'success': False,
                'error': 'No file path provided'
            }
        
        file_path = self.workspace / path
        
        exists = file_path.exists()
        is_file = file_path.is_file() if exists else False
        is_dir = file_path.is_dir() if exists else False
        
        return {
            'success': True,
            'exists': exists,
            'is_file': is_file,
            'is_directory': is_dir,
            'path': str(file_path)
        }
        
    def _handle_tail_file(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Read last N lines of file."""
        path = action.get('path', '')
        lines = action.get('lines', 20)
        
        # Handle None or empty path
        if not path:
            return {
                'success': False,
                'error': 'No file path provided'
            }
        file_path = self.workspace / path
        
        if not file_path.exists():
            return {
                'success': False,
                'error': f'File not found: {path}'
            }
            
        try:
            with open(file_path, 'r') as f:
                all_lines = f.readlines()
                tail_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                
            return {
                'success': True,
                'content': ''.join(tail_lines),
                'lines_returned': len(tail_lines),
                'total_lines': len(all_lines)
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error reading file: {e}'
            }
            
    def _handle_head_file(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Read first N lines of file."""
        path = action.get('path', '')
        lines = action.get('lines', 20)
        
        # Handle None or empty path
        if not path:
            return {
                'success': False,
                'error': 'No file path provided'
            }
        file_path = self.workspace / path
        
        if not file_path.exists():
            return {
                'success': False,
                'error': f'File not found: {path}'
            }
            
        try:
            with open(file_path, 'r') as f:
                head_lines = []
                for i, line in enumerate(f):
                    if i >= lines:
                        break
                    head_lines.append(line)
                    
            return {
                'success': True,
                'content': ''.join(head_lines),
                'lines_returned': len(head_lines)
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error reading file: {e}'
            }
            
    def _handle_grep_file(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Search for pattern in file."""
        path = action.get('path', '')
        pattern = action.get('pattern', '')
        
        # Handle None or empty path
        if not path:
            return {
                'success': False,
                'error': 'No file path provided'
            }
        file_path = self.workspace / path
        
        if not file_path.exists():
            return {
                'success': False,
                'error': f'File not found: {path}'
            }
            
        if not pattern:
            return {
                'success': False,
                'error': 'No search pattern specified'
            }
            
        try:
            matches = []
            with open(file_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    if pattern in line:
                        matches.append({
                            'line_number': line_num,
                            'content': line.rstrip()
                        })
                        
            return {
                'success': True,
                'matches': matches,
                'match_count': len(matches),
                'pattern': pattern
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error searching file: {e}'
            }
    
    def _handle_update_function_block(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Update entire function block including code and dependencies.
        
        This action updates both the function block code and its dependencies.
        Supports both Python and R function blocks.
        """
        code = action.get('code', '')
        requirements = action.get('requirements', [])
        language = action.get('language', 'python').lower()
        confidence = action.get('confidence', 0.5)
        
        if not code:
            return {
                'success': False,
                'error': 'No code provided for update_function_block'
            }
        
        if language not in ['python', 'r']:
            return {
                'success': False,
                'error': f'Unsupported language: {language}. Must be "python" or "r"'
            }
        
        # Always delegate to InteractiveExecutor if available - it has proper re-execution
        if self.interactive_executor:
            logger.info("Delegating update_function_block to InteractiveExecutor for proper re-execution")
            try:
                # InteractiveExecutor's _update_function_block expects these parameters
                return self.interactive_executor._update_function_block(
                    code=code,
                    requirements=requirements,
                    language=language,
                    confidence=confidence
                )
            except Exception as e:
                logger.warning(f"Failed to delegate to InteractiveExecutor: {e}, falling back to local implementation")
                # Fall through to existing implementation
        else:
            # Should never reach here due to __init__ check, but add warning just in case
            logger.error("CRITICAL: update_function_block called without InteractiveExecutor!")
            logger.error("This path lacks re-execution and should not be used!")
            raise RuntimeError(
                "Standalone ActionExecutor.update_function_block is deprecated. "
                "Use in-container debugging with InteractiveExecutor instead."
            )
        
        try:
            # Save original files for logging purposes
            original_code = None
            original_deps = None
            
            # Determine file paths based on language
            if language == 'python':
                # Python: function_block.py or code.py
                function_block_path = self.workspace / 'function_block.py'
                code_path = self.workspace / 'code.py'
                
                # Determine which code file to update
                if function_block_path.exists():
                    target_path = function_block_path
                    original_code = function_block_path.read_text()
                elif code_path.exists():
                    target_path = code_path
                    original_code = code_path.read_text()
                else:
                    target_path = function_block_path
                    
            else:  # R
                # R: function_block.R or code.R
                function_block_path = self.workspace / 'function_block.R'
                code_path = self.workspace / 'code.R'
                
                # Determine which code file to update
                if function_block_path.exists():
                    target_path = function_block_path
                    original_code = function_block_path.read_text()
                elif code_path.exists():
                    target_path = code_path
                    original_code = code_path.read_text()
                else:
                    target_path = function_block_path
            
            # Both Python and R use requirements.txt
            deps_file = 'requirements.txt'
            deps_path = self.workspace / deps_file
            
            # Read original dependencies if exists
            if deps_path.exists():
                original_deps = deps_path.read_text()
            
            # Use CodeVersionManager if available for versioning
            files_updated = []
            version_result = None
            
            if self.version_manager:
                # Use the version manager for structured updates
                version_result = self.version_manager.update_function_block(
                    code=code, 
                    requirements=requirements, 
                    language=language
                )
                
                if version_result['success']:
                    files_updated = version_result['files_updated']
                    logger.info(f"Updated {language} function block with versioning: {version_result.get('version_saved', 'N/A')}")
                else:
                    logger.error(f"Version manager failed: {version_result.get('error', 'Unknown error')}")
                    # Fall back to direct file update
                    target_path.write_text(code)
                    files_updated = [target_path.name]
            else:
                # Direct file update without versioning
                target_path.write_text(code)
                logger.info(f"Updated {language} function block code in {target_path.name}")
                files_updated = [target_path.name]
                
                # Update dependencies file
                if requirements:
                    if isinstance(requirements, list):
                        if language == 'python':
                            # Python: simple package names
                            deps_content = '\n'.join(requirements)
                        else:
                            # R: may include CRAN, Bioconductor, GitHub formats
                            # Format: packagename, Bioconductor::packagename, user/repo
                            deps_content = '\n'.join(requirements)
                    else:
                        deps_content = str(requirements)
                    
                    # Ensure dependencies end with newline
                    if not deps_content.endswith('\n'):
                        deps_content += '\n'
                        
                    deps_path.write_text(deps_content)
                    logger.info(f"Updated {deps_file} with {len(requirements)} packages")
                    files_updated.append(deps_file)
            
            # Log the update details
            logger.info(f"{language.capitalize()} function block updated with confidence {confidence}")
            
            result = {
                'success': True,
                'files_updated': files_updated,
                'confidence': confidence,
                'code_file': target_path.name,
                'dependencies_file': deps_file if requirements else None,
                'dependencies_updated': bool(requirements),
                'package_count': len(requirements) if requirements else 0,
                'language': language
            }
            
            # Add versioning information if available
            if version_result and version_result['success']:
                result['version_saved'] = version_result.get('version_saved')
                result['versioning_enabled'] = True
            else:
                result['versioning_enabled'] = False
            
            # Add re-execution to verify the fix
            if result['success']:
                re_execution = self._re_execute_function_block(
                    language=language,
                    code=code
                )
                result['re_execution'] = re_execution
                
                # Update success based on execution
                if not re_execution.get('success'):
                    result['success'] = False
                    result['error'] = re_execution.get('error', 'Re-execution failed')
                
            return result
            
        except Exception as e:
            logger.error(f"Error in update_function_block: {e}")
            return {
                'success': False,
                'error': f'Error updating function block: {str(e)}'
            }
    
    def _handle_list_previous_nodes(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """List available previous nodes and their files."""
        if not self.node_context:
            return {
                'success': False,
                'error': 'Previous nodes context not available'
            }
        
        try:
            node_list = self.node_context.get('node_list', 'No previous nodes available')
            index_map = self.node_context.get('index_map', {})
            
            return {
                'success': True,
                'node_count': len(index_map),
                'node_list': node_list,
                'instructions': self.node_context.get('instructions', '')
            }
        except Exception as e:
            logger.error(f"Error listing previous nodes: {e}")
            return {
                'success': False,
                'error': f'Error listing previous nodes: {str(e)}'
            }
    
    def _handle_retrieve_previous_node_file(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieve a file from a previous node."""
        if not self.node_context:
            return {
                'success': False,
                'error': 'Previous nodes context not available'
            }
        
        try:
            node_index = action.get('node_index')
            filename = action.get('filename')
            
            # Get the retrieval function from context
            retrieve_func = self.node_context.get('retrieve_func')
            if not retrieve_func:
                return {
                    'success': False,
                    'error': 'File retrieval function not available'
                }
            
            # Retrieve the file
            success, message, file_path = retrieve_func(node_index, filename)
            
            if success:
                # Copy to input directory for easy access
                input_dir = self.workspace / "input"
                input_dir.mkdir(exist_ok=True)
                dest = input_dir / f"node{node_index}_{filename}"
                shutil.copy2(file_path, dest)
                
                return {
                    'success': True,
                    'message': message,
                    'file_path': str(dest.relative_to(self.workspace)),
                    'absolute_path': str(dest)
                }
            else:
                return {
                    'success': False,
                    'error': message
                }
                
        except Exception as e:
            logger.error(f"Error retrieving file: {e}")
            return {
                'success': False,
                'error': f'Error retrieving file: {str(e)}'
            }
    
    def _handle_retrieve_previous_node_files(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieve multiple files from previous nodes."""
        if not self.node_context:
            return {
                'success': False,
                'error': 'Previous nodes context not available'
            }
        
        try:
            file_requests = action.get('files', [])
            
            # Get the batch retrieval function from context
            retrieve_batch_func = self.node_context.get('retrieve_batch_func')
            if not retrieve_batch_func:
                return {
                    'success': False,
                    'error': 'Batch file retrieval function not available'
                }
            
            # Retrieve all files
            results = retrieve_batch_func(file_requests)
            
            # Copy retrieved files to input directory
            input_dir = self.workspace / "input"
            input_dir.mkdir(exist_ok=True)
            
            for file_info in results.get('retrieved_files', []):
                source = Path(file_info['local_path'])
                dest = input_dir / source.name
                shutil.copy2(source, dest)
                file_info['container_path'] = str(dest.relative_to(self.workspace))
            
            return {
                'success': results['success'],
                'retrieved_count': len(results.get('retrieved_files', [])),
                'failed_count': len(results.get('failed_files', [])),
                'retrieved_files': results.get('retrieved_files', []),
                'failed_files': results.get('failed_files', []),
                'messages': results.get('messages', [])
            }
                
        except Exception as e:
            logger.error(f"Error retrieving multiple files: {e}")
            return {
                'success': False,
                'error': f'Error retrieving multiple files: {str(e)}'
            }
    
    def _handle_research_online(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle online research using web agent.
        
        This action runs on the HOST side, not in the container.
        It uses the web agent tool to research errors and find solutions.
        
        Args:
            action: Action dictionary with query and optional research_type
            
        Returns:
            Result with research findings
        """
        import asyncio
        from datetime import datetime
        
        query = action.get('query', '')
        research_type = action.get('research_type', 'quick')  # quick, detailed, or deep
        
        if not self.web_agent_tool:
            return {
                'success': False,
                'error': 'Web agent not available. Ensure web_agent_tool is configured.',
                'suggestion': 'The web agent needs to be enabled in the bug fixer configuration.'
            }
        
        try:
            # Create output folder for this research
            research_output = self.workspace / "web_agent_research" / f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            research_output.mkdir(parents=True, exist_ok=True)
            
            # Extract context from query for better search
            context = {}
            
            # Try to extract library/package names
            import re
            module_match = re.search(r"(?:ModuleNotFoundError|ImportError|module|package|library)[:\s]+['\"]?(\w+)['\"]?", query, re.IGNORECASE)
            if module_match:
                context["library"] = module_match.group(1)
            
            # Try to extract function/attribute names  
            attr_match = re.search(r"(?:AttributeError|has no attribute|function|method)[:\s]+['\"]?(\w+)['\"]?", query, re.IGNORECASE)
            if attr_match:
                context["function"] = attr_match.group(1)
                
            # Log the research request
            logger.info(f"Starting web research: {query[:100]}...")
            logger.info(f"Research type: {research_type}, Context: {context}")
            
            # Run the web agent research
            start_time = datetime.now()
            
            # Handle async execution
            try:
                # Try to get running loop
                loop = asyncio.get_running_loop()
                # We're in an async context, need to run in executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.web_agent_tool.research_error(
                            error_message=query,
                            context=context,
                            output_folder=research_output,
                            research_type=research_type
                        )
                    )
                    findings = future.result(timeout=self.web_agent_tool.timeout_seconds)
            except RuntimeError:
                # No running loop, we can use asyncio.run directly
                findings = asyncio.run(
                    self.web_agent_tool.research_error(
                        error_message=query,
                        context=context,
                        output_folder=research_output,
                        research_type=research_type
                    )
                )
            
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Web research completed in {duration:.1f}s")
            
            if findings and findings.get('success'):
                # Format findings for the LLM
                formatted_findings = self._format_research_findings(findings)
                
                return {
                    'success': True,
                    'findings': formatted_findings,
                    'raw_findings': findings,
                    'duration_seconds': duration,
                    'research_output_dir': str(research_output),
                    'message': f"Found {len(findings.get('findings', []))} findings, "
                              f"{len(findings.get('solutions', []))} solutions, "
                              f"{len(findings.get('code_examples', []))} code examples"
                }
            else:
                return {
                    'success': False,
                    'error': 'Web research returned no findings',
                    'duration_seconds': duration
                }
                
        except asyncio.TimeoutError:
            return {
                'success': False,
                'error': f'Web research timed out after {self.web_agent_tool.timeout_seconds} seconds',
                'suggestion': 'Try a more specific query or use research_type="quick" for faster results'
            }
        except Exception as e:
            logger.error(f"Web research failed: {e}")
            return {
                'success': False,
                'error': f'Web research failed: {str(e)}'
            }
    
    def _format_research_findings(self, findings: Dict[str, Any]) -> str:
        """Format web agent findings for LLM consumption."""
        parts = []
        
        parts.append("=== WEB RESEARCH FINDINGS ===\n")
        parts.append("IMPORTANT: Use these findings to fix the error!\n\n")
        
        if findings.get('findings'):
            parts.append("KEY FINDINGS:")
            for i, finding in enumerate(findings['findings'][:5], 1):
                parts.append(f"{i}. {finding.get('finding', 'Unknown')}")
            parts.append("")
            
        if findings.get('solutions'):
            parts.append("RECOMMENDED SOLUTIONS (Try these in order):")
            for i, solution in enumerate(findings['solutions'][:5], 1):
                parts.append(f"\n{i}. {solution.get('solution', 'Unknown')}")
                if solution.get('explanation'):
                    parts.append(f"   Explanation: {solution['explanation']}")
            parts.append("")
            
        if findings.get('code_examples'):
            parts.append("\nCODE EXAMPLES:")
            for i, example in enumerate(findings['code_examples'][:3], 1):
                parts.append(f"\n{i}. {example.get('description', 'Example')}:")
                if example.get('code'):
                    parts.append(f"```python\n{example['code']}\n```")
        
        return "\n".join(parts)
