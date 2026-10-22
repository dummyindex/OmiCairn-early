"""
Fixed write_and_run action handler that properly captures stdout/stderr even on failures.
"""

import os
import json
import logging
import base64
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class WriteAndRunAction:
    """Handler for the write_and_run action with improved error capture."""
    
    def __init__(self, container, working_dir: str, node_dir: Optional[Path] = None, 
                 attempt_number: int = 1, turn_number: int = 1):
        """
        Initialize the write_and_run action handler.
        
        Args:
            container: Docker container instance
            working_dir: Working directory inside container (/workspace)
            node_dir: Node directory on host for saving copies
            attempt_number: Current debug attempt number
            turn_number: Current turn within the attempt
        """
        self.container = container
        self.working_dir = working_dir
        self.node_dir = node_dir
        self.attempt_number = attempt_number
        self.turn_number = turn_number
    
    def execute(self, files: List[Dict[str, str]], run_script: str, 
                description: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute the write_and_run action with improved error capture.
        
        Args:
            files: List of file dictionaries with 'path' and 'content' keys
            run_script: Shell script content to execute after writing files
            description: Optional description of what this action does
            
        Returns:
            Dictionary with execution results including proper error messages
        """
        result = {
            'success': False,
            'files_written': [],
            'stdout': '',
            'stderr': '',
            'exit_code': None,
            'error': None,
            'action_dir': None,
            'debug_info': {}  # Additional debug information
        }
        
        try:
            # Create action directory in container
            action_dir = f"{self.working_dir}/debug_actions/attempt_{self.attempt_number}/turn_{self.turn_number}"
            mkdir_cmd = f"mkdir -p {action_dir}"
            
            logger.info(f"Creating action directory: {action_dir}")
            exec_result = self.container.exec_run(
                cmd=["bash", "-c", mkdir_cmd],
                stdout=True,
                stderr=True,
                demux=True
            )
            
            # Safely extract stdout/stderr
            mkdir_stdout = self._safe_decode(exec_result.output[0] if exec_result.output else None)
            mkdir_stderr = self._safe_decode(exec_result.output[1] if exec_result.output else None)
            
            if exec_result.exit_code != 0:
                result['error'] = f"Failed to create action directory: {mkdir_stderr or 'No error message captured'}"
                result['stderr'] = mkdir_stderr
                result['debug_info']['mkdir_failed'] = True
                logger.error(f"Failed to create directory: {result['error']}")
                return result
                
            result['action_dir'] = action_dir
            
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
                    parent_result = self.container.exec_run(
                        cmd=["bash", "-c", mkdir_parent_cmd],
                        stdout=True,
                        stderr=True,
                        demux=True
                    )
                    if parent_result.exit_code != 0:
                        parent_stderr = self._safe_decode(parent_result.output[1] if parent_result.output else None)
                        logger.warning(f"Failed to create parent directory for {file_path}: {parent_stderr}")
                
                # Write file content using base64 encoding to handle special characters safely
                try:
                    encoded_content = base64.b64encode(file_content.encode('utf-8')).decode('ascii')
                    write_cmd = f"echo '{encoded_content}' | base64 -d > '{full_path}'"
                    
                    write_result = self.container.exec_run(
                        cmd=["bash", "-c", write_cmd],
                        stdout=True,
                        stderr=True,
                        demux=True
                    )
                    
                    write_stderr = self._safe_decode(write_result.output[1] if write_result.output else None)
                    
                    if write_result.exit_code == 0:
                        result['files_written'].append(file_path)
                        logger.info(f"Successfully wrote file: {file_path}")
                    else:
                        error_msg = f"Failed to write file {file_path}: {write_stderr or 'No error message'}"
                        logger.warning(error_msg)
                        if 'file_write_errors' not in result['debug_info']:
                            result['debug_info']['file_write_errors'] = []
                        result['debug_info']['file_write_errors'].append(error_msg)
                        
                except Exception as e:
                    error_msg = f"Exception writing file {file_path}: {str(e)}"
                    logger.error(error_msg)
                    if 'file_write_errors' not in result['debug_info']:
                        result['debug_info']['file_write_errors'] = []
                    result['debug_info']['file_write_errors'].append(error_msg)
            
            # Write the run script
            run_script_path = f"{action_dir}/run.sh"
            try:
                # Add error capture wrapper to the script
                wrapped_script = self._wrap_script_with_error_capture(run_script)
                encoded_script = base64.b64encode(wrapped_script.encode('utf-8')).decode('ascii')
                write_script_cmd = f"echo '{encoded_script}' | base64 -d > '{run_script_path}' && chmod +x '{run_script_path}'"
                
                script_result = self.container.exec_run(
                    cmd=["bash", "-c", write_script_cmd],
                    stdout=True,
                    stderr=True,
                    demux=True
                )
                
                script_stderr = self._safe_decode(script_result.output[1] if script_result.output else None)
                
                if script_result.exit_code != 0:
                    result['error'] = f"Failed to write run script: {script_stderr or 'No error message'}"
                    result['stderr'] = script_stderr
                    logger.error(f"Failed to write run script: {result['error']}")
                    return result
                
                result['files_written'].append('run.sh')
                logger.info(f"Successfully wrote run script to {run_script_path}")
                
            except Exception as e:
                result['error'] = f"Exception writing run script: {str(e)}"
                logger.exception(f"Exception writing run script: {e}")
                return result
            
            # Execute the run script with comprehensive error capture
            logger.info(f"Executing run.sh in {action_dir}")
            
            # Use a wrapper command that ensures we capture ALL output
            exec_cmd = f"""cd {action_dir} 2>&1 && {{
                bash ./run.sh 2>&1
                echo "EXEC_EXIT_CODE=$?" >&2
            }} 2>&1 | tee /tmp/write_and_run_output.txt;
            EXIT_CODE=${{PIPESTATUS[0]}};
            echo "===STDERR_START===" >&2;
            grep -v "^EXEC_EXIT_CODE=" /tmp/write_and_run_output.txt >&2 || true;
            echo "===STDERR_END===" >&2;
            exit $EXIT_CODE"""
            
            try:
                exec_result = self.container.exec_run(
                    cmd=["bash", "-c", exec_cmd],
                    stdout=True,
                    stderr=True,
                    demux=True,
                    workdir=action_dir  # Set working directory
                )
                
                # Safely extract and decode output
                raw_stdout = exec_result.output[0] if exec_result.output else b''
                raw_stderr = exec_result.output[1] if exec_result.output else b''
                
                result['stdout'] = self._safe_decode(raw_stdout)
                result['stderr'] = self._safe_decode(raw_stderr)
                result['exit_code'] = exec_result.exit_code
                result['success'] = (exec_result.exit_code == 0)
                
                # If we got no output but command failed, try to get more info
                if exec_result.exit_code != 0 and not result['stdout'] and not result['stderr']:
                    # Try to read the output file directly
                    read_output_cmd = f"cat /tmp/write_and_run_output.txt 2>&1 || echo 'No output file found'"
                    output_result = self.container.exec_run(
                        cmd=["bash", "-c", read_output_cmd],
                        stdout=True,
                        stderr=True,
                        demux=False  # Get combined output
                    )
                    fallback_output = self._safe_decode(output_result.output)
                    
                    if fallback_output and fallback_output != 'No output file found':
                        result['stdout'] = fallback_output
                        result['debug_info']['used_fallback_output'] = True
                    else:
                        # Last resort: provide meaningful error message
                        result['stderr'] = f"Command failed with exit code {exec_result.exit_code} but no output was captured. Possible causes: command not found, permission denied, or syntax error in the script."
                        result['debug_info']['no_output_captured'] = True
                
                # Log execution results
                logger.info(f"Run script exit code: {result['exit_code']}")
                if result['stdout']:
                    stdout_preview = '\n'.join(result['stdout'].strip().split('\n')[:20])
                    logger.info(f"STDOUT (first 20 lines):\n{stdout_preview}")
                if result['stderr']:
                    stderr_preview = '\n'.join(result['stderr'].strip().split('\n')[:20])
                    logger.info(f"STDERR (first 20 lines):\n{stderr_preview}")
                    
            except Exception as e:
                logger.exception(f"Exception during script execution: {e}")
                result['error'] = f"Exception executing script: {str(e)}"
                result['stderr'] = str(e)
                result['exit_code'] = -1
                result['debug_info']['execution_exception'] = str(e)
                
            # Save copies to host if node_dir is provided
            if self.node_dir:
                self._save_to_host(files, run_script, result, description)
                
        except Exception as e:
            logger.exception(f"Unexpected error in write_and_run action: {e}")
            result['error'] = f"Unexpected error: {str(e)}"
            result['stderr'] = str(e)
            result['exception_type'] = type(e).__name__
            result['debug_info']['unexpected_error'] = True
            
            # Try to provide more context about the error
            import traceback
            result['debug_info']['traceback'] = traceback.format_exc()
            
        # Ensure we always have some error message if the action failed
        if not result['success'] and not result['error'] and not result['stderr']:
            result['error'] = "Action failed but no specific error was captured"
            result['stderr'] = "Unknown error - check debug_info for more details"
            
        return result
    
    def _safe_decode(self, data: Optional[bytes], encoding: str = 'utf-8') -> str:
        """Safely decode bytes to string, handling None and decode errors."""
        if data is None:
            return ""
        if isinstance(data, str):
            return data
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, AttributeError):
            # Try with latin-1 as fallback
            try:
                return data.decode('latin-1')
            except:
                # Last resort: return repr
                return repr(data)
    
    def _wrap_script_with_error_capture(self, script: str) -> str:
        """Wrap the script with error capture mechanisms."""
        wrapped = f"""#!/bin/bash
set -o pipefail  # Capture pipe failures
set -E          # ERR trap is inherited by shell functions

# Error handler
error_handler() {{
    local exit_code=$?
    echo "ERROR: Command failed with exit code $exit_code" >&2
    echo "Failed at line $1" >&2
    echo "Command: $2" >&2
}}

# Set trap for errors
trap 'error_handler $LINENO "$BASH_COMMAND"' ERR

# Original script
{script}

# Capture final exit code
EXIT_CODE=$?
echo "Script completed with exit code: $EXIT_CODE" >&2
exit $EXIT_CODE
"""
        return wrapped
    
    def _save_to_host(self, files: List[Dict[str, str]], run_script: str, 
                      result: Dict[str, Any], description: Optional[str] = None):
        """Save copies of files to host for debugging."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Create write_and_run directory in agent_tasks
            war_dir = self.node_dir / "agent_tasks" / "write_and_run" / f"attempt_{self.attempt_number}" / f"turn_{self.turn_number}_{timestamp}"
            war_dir.mkdir(parents=True, exist_ok=True)
            
            # Save all files
            for file_info in files:
                file_path = file_info.get('path', '')
                file_content = file_info.get('content', '')
                
                if file_path:
                    file_full_path = war_dir / file_path
                    file_full_path.parent.mkdir(parents=True, exist_ok=True)
                    file_full_path.write_text(file_content)
                    logger.debug(f"Saved file to host: {file_full_path}")
            
            # Save run script
            run_script_path = war_dir / "run.sh"
            run_script_path.write_text(run_script)
            logger.debug(f"Saved run script to host: {run_script_path}")
            
            # Save execution result
            result_path = war_dir / "result.json"
            result_copy = result.copy()
            # Ensure all values are JSON serializable
            for key in ['stdout', 'stderr', 'error']:
                if key in result_copy and result_copy[key] is not None:
                    result_copy[key] = str(result_copy[key])
            
            result_path.write_text(json.dumps(result_copy, indent=2))
            logger.debug(f"Saved result to host: {result_path}")
            
            # Save description if provided
            if description:
                desc_path = war_dir / "description.txt"
                desc_path.write_text(description)
                
            logger.info(f"Saved write_and_run files to: {war_dir}")
            
        except Exception as e:
            logger.warning(f"Failed to save files to host: {e}")


def integrate_write_and_run_action(handler_class):
    """
    Add write_and_run action to an existing action handler class.
    
    This is a mixin-style function to add the action to BaseContainerActionHandler.
    """
    
    def _action_write_and_run(self, files: List[Dict[str, str]], run_script: str, 
                              description: Optional[str] = None) -> Dict[str, Any]:
        """Execute write_and_run action with improved error capture."""
        # Get current turn and attempt from debug session if available
        attempt_number = getattr(self, 'attempt_number', 1)
        turn_number = getattr(self, 'current_turn', 1)
        
        # Create handler instance
        war_handler = WriteAndRunAction(
            container=self.container,
            working_dir=self.working_dir,
            node_dir=getattr(self, 'node_dir', None),
            attempt_number=attempt_number,
            turn_number=turn_number
        )
        
        # Execute and return result
        return war_handler.execute(files, run_script, description)
    
    # Add method to handler class
    handler_class._action_write_and_run = _action_write_and_run
    
    # Add to allowed actions if needed
    if hasattr(handler_class, 'ALLOWED_ACTIONS'):
        handler_class.ALLOWED_ACTIONS.add('write_and_run')
    
    return handler_class