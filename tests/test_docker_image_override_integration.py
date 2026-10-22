"""Integration tests for Docker image override with real function blocks."""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

from models import ExistingFunctionBlock, StaticConfig, Arg, FunctionBlockType
from job_executors.executor_manager import ExecutorManager
from job_executors.python_executor import PythonExecutor
from job_executors.r_executor import RExecutor
from utils.docker_utils import DockerManager


class TestDockerImageOverrideIntegration:
    """Integration tests for Docker image override functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.function_blocks_dir = self.test_dir / "function_blocks"
        self.function_blocks_dir.mkdir()
        
        # Create mock docker manager
        self.mock_docker_manager = Mock(spec=DockerManager)
        self.mock_docker_client = Mock()
        self.mock_docker_manager.client = self.mock_docker_client
        self.mock_docker_manager.run_container.return_value = (0, "Success", "")
    
    def teardown_method(self):
        """Clean up test environment."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def create_test_function_block(self, name: str, block_type: str, 
                                  docker_image: str = None, 
                                  additional_config: dict = None):
        """Create a test function block directory with config.json."""
        block_dir = self.function_blocks_dir / name
        block_dir.mkdir(parents=True)
        
        # Create config.json
        config = {
            "name": name,
            "type": block_type,
            "description": f"Test {name} function block",
            "parameters": {}
        }
        
        if docker_image:
            config["docker_image"] = docker_image
        
        if additional_config:
            config.update(additional_config)
        
        with open(block_dir / "config.json", 'w') as f:
            json.dump(config, f, indent=2)
        
        # Create code file
        if block_type == "python":
            code = """
def run(path_dict, params):
    print(f"Running {name} with params: {params}")
    # Analysis logic here
""".replace("{name}", name)
            with open(block_dir / "code.py", 'w') as f:
                f.write(code)
            requirements = "numpy\npandas"
        else:  # R
            code = f"""
run <- function(path_dict, params) {{
    print("Running {name}")
    # Analysis logic here
}}
"""
            with open(block_dir / "code.R", 'w') as f:
                f.write(code)
            requirements = "ggplot2\ndplyr"
        
        # Create requirements.txt
        with open(block_dir / "requirements.txt", 'w') as f:
            f.write(requirements)
        
        return block_dir
    
    def test_metabolomics_special_image(self):
        """Test MetaboAnalyst block requiring special Docker image."""
        # Create MetaboAnalyst function block with custom image
        metabo_dir = self.create_test_function_block(
            name="MetaboAnalyst",
            block_type="r",
            docker_image="omicairn/r-executor-metaboanalyst:latest",
            additional_config={
                "category": "metabolomics",
                "docker_requirements": {
                    "note": "Requires MetaboAnalystR and Bioconductor dependencies"
                }
            }
        )
        
        # Load config
        with open(metabo_dir / "config.json") as f:
            config_data = json.load(f)
        
        # Create function block with loaded config
        function_block = ExistingFunctionBlock(
            name=config_data["name"],
            type=FunctionBlockType.R,
            description=config_data["description"],
            function_block_id="metabo_001",
            static_config=StaticConfig(
                args=[],
                description=config_data["description"],
                tag="metabolomics",
                docker_image=config_data.get("docker_image")
            )
        )
        
        # Create executor and test
        executor = RExecutor(self.mock_docker_manager)
        
        # Mock that the special image exists
        self.mock_docker_client.images.get.return_value = Mock()
        
        docker_image = executor.get_docker_image(function_block)
        
        assert docker_image == "omicairn/r-executor-metaboanalyst:latest"
    
    def test_signac_chromatin_accessibility_image(self):
        """Test Signac block for chromatin accessibility with special image."""
        # Create Signac function block
        signac_dir = self.create_test_function_block(
            name="signac_atac_analysis",
            block_type="r",
            docker_image="omicairn/r-executor-signac:latest",
            additional_config={
                "category": "chromatin_accessibility",
                "description": "ATAC-seq analysis using Signac"
            }
        )
        
        # Load and create function block
        with open(signac_dir / "config.json") as f:
            config_data = json.load(f)
        
        function_block = ExistingFunctionBlock(
            name=config_data["name"],
            type=FunctionBlockType.R,
            description=config_data["description"],
            function_block_id="signac_001",
            static_config=StaticConfig(
                args=[],
                description=config_data["description"],
                tag="chromatin",
                docker_image=config_data.get("docker_image")
            )
        )
        
        executor = RExecutor(self.mock_docker_manager)
        
        # Mock image exists
        self.mock_docker_client.images.get.return_value = Mock()
        
        docker_image = executor.get_docker_image(function_block)
        
        assert docker_image == "omicairn/r-executor-signac:latest"
    
    def test_standard_python_block_default_image(self):
        """Test standard Python block uses default image."""
        # Create standard Python function block without docker_image
        standard_dir = self.create_test_function_block(
            name="standard_analysis",
            block_type="python"
            # No docker_image specified
        )
        
        # Load config
        with open(standard_dir / "config.json") as f:
            config_data = json.load(f)
        
        function_block = ExistingFunctionBlock(
            name=config_data["name"],
            type=FunctionBlockType.PYTHON,
            description=config_data["description"],
            function_block_id="standard_001",
            static_config=StaticConfig(
                args=[],
                description=config_data["description"],
                tag="analysis",
                docker_image=config_data.get("docker_image")  # Will be None
            )
        )
        
        executor = PythonExecutor(self.mock_docker_manager)
        
        docker_image = executor.get_docker_image(function_block)
        
        # Should use default Python image
        from config import config
        assert docker_image == config.python_image
    
    def test_gpu_enabled_ml_block(self):
        """Test ML block requiring GPU-enabled Docker image."""
        # Create ML function block with GPU image
        ml_dir = self.create_test_function_block(
            name="deep_learning_analysis",
            block_type="python",
            docker_image="omicairn/python-executor-gpu:latest",
            additional_config={
                "category": "machine_learning",
                "requirements": {
                    "gpu": True,
                    "cuda_version": "11.8"
                }
            }
        )
        
        with open(ml_dir / "config.json") as f:
            config_data = json.load(f)
        
        function_block = ExistingFunctionBlock(
            name=config_data["name"],
            type=FunctionBlockType.PYTHON,
            description=config_data["description"],
            function_block_id="ml_gpu_001",
            static_config=StaticConfig(
                args=[],
                description=config_data["description"],
                tag="ml",
                docker_image=config_data.get("docker_image")
            )
        )
        
        executor = PythonExecutor(self.mock_docker_manager)
        
        # Mock that GPU image exists
        self.mock_docker_client.images.get.return_value = Mock()
        
        docker_image = executor.get_docker_image(function_block)
        
        assert docker_image == "omicairn/python-executor-gpu:latest"
    
    def test_missing_custom_image_fails(self):
        """Test that missing custom image causes execution to fail."""
        # Create block with non-existent image
        bad_dir = self.create_test_function_block(
            name="bad_image_block",
            block_type="python",
            docker_image="nonexistent/image:v99"
        )
        
        with open(bad_dir / "config.json") as f:
            config_data = json.load(f)
        
        function_block = ExistingFunctionBlock(
            name=config_data["name"],
            type=FunctionBlockType.PYTHON,
            description=config_data["description"],
            function_block_id="bad_001",
            static_config=StaticConfig(
                args=[],
                description=config_data["description"],
                tag="test",
                docker_image=config_data.get("docker_image")
            )
        )
        
        executor = PythonExecutor(self.mock_docker_manager)
        
        # Mock that image doesn't exist
        import docker.errors
        self.mock_docker_client.images.get.side_effect = docker.errors.ImageNotFound("Not found")
        self.mock_docker_client.images.pull.side_effect = docker.errors.APIError("Cannot pull")
        
        with pytest.raises(RuntimeError) as exc_info:
            executor.get_docker_image(function_block)
        
        assert "nonexistent/image:v99" in str(exc_info.value)
        assert "does not exist" in str(exc_info.value)
    
    @patch('job_executors.base_executor.config')
    @patch('job_executors.executor_manager.DockerManager')
    def test_executor_manager_with_custom_images(self, mock_docker_manager_class, mock_config):
        """Test ExecutorManager handling blocks with different Docker images."""
        mock_config.temp_dir = self.test_dir / "temp"
        mock_config.temp_dir.mkdir()
        mock_config.function_block_timeout = 300
        
        # Set up mock DockerManager
        mock_docker_manager_class.return_value = self.mock_docker_manager
        
        # Create executor manager
        executor_manager = ExecutorManager()
        
        # Get the default images from the actual executors
        default_python_image = executor_manager.executors[FunctionBlockType.PYTHON].docker_image
        default_r_image = executor_manager.executors[FunctionBlockType.R].docker_image
        
        # Test data
        blocks_and_images = [
            ("python_default", "python", None, default_python_image),
            ("python_custom", "python", "custom/python:v1", "custom/python:v1"),
            ("r_default", "r", None, default_r_image),
            ("r_bioconductor", "r", "omicairn/r-bioc:latest", "omicairn/r-bioc:latest"),
        ]
        
        for name, block_type, custom_image, expected_image in blocks_and_images:
            # Create function block directory
            block_dir = self.create_test_function_block(name, block_type, custom_image)
            
            # Load config
            with open(block_dir / "config.json") as f:
                config_data = json.load(f)
            
            # Create function block
            fb_type = FunctionBlockType.PYTHON if block_type == "python" else FunctionBlockType.R
            function_block = ExistingFunctionBlock(
                name=name,
                type=fb_type,
                description=f"Test {name}",
                function_block_id=f"{name}_001",
                static_config=StaticConfig(
                    args=[],
                    description=f"Test {name}",
                    tag="test",
                    docker_image=config_data.get("docker_image")
                )
            )
            
            # Get appropriate executor from the manager's internal dictionary
            executor = executor_manager.executors[function_block.type]
            
            # Mock image validation
            if custom_image:
                self.mock_docker_client.images.get.return_value = Mock()
            
            # Check that correct image is determined
            docker_image = executor.get_docker_image(function_block)
            assert docker_image == expected_image, f"Failed for {name}: expected {expected_image}, got {docker_image}"


