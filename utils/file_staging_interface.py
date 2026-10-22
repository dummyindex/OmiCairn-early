"""Modular interface for file staging between host and containers.

This module provides an abstraction layer for file staging methods,
allowing easy switching between different implementations (copy, HTTP, etc.).
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Any
import shutil
import json

from utils.logger import get_logger

logger = get_logger(__name__)


class FileStagingInterface(ABC):
    """Abstract base class for file staging implementations."""
    
    @abstractmethod
    def stage_file(self, source_path: Path, dest_path: Path, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Stage a single file from source to destination.
        
        Args:
            source_path: Path to source file
            dest_path: Path to destination 
            metadata: Optional metadata about the file
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def stage_directory(self, source_dir: Path, dest_dir: Path, pattern: str = "*") -> int:
        """Stage multiple files from a directory.
        
        Args:
            source_dir: Source directory
            dest_dir: Destination directory
            pattern: Glob pattern for files to stage
            
        Returns:
            Number of files staged
        """
        pass
    
    @abstractmethod
    def get_staged_files(self) -> List[Dict[str, str]]:
        """Get list of files that have been staged.
        
        Returns:
            List of dictionaries with 'source' and 'destination' keys
        """
        pass


class CopyFileStaging(FileStagingInterface):
    """File staging implementation using simple file copying."""
    
    def __init__(self):
        self.staged_files = []
    
    def stage_file(self, source_path: Path, dest_path: Path, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Copy file from source to destination."""
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, dest_path)
            
            self.staged_files.append({
                'source': str(source_path),
                'destination': str(dest_path),
                'metadata': metadata or {}
            })
            
            logger.debug(f"Staged file: {source_path} -> {dest_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stage file {source_path}: {e}")
            return False
    
    def stage_directory(self, source_dir: Path, dest_dir: Path, pattern: str = "*") -> int:
        """Copy multiple files matching pattern."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        
        for source_file in source_dir.glob(pattern):
            if source_file.is_file():
                dest_file = dest_dir / source_file.name
                if self.stage_file(source_file, dest_file):
                    count += 1
                    
        return count
    
    def get_staged_files(self) -> List[Dict[str, str]]:
        """Return list of staged files."""
        return self.staged_files


class HTTPFileStaging(FileStagingInterface):
    """File staging implementation using HTTP server (future implementation).
    
    This would allow containers to request files from host via HTTP,
    reducing disk usage and copy times for large files.
    """
    
    def __init__(self, server_url: str = "http://host.docker.internal:8080"):
        self.server_url = server_url
        self.file_registry = {}
        
    def stage_file(self, source_path: Path, dest_path: Path, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Register file for HTTP access instead of copying."""
        # Future implementation would:
        # 1. Register file path with HTTP server
        # 2. Create a lightweight reference file at dest_path
        # 3. The reference would contain URL for fetching actual file
        
        # For now, just register the mapping
        file_id = f"file_{len(self.file_registry)}"
        self.file_registry[file_id] = {
            'source': str(source_path),
            'url': f"{self.server_url}/files/{file_id}",
            'metadata': metadata or {}
        }
        
        # Write reference file
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        reference = {
            'type': 'http_reference',
            'url': self.file_registry[file_id]['url'],
            'source': str(source_path)
        }
        
        with open(dest_path, 'w') as f:
            json.dump(reference, f)
            
        logger.debug(f"Registered file for HTTP access: {source_path}")
        return True
    
    def stage_directory(self, source_dir: Path, dest_dir: Path, pattern: str = "*") -> int:
        """Register multiple files for HTTP access."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        
        for source_file in source_dir.glob(pattern):
            if source_file.is_file():
                dest_file = dest_dir / source_file.name
                if self.stage_file(source_file, dest_file):
                    count += 1
                    
        return count
    
    def get_staged_files(self) -> List[Dict[str, str]]:
        """Return registry of files available via HTTP."""
        return list(self.file_registry.values())


class FileStagingFactory:
    """Factory for creating file staging implementations."""
    
    @staticmethod
    def create(method: str = "copy", **kwargs) -> FileStagingInterface:
        """Create a file staging implementation.
        
        Args:
            method: Staging method ('copy' or 'http')
            **kwargs: Additional arguments for the implementation
            
        Returns:
            FileStagingInterface implementation
        """
        if method == "copy":
            return CopyFileStaging()
        elif method == "http":
            server_url = kwargs.get('server_url', 'http://host.docker.internal:8080')
            return HTTPFileStaging(server_url)
        else:
            raise ValueError(f"Unknown staging method: {method}")


# Global default staging method
DEFAULT_STAGING_METHOD = "copy"


def get_default_file_stager() -> FileStagingInterface:
    """Get the default file staging implementation."""
    return FileStagingFactory.create(DEFAULT_STAGING_METHOD)