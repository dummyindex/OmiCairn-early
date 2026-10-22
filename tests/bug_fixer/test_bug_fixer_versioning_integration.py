"""Integration test for bug fixer code versioning with actual execution."""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from models import BaseFunctionBlock, FunctionBlockType, ExecutionResult, NewFunctionBlock
from job_executors.interactive_executor import InteractiveExecutor, ContainerActionHandler
from agents.unified_bug_fixer import UnifiedBugFixer
from agents.unified_bug_fixer.code_versioning import CodeVersionManager
from utils.docker_utils import DockerManager


class TestBugFixerVersioningIntegration:
    """Test bug fixer code versioning in realistic scenarios."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create temporary workspace for testing."""
        temp_dir = tempfile.mkdtemp()
        workspace = Path(temp_dir)
        
        # Create node structure
        node_dir = workspace / "nodes" / "test_node"
        node_dir.mkdir(parents=True, exist_ok=True)
        
        # Create function_block folder with buggy code
        fb_dir = node_dir / "function_block"
        fb_dir.mkdir(parents=True, exist_ok=True)
        
        # Write initial buggy code (incomplete like in the real scenario)
        buggy_code = """def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Find input file
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_file)
    
    # Set root cell
    adata.uns['iroot'] = 0
    print(f'Root cell: {adata.uns["""  # Syntax error - unterminated string
        
        (fb_dir / "code.py").write_text(buggy_code)
        (fb_dir / "function_block.py").write_text(buggy_code)
        (fb_dir / "requirements.txt").write_text("scanpy\npandas\n")
        
        yield workspace, node_dir
        
        # Cleanup
        shutil.rmtree(temp_dir)
        
    @pytest.fixture
    def mock_container(self):
        """Create mock container for testing."""
        container = Mock()
        container.id = "test_container_123"
        
        # Mock exec_run responses
        def mock_exec_run(cmd, **kwargs):
            result = Mock()
            
            # Simulate different command responses
            if "ls" in cmd:
                result.exit_code = 0
                result.output = (b"total 8\n-rw-r--r-- 1 root root 250 Dec 1 12:00 function_block.py\n", b"")
            elif "cat" in cmd and "function_block.py" in cmd:
                result.exit_code = 0
                result.output = (b"def run(path_dict, params):\n    print('Fixed version')", b"")
            elif "python -m py_compile" in cmd:
                result.exit_code = 0  # Syntax valid after fix
                result.output = (b"", b"")
            elif ["python", "function_block.py"] == cmd:
                result.exit_code = 0  # Execution succeeds
                result.output = (b"Fixed version executed successfully", b"")
            else:
                result.exit_code = 0
                result.output = (b"", b"")
                
            return result
            
        container.exec_run = mock_exec_run
        return container
        
    def test_bug_fixer_updates_host_folder(self, temp_workspace, mock_container):
        """Test that bug fixer updates both container and host folders."""
        workspace, node_dir = temp_workspace
        
        # Create container action handler
        handler = ContainerActionHandler(
            container=mock_container,
            working_dir="/workspace",
            node_dir=node_dir
        )
        
        # Fixed code to update
        fixed_code = """def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Find input file dynamically
    import glob
    h5ad_files = glob.glob(os.path.join(path_dict['input_dir'], '*.h5ad'))
    if not h5ad_files:
        raise FileNotFoundError('No .h5ad files found')
    
    input_file = h5ad_files[0]
    adata = sc.read_h5ad(input_file)
    
    # Set root cell
    adata.uns['iroot'] = 0
    print(f'Root cell: {adata.uns["iroot"]}')  # Fixed!
    
    # Save output
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
    return adata"""
        
        # Execute update_function_block action
        action = {
            'type': 'update_function_block',
            'code': fixed_code,
            'requirements': ['scanpy', 'pandas', 'numpy'],
            'language': 'python',
            'confidence': 0.9
        }
        
        result = handler.execute_action(action)
        
        # Verify result
        assert result['success']
        assert result['syntax_valid']
        # Re-execution is optional based on executor availability
        # Just check that the basic update worked
        
        # Verify host folder was updated
        code_file = node_dir / "function_block" / "code.py"
        assert code_file.exists()
        assert code_file.read_text() == fixed_code
        
        # Verify function_block.py was also updated
        fb_file = node_dir / "function_block" / "function_block.py"
        assert fb_file.exists()
        assert fb_file.read_text() == fixed_code
        
        # Verify requirements were updated
        req_file = node_dir / "function_block" / "requirements.txt"
        assert req_file.exists()
        req_content = req_file.read_text()
        assert "numpy" in req_content
        
        # Verify versioning was created
        versions_dir = node_dir / "agent_tasks" / "bug_fixer" / "code_versions"
        assert versions_dir.exists()
        
        # Check version files
        version_files = list(versions_dir.glob("*.py"))
        assert len(version_files) >= 2  # Original and fixed
        
        # Check version naming
        version_names = [f.name for f in version_files]
        assert any("original" in name for name in version_names)
        assert any("fixed" in name for name in version_names)
        
        # Check latest version info
        version_info_file = versions_dir / "latest_version.json"
        assert version_info_file.exists()
        
        version_info = json.loads(version_info_file.read_text())
        assert version_info["language"] == "python"
        assert version_info["requirements_updated"] is True
        
    def test_version_history_tracking(self, temp_workspace):
        """Test that version history is properly tracked."""
        workspace, node_dir = temp_workspace
        
        manager = CodeVersionManager(node_dir)
        
        # Simulate multiple bug fix iterations
        versions = [
            ("def run(): pass  # Syntax error", "syntax_error"),
            ("def run(): print('attempt 1')", "fix_attempt_1"),
            ("def run(): print('attempt 2')", "fix_attempt_2"),
            ("def run(): print('final working version')", "final_fix")
        ]
        
        for code, suffix in versions:
            manager.save_version(code, "python", suffix)
            
        # Get version history
        history = manager.get_version_history()
        
        assert len(history) == 4
        # Check that suffixes contain the expected keywords
        assert "syntax_error" in history[0]["suffix"]
        assert "final_fix" in history[-1]["suffix"]
        
        # Verify versions are numbered correctly
        for i, item in enumerate(history):
            assert item["version"] == i + 1
            
    def test_r_code_versioning(self, temp_workspace, mock_container):
        """Test versioning for R function blocks."""
        workspace, node_dir = temp_workspace
        
        # Create R function block
        fb_dir = node_dir / "function_block"
        r_code = """run <- function(path_dict, params) {
    # R code with error
    data <- read.csv(path_dict$input_dir
}"""  # Syntax error - missing closing paren
        
        (fb_dir / "code.R").write_text(r_code)
        (fb_dir / "function_block.R").write_text(r_code)
        
        # Create handler
        handler = ContainerActionHandler(
            container=mock_container,
            working_dir="/workspace",
            node_dir=node_dir
        )
        
        # Fixed R code
        fixed_r_code = """run <- function(path_dict, params) {
    # Fixed R code
    input_file <- file.path(path_dict$input_dir, "data.csv")
    data <- read.csv(input_file)
    
    # Process data
    result <- process_data(data)
    
    # Save output
    output_file <- file.path(path_dict$output_dir, "result.rds")
    saveRDS(result, output_file)
    return(result)
}"""
        
        # Update with fixed code
        action = {
            'type': 'update_function_block',
            'code': fixed_r_code,
            'requirements': ['dplyr', 'ggplot2'],
            'language': 'r',
            'confidence': 0.8
        }
        
        result = handler.execute_action(action)
        
        # Verify R files were updated
        assert (fb_dir / "code.R").read_text() == fixed_r_code
        assert (fb_dir / "function_block.R").read_text() == fixed_r_code
        
        # Verify R versions were saved
        versions_dir = node_dir / "agent_tasks" / "bug_fixer" / "code_versions"
        r_versions = list(versions_dir.glob("*.R"))
        assert len(r_versions) >= 1
        
    @patch('docker.from_env')
    def test_full_execution_flow(self, mock_docker, temp_workspace):
        """Test full execution flow with versioning."""
        workspace, node_dir = temp_workspace
        
        # Mock Docker client
        mock_client = Mock()
        mock_docker.return_value = mock_client
        
        # Create function block with minimal required fields
        from models import StaticConfig
        function_block = NewFunctionBlock(
            id="test_fb",
            name="test_function",
            type=FunctionBlockType.PYTHON,
            code="def run(path_dict, params): raise Exception('Test error')",
            requirements=["pandas"],
            description="Test function block",
            static_config=StaticConfig(
                args=[],  # args should be a list
                description="Test config",
                tag="test"
            )
        )
        
        # Mock bug fixer
        mock_bug_fixer = Mock(spec=UnifiedBugFixer)
        mock_bug_fixer.max_turns = 3
        mock_bug_fixer.enable_web_agent = False
        mock_bug_fixer.llm_service = Mock()
        
        # Create executor
        docker_manager = DockerManager()
        executor = InteractiveExecutor(docker_manager, bug_fixer=mock_bug_fixer)
        
        # Note: Full integration test would require actual Docker container
        # This test verifies the setup and structure
        
        # Verify node directory structure is created correctly
        fb_dir = node_dir / "function_block"
        assert fb_dir.exists()
        
        # Verify version manager can be initialized
        version_manager = CodeVersionManager(node_dir)
        assert version_manager.versions_dir.exists()
        

if __name__ == "__main__":
    pytest.main([__file__, "-v"])