"""Tests for Docker image override functionality via config.json."""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from datetime import datetime

from models import (
    NewFunctionBlock, ExistingFunctionBlock, StaticConfig, 
    Arg, FunctionBlockType, ExecutionResult
)
from job_executors.python_executor import PythonExecutor
from job_executors.r_executor import RExecutor
from utils.docker_utils import DockerManager


class TestDockerImageOverride:
    """Test suite for Docker image override functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_docker_client = Mock()
        self.mock_docker_manager.client = self.mock_docker_client
        
        # Mock successful container run
        self.mock_docker_manager.run_container.return_value = (0, "Success", "")
        
        # Create temporary directory for testing
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_default_docker_image_python(self):
        """Test that Python executor uses default image when no custom image specified."""
        executor = PythonExecutor(self.mock_docker_manager)
        
        # Create function block without docker_image
        function_block = NewFunctionBlock(
            name="test_block",
            type=FunctionBlockType.PYTHON,
            description="Test block",
            code="def run(path_dict, params): pass",
            requirements="numpy",
            static_config=StaticConfig(
                args=[],
                description="Test",
                tag="test"
            )
        )
        
        # Mock image validation
        with patch.object(executor, '_validate_docker_image', return_value=True):
            docker_image = executor.get_docker_image(function_block)
        
        # Should use default Python image
        assert docker_image == executor.docker_image
    
    def test_default_docker_image_r(self):
        """Test that R executor uses default image when no custom image specified."""
        executor = RExecutor(self.mock_docker_manager)
        
        # Create function block without docker_image
        function_block = NewFunctionBlock(
            name="test_block",
            type=FunctionBlockType.R,
            description="Test block",
            code="run <- function(path_dict, params) { }",
            requirements="ggplot2",
            static_config=StaticConfig(
                args=[],
                description="Test",
                tag="test"
            )
        )
        
        # Mock image validation
        with patch.object(executor, '_validate_docker_image', return_value=True):
            docker_image = executor.get_docker_image(function_block)
        
        # Should use default R image
        assert docker_image == executor.docker_image
    
    def test_custom_docker_image_in_static_config(self):
        """Test that custom Docker image from static_config is used."""
        executor = PythonExecutor(self.mock_docker_manager)
        custom_image = "my-custom-python:latest"
        
        # Create function block with docker_image in static_config
        function_block = NewFunctionBlock(
            name="test_block",
            type=FunctionBlockType.PYTHON,
            description="Test block",
            code="def run(path_dict, params): pass",
            requirements="numpy",
            static_config=StaticConfig(
                args=[],
                description="Test",
                tag="test",
                docker_image=custom_image
            )
        )
        
        # Mock image validation to return True
        with patch.object(executor, '_validate_docker_image', return_value=True):
            docker_image = executor.get_docker_image(function_block)
        
        # Should use custom image
        assert docker_image == custom_image
    
    def test_custom_docker_image_on_existing_block(self):
        """Test that custom Docker image on ExistingFunctionBlock is used."""
        executor = PythonExecutor(self.mock_docker_manager)
        custom_image = "my-special-image:v2"
        
        # Create existing function block with docker_image field
        function_block = ExistingFunctionBlock(
            name="existing_block",
            type=FunctionBlockType.PYTHON,
            description="Existing block",
            function_block_id="abc123",
            docker_image=custom_image,
            static_config=StaticConfig(
                args=[],
                description="Test",
                tag="test"
            )
        )
        
        # Mock image validation to return True
        with patch.object(executor, '_validate_docker_image', return_value=True):
            docker_image = executor.get_docker_image(function_block)
        
        # Should use custom image
        assert docker_image == custom_image
    
    def test_custom_docker_image_validation_success(self):
        """Test that valid custom Docker images are accepted."""
        executor = PythonExecutor(self.mock_docker_manager)
        custom_image = "valid-image:latest"
        
        # Mock Docker client to find the image locally
        self.mock_docker_client.images.get.return_value = Mock()
        
        function_block = NewFunctionBlock(
            name="test_block",
            type=FunctionBlockType.PYTHON,
            description="Test block",
            code="def run(path_dict, params): pass",
            requirements="numpy",
            static_config=StaticConfig(
                args=[],
                description="Test",
                tag="test",
                docker_image=custom_image
            )
        )
        
        docker_image = executor.get_docker_image(function_block)
        
        # Should use custom image
        assert docker_image == custom_image
        # Should have checked if image exists
        self.mock_docker_client.images.get.assert_called_once_with(custom_image)
    
    def test_custom_docker_image_validation_failure(self):
        """Test that missing custom Docker images raise an error."""
        executor = PythonExecutor(self.mock_docker_manager)
        missing_image = "nonexistent-image:latest"
        
        # Mock Docker client to not find the image
        import docker.errors
        self.mock_docker_client.images.get.side_effect = docker.errors.ImageNotFound("Not found")
        self.mock_docker_client.images.pull.side_effect = docker.errors.APIError("Pull failed")
        
        function_block = NewFunctionBlock(
            name="test_block",
            type=FunctionBlockType.PYTHON,
            description="Test block",
            code="def run(path_dict, params): pass",
            requirements="numpy",
            static_config=StaticConfig(
                args=[],
                description="Test",
                tag="test",
                docker_image=missing_image
            )
        )
        
        # Should raise RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            executor.get_docker_image(function_block)
        
        assert missing_image in str(exc_info.value)
        assert "does not exist" in str(exc_info.value)
    
    def test_custom_docker_image_pull_from_registry(self):
        """Test that custom Docker images are pulled from registry if not local."""
        executor = PythonExecutor(self.mock_docker_manager)
        remote_image = "omicairn/special-r:v1.2.3"
        
        # Mock Docker client to not find locally but succeed on pull
        import docker.errors
        self.mock_docker_client.images.get.side_effect = docker.errors.ImageNotFound("Not local")
        self.mock_docker_client.images.pull.return_value = Mock()
        
        function_block = NewFunctionBlock(
            name="test_block",
            type=FunctionBlockType.PYTHON,
            description="Test block",
            code="def run(path_dict, params): pass",
            requirements="numpy",
            static_config=StaticConfig(
                args=[],
                description="Test",
                tag="test",
                docker_image=remote_image
            )
        )
        
        docker_image = executor.get_docker_image(function_block)
        
        # Should use remote image
        assert docker_image == remote_image
        # Should have tried to get locally first
        self.mock_docker_client.images.get.assert_called_once_with(remote_image)
        # Should have pulled from registry
        self.mock_docker_client.images.pull.assert_called_once_with(remote_image)
    
    @patch('job_executors.base_executor.config')
    def test_execute_with_custom_docker_image(self, mock_config):
        """Test that execute method uses custom Docker image."""
        mock_config.temp_dir = self.temp_dir
        mock_config.function_block_timeout = 300
        
        executor = PythonExecutor(self.mock_docker_manager)
        custom_image = "my-python-ml:latest"
        
        # Create function block with custom image
        function_block = NewFunctionBlock(
            name="ml_block",
            type=FunctionBlockType.PYTHON,
            description="ML block",
            code="def run(path_dict, params): print('ML analysis')",
            requirements="scikit-learn",
            static_config=StaticConfig(
                args=[],
                description="ML analysis",
                tag="ml",
                docker_image=custom_image
            )
        )
        
        # Mock image validation
        self.mock_docker_client.images.get.return_value = Mock()
        
        # Create input/output directories
        input_dir = self.temp_dir / "input"
        output_dir = self.temp_dir / "output"
        input_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)
        
        # Execute the function block
        result = executor.execute(
            function_block=function_block,
            input_data_path=input_dir,
            output_dir=output_dir,
            parameters={"test": "value"}
        )
        
        # Verify that run_container was called with the custom image
        self.mock_docker_manager.run_container.assert_called_once()
        call_args = self.mock_docker_manager.run_container.call_args
        assert call_args[1]['image'] == custom_image
    
    def test_docker_image_priority_direct_over_config(self):
        """Test that direct docker_image field has priority over static_config."""
        executor = RExecutor(self.mock_docker_manager)
        direct_image = "direct-image:latest"
        config_image = "config-image:latest"
        
        # Create function block with both direct and config docker_image
        function_block = ExistingFunctionBlock(
            name="test_block",
            type=FunctionBlockType.R,
            description="Test block",
            function_block_id="xyz789",
            docker_image=direct_image,  # Direct field
            static_config=StaticConfig(
                args=[],
                description="Test",
                tag="test",
                docker_image=config_image  # Config field
            )
        )
        
        # Mock image validation
        with patch.object(executor, '_validate_docker_image', return_value=True):
            docker_image = executor.get_docker_image(function_block)
        
        # Should prefer direct field over config
        assert docker_image == direct_image
    
    def test_metabolomics_docker_image_example(self):
        """Test with a realistic MetaboAnalyst example requiring special image."""
        executor = RExecutor(self.mock_docker_manager)
        metabo_image = "omicairn/r-executor-metaboanalyst:latest"
        
        # Create MetaboAnalyst function block
        function_block = ExistingFunctionBlock(
            name="MetaboAnalyst",
            type=FunctionBlockType.R,
            description="Metabolomics analysis using MetaboAnalystR",
            function_block_id="metabo123",
            static_config=StaticConfig(
                args=[
                    Arg(name="normalization_method", value_type="string", 
                        description="Normalization method", default_value="LogNorm")
                ],
                description="Comprehensive metabolomics analysis",
                tag="metabolomics",
                docker_image=metabo_image
            )
        )
        
        # Mock that the special image exists
        self.mock_docker_client.images.get.return_value = Mock()
        
        docker_image = executor.get_docker_image(function_block)
        
        # Should use MetaboAnalyst-specific image
        assert docker_image == metabo_image
    
    def test_no_docker_image_specified_anywhere(self):
        """Test fallback to default when no docker_image specified anywhere."""
        executor = PythonExecutor(self.mock_docker_manager)
        
        # Create minimal function block with no docker_image
        function_block = NewFunctionBlock(
            name="minimal",
            type=FunctionBlockType.PYTHON,
            description="Minimal block",
            code="def run(path_dict, params): pass",
            requirements="",
            static_config=StaticConfig(
                args=[],
                description="Minimal",
                tag="basic"
                # No docker_image field
            )
        )
        
        # Should not have docker_image attribute
        assert not hasattr(function_block, 'docker_image') or function_block.docker_image is None
        assert function_block.static_config.docker_image is None
        
        docker_image = executor.get_docker_image(function_block)
        
        # Should fall back to executor's default
        assert docker_image == executor.docker_image


class TestDockerImageConfigLoading:
    """Test loading docker_image from config.json files."""
    
    def test_config_json_with_docker_image(self):
        """Test parsing config.json with docker_image field."""
        config_data = {
            "name": "SpecialAnalysis",
            "type": "python",
            "description": "Special analysis requiring custom environment",
            "docker_image": "omicairn/special-env:v2",
            "parameters": {
                "method": {
                    "type": "string",
                    "default": "advanced"
                }
            }
        }
        
        # Test that StaticConfig can handle docker_image field
        static_config = StaticConfig(
            args=[],
            description=config_data["description"],
            tag="special",
            docker_image=config_data.get("docker_image")
        )
        
        assert static_config.docker_image == "omicairn/special-env:v2"
    
    def test_config_json_without_docker_image(self):
        """Test parsing config.json without docker_image field."""
        config_data = {
            "name": "StandardAnalysis",
            "type": "r",
            "description": "Standard analysis using default image",
            "parameters": {}
        }
        
        # Test that StaticConfig works without docker_image
        static_config = StaticConfig(
            args=[],
            description=config_data["description"],
            tag="standard",
            docker_image=config_data.get("docker_image")  # Will be None
        )
        
        assert static_config.docker_image is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])