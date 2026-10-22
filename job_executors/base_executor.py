"""Base class for job executors."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional, List
import json
import tempfile
import shutil
from datetime import datetime
import docker

from models import ExecutionResult, BaseFunctionBlock, FunctionBlockType
from utils.logger import get_logger
from utils.docker_utils import DockerManager
from config import config

logger = get_logger(__name__)


class BaseExecutor(ABC):
    """Base class for function block executors."""
    
    def __init__(self, docker_manager: DockerManager):
        self.docker_manager = docker_manager
        self.temp_dir = config.temp_dir
        
    @property
    @abstractmethod
    def block_type(self) -> FunctionBlockType:
        """Return the function block type this executor handles."""
        pass
    
    @property
    @abstractmethod
    def docker_image(self) -> str:
        """Return the Docker image to use."""
        pass
    
    @abstractmethod
    def prepare_execution_dir(
        self, 
        execution_dir: Path,
        function_block: BaseFunctionBlock,
        input_data_path: Path,
        parameters: Dict[str, Any],
        previous_nodes_metadata: Optional[Dict[str, Any]] = None,
        propagated_failure_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Prepare the execution directory with necessary files."""
        pass
    
    def execute(
        self,
        function_block: BaseFunctionBlock,
        input_data_path: Path,
        output_dir: Path,
        parameters: Optional[Dict[str, Any]] = None,
        previous_nodes_metadata: Optional[Dict[str, Any]] = None,
        propagated_failure_context: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """Execute a function block in an isolated container."""
        
        start_time = datetime.now()
        execution_id = f"{function_block.id}_{start_time.strftime('%Y%m%d_%H%M%S')}"
        
        # Create temporary execution directory
        execution_dir = self.temp_dir / execution_id
        execution_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Prepare execution directory
            logger.info(f"Preparing execution environment for {function_block.name}")
            self.prepare_execution_dir(
                execution_dir, 
                function_block,
                input_data_path,
                parameters or {},
                previous_nodes_metadata,
                propagated_failure_context
            )
            
            # Set up volumes
            volumes = {
                str(execution_dir): {
                    "bind": "/workspace",
                    "mode": "rw"
                }
            }
            
            # Set up environment variables
            environment = {
                "COMPUTATION_ID": execution_id,
                "FUNCTION_BLOCK_NAME": function_block.name,
                "INPUT_DIR": "/workspace/input",
                "OUTPUT_DIR": "/workspace/output",
                "PARAMETERS_PATH": "/workspace/parameters.json",
                "OMICAIRN_LOCAL_MODE": "true"
            }
            
            # Determine which Docker image to use
            docker_image = self.get_docker_image(function_block)
            
            # Run container
            logger.info(f"Executing function block {function_block.name} in container with image: {docker_image}")
            container_start_time = datetime.now()
            exit_code, stdout, stderr = self.docker_manager.run_container(
                image=docker_image,
                command=self.get_execution_command(),
                volumes=volumes,
                environment=environment,
                timeout=config.function_block_timeout
            )
            container_end_time = datetime.now()
            
            # Process results
            duration = (container_end_time - start_time).total_seconds()
            
            # Create result object with all execution details
            if exit_code == 0:
                logger.info(f"Function block {function_block.name} completed successfully")
                result = self.collect_results(execution_dir, output_dir)
                result.duration = duration
                # Add container status to logs
                container_status = f"Container completed with code {exit_code}"
                result.logs = f"{container_status}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
                result.stdout = stdout
                result.stderr = stderr
                result.start_time = container_start_time
                result.end_time = container_end_time
                result.exit_code = exit_code
            else:
                logger.error(f"Function block {function_block.name} failed with exit code {exit_code}")
                # Log stdout/stderr for debugging
                if stdout:
                    logger.debug(f"STDOUT:\n{stdout}")
                if stderr:
                    logger.debug(f"STDERR:\n{stderr}")
                
                # Try to collect execution.log for actual error details
                execution_log = ""
                log_path = execution_dir / "output" / "execution.log"
                if log_path.exists():
                    try:
                        execution_log = log_path.read_text()
                        logger.debug(f"Collected execution.log:\n{execution_log}")
                    except Exception as e:
                        logger.warning(f"Failed to read execution.log: {e}")
                
                # Also try to collect error_details.txt
                error_details_path = execution_dir / "output" / "error_details.txt"
                if error_details_path.exists():
                    try:
                        error_details = error_details_path.read_text()
                        if error_details and not execution_log:
                            execution_log = f"Error details:\n{error_details}"
                        logger.debug(f"Collected error_details.txt:\n{error_details}")
                    except Exception as e:
                        logger.warning(f"Failed to read error_details.txt: {e}")
                
                # Extract actual error from execution.log if available
                actual_error = stderr  # Default to stderr
                if execution_log:
                    # Look for Python traceback in execution log
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
                                # End of traceback
                                break
                    
                    if error_lines:
                        actual_error = '\n'.join(error_lines)
                    
                # Add container status to logs
                container_status = f"Container completed with code {exit_code}"
                logs_with_status = f"{container_status}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}\n\nEXECUTION LOG:\n{execution_log}"
                
                result = ExecutionResult(
                    success=False,
                    error=actual_error,  # Use actual error from execution.log if available
                    logs=logs_with_status,
                    stdout=stdout,
                    stderr=stderr,
                    duration=duration,
                    start_time=container_start_time,
                    end_time=container_end_time,
                    exit_code=exit_code
                )
            
            # Job history is now managed by tree_manager through job directories
            # The deprecated save_job_history method is no longer called
            
            return result
                
        except Exception as e:
            logger.error(f"Error executing function block: {e}")
            return ExecutionResult(
                success=False,
                error=str(e),
                duration=(datetime.now() - start_time).total_seconds()
            )
        finally:
            # Clean up temp execution directory
            if execution_dir.exists():
                shutil.rmtree(execution_dir)
                logger.debug(f"Cleaned up temp execution directory: {execution_dir}")
    
    @abstractmethod
    def get_execution_command(self) -> List[str]:
        """Get the command to execute in the container."""
        pass
    
    def get_docker_image(self, function_block: BaseFunctionBlock) -> str:
        """Get the Docker image to use for this function block.
        
        First checks if the function block has a docker_image specified in its config.
        If not, falls back to the default image for the executor type.
        If a custom image is specified but doesn't exist, raises an error.
        
        Args:
            function_block: The function block to execute
            
        Returns:
            The Docker image name to use
            
        Raises:
            RuntimeError: If a specified custom Docker image doesn't exist
        """
        # Check if function block has a custom docker image in its config
        custom_image = None
        
        # For existing function blocks loaded from file system
        if hasattr(function_block, 'docker_image') and function_block.docker_image:
            custom_image = function_block.docker_image
        # Check in static_config if it exists
        elif hasattr(function_block, 'static_config') and function_block.static_config:
            custom_image = getattr(function_block.static_config, 'docker_image', None)
        
        if custom_image:
            # Validate that the custom image exists
            logger.info(f"Function block {function_block.name} specifies custom Docker image: {custom_image}")
            if not self._validate_docker_image(custom_image):
                error_msg = (
                    f"Docker image '{custom_image}' specified for function block "
                    f"'{function_block.name}' does not exist. "
                    f"Please ensure the image is built or pulled before execution."
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            logger.info(f"Using custom Docker image: {custom_image}")
            return custom_image
        
        # Fall back to default image for this executor type
        default_image = self.docker_image
        logger.info(f"Using default Docker image: {default_image}")
        return default_image
    
    def _validate_docker_image(self, image_name: str) -> bool:
        """Check if a Docker image exists locally or can be pulled.
        
        Args:
            image_name: The Docker image name to validate
            
        Returns:
            True if the image exists or can be pulled, False otherwise
        """
        try:
            # First try to find the image locally
            try:
                self.docker_manager.client.images.get(image_name)
                logger.debug(f"Docker image {image_name} found locally")
                return True
            except docker.errors.ImageNotFound:
                logger.debug(f"Docker image {image_name} not found locally, checking registry...")
            
            # Try to pull from registry
            try:
                self.docker_manager.client.images.pull(image_name)
                logger.info(f"Successfully pulled Docker image {image_name}")
                return True
            except docker.errors.APIError as e:
                logger.debug(f"Failed to pull Docker image {image_name}: {e}")
                return False
                
        except Exception as e:
            logger.error(f"Error validating Docker image {image_name}: {e}")
            return False
    
    def collect_results(self, execution_dir: Path, output_dir: Path) -> ExecutionResult:
        """Collect ALL results from execution directory."""
        
        output_dir.mkdir(parents=True, exist_ok=True)
        result = ExecutionResult(success=True)
        
        # Copy ALL files from execution output to job output directory
        execution_output_dir = execution_dir / "output"
        if execution_output_dir.exists():
            # Copy all files in the output directory
            for item in execution_output_dir.glob("*"):
                if item.is_file():
                    dest_path = output_dir / item.name
                    shutil.copy2(item, dest_path)
                    
                    # Track specific file types by extension
                    if item.suffix in [".h5ad", ".rds"]:
                        # Track primary data files (h5ad for Python, rds for R)
                        result.output_data_path = str(dest_path)
                    elif item.name == "metadata.json":
                        with open(item) as f:
                            result.metadata = json.load(f)
                elif item.is_dir():
                    # Copy entire subdirectories (e.g., figures/)
                    dest_dir = output_dir / item.name
                    if item.name == "figures":
                        # Special handling for figures directory
                        dest_dir.mkdir(exist_ok=True)
                        for fig_path in item.glob("*"):
                            if fig_path.suffix.lower() in [".png", ".jpg", ".jpeg", ".pdf", ".svg"]:
                                dest_fig = dest_dir / fig_path.name
                                shutil.copy2(fig_path, dest_fig)
                                result.figures.append(str(dest_fig))
                    else:
                        # Copy other directories as-is
                        shutil.copytree(item, dest_dir, dirs_exist_ok=True)
        
        # Collect logs
        log_path = execution_dir / "output" / "execution.log"
        if log_path.exists():
            result.logs += "\n" + log_path.read_text()
        
        return result
    
    def write_parameters(self, path: Path, parameters: Dict[str, Any]) -> None:
        """Write parameters to JSON file."""
        with open(path, "w") as f:
            json.dump(parameters, f, indent=2)
    
    def save_job_history(self, output_dir: Path, result: ExecutionResult, function_block: BaseFunctionBlock) -> None:
        """Save job execution history with stdout, stderr, and metrics.
        
        NOTE: This method is deprecated. Job history should be managed by the
        tree_manager creating separate job directories under nodes/node_id/jobs/.
        This method is kept for backwards compatibility but should not be used
        for new implementations.
        """
        
        # Create past_jobs directory (for backwards compatibility only)
        past_jobs_dir = output_dir / "past_jobs"
        past_jobs_dir.mkdir(parents=True, exist_ok=True)
        
        # Create job directory with timestamp and status
        job_status = "success" if result.success else "failed"
        job_timestamp = result.start_time.strftime('%Y%m%d_%H%M%S') if result.start_time else datetime.now().strftime('%Y%m%d_%H%M%S')
        job_dir_name = f"{job_timestamp}_{job_status}_{result.job_id[:8]}"
        job_dir = past_jobs_dir / job_dir_name
        job_dir.mkdir(parents=True, exist_ok=True)
        
        # Save stdout
        if result.stdout:
            stdout_path = job_dir / "stdout.txt"
            stdout_path.write_text(result.stdout)
            logger.debug(f"Saved stdout to {stdout_path}")
        
        # Save stderr
        if result.stderr:
            stderr_path = job_dir / "stderr.txt"
            stderr_path.write_text(result.stderr)
            logger.debug(f"Saved stderr to {stderr_path}")
        
        # Save job metrics as CSV
        import csv
        metrics_path = job_dir / "job_metrics.csv"
        with open(metrics_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['metric', 'value'])
            writer.writerow(['job_id', result.job_id])
            writer.writerow(['function_block_name', function_block.name])
            writer.writerow(['function_block_type', function_block.type])
            writer.writerow(['start_time', result.start_time.isoformat() if result.start_time else ''])
            writer.writerow(['end_time', result.end_time.isoformat() if result.end_time else ''])
            writer.writerow(['duration_seconds', result.duration])
            writer.writerow(['exit_code', result.exit_code if result.exit_code is not None else ''])
            writer.writerow(['success', result.success])
            writer.writerow(['error', result.error or ''])
            writer.writerow(['output_data_path', result.output_data_path or ''])
            writer.writerow(['num_figures', len(result.figures)])
        logger.debug(f"Saved job metrics to {metrics_path}")
        
        # Save job info as JSON for easier programmatic access
        job_info = {
            "job_id": result.job_id,
            "function_block": {
                "name": function_block.name,
                "type": function_block.type,
                "description": function_block.description,
                "parameters": function_block.parameters
            },
            "execution": {
                "start_time": result.start_time.isoformat() if result.start_time else None,
                "end_time": result.end_time.isoformat() if result.end_time else None,
                "duration_seconds": result.duration,
                "exit_code": result.exit_code,
                "success": result.success,
                "error": result.error
            },
            "outputs": {
                "output_data_path": result.output_data_path,
                "figures": result.figures,
                "metadata": result.metadata
            }
        }
        
        job_info_path = job_dir / "job_info.json"
        with open(job_info_path, 'w') as f:
            json.dump(job_info, f, indent=2)
        logger.debug(f"Saved job info to {job_info_path}")
        
        # NOTE: No current_job symlink - this is handled by tree_manager's job structure
        # The 'latest' symlink in the jobs directory serves this purpose