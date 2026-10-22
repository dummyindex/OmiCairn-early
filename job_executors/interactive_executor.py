"""Interactive executor for in-container debugging."""

import os
import json
import time
import threading
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import docker
from docker.models.containers import Container

from models import ExecutionResult, BaseFunctionBlock, FunctionBlockType
from utils.logger import get_logger
from utils.docker_utils import DockerManager
from utils.function_block_validator import FunctionBlockValidator
from agents.unified_bug_fixer import UnifiedBugFixer
from config import config
from constants import (
    CONTAINER_ID_LENGTH, STDOUT_PREVIEW_LINES, LOG_PREVIEW_LINES,
    ENV_OPENAI_API_KEY,
    get_debug_session_timeout,
    get_action_timeout,
    CONTAINER_OPERATION_TIMEOUT,
    LLM_CALL_TIMEOUT
)

logger = get_logger(__name__)


class InteractiveExecutor:
    """Executor that supports interactive debugging within the same container."""
    
    def __init__(self, docker_manager: DockerManager, bug_fixer: Optional[UnifiedBugFixer] = None, output_collector=None, llm_service=None, docker_execution_timeout: Optional[int] = None):
        self.docker_manager = docker_manager
        self.bug_fixer = bug_fixer
        self.output_collector = output_collector
        self.llm_service = llm_service  # Proper LLM service for code checker
        self.client = docker_manager.client
        # Tree context for previous node access (set by NodeExecutor)
        self.tree = None
        self.tree_dir = None
        self.current_node_id = None
        self.current_execution_dir = None
        self.node_dir = None  # Initialize node_dir
        
        # Configurable Docker execution timeout (defaults to 30 minutes)
        from constants import DEFAULT_DOCKER_EXECUTION_TIMEOUT
        self.docker_execution_timeout = docker_execution_timeout if docker_execution_timeout is not None else DEFAULT_DOCKER_EXECUTION_TIMEOUT
    
    def set_tree_context(self, tree, tree_dir: Path, current_node_id: str):
        """Set tree context for previous node access.
        
        Args:
            tree: The analysis tree
            tree_dir: Path to the tree directory
            current_node_id: ID of the current node being executed
        """
        self.tree = tree
        self.tree_dir = tree_dir
        self.current_node_id = current_node_id
        
    def execute_with_debugging(
        self,
        function_block: BaseFunctionBlock,
        input_data_path: Path,
        output_dir: Path,
        parameters: Optional[Dict[str, Any]] = None,
        max_debug_attempts: int = 3,
        debug_callback: Optional[callable] = None,
        node_dir: Optional[Path] = None
    ) -> ExecutionResult:
        """Execute function block with in-container debugging support.
        
        Args:
            function_block: Function block to execute
            input_data_path: Path to input data
            output_dir: Output directory path
            parameters: Optional parameters
            max_debug_attempts: Maximum debugging attempts
            debug_callback: Optional callback for debugging progress
            
        Returns:
            ExecutionResult with success status and outputs
        """
        
        start_time = datetime.now()
        execution_id = f"{function_block.id}_{start_time.strftime('%Y%m%d_%H%M%S')}"
        
        # Create temporary execution directory
        execution_dir = Path(config.temp_dir) / execution_id
        execution_dir.mkdir(parents=True, exist_ok=True)
        
        # Save for bug fixer access
        self.current_execution_dir = execution_dir
        
        # Prepare execution directory (delegate to specific executor)
        from .python_executor import PythonExecutor
        from .r_executor import RExecutor
        
        if function_block.type == FunctionBlockType.PYTHON:
            executor = PythonExecutor(self.docker_manager)
        else:
            executor = RExecutor(self.docker_manager)
            
        executor.prepare_execution_dir(
            execution_dir, 
            function_block,
            input_data_path,
            parameters or {}
        )
        
        # Set up volumes
        volumes = {
            str(execution_dir): {
                "bind": "/workspace",
                "mode": "rw"
            }
        }
        
        # Set up environment
        environment = {
            "COMPUTATION_ID": execution_id,
            "FUNCTION_BLOCK_NAME": function_block.name,
            "INPUT_DIR": "/workspace/input",
            "OUTPUT_DIR": "/workspace/output",
            "PARAMETERS_PATH": "/workspace/parameters.json",
            "OMICAIRN_LOCAL_MODE": "true",
            "OMICAIRN_DEBUG_MODE": "true"  # Enable debug mode
        }
        
        # Initialize validator if specifications exist
        validator = None
        enforce_validation = False
        if function_block.static_config:
            validator = FunctionBlockValidator(function_block.static_config.dict())
            enforce_validation = getattr(function_block.static_config, 'enforce_validation', False)
            
            # Pre-flight validation
            logger.info("Performing pre-flight input validation")
            input_valid, input_errors = validator.validate_input(execution_dir / "input")
            if not input_valid:
                error_msg = f"Input validation failed: {'; '.join(input_errors)}"
                logger.error(error_msg)
                if enforce_validation:
                    # Only fail execution if enforcement is enabled
                    return ExecutionResult(
                        success=False,
                        error=error_msg,
                        logs=f"Pre-flight validation failed\n\nErrors:\n" + '\n'.join(f"- {e}" for e in input_errors),
                        duration=0,
                        exit_code=-1,
                        metadata={'validation_type': 'input', 'validation_errors': input_errors}
                    )
                else:
                    # Just log the validation errors but continue execution
                    logger.warning(f"Input validation failed but enforcement is disabled: {error_msg}")
            else:
                logger.info("Input validation passed")
        
        # Start container in interactive mode
        container = None
        try:
            logger.info(f"Starting interactive container for {function_block.name}")
            container = self._start_interactive_container(
                image=executor.docker_image,
                volumes=volumes,
                environment=environment
            )
            
            # Initial execution
            attempt = 0
            last_error = None
            exit_code = -1  # Default exit code for failures
            previous_attempts = []  # Track all debug attempts
            
            while attempt < max_debug_attempts:
                attempt += 1
                logger.info(f"Execution attempt {attempt}/{max_debug_attempts}")
                
                # Reset last_error for this attempt
                last_error = None
                
                # Execute the function block
                exit_code, stdout, stderr = self._execute_in_container(
                    container,
                    executor.get_execution_command()
                )
                
                if exit_code == 0 and not last_error:  # Check if no validation error
                    # Success!
                    logger.info(f"Function block {function_block.name} completed successfully")
                    
                    # Perform output validation if validator exists
                    if validator:
                        logger.info("Performing output validation")
                        # Get output from container
                        output_valid, output_errors = validator.validate_output(execution_dir / "output")
                        if not output_valid:
                            error_msg = f"Output validation failed: {'; '.join(output_errors)}"
                            logger.error(error_msg)
                            
                            if enforce_validation:
                                # Treat as execution failure - continue to debug
                                last_error = error_msg + "\n\nValidation errors:\n" + '\n'.join(f"- {e}" for e in output_errors)
                                
                                # If we have debug attempts remaining, treat this as a failure to fix
                                if self.bug_fixer and attempt < max_debug_attempts:
                                    logger.info("Output validation failed, attempting to debug")
                                    # Continue to debugging section below
                                else:
                                    # No more attempts, return failure
                                    return ExecutionResult(
                                        success=False,
                                        error=error_msg,
                                        logs=f"Output validation failed after successful execution\n\nValidation errors:\n" + '\n'.join(f"- {e}" for e in output_errors) + f"\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}",
                                        duration=(datetime.now() - start_time).total_seconds(),
                                        exit_code=0,  # Execution succeeded but validation failed
                                        metadata={'validation_type': 'output', 'validation_errors': output_errors, 'debug_attempts': attempt}
                                    )
                            else:
                                # Just log the validation errors but continue as success
                                logger.warning(f"Output validation failed but enforcement is disabled: {error_msg}")
                        else:
                            logger.info("Output validation passed")
                            
                            # Run output collector if available
                            collection_result = None
                            if self.output_collector:
                                # Skip output collector for data loading root nodes
                                if function_block.name == "load_input_data":
                                    logger.debug("Skipping output collector for data loading root node")
                                else:
                                    logger.info("Running output collector to gather scattered outputs")
                                    collection_result = self._run_output_collector(
                                        container, execution_dir, output_dir, 
                                        function_block.name, 
                                        function_block.type.value if hasattr(function_block.type, 'value') else 'python'
                                    )
                                    logger.info(f"Output collector finished: collected {collection_result.get('total_files_collected', 0)} files")
                            else:
                                logger.debug("Output collector is not enabled for this execution")
                            
                            # Validation passed, collect results
                            result = self._collect_results(execution_dir, output_dir, container)
                            result.duration = (datetime.now() - start_time).total_seconds()
                            result.logs = f"Container completed successfully after {attempt} attempt(s)\n\nValidation: PASSED\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
                            result.stdout = stdout
                            result.stderr = stderr
                            result.exit_code = exit_code
                            result.metadata['debug_attempts'] = attempt
                            result.metadata['validation_passed'] = True
                            if self.output_collector and collection_result:
                                result.metadata['output_collection'] = collection_result
                            return result
                    else:
                        # No validator, proceed as before
                        
                        # Run output collector if available
                        collection_result = None
                        if self.output_collector:
                            # Skip output collector for data loading root nodes
                            if function_block.name == "load_input_data":
                                logger.debug("Skipping output collector for data loading root node")
                            else:
                                logger.info("Running output collector to gather scattered outputs")
                                collection_result = self._run_output_collector(
                                    container, execution_dir, output_dir, 
                                    function_block.name, 
                                    function_block.type.value if hasattr(function_block.type, 'value') else 'python'
                                )
                                logger.info(f"Output collector finished: collected {collection_result.get('total_files_collected', 0)} files")
                        else:
                            logger.debug("Output collector is not enabled for this execution")
                        
                        result = self._collect_results(execution_dir, output_dir, container)
                        result.duration = (datetime.now() - start_time).total_seconds()
                        result.logs = f"Container completed successfully after {attempt} attempt(s)\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
                        result.stdout = stdout
                        result.stderr = stderr
                        result.exit_code = exit_code
                        result.metadata['debug_attempts'] = attempt
                        if self.output_collector and collection_result:
                            result.metadata['output_collection'] = collection_result
                        return result
                
                # Execution failed
                logger.error(f"Execution failed with exit code {exit_code}")
                
                # Show execution output for debugging
                if stdout:
                    stdout_lines = stdout.strip().split('\n')
                    logger.error(f"STDOUT from failed execution ({len(stdout_lines)} lines):")
                    for line in stdout_lines[-20:]:  # Show last 20 lines
                        logger.error(f"  {line}")
                
                if stderr:
                    stderr_lines = stderr.strip().split('\n')
                    logger.error(f"STDERR from failed execution ({len(stderr_lines)} lines):")
                    for line in stderr_lines[-20:]:  # Show last 20 lines
                        logger.error(f"  {line}")
                
                # Try to get actual error from execution.log
                actual_error = stderr or stdout
                exec_log_cmd = ["cat", "/workspace/output/execution.log"]
                log_result = container.exec_run(
                    cmd=exec_log_cmd,
                    stdout=True,
                    stderr=False
                )
                if log_result.exit_code == 0:
                    log_output = log_result.output
                    if isinstance(log_output, tuple):
                        log_output = log_output[0]
                    if log_output:
                        execution_log = log_output.decode('utf-8')
                        # Look for Python traceback
                        if 'Traceback' in execution_log:
                            lines = execution_log.split('\n')
                            error_lines = []
                            capturing = False
                            for line in lines:
                                if 'Traceback (most recent call last):' in line:
                                    capturing = True
                                    error_lines = [line]
                                elif capturing:
                                    error_lines.append(line)
                                    if line and not line.startswith(' ') and not line.startswith('\t'):
                                        break
                            if error_lines:
                                actual_error = '\n'.join(error_lines)
                
                last_error = actual_error
                
                # If we have a bug fixer and attempts remaining, try to fix
                logger.info(f"Bug fixer check: bug_fixer={self.bug_fixer is not None}, attempt={attempt}, max_debug_attempts={max_debug_attempts}")
                if self.bug_fixer and attempt < max_debug_attempts:
                    logger.info("Attempting in-container debugging")
                    
                    if debug_callback:
                        debug_callback(f"Debug attempt {attempt}: {last_error}")
                    
                    # Create bug fixer attempt directory
                    bug_fixer_attempt_dir = None
                    if node_dir:
                        bug_fixer_attempt_dir = node_dir / "agent_tasks" / "unified_bug_fixer" / f"attempt_{attempt}"
                        bug_fixer_attempt_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Run bug fixer IN THE SAME CONTAINER
                    debug_result = self._debug_in_container(
                        container=container,
                        function_block=function_block,
                        error_message=last_error,
                        stdout=stdout,
                        stderr=stderr,
                        attempt_number=attempt,
                        previous_attempts=previous_attempts,
                        node_dir=node_dir,
                        bug_fixer_attempt_dir=bug_fixer_attempt_dir
                    )
                    
                    # Track this attempt
                    previous_attempts.append(debug_result)
                    
                    if not debug_result.get('success', False):
                        logger.warning(f"Bug fixing attempt {attempt} failed")
                        # Continue to next attempt
                    else:
                        logger.info(f"Bug fixing attempt {attempt} succeeded, will retry execution")
                        # Continue to next attempt to re-run with fixed code
                else:
                    # No more attempts
                    break
            
            # If we get here, all attempts failed (we only break the loop on failure)
            logger.error(f"Function block {function_block.name} failed after {attempt} attempts")
            
            # Save comprehensive error tracking summary for all attempts
            if previous_attempts and node_dir:
                try:
                    all_attempts_summary_file = node_dir / "agent_tasks" / "bug_fixer" / "all_attempts_summary.json"
                    all_attempts_summary_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    all_attempts_summary = {
                        "total_attempts": len(previous_attempts),
                        "all_failed": True,
                        "function_block": function_block.name,
                        "attempts": []
                    }
                    
                    for i, attempt_data in enumerate(previous_attempts, 1):
                        attempt_summary = {
                            "attempt_number": i,
                            "success": attempt_data.get('success', False),
                            "turn_count": attempt_data.get('turn_count', 0),
                            "duration_seconds": attempt_data.get('duration_seconds', 0),
                            "error_tracking": attempt_data.get('error_tracking', {}),
                            "files_modified": attempt_data.get('files_modified', []),
                            "detailed_turns": attempt_data.get('detailed_turns', [])
                        }
                        all_attempts_summary["attempts"].append(attempt_summary)
                    
                    with open(all_attempts_summary_file, 'w') as f:
                        json.dump(all_attempts_summary, f, indent=2)
                    
                    logger.info(f"Saved all attempts summary to {all_attempts_summary_file}")
                except Exception as e:
                    logger.error(f"Failed to save all attempts summary: {e}")
            
            # Try to get execution.log one more time for the final error
            try:
                log_result = container.exec_run(
                    cmd=["cat", "/workspace/output/execution.log"],
                    stdout=True,
                    stderr=False
                )
                if log_result.exit_code == 0:
                    log_output = log_result.output
                    if isinstance(log_output, tuple):
                        log_output = log_output[0]
                    if log_output:
                        execution_log = log_output.decode('utf-8', errors='replace')  # Handle encoding errors
                        logs_with_exec = f"Container failed after {attempt} attempts\n\nLast error:\n{last_error}\n\nEXECUTION LOG:\n{execution_log}"
                    else:
                        logs_with_exec = f"Container failed after {attempt} attempts\n\nLast error:\n{last_error}"
                else:
                    logs_with_exec = f"Container failed after {attempt} attempts\n\nLast error:\n{last_error}"
            except docker.errors.APIError as e:
                logger.warning(f"Could not retrieve execution log from container: {e}")
                logs_with_exec = f"Container failed after {attempt} attempts\n\nLast error:\n{last_error}\n\n[Could not retrieve execution log: {str(e)}]"
            except UnicodeDecodeError as e:
                logger.warning(f"Execution log contains non-UTF8 data: {e}")
                logs_with_exec = f"Container failed after {attempt} attempts\n\nLast error:\n{last_error}\n\n[Execution log contains binary data]"
            
            return ExecutionResult(
                success=False,
                error=last_error,
                logs=logs_with_exec,
                duration=(datetime.now() - start_time).total_seconds(),
                exit_code=exit_code,
                metadata={'debug_attempts': attempt}
            )
            
        finally:
            # Clean up container
            if container:
                try:
                    container.stop(timeout=10)
                    container.remove()
                except Exception as e:
                    logger.warning(f"Failed to clean up container: {e}")
            
            # Clean up temp directory
            try:
                import shutil
                shutil.rmtree(execution_dir)
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory: {e}")
    
    def _start_interactive_container(
        self,
        image: str,
        volumes: Dict[str, Dict[str, str]],
        environment: Dict[str, str]
    ) -> Container:
        """Start a container in interactive mode that stays running."""
        
        # Start container with a long-running command
        container = self.client.containers.run(
            image=image,
            command=["bash", "-c", "tail -f /dev/null"],  # Keep container running
            volumes=volumes,
            environment=environment,
            working_dir="/workspace",
            detach=True,
            remove=False,  # Manual cleanup in finally block for better control during debugging
            mem_limit=config.container_memory_limit,
            nano_cpus=int(config.container_cpu_limit * 1e9),
            stdin_open=True,
            tty=True
        )
        
        # Wait for container to be ready
        time.sleep(1)
        
        return container
    
    def _execute_in_container(
        self,
        container: Container,
        command: List[str]
    ) -> Tuple[int, str, str]:
        """Execute a command in the running container with timeout support."""
        
        # Use instance-specific timeout
        timeout = self.docker_execution_timeout
        
        # Log the command being executed
        logger.info(f"Executing container command with {timeout}s timeout ({timeout/60:.1f} minutes): {' '.join(command[:3])}...")
        
        # IMPORTANT: There's a known issue with docker exec_run + demux=True that can cause hangs
        # As a workaround, we'll use demux=False and manually parse the output
        
        result_container = []
        exception_container = []
        
        def run_exec():
            try:
                # Execute command WITHOUT demux to avoid hanging issue
                exec_result = container.exec_run(
                    cmd=command,
                    stdout=True,
                    stderr=True,
                    stdin=False,
                    tty=False,
                    demux=False  # CRITICAL: demux=True can cause indefinite hangs
                )
                
                exit_code = exec_result.exit_code
                
                # When demux=False, output is combined stdout+stderr
                output = exec_result.output.decode('utf-8', errors='replace') if exec_result.output else ""
                
                # For now, we'll put all output in stderr if exit code != 0, else in stdout
                if exit_code == 0:
                    stdout = output
                    stderr = ""
                else:
                    stdout = ""
                    stderr = output
                
                result_container.append((exit_code, stdout, stderr))
            except Exception as e:
                exception_container.append(e)
        
        # Run in thread with timeout
        thread = threading.Thread(target=run_exec)
        thread.daemon = True
        thread.start()
        
        # Wait for thread with timeout
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            # Command is still running after timeout
            logger.error(f"Container command timed out after {timeout} seconds: {' '.join(command)}")
            
            # Try to kill the hanging process in the container
            try:
                # First try to identify and kill the specific process
                kill_commands = [
                    ["pkill", "-TERM", "-f", "pip install"],
                    ["pkill", "-TERM", "-f", "python run.py"],
                    ["pkill", "-TERM", "-f", "python function_block.py"]
                ]
                
                for kill_cmd in kill_commands:
                    try:
                        container.exec_run(cmd=kill_cmd, detach=True)
                    except:
                        pass
                
                time.sleep(1)
                
                # Force kill if still running
                container.exec_run(cmd=["pkill", "-KILL", "-f", "python"], detach=True)
            except Exception as e:
                logger.warning(f"Failed to kill hanging process: {e}")
            
            return -1, "", f"Command timed out after {timeout} seconds. This might be due to: 1) Infinite loop in code, 2) Very large computation, 3) Network issues during pip install"
        
        if exception_container:
            # An exception occurred
            error = exception_container[0]
            logger.error(f"Container command failed with error: {error}")
            return -1, "", str(error)
        
        if result_container:
            exit_code, stdout, stderr = result_container[0]
            logger.debug(f"Container command completed with exit code {exit_code}")
            return exit_code, stdout, stderr
        
        # This shouldn't happen
        logger.error("Container command completed without result")
        return -1, "", "Command completed without result"
    
    def _debug_in_container(
        self,
        container: Container,
        function_block: BaseFunctionBlock,
        error_message: str,
        stdout: str,
        stderr: str,
        attempt_number: int,
        previous_attempts: Optional[List[Dict]] = None,
        node_dir: Optional[Path] = None,
        bug_fixer_attempt_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Run bug fixer inside the container with access to actual data.
        
        Returns:
            Debug result dictionary
        """
        
        # Create an in-container bug fixing session
        debug_session = InContainerDebugSession(
            container=container,
            working_dir="/workspace",
            bug_fixer=self.bug_fixer,
            tree=self.tree,
            tree_dir=self.tree_dir,
            current_node_id=self.current_node_id,
            host_workspace_path=self.current_execution_dir
        )
        
        # Run bug fixing session
        result = debug_session.fix_bug(
            node_name=function_block.name,
            error_message=error_message,
            stdout=stdout,
            stderr=stderr,
            attempt_number=attempt_number,
            previous_attempts=previous_attempts,
            node_dir=node_dir,
            bug_fixer_attempt_dir=bug_fixer_attempt_dir,
            node_description=function_block.description
        )
        
        return result
    
    def _collect_results(
        self,
        execution_dir: Path,
        output_dir: Path,
        container: Container
    ) -> ExecutionResult:
        """Collect results from the container."""
        
        # Copy output files from container
        output_files = {}
        figures = []
        
        # List files in container output directory
        exec_result = container.exec_run(
            cmd=["find", "/workspace/output", "-type", "f"],
            stdout=True,
            stderr=False
        )
        
        if exec_result.exit_code == 0:
            # Handle demux output (stdout, stderr) tuple
            stdout = exec_result.output[0] if isinstance(exec_result.output, tuple) else exec_result.output
            files = stdout.decode('utf-8').strip().split('\n') if stdout else []
            
            for file_path in files:
                if file_path:
                    # Get file content from container
                    exec_result = container.exec_run(
                        cmd=["cat", file_path],
                        stdout=True,
                        stderr=False
                    )
                    
                    if exec_result.exit_code == 0:
                        # Save to local output directory
                        relative_path = file_path.replace('/workspace/output/', '')
                        local_path = output_dir / relative_path
                        local_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Write file content (handle demux output)
                        content = exec_result.output[0] if isinstance(exec_result.output, tuple) else exec_result.output
                        local_path.write_bytes(content if content else b"")
                        
                        # Track outputs
                        if relative_path.startswith('figures/'):
                            figures.append(str(local_path))
                        else:
                            output_files[relative_path] = str(local_path)
        
        return ExecutionResult(
            success=True,
            outputs=output_files,
            figures=figures
        )
    
    def _run_output_collector(self, container: Container, execution_dir: Path, 
                             output_dir: Path, node_name: str, function_type: str) -> Dict[str, Any]:
        """Run output collector to gather scattered outputs.
        
        Args:
            container: Docker container
            execution_dir: Execution directory on host  
            output_dir: Output directory on host
            node_name: Name of the function block
            function_type: Type of function (python/R)
            
        Returns:
            Collection result summary
        """
        try:
            # Create output collector with the container
            from agents.output_collector import OutputCollectorAgent
            
            # Get prompt injector if available
            prompt_injector = None
            if hasattr(self, 'bug_fixer') and self.bug_fixer:
                prompt_injector = getattr(self.bug_fixer, 'prompt_injector', None)
            
            collector = OutputCollectorAgent(
                llm_service=self.output_collector,  # This is the LLM service passed in
                container=container,
                working_dir="/workspace",
                max_turns=5,
                enable_domain_knowledge=True,
                prompt_injector=prompt_injector,
                domain_knowledge_domains=['single_cell_genomics']
            )
            
            # The execution_dir is on the host, we need to pass proper paths
            # job_dir should be the job directory that contains agent_tasks
            if self.node_dir:
                # We have node_dir, use it to find the current job
                job_dir = self.current_execution_dir if hasattr(self, 'current_execution_dir') else execution_dir
            else:
                job_dir = execution_dir
                
            # Run collection
            result = collector.collect_outputs(
                job_dir=job_dir,
                output_dir=Path("/workspace/output"),  # Container path for output
                node_name=node_name,
                function_type=function_type
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error running output collector: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'total_files_collected': 0
            }


class InContainerDebugSession:
    """Debug session that runs inside the container."""
    
    def __init__(self, container: Container, working_dir: str, bug_fixer: UnifiedBugFixer, 
                 tree=None, tree_dir=None, current_node_id=None, host_workspace_path=None):
        self.container = container
        self.working_dir = working_dir
        self.bug_fixer = bug_fixer
        self.tree = tree
        self.tree_dir = tree_dir
        self.current_node_id = current_node_id
        self.host_workspace_path = host_workspace_path
        
    def fix_bug(
        self,
        node_name: str,
        error_message: str,
        stdout: str,
        stderr: str,
        attempt_number: int,
        previous_attempts: Optional[List[Dict]] = None,
        node_dir: Optional[Path] = None,
        bug_fixer_attempt_dir: Optional[Path] = None,
        node_description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fix bug with access to actual data in the container.
        
        This method provides a bridge between the bug fixer's action-based
        interface and the container's exec interface.
        """
        
        # Create a container action handler with executor reference for re-execution
        action_handler = ContainerActionHandler(
            container=self.container, 
            working_dir=self.working_dir, 
            executor=self, 
            node_dir=node_dir,
            tree=self.tree,
            tree_dir=self.tree_dir,
            current_node_id=self.current_node_id,
            log_lines_head=100,  # Show first 100 lines
            log_lines_tail=100,   # Show last 100 lines
            bug_fixer=self.bug_fixer  # Pass bug fixer for HOST-side actions
        )
        
        # Set host workspace path if available
        if self.host_workspace_path:
            action_handler.host_workspace_path = self.host_workspace_path
            
        # Set bug fixer attempt directory if provided
        if bug_fixer_attempt_dir:
            action_handler.bug_fixer_attempt_dir = bug_fixer_attempt_dir
        
        # Import the debug session class
        from agents.unified_bug_fixer.enhanced_debug_session import EnhancedDebugSession
        
        # Create enhanced debug session with proper error tracking and domain knowledge
        session_kwargs = {
            "action_executor": action_handler,
            "llm_service": self.bug_fixer.llm_service,
            "max_turns": self.bug_fixer.max_turns,
            "node_dir": node_dir,
            "attempt_number": attempt_number
        }
        
        # Pass bug fixer attempt directory if provided
        if bug_fixer_attempt_dir:
            session_kwargs["bug_fixer_attempt_dir"] = bug_fixer_attempt_dir
        
        # Pass domain knowledge parameters if enabled
        if self.bug_fixer.enable_domain_knowledge:
            session_kwargs["enable_domain_knowledge"] = True
            session_kwargs["prompt_injector"] = self.bug_fixer.prompt_injector
            session_kwargs["domain_knowledge_domains"] = self.bug_fixer.domain_knowledge_domains
        
        session = EnhancedDebugSession(**session_kwargs)
        
        # Preserve original web agent setting
        # Web agent now supported in containers with crawl4ai installed
        original_enable_web_agent = self.bug_fixer.enable_web_agent
        
        # Define timeout - use bug fixer's timeout if available, otherwise config
        if hasattr(self.bug_fixer, 'timeout') and self.bug_fixer.timeout is not None:
            timeout = self.bug_fixer.timeout
        else:
            # Use configured timeout (None means no timeout)
            timeout = get_debug_session_timeout()
            if timeout is None:
                # If None, use a very large timeout (1 week) to effectively disable timeout
                # while still allowing the thread mechanism to work
                timeout = 604800
                logger.info("Debug session timeout disabled (set to 1 week)")
            else:
                logger.info(f"Debug session timeout set to {timeout} seconds")
        
        # Use threading to implement timeout
        result_container = []
        exception_container = []
        
        def run_debug_with_timeout():
            try:
                # Run debug session
                debug_result = session.debug(
                    node_name=node_name,
                    error_message=error_message,
                    stdout=stdout,
                    stderr=stderr,
                    attempt_number=attempt_number,
                    previous_attempts=previous_attempts,
                    node_description=node_description
                )
                result_container.append(debug_result)
            except Exception as e:
                logger.error(f"Error during debug session: {str(e)}")
                exception_container.append(e)
        
        # Create and start the thread
        debug_thread = threading.Thread(target=run_debug_with_timeout)
        debug_thread.daemon = True
        debug_thread.start()
        
        try:
            # Wait for thread to complete with timeout
            debug_thread.join(timeout=timeout)
            
            if debug_thread.is_alive():
                # Thread is still running after timeout
                logger.error(f"Bug fix timed out after {timeout} seconds")
                
                # Create timeout result
                result = {
                    'success': False,
                    'error': f'Bug fix attempt timed out after {timeout} seconds',
                    'timeout': True,
                    'is_container_debug': True,
                    'container_id': self.container.id[:12],
                    'actions_taken': getattr(session, 'actions_taken', []),
                    'files_modified': list(getattr(session, 'files_modified', set())),
                    'turn_count': getattr(session, 'turn_count', 0)
                }
                
                # Note: We can't cleanly kill the thread, but at least we return control
                logger.warning("Debug thread may still be running in background")
                
            elif exception_container:
                # Thread completed with exception
                raise exception_container[0]
            
            elif result_container:
                # Thread completed successfully
                result = result_container[0]
                # Add metadata
                result['is_container_debug'] = True
                result['container_id'] = self.container.id[:12]
            
            else:
                # This shouldn't happen
                result = {
                    'success': False,
                    'error': 'Debug session completed without result',
                    'is_container_debug': True,
                    'container_id': self.container.id[:12]
                }
            
        finally:
            # Restore original settings
            self.bug_fixer.enable_web_agent = original_enable_web_agent
        
        return result


class ContainerActionHandler:
    """Handles bug fixer actions inside a container."""
    
    def __init__(self, container: Container, working_dir: str, executor=None, node_dir=None, tree=None, tree_dir=None, current_node_id=None,
                 log_lines_head: int = 100, log_lines_tail: int = 100, bug_fixer=None):
        self.container = container
        self.working_dir = working_dir
        self.executor = executor  # Reference to InteractiveExecutor for re-execution
        self.node_dir = node_dir  # Node directory for versioning
        self.tree = tree  # Analysis tree for accessing previous nodes
        self.tree_dir = tree_dir  # Tree directory on host
        self.current_node_id = current_node_id  # Current node being executed
        self.log_lines_head = log_lines_head  # Number of lines to show from beginning of output
        self.log_lines_tail = log_lines_tail  # Number of lines to show from end of output
        self.bug_fixer = bug_fixer  # Reference to bug fixer for HOST-side actions
        
        # Initialize timing tracker for actions
        from utils.timing_tracker import ActionTimingTracker
        timing_dir = node_dir / "agent_tasks" / "bug_fixer" / "timing" if node_dir else None
        self.timing_tracker = ActionTimingTracker(output_dir=timing_dir)
        self.current_turn = 0
    
    def increment_turn(self):
        """Increment the current turn number."""
        self.current_turn += 1
    
    def save_timing_summary(self):
        """Save the timing summary to file."""
        if self.timing_tracker and self.timing_tracker.output_dir:
            try:
                self.timing_tracker.save('action_timing_summary.json')
                logger.info(f"Saved action timing to {self.timing_tracker.output_dir / 'action_timing_summary.json'}")
            except Exception as e:
                logger.warning(f"Failed to save timing summary: {e}")
        
    def _execute_with_timeout(self, func, args, action_type: str, timeout: Optional[int] = None):
        """Execute a function with timeout control.
        
        Args:
            func: Function to execute
            args: Arguments for the function
            action_type: Type of action for timeout lookup
            timeout: Override timeout in seconds (None uses config)
            
        Returns:
            Function result or timeout error
        """
        if timeout is None:
            timeout = get_action_timeout(action_type)
        
        result_container = []
        exception_container = []
        
        def run_with_timeout():
            try:
                result = func(*args) if isinstance(args, tuple) else func(args)
                result_container.append(result)
            except Exception as e:
                exception_container.append(e)
        
        thread = threading.Thread(target=run_with_timeout)
        thread.daemon = True
        thread.start()
        
        # Wait for thread with timeout
        thread.join(timeout=timeout)
        
        if thread.is_alive():
            # Thread is still running after timeout
            logger.error(f"Action {action_type} timed out after {timeout} seconds")
            return {
                'success': False,
                'error': f'Action {action_type} timed out after {timeout} seconds',
                'timeout': True
            }
        
        if exception_container:
            # Thread raised an exception
            error = exception_container[0]
            logger.error(f"Action {action_type} failed with error: {str(error)}")
            return {
                'success': False,
                'error': str(error)
            }
        
        if result_container:
            return result_container[0]
        
        # Shouldn't happen
        return {
            'success': False,
            'error': f'Action {action_type} completed without result'
        }
    
    def execute_action(self, action: Dict[str, Any], original_llm_response: str = "") -> Dict[str, Any]:
        """Execute a bug fixer action inside the container with input validation and timeout."""
        
        # Import validator here to avoid circular imports
        from agents.unified_bug_fixer.action_input_validator import ActionInputValidator
        
        try:
            # Validate action input
            validation_result = ActionInputValidator.validate_action(action, original_llm_response)
            
            if not validation_result['valid']:
                error_msg = f"Action validation failed: {'; '.join(validation_result['errors'])}"
                logger.error(f"INVALID ACTION INPUT: {error_msg}")
                logger.error(f"Original action: {action}")
                
                # Create crash report
                crash_report = ActionInputValidator.create_crash_report_action(
                    "INVALID_ACTION_INPUT", 
                    action, 
                    original_llm_response,
                    error_msg
                )
                
                return {
                    'success': False,
                    'error': error_msg,
                    'crash_report': crash_report,
                    'validation_errors': validation_result['errors'],
                    'next_turn_instruction': "Previous action had invalid parameters. Please provide valid parameters for the action."
                }
            
            # Log warnings if any
            if validation_result['warnings']:
                logger.warning(f"Action validation warnings: {'; '.join(validation_result['warnings'])}")
            
            # Use validated action
            validated_action = validation_result['action']
            action_type = validated_action.get('type')
            
            # Extract parameters from validated action (now guaranteed to be safe)
            params = validated_action.copy()
            params.pop('type', None)  # Remove type from params
            params.pop('explanation', None)  # Remove explanation from params  
            params.pop('confidence', None)  # Remove confidence from params
            
            # Track timing for this action
            with self.timing_tracker.track_action(action_type, self.current_turn, metadata={'params': params}) as tracker:
                # Now execute action with validated parameters (all guaranteed to be non-None for required params)
                # Each action is wrapped with timeout control
                if action_type == 'list_directory':
                    path = params.get('path', '.')  # Default to current directory
                    return self._execute_with_timeout(self._list_directory, path, action_type)
                    
                elif action_type == 'read_file':
                    path = params['path']  # Required, guaranteed to exist and be valid
                    max_lines = params.get('max_lines', 1000)  # Optional with default
                    return self._execute_with_timeout(self._read_file, (path, max_lines), action_type)
                
                elif action_type == 'write_file':
                    path = params['path']  # Required
                    content = params['content']  # Required
                    logger.info(f"Writing file: {path}")
                    return self._execute_with_timeout(self._write_file, (path, content), action_type)
                
                elif action_type == 'execute_command':
                    command = params['command']  # Required
                    logger.info(f"Executing command: {command}")
                    return self._execute_with_timeout(self._execute_command, command, action_type)
                
                elif action_type == 'check_file_exists':
                    path = params['path']  # Required
                    return self._execute_with_timeout(self._check_file_exists, path, action_type)
                
                elif action_type == 'head_file':
                    path = params['path']  # Required
                    lines = params.get('lines', 20)  # Optional with default
                    return self._execute_with_timeout(self._head_file, (path, lines), action_type)
                
                elif action_type == 'tail_file':
                    path = params['path']  # Required
                    lines = params.get('lines', 20)  # Optional with default
                    return self._execute_with_timeout(self._tail_file, (path, lines), action_type)
                
                elif action_type == 'grep_file':
                    path = params['path']  # Required
                    pattern = params['pattern']  # Required
                    return self._execute_with_timeout(self._grep_file, (path, pattern), action_type)
                
                elif action_type == 'create_directory':
                    path = params['path']  # Required
                    return self._execute_with_timeout(self._create_directory, path, action_type)
                
                elif action_type == 'install_package':
                    package = params['package']  # Required
                    return self._execute_with_timeout(self._install_package, package, action_type)
                
                elif action_type == 'update_function_block':
                    code = params['code']  # Required
                    requirements = params.get('requirements', [])  # Optional with default
                    language = params.get('language', 'python')  # Optional with default
                    confidence = params.get('confidence', 0.5)  # Optional with default
                    # Use special timeout for update_function_block (30 minutes)
                    return self._execute_with_timeout(
                        self._update_function_block, 
                        (code, requirements, language, confidence), 
                        action_type
                    )
                
                elif action_type == 'list_previous_nodes':
                    return self._execute_with_timeout(self._list_previous_nodes, (), action_type)
                
                elif action_type == 'retrieve_previous_node_file':
                    node_index = params['node_index']  # Required
                    filename = params['filename']  # Required
                    return self._execute_with_timeout(
                        self._retrieve_previous_node_file, 
                        (node_index, filename), 
                        action_type
                    )
                
                elif action_type == 'retrieve_previous_node_files':
                    files = params['files']  # Required
                    return self._execute_with_timeout(self._retrieve_previous_node_files, files, action_type)
                
                elif action_type == 'write_and_run':
                    files = params['files']  # Required
                    run_script = params['run_script']  # Required
                    description = params.get('description')  # Optional
                    # Use special timeout for write_and_run (30 minutes like update_function_block)
                    return self._execute_with_timeout(
                        self._write_and_run, 
                        (files, run_script, description), 
                        'update_function_block'  # Use same timeout as update_function_block
                    )
                
                elif action_type in ['research_online', 'research_online_claude']:
                    # These are HOST-side actions that need to be delegated
                    return self._handle_host_side_action(action_type, params)
                
                else:
                    return {'success': False, 'error': f'Unknown action type: {action_type}'}
                
        except Exception as e:
            # Catch any unexpected crashes and create detailed crash report
            error_msg = f"Unexpected error during action execution: {str(e)}"
            logger.exception(f"SYSTEM CRASH in execute_action: {error_msg}")
            
            # Create crash report
            crash_report = ActionInputValidator.create_crash_report_action(
                "EXECUTION_CRASH",
                action,
                original_llm_response,
                f"{type(e).__name__}: {str(e)}"
            )
            
            return {
                'success': False,
                'error': error_msg,
                'crash_report': crash_report,
                'exception_type': type(e).__name__,
                'next_turn_instruction': "Previous action caused system crash. Please try a different approach or simpler action."
            }
    
    def _list_directory(self, path: str) -> Dict[str, Any]:
        """List directory contents in container."""
        
        # Convert relative path to absolute
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
                # More robust parsing for ls -la output
                # Format: permissions links owner group size month day time/year name
                parts = line.split(None, 8)  # Split on whitespace, max 9 parts
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
    
    def _read_file(self, path: str, max_lines: int = 1000) -> Dict[str, Any]:
        """Read file content from container with line limit.
        
        Note: This uses 'head' command to limit lines. Binary files will fail.
        """
        
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
        
        # Check if it's a binary file extension
        binary_extensions = {'.h5ad', '.h5', '.hdf5', '.pkl', '.pickle', '.npy', '.npz', 
                           '.parquet', '.feather', '.arrow', '.db', '.sqlite', '.gz', 
                           '.zip', '.tar', '.bz2', '.xz', '.jpg', '.png', '.pdf', '.xlsx'}
        
        file_ext = os.path.splitext(path)[1].lower()
        if file_ext in binary_extensions:
            return {
                'success': False,
                'error': f'Cannot read binary file with read_file action. File type: {file_ext}. Use execute_command with Python/R code to read this file type.',
                'path': path,
                'is_binary': True,
                'file_type': file_ext
            }
            
        # First check if file exists
        check_result = self._check_file_exists(path)
        if not check_result['exists']:
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
            # Check if it's a binary file error
            if 'binary file' in error_msg.lower() or 'cannot display' in error_msg.lower():
                return {
                    'success': False,
                    'error': 'File appears to be binary. Use execute_command with appropriate tools to read this file.',
                    'path': path,
                    'is_binary': True
                }
            return {
                'success': False,
                'error': error_msg
            }
        
        content = exec_result.output[0].decode('utf-8', errors='replace') if exec_result.output[0] else ""
        
        # Check if file was truncated by counting total lines
        wc_result = self.container.exec_run(
            cmd=["wc", "-l", path],
            stdout=True,
            stderr=False
        )
        
        total_lines = max_lines  # Default
        truncated = False
        if wc_result.exit_code == 0 and wc_result.output:
            try:
                total_lines = int(wc_result.output.decode('utf-8').split()[0])
                truncated = total_lines > max_lines
            except (ValueError, UnicodeDecodeError, IndexError) as e:
                logger.debug(f"Could not parse wc output for line count: {e}")
                # Keep default values - not critical for operation
        
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
    
    def _write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write file content in container."""
        
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
            
        # Use echo with heredoc for multi-line content
        # Don't escape when using single-quoted heredoc delimiter
        
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
    
    def _execute_command(self, command: str) -> Dict[str, Any]:
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
        
        # Log the command and its output at INFO level for visibility
        logger.info(f"Execute command: {command}")
        logger.info(f"Exit code: {exit_code}")
        
        # Show full output for better debugging
        if stdout:
            # Split into lines and show up to 50 lines
            stdout_lines = stdout.strip().split('\n')
            logger.info(f"STDOUT ({len(stdout_lines)} lines):")
            for line in stdout_lines[:50]:
                logger.info(f"  {line}")
            if len(stdout_lines) > 50:
                logger.info(f"  ... ({len(stdout_lines) - 50} more lines)")
        
        if stderr:
            # Show all stderr as it's usually important
            stderr_lines = stderr.strip().split('\n')
            logger.info(f"STDERR ({len(stderr_lines)} lines):")
            for line in stderr_lines:
                logger.info(f"  {line}")
        
        # Determine success based on exit code
        success = exit_code == 0
        
        result = {
            'success': success,
            'stdout': stdout,
            'stderr': stderr,
            'return_code': exit_code
        }
        
        # If command failed, include error message
        if not success:
            error_msg = stderr if stderr else f"Command failed with exit code {exit_code}"
            result['error'] = error_msg
        
        return result
    
    def _check_file_exists(self, path: str) -> Dict[str, Any]:
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
            'is_file': is_file,
            'is_directory': is_directory,
            'path': path
        }
    
    def _head_file(self, path: str, lines: int) -> Dict[str, Any]:
        """Read first N lines of file."""
        
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
        
        content = exec_result.output[0].decode('utf-8') if exec_result.output[0] else ""
        return {
            'success': True,
            'content': content,
            'lines_returned': len(content.split('\n')) if content else 0
        }
    
    def _tail_file(self, path: str, lines: int) -> Dict[str, Any]:
        """Read last N lines of file."""
        
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
        
        content = exec_result.output[0].decode('utf-8') if exec_result.output[0] else ""
        return {
            'success': True,
            'content': content,
            'lines_returned': len(content.split('\n')) if content else 0
        }
    
    def _grep_file(self, path: str, pattern: str) -> Dict[str, Any]:
        """Search for pattern in file."""
        
        if not path.startswith('/'):
            path = os.path.join(self.working_dir, path)
            
        exec_result = self.container.exec_run(
            cmd=["grep", "-n", pattern, path],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        matches = []
        if exec_result.exit_code == 0 and exec_result.output[0]:
            for line in exec_result.output[0].decode('utf-8').strip().split('\n'):
                if ':' in line:
                    line_num, content = line.split(':', 1)
                    matches.append({
                        'line_number': int(line_num),
                        'content': content
                    })
        
        return {
            'success': True,
            'matches': matches,
            'match_count': len(matches)
        }
    
    def _create_directory(self, path: str) -> Dict[str, Any]:
        """Create directory in container."""
        
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
            'path': path
        }
    
    def _install_package(self, package: str) -> Dict[str, Any]:
        """Install Python package in container."""
        
        exec_result = self.container.exec_run(
            cmd=["pip", "install", package],
            stdout=True,
            stderr=True,
            demux=True
        )
        
        if exec_result.exit_code != 0:
            return {
                'success': False,
                'error': exec_result.output[1].decode('utf-8') if exec_result.output[1] else 'Failed to install package'
            }
        
        return {
            'success': True,
            'output': exec_result.output[0].decode('utf-8') if exec_result.output[0] else ""
        }
    
    
    def _validate_imports(self, original_code: str, new_code: str, language: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validate that critical imports are preserved in the new code.
        
        Returns:
            Tuple of (is_valid, error_message, fixed_code)
        """
        if language.lower() != 'python':
            # Only validate Python imports for now
            return True, None, None
            
        import re
        
        # Extract imports from original code
        import_pattern = r'^(from\s+\S+\s+import\s+\S+|import\s+\S+).*$'
        original_imports = set(re.findall(import_pattern, original_code, re.MULTILINE))
        new_imports = set(re.findall(import_pattern, new_code, re.MULTILINE))
        
        # Check for critical runtime imports
        critical_imports = {
            'from function_block_runtime import previous_nodes',
        }
        
        missing_critical = []
        for critical in critical_imports:
            # Check if any variant of the critical import exists in original
            if any(critical in imp for imp in original_imports):
                # Check if it's missing in new code
                if not any(critical in imp for imp in new_imports):
                    missing_critical.append(critical)
        
        if missing_critical:
            # Try to fix by adding missing imports
            fixed_code = new_code
            
            # Find where to insert imports (after other imports or at the beginning)
            import_lines = []
            code_lines = new_code.split('\n')
            last_import_idx = -1
            
            for i, line in enumerate(code_lines):
                if re.match(import_pattern, line):
                    last_import_idx = i
            
            # Add missing imports after the last import
            if last_import_idx >= 0:
                for imp in missing_critical:
                    code_lines.insert(last_import_idx + 1, imp)
                    last_import_idx += 1
            else:
                # Add at the beginning of the function
                for i, line in enumerate(code_lines):
                    if line.strip().startswith('def run('):
                        for j, imp in enumerate(missing_critical):
                            code_lines.insert(i + 1 + j, '    ' + imp)
                        break
            
            fixed_code = '\n'.join(code_lines)
            
            return False, f"Critical imports were removed: {', '.join(missing_critical)}", fixed_code
        
        return True, None, None
    
    def _update_function_block(self, code: str, requirements: List[str], language: str, confidence: float) -> Dict[str, Any]:
        """Update the function block and optionally re-execute to verify fix.
        
        This enhanced version:
        1. Updates code and requirements
        2. Verifies syntax
        3. Optionally re-executes the function block
        4. Returns execution results for bug fixer context
        5. Updates host function_block folder with versioning
        """
        
        if not code:
            return {
                'success': False,
                'error': 'No code provided for update_function_block'
            }
        
        # Determine file extension based on language
        if language.lower() == 'python':
            code_file = 'function_block.py'
            compile_cmd = 'python -m py_compile function_block.py'
        elif language.lower() == 'r':
            code_file = 'function_block.R'
            compile_cmd = None  # R doesn't have a simple compile check
        else:
            return {
                'success': False,
                'error': f'Unsupported language: {language}'
            }
        
        # Read original code for import validation
        original_code = ""
        try:
            original_path = os.path.join(self.working_dir, code_file)
            read_result = self._read_file(original_path)
            if read_result['success']:
                original_code = read_result['content']
        except Exception as e:
            logger.warning(f"Could not read original code for import validation: {e}")
        
        # Validate imports if we have original code
        if original_code:
            is_valid, error_msg, fixed_code = self._validate_imports(original_code, code, language)
            if not is_valid and fixed_code:
                logger.warning(f"Import validation failed: {error_msg}")
                logger.info("Automatically fixing missing imports...")
                code = fixed_code
        
        # Write code file
        code_path = os.path.join(self.working_dir, code_file)
        code_result = self._write_file(code_path, code)
        
        if not code_result['success']:
            return code_result
        
        # Write requirements if provided
        if requirements:
            req_content = '\n'.join(requirements) + '\n'
            req_result = self._write_file('requirements.txt', req_content)
            if not req_result['success']:
                return {
                    'success': False,
                    'error': f"Code written but failed to update requirements: {req_result.get('error')}"
                }
        
        # Verify syntax for Python
        syntax_valid = True
        syntax_error = None
        if compile_cmd:
            verify_result = self._execute_command(compile_cmd)
            syntax_valid = verify_result['return_code'] == 0
            if not syntax_valid:
                syntax_error = verify_result.get('stderr', 'Unknown syntax error')
        
        # Apply code checking if available
        code_check_result = None
        code_check_applied = False
        if syntax_valid:  # Only check if syntax is valid
            try:
                # Try to import and use code checker
                from agents.code_checker_agent import CodeCheckerAgent
                
                # Use the same LLM service as the main agent
                if self.executor and hasattr(self.executor, 'llm_service') and self.executor.llm_service:
                    code_checker = CodeCheckerAgent(self.executor.llm_service)
                    logger.debug(f"Using main agent's LLM service for code checker: {type(self.executor.llm_service).__name__}")
                else:
                    # No LLM service available - skip code checking
                    logger.debug("No LLM service available for code checker - skipping code quality check")
                    code_checker = None
                
                if code_checker:
                    
                    # Extract function description if available
                    function_description = "Function block code"
                    if hasattr(self, 'current_function_block') and self.current_function_block:
                        function_description = getattr(self.current_function_block, 'description', function_description)
                    
                    code_check_result = code_checker.check_code(
                        code=code,
                        language=language.lower(),
                        requirements=requirements or [],
                        function_description=function_description
                    )
                    
                    # Save code checker reports to bug_fixer folder during debugging
                    if self.node_dir and hasattr(code_checker, 'save_reports_to_directory'):
                        # During bug fixing, save to the current attempt folder
                        if hasattr(self, 'bug_fixer_attempt_dir') and self.bug_fixer_attempt_dir:
                            save_dir = self.bug_fixer_attempt_dir
                            logger.info(f"Saving code checker reports to bug fixer attempt: {save_dir}")
                        else:
                            # Default to function_block folder for function creation
                            save_dir = self.node_dir / "function_block"
                            logger.info(f"Saving code checker reports to function block folder: {save_dir}")
                        
                        code_checker.save_reports_to_directory(save_dir)
                    
                    # Report code checker findings but DO NOT automatically apply fixes
                    # The LLM should decide what to do based on the reported issues
                    if code_check_result.must_fix:
                        logger.info(f"Code checker found critical issues: {len(code_check_result.issues)} issues")
                        if code_check_result.suggested_code:
                            logger.info("Code checker has suggestions available (not automatically applied)")
                        # Store the issues in the result for the LLM to see
                        result['code_checker_issues'] = code_check_result.to_dict()
                    elif not code_check_result.valid:
                        logger.warning(f"Code checker found {len(code_check_result.issues)} issues")
                        result['code_checker_issues'] = code_check_result.to_dict()
                    
            except Exception as e:
                logger.debug(f"Code checking not available or failed: {e}")
                # Continue without code checking - it's optional
        
        # Update host function_block folder with versioning
        if self.node_dir:
            try:
                from agents.unified_bug_fixer.code_versioning import CodeVersionManager
                version_manager = CodeVersionManager(self.node_dir)
                version_result = version_manager.update_function_block(code, requirements, language)
                
                if version_result['success']:
                    logger.info(f"Updated host function_block folder with versioning: {version_result['version_saved']}")
                else:
                    logger.warning(f"Failed to update host function_block folder: {version_result.get('error')}")
                    
            except Exception as e:
                logger.warning(f"Failed to update host function_block folder with versioning: {e}")
        
        # Prepare result
        result = {
            'success': True,
            'path': code_path,
            'confidence': confidence,
            'syntax_valid': syntax_valid,
            'bytes_written': code_result.get('bytes_written', 0),
            'requirements_updated': bool(requirements),
            'language': language
        }
        
        if syntax_error:
            result['syntax_error'] = syntax_error
        
        # Auto re-execution if syntax is valid
        if syntax_valid and hasattr(self, 'executor') and self.executor:
            logger.info("=" * 80)
            logger.info("🔄 UPDATE_FUNCTION_BLOCK: Attempting immediate re-execution...")
            logger.info(f"   Language: {language}")
            logger.info(f"   Code length: {len(code)} chars")
            logger.info(f"   Requirements: {requirements}")
            logger.info(f"   Confidence: {confidence}")
            logger.info("=" * 80)
            
            try:
                # For Python, we need to actually run the function, not just load the file
                if language == 'python':
                    # Create a minimal wrapper to execute the function
                    wrapper_code = '''
import sys
import json
import os
sys.path.insert(0, '/workspace/input')

# Import the function block
from function_block import run

# Set up path_dict and params
path_dict = {
    'input_dir': '/workspace/input',
    'output_dir': '/workspace/output'
}

# Load params if available
params = {}
if os.path.exists('/workspace/params.json'):
    with open('/workspace/params.json') as f:
        params = json.load(f)

# Create output directory
os.makedirs(path_dict['output_dir'], exist_ok=True)

# Run the function
try:
    run(path_dict, params)
    print("FUNCTION_EXECUTION_SUCCESS")
except Exception as e:
    print(f"FUNCTION_EXECUTION_ERROR: {e}")
    import traceback
    traceback.print_exc()
'''
                    # Write the wrapper
                    self._write_file('_test_wrapper.py', wrapper_code)
                    exec_cmd = ['python', '_test_wrapper.py']
                else:
                    # For R, similar approach
                    wrapper_code = '''
source("/workspace/function_block.R")

path_dict <- list(
    input_dir = "/workspace/input",
    output_dir = "/workspace/output"
)

# Load params if available
params <- list()
if (file.exists("/workspace/params.json")) {
    library(jsonlite)
    params <- fromJSON("/workspace/params.json")
}

# Create output directory
dir.create(path_dict$output_dir, recursive = TRUE, showWarnings = FALSE)

# Run the function
tryCatch({
    run(path_dict, params)
    cat("FUNCTION_EXECUTION_SUCCESS\n")
}, error = function(e) {
    cat(paste("FUNCTION_EXECUTION_ERROR:", e$message, "\n"))
    traceback()
})
'''
                    self._write_file('_test_wrapper.R', wrapper_code)
                    exec_cmd = ['Rscript', '_test_wrapper.R']
                
                # Execute the wrapper
                exec_result = self.container.exec_run(
                    cmd=exec_cmd,
                    stdout=True,
                    stderr=True,
                    demux=True,
                    workdir=self.working_dir
                )
                
                stdout = exec_result.output[0].decode('utf-8') if exec_result.output[0] else ""
                stderr = exec_result.output[1].decode('utf-8') if exec_result.output[1] else ""
                
                # Log full execution output
                logger.info(f"Re-execution exit code: {exec_result.exit_code}")
                
                if stdout:
                    stdout_lines = stdout.strip().split('\n')
                    logger.info(f"Re-execution STDOUT ({len(stdout_lines)} lines):")
                    for line in stdout_lines[:30]:  # Show first 30 lines
                        logger.info(f"  {line}")
                    if len(stdout_lines) > 30:
                        logger.info(f"  ... ({len(stdout_lines) - 30} more lines)")
                
                if stderr:
                    stderr_lines = stderr.strip().split('\n')
                    logger.info(f"Re-execution STDERR ({len(stderr_lines)} lines):")
                    for line in stderr_lines[:30]:  # Show first 30 lines
                        logger.info(f"  {line}")
                    if len(stderr_lines) > 30:
                        logger.info(f"  ... ({len(stderr_lines) - 30} more lines)")
                
                # Determine if function actually succeeded
                function_success = False
                actual_error = None
                execution_status = "unknown"  # Default to unknown
                
                # Check for our success marker
                if "FUNCTION_EXECUTION_SUCCESS" in stdout:
                    function_success = True
                    execution_status = "success"
                elif "FUNCTION_EXECUTION_ERROR:" in stdout:
                    # Extract the actual error from stdout
                    execution_status = "error"
                    for line in stdout.split('\n'):
                        if "FUNCTION_EXECUTION_ERROR:" in line:
                            actual_error = line.split("FUNCTION_EXECUTION_ERROR:", 1)[1].strip()
                            break
                
                # Also check stderr for error markers (some execution environments put it there)
                if execution_status == "unknown" and "FUNCTION_EXECUTION_ERROR:" in stderr:
                    execution_status = "error"
                    for line in stderr.split('\n'):
                        if "FUNCTION_EXECUTION_ERROR:" in line:
                            actual_error = line.split("FUNCTION_EXECUTION_ERROR:", 1)[1].strip()
                            break
                
                # If still unknown, treat as failure and extract real error from stderr
                if execution_status == "unknown":
                    function_success = False
                    
                    # Try to extract the actual error from stderr if available
                    if stderr and exec_result.exit_code != 0:
                        # Look for common Python error patterns
                        error_lines = stderr.split('\n')
                        
                        # First, try to find the most specific error (often the first one in a chain)
                        for i, line in enumerate(error_lines):
                            if 'Error:' in line or 'Exception:' in line:
                                # Skip lines that are part of the traceback structure
                                if line.strip().startswith('File ') or line.strip().startswith('Traceback'):
                                    continue
                                # Found an error line, this is likely the actual error
                                actual_error = line.strip()
                                break
                        
                        # If we still don't have an error, check for traceback pattern from the end
                        if not actual_error:
                            for line in reversed(error_lines):
                                if line.strip() and not line.strip().startswith('File ') and not line.strip().startswith('  '):
                                    if 'Error' in line or 'Exception' in line:
                                        actual_error = line.strip()
                                        break
                    
                    # Fallback to generic message only if we couldn't extract anything
                    if not actual_error:
                        actual_error = "Function execution completed but status is unknown (no SUCCESS/ERROR marker found)"
                    
                    logger.warning(f"⚠️ Function execution status UNKNOWN - extracted error: {actual_error}")
                
                # Add execution results
                result['re_execution'] = {
                    'attempted': True,
                    'exit_code': exec_result.exit_code,
                    'success': function_success,  # Based on actual function execution, not just exit code
                    'stdout': stdout,  # Full output for bug fixer
                    'stderr': stderr,  # Full output for bug fixer
                    'function_executed': True,  # We actually ran the function
                    'actual_error': actual_error  # The real error if function failed
                }
                
                # Check for output files regardless of exit code (for better diagnostics)
                list_output = self._list_directory('output')
                output_files = []
                output_file_sizes = {}
                
                if list_output.get('success'):
                    # Filter out hidden files and get sizes
                    for item in list_output.get('contents', []):
                        if not item.startswith('.'):
                            output_files.append(item)
                            # Try to get file size for validation
                            size_cmd = f"stat -c %s /workspace/output/{item} 2>/dev/null || echo 0"
                            size_result = self.container.exec_run(
                                cmd=['sh', '-c', size_cmd],
                                stdout=True,
                                stderr=False
                            )
                            if size_result.exit_code == 0:
                                try:
                                    file_size = int(size_result.output.decode('utf-8').strip())
                                    output_file_sizes[item] = file_size
                                except:
                                    output_file_sizes[item] = -1  # Unknown size
                
                result['re_execution']['output_files'] = output_files
                result['re_execution']['output_file_sizes'] = output_file_sizes
                result['re_execution']['has_output'] = len(output_files) > 0
                
                # Just report what we found - no validation or judgment
                
                # Log detailed outcome - just report facts, no judgment
                if exec_result.exit_code != 0:
                    logger.error(f"❌ Function block re-execution FAILED - script crashed with exit code {exec_result.exit_code}")
                elif function_success:
                    logger.info(f"✅ Function block re-execution completed with exit code 0")
                    logger.info(f"   Output files: {output_files if output_files else 'None'}")
                    if output_file_sizes:
                        logger.info(f"   File sizes: {output_file_sizes}")
                else:
                    logger.warning(f"⚠️ Function block re-execution PARTIAL SUCCESS - script ran but function failed")
                    logger.warning(f"   Exit code: 0 (script executed)")
                    logger.warning(f"   Function success: False (error in run() function)")
                    if actual_error:
                        logger.warning(f"   Function error: {actual_error}")
                    logger.info(f"   The update_function_block action worked correctly, but the fix didn't resolve the issue")
                    
            except Exception as e:
                logger.error(f"Error during re-execution: {e}")
                result['re_execution'] = {
                    'attempted': True,
                    'success': False,
                    'error': str(e)
                }
        
        return result
    
    def _list_previous_nodes(self) -> Dict[str, Any]:
        """List available previous nodes."""
        if not self.tree or not self.tree_dir or not self.current_node_id:
            return {
                'success': False,
                'error': 'Tree context not available for previous node access'
            }
        
        try:
            from utils.node_file_access import NodeFileAccessor
            
            accessor = NodeFileAccessor(self.tree, Path(self.tree_dir))
            index_map = accessor.get_node_index_map(self.current_node_id)
            
            # Create a structured format for better LLM understanding
            nodes_info = []
            for idx, info in sorted(index_map.items()):
                node_entry = {
                    'node_index': idx,
                    'name': info['node_name'],
                    'description': info['description'],
                    'level': info['level'],
                    'is_parent': info['is_parent'],
                    'output_files': info['output_files']
                }
                
                # Try to get input files for this node
                node_id = info['node_id']
                node = self.tree.get_node(node_id)
                if node and node.parent_id:
                    parent_node = self.tree.get_node(node.parent_id)
                    if parent_node and parent_node.output_data_id:
                        # Get parent's output files which are this node's inputs
                        parent_output_dir = Path(parent_node.output_data_id)
                        if parent_output_dir.exists():
                            input_files = [f.name for f in parent_output_dir.iterdir() if f.is_file()]
                            node_entry['input_files'] = input_files
                        else:
                            node_entry['input_files'] = []
                    else:
                        node_entry['input_files'] = []
                else:
                    node_entry['input_files'] = []
                
                nodes_info.append(node_entry)
            
            # Create helpful instructions with explicit paths
            instructions = (
                "Files from previous nodes are pre-staged in subdirectories:\n"
                "- /workspace/input/previous_nodes/node_{idx}/outputs/\n"
                "- /workspace/input/previous_nodes/node_{idx}/inputs/\n\n"
                "To access files:\n"
                "1. DIRECTLY use the correct path in your code:\n"
                "   Example: '/workspace/input/previous_nodes/node_1/outputs/processed_data.h5ad'\n"
                "2. Or use glob to find files:\n"
                "   glob.glob('/workspace/input/previous_nodes/node_*/outputs/*.h5ad')\n"
                "3. Or retrieve additional files using retrieve_previous_node_file action"
            )
            
            # Add explicit file paths to the node info
            for node in nodes_info:
                idx = node['node_index']
                node['file_paths'] = {
                    'outputs': [f"/workspace/input/previous_nodes/node_{idx}/outputs/{f}" 
                               for f in node.get('output_files', [])],
                    'inputs': [f"/workspace/input/previous_nodes/node_{idx}/inputs/{f}" 
                              for f in node.get('input_files', [])]
                }
            
            return {
                'success': True,
                'node_count': len(index_map),
                'nodes': nodes_info,
                'instructions': instructions,
                'example_usage': {
                    'direct_access': {
                        'description': 'Access file directly using full path',
                        'code': "adata = sc.read_h5ad('/workspace/input/previous_nodes/node_1/outputs/processed_data.h5ad')"
                    },
                    'glob_pattern': {
                        'description': 'Find all h5ad files from previous nodes',
                        'code': "h5ad_files = glob.glob('/workspace/input/previous_nodes/node_*/outputs/*.h5ad')"
                    },
                    'retrieve_additional': {
                        'description': 'Retrieve additional files if needed',
                        'action': {
                            'type': 'retrieve_previous_node_file',
                            'node_index': 1,
                            'filename': 'additional_data.csv'
                        }
                    }
                }
            }
        except Exception as e:
            logger.error(f"Error listing previous nodes: {e}")
            return {
                'success': False,
                'error': f'Error listing previous nodes: {str(e)}'
            }
    
    def _retrieve_previous_node_file(self, node_index: int, filename: str) -> Dict[str, Any]:
        """Retrieve a file from a previous node and copy into container."""
        if not self.tree or not self.tree_dir or not self.current_node_id:
            return {
                'success': False,
                'error': 'Tree context not available for previous node access'
            }
        
        try:
            from utils.node_file_access import NodeFileAccessor
            import tempfile
            import shutil
            
            # Get file from host filesystem
            accessor = NodeFileAccessor(self.tree, Path(self.tree_dir))
            index_map = accessor.get_node_index_map(self.current_node_id)
            
            # Retrieve to a temporary location on host
            temp_dir = Path(tempfile.mkdtemp())
            success, message, file_path = accessor.retrieve_node_file(
                node_index, filename, index_map, temp_dir
            )
            
            if success:
                # Create previous_nodes directory in container
                self._create_directory('/workspace/input/previous_nodes')
                
                # The destination path in container
                container_dest = f"/workspace/input/previous_nodes/node{node_index}_{filename}"
                
                # Get the host workspace path (the directory mounted as /workspace)
                # This is typically the execution_dir passed to the container
                host_workspace = self._get_host_workspace_path()
                
                if host_workspace:
                    # Copy file to the mounted volume location
                    dest_path = host_workspace / "input" / "previous_nodes" / f"node{node_index}_{filename}"
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, dest_path)
                    
                    # Verify file exists in container
                    check_result = self._check_file_exists(container_dest)
                    
                    # Cleanup temp
                    shutil.rmtree(temp_dir)
                    
                    if check_result.get('exists'):
                        return {
                            'success': True,
                            'message': f"Retrieved {filename} from node {node_index}",
                            'container_path': container_dest,
                            'file_size': check_result.get('size', 0)
                        }
                    else:
                        return {
                            'success': False,
                            'error': 'File copied but not accessible in container'
                        }
                else:
                    # Fallback: Try to determine workspace from container inspection
                    # This is less reliable but might work
                    shutil.rmtree(temp_dir)
                    return {
                        'success': False,
                        'error': 'Could not determine host workspace path'
                    }
            else:
                shutil.rmtree(temp_dir)
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
    
    def _retrieve_previous_node_files(self, file_requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Retrieve multiple files from previous nodes."""
        if not self.tree or not self.tree_dir or not self.current_node_id:
            return {
                'success': False,
                'error': 'Tree context not available for previous node access'
            }
        
        retrieved = []
        failed = []
        
        for request in file_requests:
            node_index = request.get('node_index')
            filename = request.get('filename')
            
            if not node_index or not filename:
                failed.append({
                    'request': request,
                    'error': 'Missing node_index or filename'
                })
                continue
            
            result = self._retrieve_previous_node_file(node_index, filename)
            
            if result['success']:
                retrieved.append({
                    'node_index': node_index,
                    'filename': filename,
                    'container_path': result.get('container_path'),
                    'message': result.get('message')
                })
            else:
                failed.append({
                    'node_index': node_index,
                    'filename': filename,
                    'error': result.get('error')
                })
        
        return {
            'success': len(failed) == 0,
            'retrieved_count': len(retrieved),
            'failed_count': len(failed),
            'retrieved_files': retrieved,
            'failed_files': failed,
            'message': f"Retrieved {len(retrieved)} files, {len(failed)} failed"
        }
    
    def _get_host_workspace_path(self) -> Optional[Path]:
        """Get the host path that's mounted as /workspace in container."""
        # The executor should set this when creating the handler
        if hasattr(self, 'host_workspace_path'):
            return Path(self.host_workspace_path)
        
        # Try to get from executor if available
        if self.executor and hasattr(self.executor, 'current_execution_dir'):
            return Path(self.executor.current_execution_dir)
        
        # Try to get from node_dir parent
        if self.node_dir:
            # node_dir is like .../nodes/node_xxx/
            # execution_dir would be .../nodes/node_xxx/jobs/job_xxx/
            node_path = Path(self.node_dir)
            if node_path.name.startswith('node_'):
                # Look for the most recent job directory
                jobs_dir = node_path / 'jobs'
                if jobs_dir.exists():
                    job_dirs = sorted([d for d in jobs_dir.iterdir() if d.is_dir()], 
                                    key=lambda x: x.stat().st_mtime, reverse=True)
                    if job_dirs:
                        return job_dirs[0]
        
        return None
    
    def _write_and_run(self, files: List[Dict[str, str]], run_script: str, 
                       description: Optional[str] = None) -> Dict[str, Any]:
        """
        Write multiple files and execute a run script.
        Avoids Python one-liner syntax issues by writing proper scripts.
        
        Args:
            files: List of file dictionaries with 'path' and 'content' keys
            run_script: Shell script content to execute after writing files
            description: Optional description of what this action does
            
        Returns:
            Dictionary with execution results
        """
        import base64
        from datetime import datetime
        
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
            # Create action directory in container
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            action_dir = f"{self.working_dir}/debug_actions/write_and_run_{timestamp}"
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
            logger.info(f"Created write_and_run directory: {action_dir}")
            
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
            
            # Log execution results with configurable truncation
            logger.info(f"Run script exit code: {result['exit_code']}")
            if result['stdout']:
                stdout_lines = result['stdout'].strip().split('\n')
                total_lines = len(stdout_lines)
                if total_lines <= self.log_lines_head + self.log_lines_tail:
                    # Show all lines if within limit
                    logger.info(f"STDOUT ({total_lines} lines):\n" + "\n".join(stdout_lines))
                else:
                    # Show head and tail with ellipsis
                    head_lines = stdout_lines[:self.log_lines_head]
                    tail_lines = stdout_lines[-self.log_lines_tail:]
                    logger.info(f"STDOUT (showing first {self.log_lines_head} and last {self.log_lines_tail} of {total_lines} lines):\n" + 
                               "\n".join(head_lines) + 
                               f"\n... [{total_lines - self.log_lines_head - self.log_lines_tail} lines omitted] ...\n" + 
                               "\n".join(tail_lines))
            if result['stderr']:
                stderr_lines = result['stderr'].strip().split('\n')
                total_lines = len(stderr_lines)
                if total_lines <= self.log_lines_head + self.log_lines_tail:
                    # Show all lines if within limit
                    logger.warning(f"STDERR ({total_lines} lines):\n" + "\n".join(stderr_lines))
                else:
                    # Show head and tail with ellipsis
                    head_lines = stderr_lines[:self.log_lines_head]
                    tail_lines = stderr_lines[-self.log_lines_tail:]
                    logger.warning(f"STDERR (showing first {self.log_lines_head} and last {self.log_lines_tail} of {total_lines} lines):\n" + 
                                  "\n".join(head_lines) + 
                                  f"\n... [{total_lines - self.log_lines_head - self.log_lines_tail} lines omitted] ...\n" + 
                                  "\n".join(tail_lines))
                
        except Exception as e:
            logger.exception(f"Error in write_and_run action: {e}")
            result['error'] = str(e)
            result['exception_type'] = type(e).__name__
            
        return result
    
    def _handle_host_side_action(self, action_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle actions that run on the HOST, not in the container.
        
        These actions include web search and other operations that need
        to run outside the container environment.
        
        Args:
            action_type: Type of action ('research_online' or 'research_online_claude')
            params: Action parameters
            
        Returns:
            Action result dictionary
        """
        # Check if we have access to the bug fixer
        if not self.bug_fixer:
            return {
                'success': False,
                'error': f'Cannot execute {action_type}: Bug fixer reference not available',
                'suggestion': 'This action requires bug fixer to be passed to ContainerActionHandler'
            }
        
        # Create a temporary ActionExecutor to handle the HOST-side action
        # This is a workaround since these actions are implemented in ActionExecutor
        from agents.unified_bug_fixer.action_executor import ActionExecutor
        from pathlib import Path
        
        # Determine workspace path
        workspace = Path(self.node_dir) if self.node_dir else Path.cwd()
        
        try:
            # Create action with params
            action = {'type': action_type}
            action.update(params)
            
            # Handle different types of research actions
            if action_type == 'research_online':
                # Check if web agent tool is available
                if not hasattr(self.bug_fixer, 'web_agent_tool') or not self.bug_fixer.web_agent_tool:
                    return {
                        'success': False,
                        'error': 'Web agent not available. OpenAI-based web search is not enabled.',
                        'suggestion': 'Enable web_agent in MainAgent or use research_online_claude instead'
                    }
                
                # Create temporary executor with web agent
                temp_executor = ActionExecutor(
                    workspace=workspace,
                    interactive_executor=self,  # Pass self as interactive executor to avoid deprecation
                    web_agent_tool=self.bug_fixer.web_agent_tool,
                    enable_claude_web_search=False
                )
                
            elif action_type == 'research_online_claude':
                # Check if Claude web search is enabled
                if not hasattr(self.bug_fixer, 'enable_claude_web_search') or not self.bug_fixer.enable_claude_web_search:
                    return {
                        'success': False,
                        'error': 'Claude web search not enabled.',
                        'suggestion': 'Set enable_claude_web_search=True in MainAgent'
                    }
                
                # Create temporary executor with Claude web search
                temp_executor = ActionExecutor(
                    workspace=workspace,
                    interactive_executor=self,  # Pass self as interactive executor to avoid deprecation
                    web_agent_tool=None,
                    enable_claude_web_search=True
                )
            else:
                return {
                    'success': False,
                    'error': f'Unknown HOST-side action: {action_type}'
                }
            
            # Execute the action using the appropriate handler
            if action_type == 'research_online':
                result = temp_executor._handle_research_online(action)
            elif action_type == 'research_online_claude':
                result = temp_executor._handle_research_online_claude(action)
            else:
                result = {'success': False, 'error': f'No handler for {action_type}'}
            
            # Log the result
            if result.get('success'):
                logger.info(f"HOST-side action {action_type} completed successfully")
                if 'message' in result:
                    logger.info(f"  {result['message']}")
            else:
                logger.warning(f"HOST-side action {action_type} failed: {result.get('error', 'Unknown error')}")
            
            return result
            
        except Exception as e:
            logger.exception(f"Error executing HOST-side action {action_type}: {e}")
            return {
                'success': False,
                'error': f'Failed to execute {action_type}: {str(e)}',
                'exception_type': type(e).__name__
            }