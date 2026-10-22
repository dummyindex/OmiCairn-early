"""Centralized JSON handling utilities."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, List
from datetime import datetime, date

logger = logging.getLogger(__name__)

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime objects."""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Path):
            return str(obj)
        return super().default(obj)

def save_json(data: Dict[str, Any], filepath: Path, indent: int = 2, 
              create_dirs: bool = True) -> bool:
    """
    Save data to JSON file with error handling.
    
    Args:
        data: Data to save
        filepath: Path to save to
        indent: JSON indentation (default: 2)
        create_dirs: Create parent directories if they don't exist
        
    Returns:
        True if successful, False otherwise
    """
    try:
        filepath = Path(filepath)
        
        if create_dirs:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=indent, cls=DateTimeEncoder)
            
        logger.debug(f"Saved JSON to {filepath}")
        return True
        
    except (IOError, OSError) as e:
        logger.error(f"Failed to save JSON to {filepath}: {e}")
        return False
    except (TypeError, ValueError) as e:
        logger.error(f"JSON serialization error for {filepath}: {e}")
        return False

def load_json(filepath: Path, default: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Load JSON file with error handling.
    
    Args:
        filepath: Path to load from
        default: Default value if file doesn't exist or is invalid
        
    Returns:
        Loaded data or default value
    """
    try:
        filepath = Path(filepath)
        
        if not filepath.exists():
            logger.debug(f"JSON file {filepath} doesn't exist, returning default")
            return default if default is not None else {}
            
        with open(filepath, 'r') as f:
            data = json.load(f)
            
        logger.debug(f"Loaded JSON from {filepath}")
        return data
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        return default if default is not None else {}
    except (IOError, OSError) as e:
        logger.error(f"Failed to read JSON from {filepath}: {e}")
        return default if default is not None else {}

def validate_json_schema(data: Dict, schema: Dict) -> tuple[bool, List[str]]:
    """
    Validate JSON data against schema.
    
    Args:
        data: Data to validate
        schema: JSON schema dict
        
    Returns:
        (is_valid, list_of_errors)
    """
    try:
        import jsonschema
        
        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(data))
        
        if errors:
            error_messages = [f"{'.'.join(str(p) for p in e.path)}: {e.message}" for e in errors]
            return False, error_messages
            
        return True, []
        
    except ImportError:
        logger.warning("jsonschema not installed, skipping validation")
        return True, []
    except Exception as e:
        logger.error(f"Schema validation error: {e}")
        return False, [str(e)]

def merge_json_files(file_paths: List[Path], output_path: Path) -> bool:
    """
    Merge multiple JSON files into one.
    
    Args:
        file_paths: List of JSON files to merge
        output_path: Output file path
        
    Returns:
        True if successful
    """
    merged = {}
    
    for filepath in file_paths:
        data = load_json(filepath)
        if data:
            merged.update(data)
            
    return save_json(merged, output_path)

def append_to_json_array(filepath: Path, item: Any, create_if_missing: bool = True) -> bool:
    """
    Append an item to a JSON array file.
    
    Args:
        filepath: Path to JSON array file
        item: Item to append
        create_if_missing: Create file with new array if it doesn't exist
        
    Returns:
        True if successful
    """
    try:
        filepath = Path(filepath)
        
        if filepath.exists():
            data = load_json(filepath, default=[])
            if not isinstance(data, list):
                logger.error(f"JSON file {filepath} is not an array")
                return False
        else:
            if not create_if_missing:
                logger.error(f"JSON file {filepath} doesn't exist")
                return False
            data = []
            
        data.append(item)
        return save_json(data, filepath)
        
    except Exception as e:
        logger.error(f"Failed to append to JSON array {filepath}: {e}")
        return False