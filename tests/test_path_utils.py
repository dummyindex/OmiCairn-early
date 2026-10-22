"""Tests for path utilities."""

import tempfile
import shutil
from pathlib import Path
import pytest

from agents.utils.path_utils import (
    ensure_directory,
    create_timestamped_dir,
    find_files,
    safe_remove,
    copy_with_structure,
    get_size_mb,
    find_most_recent,
    ensure_parent_dir,
    relative_to_cwd
)

def test_ensure_directory():
    """Test directory creation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create new directory
        new_dir = tmppath / "new_dir"
        result = ensure_directory(new_dir)
        assert result == new_dir
        assert new_dir.exists()
        assert new_dir.is_dir()
        
        # Ensure existing directory (should not fail)
        result2 = ensure_directory(new_dir)
        assert result2 == new_dir
        assert new_dir.exists()
        
def test_ensure_directory_clean():
    """Test directory creation with cleaning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create directory with file
        test_dir = tmppath / "test_dir"
        test_dir.mkdir()
        test_file = test_dir / "file.txt"
        test_file.write_text("content")
        
        # Ensure with clean=True
        result = ensure_directory(test_dir, clean=True)
        assert result == test_dir
        assert test_dir.exists()
        assert not test_file.exists()  # File should be gone
        
def test_create_timestamped_dir():
    """Test timestamped directory creation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create timestamped directory
        result = create_timestamped_dir(tmppath, prefix="test_", suffix="_dir")
        assert result.exists()
        assert result.is_dir()
        assert result.name.startswith("test_")
        assert result.name.endswith("_dir")
        
        # Check timestamp format
        timestamp_part = result.name[5:-4]  # Remove prefix and suffix
        assert len(timestamp_part) == 15  # YYYYMMDD_HHMMSS
        
def test_find_files():
    """Test file finding."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create test structure
        (tmppath / "file1.txt").write_text("1")
        (tmppath / "file2.py").write_text("2")
        subdir = tmppath / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("3")
        (subdir / "file4.py").write_text("4")
        
        # Find all txt files recursively
        txt_files = find_files(tmppath, "*.txt", recursive=True)
        assert len(txt_files) == 2
        assert any("file1.txt" in str(f) for f in txt_files)
        assert any("file3.txt" in str(f) for f in txt_files)
        
        # Find py files non-recursively
        py_files = find_files(tmppath, "*.py", recursive=False)
        assert len(py_files) == 1
        assert "file2.py" in str(py_files[0])
        
        # Find all files (note: this also finds directories)
        all_items = find_files(tmppath, "*", recursive=True)
        # Filter to just files for the test
        all_files = [f for f in all_items if f.is_file()]
        assert len(all_files) == 4
        
def test_safe_remove():
    """Test safe file/directory removal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Remove file
        test_file = tmppath / "test.txt"
        test_file.write_text("content")
        assert safe_remove(test_file)
        assert not test_file.exists()
        
        # Remove directory
        test_dir = tmppath / "test_dir"
        test_dir.mkdir()
        (test_dir / "file.txt").write_text("content")
        assert safe_remove(test_dir)
        assert not test_dir.exists()
        
        # Remove non-existent with missing_ok=True (default)
        assert safe_remove(tmppath / "nonexistent")
        
        # Remove non-existent with missing_ok=False
        assert not safe_remove(tmppath / "nonexistent", missing_ok=False)
        
def test_copy_with_structure():
    """Test copying with structure preservation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Copy file
        src_file = tmppath / "source.txt"
        src_file.write_text("content")
        dst_file = tmppath / "dest" / "file.txt"
        
        assert copy_with_structure(src_file, dst_file)
        assert dst_file.exists()
        assert dst_file.read_text() == "content"
        
        # Copy directory
        src_dir = tmppath / "src_dir"
        src_dir.mkdir()
        (src_dir / "file1.txt").write_text("1")
        (src_dir / "subdir").mkdir()
        (src_dir / "subdir" / "file2.txt").write_text("2")
        
        dst_dir = tmppath / "dst_dir"
        assert copy_with_structure(src_dir, dst_dir)
        assert (dst_dir / "file1.txt").exists()
        assert (dst_dir / "subdir" / "file2.txt").exists()
        
def test_get_size_mb():
    """Test size calculation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # File size
        test_file = tmppath / "test.txt"
        content = "x" * (1024 * 1024)  # 1MB
        test_file.write_text(content)
        
        size = get_size_mb(test_file)
        assert 0.9 < size < 1.1  # Allow some tolerance
        
        # Directory size
        test_dir = tmppath / "test_dir"
        test_dir.mkdir()
        (test_dir / "file1.txt").write_text("x" * 500000)
        (test_dir / "file2.txt").write_text("x" * 500000)
        
        dir_size = get_size_mb(test_dir)
        assert 0.9 < dir_size < 1.1
        
        # Non-existent path
        assert get_size_mb(tmppath / "nonexistent") == 0.0
        
def test_find_most_recent():
    """Test finding most recent file."""
    import time
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create files with different timestamps
        file1 = tmppath / "file1.txt"
        file1.write_text("1")
        time.sleep(0.01)  # Small delay
        
        file2 = tmppath / "file2.txt"
        file2.write_text("2")
        time.sleep(0.01)
        
        file3 = tmppath / "file3.txt"
        file3.write_text("3")
        
        # Find most recent
        most_recent = find_most_recent(tmppath, "*.txt")
        assert most_recent == file3
        
        # No matches
        assert find_most_recent(tmppath, "*.xyz") is None
        
def test_ensure_parent_dir():
    """Test ensuring parent directory exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        filepath = tmppath / "nested" / "dirs" / "file.txt"
        parent = ensure_parent_dir(filepath)
        
        assert parent.exists()
        assert parent == filepath.parent
        assert parent.is_dir()
        
def test_relative_to_cwd():
    """Test getting path relative to cwd."""
    # Get a path under cwd
    cwd = Path.cwd()
    test_path = cwd / "subdir" / "file.txt"
    
    relative = relative_to_cwd(test_path)
    assert str(relative) == "subdir/file.txt"
    
    # Path not under cwd
    root_path = Path("/tmp/absolute/path")
    result = relative_to_cwd(root_path)
    assert result.is_absolute()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])