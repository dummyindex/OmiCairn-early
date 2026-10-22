"""Manager for job executors."""

from pathlib import Path
from typing import Dict, Any, Optional
import docker

from .base_executor import BaseExecutor
from .python_executor import PythonExecutor
from .r_executor import RExecutor
from models import BaseFunctionBlock, FunctionBlockType, ExecutionResult
from utils.logger import get_logger
from utils.docker_utils import DockerManager

logger = get_logger(__name__)


class ExecutorManager:
    """Manages execution of function blocks across different languages."""
    
    def __init__(self):
        self.docker_manager = DockerManager()
        self.executors: Dict[FunctionBlockType, BaseExecutor] = {
            FunctionBlockType.PYTHON: PythonExecutor(self.docker_manager),
            FunctionBlockType.R: RExecutor(self.docker_manager)
        }
        
        # Images are now checked on-demand during execution
        # self._ensure_images()
    
    def _ensure_images(self) -> None:
        """Ensure required Docker images are available."""
        images_to_check = [
            (FunctionBlockType.PYTHON, self.executors[FunctionBlockType.PYTHON].docker_image),
            (FunctionBlockType.R, self.executors[FunctionBlockType.R].docker_image)
        ]
        
        for block_type, image in images_to_check:
            logger.info(f"Checking {block_type.value} image: {image}")
            if not self.docker_manager.pull_or_build_image(image):
                logger.warning(f"Image {image} not available. You may need to build it manually.")
    
    def execute(
        self,
        function_block: BaseFunctionBlock,
        input_data_path: Path,
        output_dir: Path,
        parameters: Optional[Dict[str, Any]] = None,
        previous_nodes_metadata: Optional[Dict[str, Any]] = None,
        propagated_failure_context: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """Execute a function block."""
        
        # Get appropriate executor
        # Convert string type to enum if necessary
        block_type = function_block.type
        if isinstance(block_type, str):
            block_type = FunctionBlockType(block_type)
        
        executor = self.executors.get(block_type)
        if not executor:
            logger.error(f"No executor available for type {function_block.type}")
            return ExecutionResult(
                success=False,
                error=f"Unsupported function block type: {function_block.type}"
            )
        
        # Validate only the required image
        validation = self.validate_required_image(block_type)
        if not validation["docker_available"]:
            return ExecutionResult(
                success=False,
                error="Docker is not available"
            )
        
        if not validation["required_image"]:
            return ExecutionResult(
                success=False,
                error=f"Required Docker image not found: {validation['image_name']}. Please build it manually."
            )
        
        # Execute the function block
        type_str = function_block.type.value if hasattr(function_block.type, 'value') else str(function_block.type)
        logger.info(f"Executing {type_str} function block: {function_block.name}")
        return executor.execute(
            function_block=function_block,
            input_data_path=input_data_path,
            output_dir=output_dir,
            parameters=parameters or function_block.parameters,
            previous_nodes_metadata=previous_nodes_metadata,
            propagated_failure_context=propagated_failure_context
        )
    
    def validate_environment(self) -> Dict[str, bool]:
        """Validate that the execution environment is properly set up."""
        validation = {
            "docker_available": False,
            "python_image": False,
            "r_image": False
        }
        
        try:
            # Check Docker
            self.docker_manager.client.ping()
            validation["docker_available"] = True
            
            # Check images
            try:
                self.docker_manager.client.images.get(self.executors[FunctionBlockType.PYTHON].docker_image)
                validation["python_image"] = True
            except docker.errors.ImageNotFound:
                validation["python_image"] = False
                logger.info(f"Python executor image not found: {self.executors[FunctionBlockType.PYTHON].docker_image}")
            except docker.errors.APIError as e:
                validation["python_image"] = False
                logger.warning(f"Docker API error checking Python image: {e}")
                
            try:
                self.docker_manager.client.images.get(self.executors[FunctionBlockType.R].docker_image)
                validation["r_image"] = True
            except docker.errors.ImageNotFound:
                validation["r_image"] = False
                logger.info(f"R executor image not found: {self.executors[FunctionBlockType.R].docker_image}")
            except docker.errors.APIError as e:
                validation["r_image"] = False
                logger.warning(f"Docker API error checking R image: {e}")
                
        except Exception as e:
            logger.error(f"Environment validation error: {e}")
            
        return validation
    
    def validate_required_image(self, function_type: FunctionBlockType) -> Dict[str, bool]:
        """Validate only the required image for the given function block type."""
        validation = {
            "docker_available": False,
            "required_image": False,
            "image_name": self.executors[function_type].docker_image
        }
        
        try:
            # Check Docker
            self.docker_manager.client.ping()
            validation["docker_available"] = True
            
            # Check only the required image
            try:
                self.docker_manager.client.images.get(self.executors[function_type].docker_image)
                validation["required_image"] = True
                logger.info(f"Found required {function_type.value} image: {validation['image_name']}")
            except Exception as e:
                logger.warning(f"Required {function_type.value} image not found: {validation['image_name']}")
                
        except Exception as e:
            logger.error(f"Docker validation error: {e}")
            
        return validation
    
    def cleanup(self) -> None:
        """Clean up resources. 
        
        Note: Individual job containers are automatically cleaned up after each execution
        via auto_remove=True in DockerManager.run_container().
        """
        logger.debug("ExecutorManager cleanup called (containers auto-removed per job)")