class TestDockerImageOverrideRealWorld:
    """Test Docker image override with real-world scenarios."""
    
    def test_seurat_converter_special_image(self):
        """Test Seurat converter requiring special R environment."""
        # This simulates the actual Seurat converter that might need 
        # a special image with specific R packages pre-installed
        
        config_content = {
            "name": "seurat_converter",
            "type": "r",
            "description": "Convert between Seurat and AnnData formats",
            "docker_image": "omicairn/r-executor-seurat:v5",
            "parameters": {
                "conversion_direction": {
                    "type": "string",
                    "default": "seurat_to_anndata",
                    "options": ["seurat_to_anndata", "anndata_to_seurat"]
                }
            },
            "inputs": {
                "data": {
                    "type": "h5ad or rds",
                    "description": "Input data file"
                }
            },
            "outputs": {
                "converted": {
                    "type": "h5ad or rds",
                    "description": "Converted data file"
                }
            }
        }
        
        # Create function block from config
        function_block = ExistingFunctionBlock(
            name=config_content["name"],
            type=FunctionBlockType.R,
            description=config_content["description"],
            function_block_id="seurat_conv_001",
            static_config=StaticConfig(
                args=[
                    Arg(
                        name="conversion_direction",
                        value_type="string",
                        description="Direction of conversion",
                        default_value="seurat_to_anndata"
                    )
                ],
                description=config_content["description"],
                tag="conversion",
                docker_image=config_content["docker_image"]
            )
        )
        
        # Test with mock docker manager
        mock_docker_manager = Mock(spec=DockerManager)
        mock_docker_client = Mock()
        mock_docker_manager.client = mock_docker_client
        mock_docker_client.images.get.return_value = Mock()  # Image exists
        
        executor = RExecutor(mock_docker_manager)
        docker_image = executor.get_docker_image(function_block)
        
        assert docker_image == "omicairn/r-executor-seurat:v5"
    
    def test_squidpy_spatial_analysis_image(self):
        """Test Squidpy spatial analysis with specialized image."""
        # Squidpy might need special dependencies for spatial analysis
        
        config_content = {
            "name": "squidpy_spatial_analysis",
            "type": "python",
            "description": "Spatial transcriptomics analysis using Squidpy",
            "docker_image": "omicairn/python-executor-spatial:latest",
            "category": "spatial_analysis"
        }
        
        function_block = ExistingFunctionBlock(
            name=config_content["name"],
            type=FunctionBlockType.PYTHON,
            description=config_content["description"],
            function_block_id="squidpy_001",
            static_config=StaticConfig(
                args=[],
                description=config_content["description"],
                tag="spatial",
                docker_image=config_content["docker_image"]
            )
        )
        
        mock_docker_manager = Mock(spec=DockerManager)
        mock_docker_client = Mock()
        mock_docker_manager.client = mock_docker_client
        mock_docker_client.images.get.return_value = Mock()  # Image exists
        
        executor = PythonExecutor(mock_docker_manager)
        docker_image = executor.get_docker_image(function_block)
        
        assert docker_image == "omicairn/python-executor-spatial:latest"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])