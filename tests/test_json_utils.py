"""Tests for JSON utilities."""

import json
import tempfile
from pathlib import Path
from datetime import datetime, date
import pytest

from agents.utils.json_utils import (
    save_json,
    load_json,
    validate_json_schema,
    merge_json_files,
    append_to_json_array,
    DateTimeEncoder
)

def test_save_and_load_json():
    """Test basic save and load functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "test.json"
        data = {"key": "value", "number": 42}
        
        # Test save
        assert save_json(data, filepath)
        assert filepath.exists()
        
        # Test load
        loaded = load_json(filepath)
        assert loaded == data
        
def test_save_json_creates_directories():
    """Test that save_json creates parent directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "nested" / "dirs" / "test.json"
        data = {"test": "data"}
        
        assert save_json(data, filepath, create_dirs=True)
        assert filepath.exists()
        
def test_load_json_with_default():
    """Test loading non-existent file with default."""
    filepath = Path("/nonexistent/file.json")
    default = {"default": "value"}
    
    result = load_json(filepath, default=default)
    assert result == default
    
def test_load_json_invalid_content():
    """Test loading file with invalid JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "invalid.json"
        filepath.write_text("not valid json")
        
        result = load_json(filepath, default={"fallback": True})
        assert result == {"fallback": True}
        
def test_datetime_encoder():
    """Test datetime encoding in JSON."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "datetime.json"
        now = datetime.now()
        today = date.today()
        data = {
            "datetime": now,
            "date": today,
            "path": Path("/some/path")
        }
        
        assert save_json(data, filepath)
        
        # Load and check it's serialized correctly
        with open(filepath) as f:
            loaded = json.load(f)
        
        assert loaded["datetime"] == now.isoformat()
        assert loaded["date"] == today.isoformat()
        assert loaded["path"] == "/some/path"
        
def test_validate_json_schema():
    """Test JSON schema validation."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "number"}
        },
        "required": ["name"]
    }
    
    # Valid data
    valid_data = {"name": "John", "age": 30}
    is_valid, errors = validate_json_schema(valid_data, schema)
    assert is_valid
    assert errors == []
    
    # Invalid data - missing required field
    invalid_data = {"age": 30}
    is_valid, errors = validate_json_schema(invalid_data, schema)
    assert not is_valid
    assert len(errors) > 0
    
    # Invalid data - wrong type
    invalid_data2 = {"name": 123, "age": "thirty"}
    is_valid, errors = validate_json_schema(invalid_data2, schema)
    assert not is_valid
    assert len(errors) > 0
    
def test_merge_json_files():
    """Test merging multiple JSON files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        
        # Create test files
        file1 = tmppath / "file1.json"
        file2 = tmppath / "file2.json"
        output = tmppath / "merged.json"
        
        save_json({"a": 1, "b": 2}, file1)
        save_json({"c": 3, "b": 4}, file2)  # b will be overwritten
        
        # Merge
        assert merge_json_files([file1, file2], output)
        
        # Check result
        merged = load_json(output)
        assert merged == {"a": 1, "b": 4, "c": 3}
        
def test_append_to_json_array():
    """Test appending to JSON array."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "array.json"
        
        # Create new array
        assert append_to_json_array(filepath, "item1")
        assert load_json(filepath) == ["item1"]
        
        # Append to existing
        assert append_to_json_array(filepath, "item2")
        assert load_json(filepath) == ["item1", "item2"]
        
        # Complex items
        assert append_to_json_array(filepath, {"key": "value"})
        assert load_json(filepath) == ["item1", "item2", {"key": "value"}]
        
def test_append_to_non_array():
    """Test that appending to non-array fails gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "object.json"
        save_json({"not": "array"}, filepath)
        
        # Should fail
        assert not append_to_json_array(filepath, "item")
        
        # Original should be unchanged
        assert load_json(filepath) == {"not": "array"}

if __name__ == "__main__":
    pytest.main([__file__, "-v"])