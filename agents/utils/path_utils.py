"""Centralized path and directory utilities."""

import os
import shutil
import logging
from pathlib import Path
from typing import Optional, List, Union
from datetime import datetime

logger = logging.getLogger(__name__)

def ensure_directory(path: Union[str, Path], clean: bool = False) -> Path:
    """
    Ensure directory exists, optionally cleaning it first.
    
    Args:
        path: Directory path
        clean: If True, remove existing directory first
        
    Returns:
        Path object for the directory
    """
    path = Path(path)
    
    try:
        if clean and path.exists():
            logger.debug(f"Cleaning existing directory: {path}")
            shutil.rmtree(path)
            
        path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured directory exists: {path}")
        return path
        
    except (IOError, OSError) as e:
        logger.error(f"Failed to create directory {path}: {e}")
        raise

def create_timestamped_dir(base_path: Union[str, Path], prefix: str = "", 
                          suffix: str = "", format: str = "%Y%m%d_%H%M%S") -> Path:
    """
    Create a timestamped directory.
    
    Args:
        base_path: Parent directory
        prefix: Prefix for directory name
        suffix: Suffix for directory name
        format: Timestamp format string
        
    Returns:
        Path to created directory
    """
    base_path = Path(base_path)
    timestamp = datetime.now().strftime(format)
    dir_name = f"{prefix}{timestamp}{suffix}"
    
    dir_path = base_path / dir_name
    return ensure_directory(dir_path)

def find_files(directory: Union[str, Path], pattern: str = "*", 
               recursive: bool = True) -> List[Path]:
    """
    Find files matching pattern.
    
    Args:
        directory: Directory to search
        pattern: Glob pattern
        recursive: Search recursively
        
    Returns:
        List of matching file paths
    """
    directory = Path(directory)
    
    if not directory.exists():
        logger.warning(f"Directory doesn't exist: {directory}")
        return []
        
    if recursive:
        return list(directory.rglob(pattern))
    else:
        return list(directory.glob(pattern))

def safe_remove(path: Union[str, Path], missing_ok: bool = True) -> bool:
    """
    Safely remove file or directory.
    
    Args:
        path: Path to remove
        missing_ok: If True, don't error if path doesn't exist
        
    Returns:
        True if removed successfully
    """
    path = Path(path)
    
    try:
        if not path.exists():
            if not missing_ok:
                logger.error(f"Path doesn't exist: {path}")
                return False
            return True
            
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
            
        logger.debug(f"Removed: {path}")
        return True
        
    except (IOError, OSError) as e:
        logger.error(f"Failed to remove {path}: {e}")
        return False

def copy_with_structure(src: Union[str, Path], dst: Union[str, Path], 
                       preserve_tree: bool = True) -> bool:
    """
    Copy files preserving directory structure.
    
    Args:
        src: Source path
        dst: Destination path
        preserve_tree: Preserve directory structure
        
    Returns:
        True if successful
    """
    try:
        src, dst = Path(src), Path(dst)
        
        if src.is_file():
            ensure_directory(dst.parent)
            shutil.copy2(src, dst)
        else:
            shutil.copytree(src, dst, dirs_exist_ok=True)
            
        logger.debug(f"Copied {src} to {dst}")
        return True
        
    except (IOError, OSError) as e:
        logger.error(f"Failed to copy {src} to {dst}: {e}")
        return False

def get_size_mb(path: Union[str, Path]) -> float:
    """
    Get size of file or directory in MB.
    
    Args:
        path: Path to measure
        
    Returns:
        Size in megabytes
    """
    path = Path(path)
    
    if not path.exists():
        return 0.0
        
    if path.is_file():
        return path.stat().st_size / (1024 * 1024)
    else:
        total = 0
        for file in path.rglob('*'):
            if file.is_file():
                total += file.stat().st_size
        return total / (1024 * 1024)

def find_most_recent(directory: Union[str, Path], pattern: str = "*") -> Optional[Path]:
    """
    Find most recently modified file matching pattern.
    
    Args:
        directory: Directory to search
        pattern: Glob pattern
        
    Returns:
        Path to most recent file, or None if no matches
    """
    files = find_files(directory, pattern)
    
    if not files:
        return None
        
    return max(files, key=lambda p: p.stat().st_mtime)

def ensure_parent_dir(filepath: Union[str, Path]) -> Path:
    """
    Ensure parent directory of a file exists.
    
    Args:
        filepath: File path
        
    Returns:
        Path to parent directory
    """
    filepath = Path(filepath)
    return ensure_directory(filepath.parent)

def relative_to_cwd(path: Union[str, Path]) -> Path:
    """
    Get path relative to current working directory.
    
    Args:
        path: Absolute or relative path
        
    Returns:
        Path relative to cwd, or absolute path if not under cwd
    """
    path = Path(path).resolve()
    cwd = Path.cwd()
    
    try:
        return path.relative_to(cwd)
    except ValueError:
        return path