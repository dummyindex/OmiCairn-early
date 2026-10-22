"""Base container action handler shared by multiple agents."""

import os
import json
import logging
import base64
from typing import Dict, Any, Optional, List, Set
from pathlib import Path
from datetime import datetime
from docker.models.containers import Container

from .action_schemas import ACTION_SCHEMAS

logger = logging.getLogger(__name__)


class BaseContainerActionHandler:
    """Base class for handling actions inside a container."""
    
    def __init__(self, 
                 container: Container, 
                 working_dir: str, 
                 allowed_actions: Set[str],
                 executor=None, 
                 node_dir=None, 
                 tree=None, 
                 tree_dir=None, 
                 current_node_id=None):
        """Initialize the base action handler.
        
        Args:
            container: Docker container instance
            working_dir: Working directory inside the container
            allowed_actions: Set of allowed action types for this handler
            executor: Reference to InteractiveExecutor (optional)
            node_dir: Node directory for versioning (optional)
            tree: Analysis tree for accessing previous nodes (optional)
            tree_dir: Tree directory on host (optional)
            current_node_id: Current node being executed (optional)
        """
        self.container = container
        self.working_dir = working_dir
        self.allowed_actions = allowed_actions
        self.executor = executor
        self.node_dir = node_dir
        self.tree = tree
        self.tree_dir = tree_dir
        self.current_node_id = current_node_id
        
    def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action inside the container.
        
        Args:
            action: Action dictionary with 'type' and parameters
            
        Returns:
            Result dictionary with 'success' and other fields
        """
        try:
            action_type = action.get('type')
            
            # Check if action is allowed
            if action_type not in self.allowed_actions:
                return {
                    'success': False,
                    'error': f'Action type "{action_type}" is not allowed for this agent'
                }
            
            # Check if action is known
            if action_type not in ACTION_SCHEMAS:
                return {
                    'success': False,
                    'error': f'Unknown action type: {action_type}'
                }
            
            # Extract parameters
            params = action.copy()
            params.pop('type', None)
            params.pop('explanation', None)
            params.pop('confidence', None)
            
            # Filter parameters based on schema to avoid unexpected keyword arguments
            schema = ACTION_SCHEMAS[action_type]
            valid_params = {}
            
            # Add required parameters
            for param in schema.get('required', []):
                if param in params:
                    valid_params[param] = params[param]
                else:
                    return {
                        'success': False,
                        'error': f'Missing required parameter: {param}'
                    }
            
            # Add optional parameters if present
            for param in schema.get('optional', []):
                if param in params:
                    valid_params[param] = params[param]
            
            # Add defaults for missing optional parameters
            for param, default_value in schema.get('defaults', {}).items():
                if param not in valid_params:
                    valid_params[param] = default_value
            
            # Log if any parameters were filtered out
            filtered_params = set(params.keys()) - set(valid_params.keys())
            if filtered_params:
                logger.warning(f"Ignoring unexpected parameters for action '{action_type}': {filtered_params}")
            
            # Route to appropriate method
            method_name = f'_action_{action_type}'
            if hasattr(self, method_name):
                method = getattr(self, method_name)
                return method(**valid_params)
            else:
                return {
                    'success': False,
                    'error': f'Action "{action_type}" not implemented'
                }
                
        except Exception as e:
            logger.exception(f"Error executing action: {e}")
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'exception_type': type(e).__name__
            }
    
    # Common action implementations
    
    def _action_list_directory(self, path: str = '.') -> Dict[str, Any]:
        """List directory contents in container."""
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
            
        exec_result = self.container.exec_run(
            cmd=["ls", "-la", path],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        if exec_result.exit_code != 0:
            return {
                'success': False,
                'error': exec_result.output[1].decode('utf-8') if exec_result.output[1] else 'Failed to list directory'
            }
        
        # Parse ls output
        output = exec_result.output[0].decode('utf-8') if exec_result.output[0] else ""
        entries = []
        
        for line in output.strip().split('\n')[1:]:  # Skip total line
            if line and not line.startswith('total'):
                parts = line.split(None, 8)
                if len(parts) >= 9:
                    name = parts[8]
                    if name not in ['.', '..']:
                        entries.append({
                            'name': name,
                            'type': 'directory' if parts[0].startswith('d') else 'file',
                            'size': int(parts[4]) if not parts[0].startswith('d') else None
                        })
        
        return {
            'success': True,
            'path': path,
            'entries': entries
        }
    
    def _action_read_file(self, path: str, max_lines: int = 1000) -> Dict[str, Any]:
        """Read file content from container with line limit."""
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
        
        # Check for binary files
        binary_extensions = {'.h5ad', '.h5', '.hdf5', '.pkl', '.pickle', '.npy', '.npz', 
                           '.parquet', '.feather', '.arrow', '.db', '.sqlite', '.gz', 
                           '.zip', '.tar', '.bz2', '.xz', '.jpg', '.png', '.pdf', '.xlsx'}
        
        file_ext = os.path.splitext(path)[1].lower()
        if file_ext in binary_extensions:
            return {
                'success': False,
                'error': f'Cannot read binary file with read_file action. File type: {file_ext}',
                'path': path,
                'is_binary': True,
                'file_type': file_ext
            }
            
        # Check if file exists
        check_result = self._action_check_file_exists(path)
        if not check_result.get('exists', False):
            return {
                'success': False,
                'error': f'File not found: {path}'
            }
        
        # Use head to limit lines
        exec_result = self.container.exec_run(
            cmd=["head", f"-n{max_lines}", path],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        if exec_result.exit_code != 0:
            error_msg = exec_result.output[1].decode('utf-8') if exec_result.output[1] else 'Failed to read file'
            return {
                'success': False,
                'error': error_msg
            }
        
        content = exec_result.output[0].decode('utf-8', errors='replace') if exec_result.output[0] else ""
        
        # Check if file was truncated
        wc_result = self.container.exec_run(
            cmd=["wc", "-l", path],
            stdout=True,
            stderr=False
        )
        
        total_lines = max_lines
        truncated = False
        if wc_result.exit_code == 0 and wc_result.output:
            try:
                total_lines = int(wc_result.output.decode('utf-8').split()[0])
                truncated = total_lines > max_lines
            except:
                pass
        
        result = {
            'success': True,
            'content': content,
            'path': path,
            'line_count': min(total_lines, max_lines),
            'total_lines': total_lines,
            'truncated': truncated,
            'max_lines': max_lines
        }
        
        if truncated:
            result['content'] += f"\n\n... (truncated after {max_lines} lines, file has {total_lines} total lines)"
            
        return result
    
    def _action_write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write file content in container."""
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
            
        exec_result = self.container.exec_run(
            cmd=["bash", "-c", f'cat > "{path}" << \'EOF\'\n{content}\nEOF'],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        if exec_result.exit_code != 0:
            return {
                'success': False,
                'error': exec_result.output[1].decode('utf-8') if exec_result.output[1] else 'Failed to write file'
            }
        
        return {
            'success': True,
            'path': path,
            'bytes_written': len(content.encode('utf-8'))
        }
    
    def _action_execute_command(self, command: str) -> Dict[str, Any]:
        """Execute command in container."""
        exec_result = self.container.exec_run(
            cmd=["bash", "-c", f"cd {self.working_dir} && {command}"],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        stdout = exec_result.output[0].decode('utf-8') if exec_result.output[0] else ""
        stderr = exec_result.output[1].decode('utf-8') if exec_result.output[1] else ""
        exit_code = exec_result.exit_code
        
        logger.info(f"Execute command: {command}")
        logger.info(f"Exit code: {exit_code}")
        
        success = exit_code == 0
        
        result = {
            'success': success,
            'stdout': stdout,
            'stderr': stderr,
            'return_code': exit_code
        }
        
        if not success:
            error_msg = stderr if stderr else f"Command failed with exit code {exit_code}"
            result['error'] = error_msg
        
        return result
    
    def _action_check_file_exists(self, path: str) -> Dict[str, Any]:
        """Check if file exists in container."""
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
            
        exec_result = self.container.exec_run(
            cmd=["test", "-e", path],
            stdout=False,
            stderr=False
        )
        
        exists = exec_result.exit_code == 0
        
        if exists:
            # Check if it's a file or directory
            exec_result = self.container.exec_run(
                cmd=["test", "-f", path],
                stdout=False,
                stderr=False
            )
            is_file = exec_result.exit_code == 0
            
            exec_result = self.container.exec_run(
                cmd=["test", "-d", path],
                stdout=False,
                stderr=False
            )
            is_directory = exec_result.exit_code == 0
        else:
            is_file = False
            is_directory = False
        
        return {
            'success': True,
            'exists': exists,
            'path': path,
            'is_file': is_file,
            'is_directory': is_directory
        }
    
    def _action_head_file(self, path: str, lines: int = 20) -> Dict[str, Any]:
        """Read first N lines of a file."""
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
            
        exec_result = self.container.exec_run(
            cmd=["head", f"-n{lines}", path],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        if exec_result.exit_code != 0:
            return {
                'success': False,
                'error': exec_result.output[1].decode('utf-8') if exec_result.output[1] else 'Failed to read file'
            }
        
        content = exec_result.output[0].decode('utf-8', errors='replace') if exec_result.output[0] else ""
        
        return {
            'success': True,
            'content': content,
            'path': path,
            'lines_requested': lines
        }
    
    def _action_tail_file(self, path: str, lines: int = 20) -> Dict[str, Any]:
        """Read last N lines of a file."""
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
            
        exec_result = self.container.exec_run(
            cmd=["tail", f"-n{lines}", path],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        if exec_result.exit_code != 0:
            return {
                'success': False,
                'error': exec_result.output[1].decode('utf-8') if exec_result.output[1] else 'Failed to read file'
            }
        
        content = exec_result.output[0].decode('utf-8', errors='replace') if exec_result.output[0] else ""
        
        return {
            'success': True,
            'content': content,
            'path': path,
            'lines_requested': lines
        }
    
    def _action_grep_file(self, path: str, pattern: str) -> Dict[str, Any]:
        """Search for pattern in a file."""
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
            
        exec_result = self.container.exec_run(
            cmd=["grep", "-n", pattern, path],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        # grep returns exit code 1 if no matches found, which is not an error
        if exec_result.exit_code == 2:
            return {
                'success': False,
                'error': exec_result.output[1].decode('utf-8') if exec_result.output[1] else 'Failed to search file'
            }
        
        matches = []
        if exec_result.exit_code == 0 and exec_result.output[0]:
            output = exec_result.output[0].decode('utf-8', errors='replace')
            for line in output.strip().split('\n'):
                if ':' in line:
                    line_num, content = line.split(':', 1)
                    matches.append({
                        'line_number': int(line_num),
                        'content': content
                    })
        
        return {
            'success': True,
            'path': path,
            'pattern': pattern,
            'matches': matches,
            'match_count': len(matches)
        }
    
    def _action_create_directory(self, path: str) -> Dict[str, Any]:
        """Create a directory."""
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
            
        exec_result = self.container.exec_run(
            cmd=["mkdir", "-p", path],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        if exec_result.exit_code != 0:
            return {
                'success': False,
                'error': exec_result.output[1].decode('utf-8') if exec_result.output[1] else 'Failed to create directory'
            }
        
        return {
            'success': True,
            'path': path,
            'created': True
        }
    
    # New actions for output collector
    
    def _action_tree_directory(self, path: str, max_depth: int = 3) -> Dict[str, Any]:
        """Show directory tree structure."""
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
        
        # Try using tree command first
        exec_result = self.container.exec_run(
            cmd=["tree", "-L", str(max_depth), path],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        if exec_result.exit_code == 0:
            output = exec_result.output[0].decode('utf-8') if exec_result.output[0] else ""
            return {
                'success': True,
                'path': path,
                'tree': output,
                'max_depth': max_depth
            }
        
        # Fallback to find command if tree is not available
        exec_result = self.container.exec_run(
            cmd=["find", path, "-maxdepth", str(max_depth), "-type", "f", "-o", "-type", "d"],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        if exec_result.exit_code != 0:
            return {
                'success': False,
                'error': exec_result.output[1].decode('utf-8') if exec_result.output[1] else 'Failed to show directory tree'
            }
        
        output = exec_result.output[0].decode('utf-8') if exec_result.output[0] else ""
        return {
            'success': True,
            'path': path,
            'tree': output,
            'max_depth': max_depth,
            'note': 'Using find command as tree is not available'
        }
    
    def _action_find_files(self, pattern: str, path: str = '.', type: str = 'all') -> Dict[str, Any]:
        """Find files matching pattern."""
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
        
        # Build find command based on type
        cmd = ["find", path]
        if type == 'file':
            cmd.extend(["-type", "f"])
        elif type == 'directory':
            cmd.extend(["-type", "d"])
        # 'all' doesn't need type specification
        
        cmd.extend(["-name", pattern])
        
        exec_result = self.container.exec_run(
            cmd=cmd,
            stdout=True,
            stderr=True,
            demux=True
        )
        
        if exec_result.exit_code != 0:
            stderr = exec_result.output[1].decode('utf-8') if exec_result.output[1] else ''
            # find returns 1 if no files found, which is not an error
            if 'No such file or directory' in stderr:
                return {
                    'success': False,
                    'error': stderr
                }
        
        files = []
        if exec_result.output[0]:
            output = exec_result.output[0].decode('utf-8')
            files = [f.strip() for f in output.strip().split('\n') if f.strip()]
        
        return {
            'success': True,
            'pattern': pattern,
            'path': path,
            'type': type,
            'files': files,
            'count': len(files)
        }
    
    def _action_copy_file(self, source: str, destination: str) -> Dict[str, Any]:
        """Copy a file to another location."""
        if not source.startswith('/'):
            source = os.path.join(self.working_dir, source)
        if not destination.startswith('/'):
            destination = os.path.join(self.working_dir, destination)
        
        # Create destination directory if needed
        dest_dir = os.path.dirname(destination)
        mkdir_result = self.container.exec_run(
            cmd=["mkdir", "-p", dest_dir],
            stdout=False,
            stderr=False
        )
        
        # Copy the file
        exec_result = self.container.exec_run(
            cmd=["cp", "-p", source, destination],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        if exec_result.exit_code != 0:
            return {
                'success': False,
                'error': exec_result.output[1].decode('utf-8') if exec_result.output[1] else 'Failed to copy file'
            }
        
        return {
            'success': True,
            'source': source,
            'destination': destination,
            'copied': True
        }
    
    def _action_move_file(self, source: str, destination: str) -> Dict[str, Any]:
        """Move a file to another location."""
        if not source.startswith('/'):
            source = os.path.join(self.working_dir, source)
        if not destination.startswith('/'):
            destination = os.path.join(self.working_dir, destination)
        
        # Create destination directory if needed
        dest_dir = os.path.dirname(destination)
        mkdir_result = self.container.exec_run(
            cmd=["mkdir", "-p", dest_dir],
            stdout=False,
            stderr=False
        )
        
        # Move the file
        exec_result = self.container.exec_run(
            cmd=["mv", source, destination],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        if exec_result.exit_code != 0:
            return {
                'success': False,
                'error': exec_result.output[1].decode('utf-8') if exec_result.output[1] else 'Failed to move file'
            }
        
        return {
            'success': True,
            'source': source,
            'destination': destination,
            'moved': True
        }
    
    def _action_get_file_info(self, path: str) -> Dict[str, Any]:
        """Get file metadata."""
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
        
        # Use stat command to get file info
        exec_result = self.container.exec_run(
            cmd=["stat", "-c", "%s|%Y|%U|%G|%a|%F", path],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        if exec_result.exit_code != 0:
            return {
                'success': False,
                'error': exec_result.output[1].decode('utf-8') if exec_result.output[1] else 'Failed to get file info'
            }
        
        output = exec_result.output[0].decode('utf-8').strip()
        parts = output.split('|')
        
        if len(parts) >= 6:
            import datetime
            file_info = {
                'success': True,
                'path': path,
                'size': int(parts[0]),
                'modified_timestamp': int(parts[1]),
                'modified_time': datetime.datetime.fromtimestamp(int(parts[1])).isoformat(),
                'owner': parts[2],
                'group': parts[3],
                'permissions': parts[4],
                'type': parts[5]
            }
            
            # Add human-readable size
            size = file_info['size']
            for unit in ['B', 'KB', 'MB', 'GB']:
                if size < 1024:
                    file_info['size_human'] = f"{size:.1f} {unit}"
                    break
                size /= 1024
            else:
                file_info['size_human'] = f"{size:.1f} TB"
            
            return file_info
        
        return {
            'success': False,
            'error': 'Failed to parse file info'
        }
    
    def _action_write_and_run(self, files: List[Dict[str, str]], run_script: str, 
                              description: Optional[str] = None) -> Dict[str, Any]:
        """
        Write multiple files and execute a run script.
        
        This action avoids Python one-liner syntax issues by allowing the LLM to write
        proper script files and execute them.
        
        Args:
            files: List of file dictionaries with 'path' and 'content' keys
            run_script: Shell script content to execute after writing files
            description: Optional description of what this action does
            
        Returns:
            Dictionary with execution results
        """
        result = {
            'success': False,
            'files_written': [],
            'stdout': '',
            'stderr': '',
            'exit_code': None,
            'error': None,
            'action_dir': None
        }
        
        try:
            # Get current turn and attempt info if available
            attempt_number = getattr(self, 'attempt_number', 1)
            turn_number = getattr(self, 'current_turn', 1)
            
            # Create action directory in container
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            action_dir = f"{self.working_dir}/debug_actions/attempt_{attempt_number}/turn_{turn_number}_{timestamp}"
            mkdir_cmd = f"mkdir -p {action_dir}"
            
            exec_result = self.container.exec_run(
                cmd=["bash", "-c", mkdir_cmd],
                stdout=True,
                stderr=True,
                demux=True
            )
            
            if exec_result.exit_code != 0:
                result['error'] = f"Failed to create action directory: {exec_result.output[1].decode('utf-8') if exec_result.output[1] else 'Unknown error'}"
                return result
                
            result['action_dir'] = action_dir
            logger.info(f"Created action directory: {action_dir}")
            
            # Write all files to the action directory
            for file_info in files:
                file_path = file_info.get('path', '')
                file_content = file_info.get('content', '')
                
                if not file_path:
                    logger.warning("Skipping file with empty path")
                    continue
                    
                # Ensure path is relative and safe
                if file_path.startswith('/'):
                    file_path = file_path[1:]
                    
                full_path = f"{action_dir}/{file_path}"
                
                # Create parent directories if needed
                parent_dir = os.path.dirname(full_path)
                if parent_dir and parent_dir != action_dir:
                    mkdir_parent_cmd = f"mkdir -p {parent_dir}"
                    self.container.exec_run(
                        cmd=["bash", "-c", mkdir_parent_cmd],
                        stdout=True,
                        stderr=True,
                        demux=True
                    )
                
                # Write file content using base64 to handle special characters safely
                encoded_content = base64.b64encode(file_content.encode('utf-8')).decode('ascii')
                write_cmd = f"echo '{encoded_content}' | base64 -d > '{full_path}'"
                
                write_result = self.container.exec_run(
                    cmd=["bash", "-c", write_cmd],
                    stdout=True,
                    stderr=True,
                    demux=True
                )
                
                if write_result.exit_code == 0:
                    result['files_written'].append(file_path)
                    logger.info(f"Wrote file: {file_path}")
                else:
                    logger.warning(f"Failed to write file {file_path}: {write_result.output[1].decode('utf-8') if write_result.output[1] else 'Unknown error'}")
            
            # Write the run script
            run_script_path = f"{action_dir}/run.sh"
            encoded_script = base64.b64encode(run_script.encode('utf-8')).decode('ascii')
            write_script_cmd = f"echo '{encoded_script}' | base64 -d > '{run_script_path}' && chmod +x '{run_script_path}'"
            
            script_result = self.container.exec_run(
                cmd=["bash", "-c", write_script_cmd],
                stdout=True,
                stderr=True,
                demux=True
            )
            
            if script_result.exit_code != 0:
                result['error'] = f"Failed to write run script: {script_result.output[1].decode('utf-8') if script_result.output[1] else 'Unknown error'}"
                return result
            
            result['files_written'].append('run.sh')
            logger.info(f"Wrote run script to {run_script_path}")
            
            # Execute the run script
            logger.info(f"Executing run.sh in {action_dir}")
            exec_cmd = f"cd {action_dir} && bash ./run.sh"
            
            exec_result = self.container.exec_run(
                cmd=["bash", "-c", exec_cmd],
                stdout=True,
                stderr=True,
                demux=True
            )
            
            result['stdout'] = exec_result.output[0].decode('utf-8') if exec_result.output[0] else ""
            result['stderr'] = exec_result.output[1].decode('utf-8') if exec_result.output[1] else ""
            result['exit_code'] = exec_result.exit_code
            result['success'] = (exec_result.exit_code == 0)
            
            # Log execution results
            logger.info(f"Run script exit code: {result['exit_code']}")
            if result['stdout']:
                stdout_lines = result['stdout'].strip().split('\n')[:20]
                logger.info(f"STDOUT (first 20 lines):\n" + "\n".join(stdout_lines))
            if result['stderr']:
                stderr_lines = result['stderr'].strip().split('\n')[:20]
                logger.info(f"STDERR (first 20 lines):\n" + "\n".join(stderr_lines))
            
            # Save to host if node_dir is available
            if self.node_dir:
                self._save_write_and_run_to_host(files, run_script, result, description, 
                                                  attempt_number, turn_number)
                
        except Exception as e:
            logger.exception(f"Error in write_and_run action: {e}")
            result['error'] = str(e)
            result['exception_type'] = type(e).__name__
            
        return result
    
    def _save_write_and_run_to_host(self, files: List[Dict[str, str]], run_script: str, 
                                     result: Dict[str, Any], description: Optional[str],
                                     attempt_number: int, turn_number: int):
        """Save write_and_run files to host for debugging."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            host_dir = self.node_dir / "agent_tasks" / "bug_fixer" / f"attempt_{attempt_number}" / f"turn_{turn_number}_write_and_run_{timestamp}"
            host_dir.mkdir(parents=True, exist_ok=True)
            
            # Save metadata
            metadata = {
                'timestamp': datetime.now().isoformat(),
                'attempt': attempt_number,
                'turn': turn_number,
                'description': description,
                'files_written': result['files_written'],
                'exit_code': result['exit_code'],
                'success': result['success'],
                'error': result.get('error'),
                'container_action_dir': result.get('action_dir')
            }
            
            with open(host_dir / 'metadata.json', 'w') as f:
                json.dump(metadata, f, indent=2)
            
            # Save all files
            for file_info in files:
                file_path = file_info.get('path', '')
                file_content = file_info.get('content', '')
                
                if file_path:
                    file_host_path = host_dir / file_path
                    file_host_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(file_host_path, 'w') as f:
                        f.write(file_content)
            
            # Save run script
            with open(host_dir / 'run.sh', 'w') as f:
                f.write(run_script)
            
            # Save execution results
            with open(host_dir / 'execution_result.txt', 'w') as f:
                f.write(f"Exit Code: {result['exit_code']}\n")
                f.write(f"Success: {result['success']}\n")
                f.write(f"\n=== STDOUT ===\n{result['stdout']}\n")
                f.write(f"\n=== STDERR ===\n{result['stderr']}\n")
                if result.get('error'):
                    f.write(f"\n=== ERROR ===\n{result['error']}\n")
                    
            logger.info(f"Saved write_and_run files to host: {host_dir}")
            
        except Exception as e:
            logger.warning(f"Failed to save write_and_run files to host: {e}")