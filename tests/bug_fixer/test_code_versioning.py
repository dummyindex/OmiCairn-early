"""Test code versioning functionality for bug fixer updates."""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import json

from agents.unified_bug_fixer.code_versioning import CodeVersionManager


class TestCodeVersioning:
    """Test the code versioning functionality."""
    
    @pytest.fixture
    def temp_node_dir(self):
        """Create a temporary node directory for testing."""
        temp_dir = tempfile.mkdtemp()
        node_dir = Path(temp_dir) / "test_node"
        node_dir.mkdir(parents=True, exist_ok=True)
        
        # Create function_block folder
        fb_dir = node_dir / "function_block"
        fb_dir.mkdir(parents=True, exist_ok=True)
        
        yield node_dir
        
        # Cleanup
        shutil.rmtree(temp_dir)
        
    def test_version_manager_init(self, temp_node_dir):
        """Test CodeVersionManager initialization."""
        manager = CodeVersionManager(temp_node_dir)
        
        assert manager.node_dir == temp_node_dir
        assert manager.function_block_dir.exists()
        assert manager.versions_dir.exists()
        
    def test_save_version(self, temp_node_dir):
        """Test saving code versions."""
        manager = CodeVersionManager(temp_node_dir)
        
        # Save first version
        code1 = "def run(path_dict, params):\n    print('Version 1')"
        version_path1 = manager.save_version(code1, "python", "original")
        
        assert version_path1.exists()
        assert version_path1.read_text() == code1
        assert "v01_original_" in version_path1.name
        assert version_path1.suffix == ".py"
        
        # Save second version
        code2 = "def run(path_dict, params):\n    print('Version 2 - fixed')"
        version_path2 = manager.save_version(code2, "python", "fixed")
        
        assert version_path2.exists()
        assert version_path2.read_text() == code2
        assert "v02_fixed_" in version_path2.name
        
    def test_save_r_version(self, temp_node_dir):
        """Test saving R code versions."""
        manager = CodeVersionManager(temp_node_dir)
        
        r_code = "run <- function(path_dict, params) {\n  print('R version')\n}"
        version_path = manager.save_version(r_code, "r", "original")
        
        assert version_path.exists()
        assert version_path.suffix == ".R"
        assert version_path.read_text() == r_code
        
    def test_update_function_block(self, temp_node_dir):
        """Test updating function block with versioning."""
        manager = CodeVersionManager(temp_node_dir)
        
        # Create original code
        original_code = "def run(path_dict, params):\n    print('Original')"
        code_file = manager.function_block_dir / "code.py"
        code_file.write_text(original_code)
        
        # Update with new code
        new_code = "def run(path_dict, params):\n    print('Updated')"
        requirements = ["pandas", "numpy"]
        
        result = manager.update_function_block(new_code, requirements, "python")
        
        assert result["success"]
        assert (manager.function_block_dir / "code.py").read_text() == new_code
        assert (manager.function_block_dir / "function_block.py").read_text() == new_code
        assert (manager.function_block_dir / "requirements.txt").exists()
        
        # Check versions were saved
        versions = list(manager.versions_dir.glob("*.py"))
        assert len(versions) >= 2  # Original and fixed
        
        # Check version info file
        version_info_file = manager.versions_dir / "latest_version.json"
        assert version_info_file.exists()
        
        version_info = json.loads(version_info_file.read_text())
        assert version_info["language"] == "python"
        assert version_info["requirements_updated"] is True
        
    def test_get_version_history(self, temp_node_dir):
        """Test getting version history."""
        manager = CodeVersionManager(temp_node_dir)
        
        # Create multiple versions
        manager.save_version("code1", "python", "original")
        manager.save_version("code2", "python", "fix1")
        manager.save_version("code3", "python", "fix2")
        
        history = manager.get_version_history()
        
        assert len(history) == 3
        assert history[0]["version"] == 1
        assert history[1]["version"] == 2
        assert history[2]["version"] == 3
        
        # Check history details
        for item in history:
            assert "filename" in item
            assert "timestamp" in item
            assert "size" in item
            assert "suffix" in item
            
    def test_version_numbering(self, temp_node_dir):
        """Test automatic version numbering."""
        manager = CodeVersionManager(temp_node_dir)
        
        # Create versions with gaps
        (manager.versions_dir / "v01_test.py").write_text("test1")
        (manager.versions_dir / "v03_test.py").write_text("test3")
        (manager.versions_dir / "v05_test.py").write_text("test5")
        
        # Next version should be 6
        assert manager._get_next_version_number() == 6
        
    def test_requirements_update(self, temp_node_dir):
        """Test requirements file update."""
        manager = CodeVersionManager(temp_node_dir)
        
        code = "def run(path_dict, params): pass"
        requirements = ["scanpy==1.9.0", "pandas>=2.0.0", "numpy"]
        
        result = manager.update_function_block(code, requirements, "python")
        
        assert result["success"]
        
        req_file = manager.function_block_dir / "requirements.txt"
        assert req_file.exists()
        
        req_content = req_file.read_text()
        assert "scanpy==1.9.0" in req_content
        assert "pandas>=2.0.0" in req_content
        assert "numpy" in req_content
        assert req_content.endswith('\n')
        
    def test_error_handling(self, temp_node_dir):
        """Test error handling in version manager."""
        # Test with writable temporary directory
        temp_test_dir = tempfile.mkdtemp()
        try:
            test_dir = Path(temp_test_dir) / "test_path"
            manager = CodeVersionManager(test_dir)
            
            # Should create directories even if they don't exist
            assert manager.function_block_dir.exists()
            assert manager.versions_dir.exists()
            
            # Test save_version with invalid input
            with pytest.raises(Exception):  # Will raise TypeError or AttributeError
                manager.save_version(None, "python")
        finally:
            shutil.rmtree(temp_test_dir)
            
    def test_no_original_code(self, temp_node_dir):
        """Test updating when no original code exists."""
        manager = CodeVersionManager(temp_node_dir)
        
        # Update without any existing code
        new_code = "def run(path_dict, params): pass"
        result = manager.update_function_block(new_code, [], "python")
        
        assert result["success"]
        assert (manager.function_block_dir / "code.py").exists()
        assert (manager.function_block_dir / "function_block.py").exists()
        
        # Should have one version saved
        versions = list(manager.versions_dir.glob("*.py"))
        assert len(versions) == 1
        

if __name__ == "__main__":
    pytest.main([__file__, "-v"])