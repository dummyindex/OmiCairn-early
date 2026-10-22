"""Code versioning for bug fixer updates.

This module handles versioning of function block code when the bug fixer
makes updates, ensuring both the container and host folders are synchronized
and maintaining a history of code versions.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class CodeVersionManager:
    """Manages code versioning for function blocks during bug fixing."""
    
    def __init__(self, node_dir: Path):
        """Initialize with the node directory path.
        
        Args:
            node_dir: Path to the node directory containing function_block folder
        """
        self.node_dir = node_dir
        self.function_block_dir = node_dir / "function_block"
        self.versions_dir = node_dir / "agent_tasks" / "bug_fixer" / "code_versions"
        
        # Ensure directories exist
        self.function_block_dir.mkdir(parents=True, exist_ok=True)
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        
    def save_version(self, code: str, language: str = "python", 
                     version_suffix: Optional[str] = None) -> Path:
        """Save a version of the code with timestamp.
        
        Args:
            code: The code content to save
            language: Programming language ("python" or "r")
            version_suffix: Optional suffix for the version (e.g., "fixed", "original")
            
        Returns:
            Path to the saved version file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = ".py" if language == "python" else ".R"
        
        # Get current version number
        version_num = self._get_next_version_number()
        
        if version_suffix:
            filename = f"v{version_num:02d}_{version_suffix}_{timestamp}{extension}"
        else:
            filename = f"v{version_num:02d}_{timestamp}{extension}"
            
        version_path = self.versions_dir / filename
        version_path.write_text(code)
        
        logger.info(f"Saved code version: {filename}")
        return version_path
        
    def _get_next_version_number(self) -> int:
        """Get the next version number based on existing versions."""
        existing_versions = list(self.versions_dir.glob("v*.py")) + \
                           list(self.versions_dir.glob("v*.R"))
        
        if not existing_versions:
            return 1
            
        # Extract version numbers
        version_nums = []
        for v in existing_versions:
            try:
                # Extract version number from filename like "v01_fixed_20240815_120000.py"
                version_str = v.stem.split('_')[0][1:]  # Remove 'v' prefix
                version_nums.append(int(version_str))
            except (ValueError, IndexError):
                continue
                
        return max(version_nums, default=0) + 1
        
    def update_function_block(self, code: str, requirements: list, 
                             language: str = "python") -> Dict[str, Any]:
        """Update the function block code and requirements with versioning.
        
        Args:
            code: New code content
            requirements: List of requirements/dependencies
            language: Programming language ("python" or "r")
            
        Returns:
            Dictionary with update results
        """
        try:
            # Determine file names based on language
            code_filename = "code.py" if language == "python" else "code.R"
            function_block_filename = "function_block.py" if language == "python" else "function_block.R"
            
            # Paths in function_block directory
            code_path = self.function_block_dir / code_filename
            function_block_path = self.function_block_dir / function_block_filename
            requirements_path = self.function_block_dir / "requirements.txt"
            
            # Save original versions if they exist
            if code_path.exists():
                original_code = code_path.read_text()
                self.save_version(original_code, language, "original")
                
            if function_block_path.exists() and function_block_path != code_path:
                original_fb = function_block_path.read_text()
                self.save_version(original_fb, language, "original_fb")
                
            # Save the new version
            new_version_path = self.save_version(code, language, "fixed")
            
            # Update the actual files
            code_path.write_text(code)
            function_block_path.write_text(code)  # Keep both in sync
            
            # Update requirements
            if requirements:
                requirements_content = '\n'.join(requirements)
                if not requirements_content.endswith('\n'):
                    requirements_content += '\n'
                requirements_path.write_text(requirements_content)
                
            # Create a version info file
            version_info = {
                "timestamp": datetime.now().isoformat(),
                "version_file": str(new_version_path.name),
                "language": language,
                "requirements_updated": bool(requirements),
                "files_updated": [code_filename, function_block_filename]
            }
            
            version_info_path = self.versions_dir / "latest_version.json"
            import json
            version_info_path.write_text(json.dumps(version_info, indent=2))
            
            logger.info(f"Updated function block with versioning: {new_version_path.name}")
            
            return {
                "success": True,
                "version_saved": str(new_version_path),
                "files_updated": [code_filename, function_block_filename],
                "requirements_updated": bool(requirements)
            }
            
        except Exception as e:
            logger.error(f"Error updating function block with versioning: {e}")
            return {
                "success": False,
                "error": str(e)
            }
            
    def get_version_history(self) -> list:
        """Get the history of code versions.
        
        Returns:
            List of version information dictionaries
        """
        versions = []
        
        for version_file in sorted(self.versions_dir.glob("v*.*")):
            try:
                # Parse version info from filename
                parts = version_file.stem.split('_')
                version_num = int(parts[0][1:])  # Remove 'v' prefix
                
                # Extract suffix - it's everything between version and timestamp
                # e.g., v01_syntax_error_20240101_120000.py -> suffix is "syntax_error"
                suffix = None
                if len(parts) > 2:
                    # Join all parts between version and timestamp
                    suffix_parts = parts[1:-1]  # Exclude version and timestamp
                    suffix = "_".join(suffix_parts) if suffix_parts else None
                
                version_info = {
                    "version": version_num,
                    "filename": version_file.name,
                    "timestamp": version_file.stat().st_mtime,
                    "size": version_file.stat().st_size,
                    "suffix": suffix
                }
                versions.append(version_info)
                
            except (ValueError, IndexError):
                continue
                
        return sorted(versions, key=lambda x: x["version"])