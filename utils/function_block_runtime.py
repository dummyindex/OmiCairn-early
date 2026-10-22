"""Runtime utilities available to function blocks during execution.

This module provides a clean interface for function blocks to access files
from previous nodes in the analysis tree.
"""

import os
import json
from pathlib import Path
from typing import Optional, Union, List, Dict, Any
from datetime import datetime


class PreviousNodes:
    """Access files from previous nodes in the analysis tree.
    
    This class is automatically available in function blocks as `previous_nodes`.
    It provides paths to files - function blocks are responsible for reading them.
    
    Example usage:
        # Import the runtime
        from function_block_runtime import previous_nodes
        
        # List available nodes
        nodes = previous_nodes.list()
        
        # Find and get path to files from any available node
        for node in nodes:
            # Look for h5ad files
            h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]
            if h5ad_files:
                path = previous_nodes.get_file_path(node['index'], h5ad_files[0])
                if path:
                    import scanpy as sc
                    adata = sc.read_h5ad(path)
                    break
        
        # Find CSV files from any node
        for node in nodes:
            csv_files = [f for f in node['files'] if f.endswith('.csv')]
            if csv_files:
                csv_path = previous_nodes.get_file_path(node['index'], csv_files[0])
                if csv_path:
                    import pandas as pd
                    df = pd.read_csv(csv_path)
                    break
    """
    
    def __init__(self):
        """Initialize with container environment."""
        self._cache_dir = Path("/workspace/input/previous_nodes")
        self._index_file = Path("/workspace/input/previous_nodes_index.json")
        self._index = self._load_index()
        
    def _load_index(self) -> Dict[int, Dict[str, Any]]:
        """Load node index from file."""
        if self._index_file.exists():
            with open(self._index_file) as f:
                # Convert string keys to int
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        return {}
    
    def list(self) -> List[Dict[str, Any]]:
        """List all available previous nodes.
        
        Returns:
            List of node info dicts with keys: index, name, level, files
            
        Example:
            >>> nodes = previous_nodes.list()
            >>> for node in nodes:
            ...     print(f"Node {node['index']}: {node['name']}")
        """
        nodes = []
        for idx, info in sorted(self._index.items()):
            nodes.append({
                'index': idx,
                'name': info.get('node_name', 'Unknown'),
                'level': info.get('level', 0),
                'description': info.get('description', ''),
                'files': [f['original'] for f in info.get('available_files', [])],
                'is_parent': info.get('is_parent', False)
            })
        return nodes
    
    def get_file_path(self, node_index: int, relative_path: str) -> Optional[Path]:
        """Get the path to a file from a previous node.
        
        Args:
            node_index: 1-based index of the node
            relative_path: Path relative to node directory (e.g., 'outputs/data.h5ad')
            
        Returns:
            Path object if file exists, None if not found
            
        Example:
            # Find and get path to processed data dynamically
            nodes = previous_nodes.list()
            for node in nodes:
                if 'outputs/processed.h5ad' in node['files']:
                    path = previous_nodes.get_file_path(node['index'], 'outputs/processed.h5ad')
                    if path:
                        import scanpy as sc
                        adata = sc.read_h5ad(path)
                        break
        """
        if node_index not in self._index:
            available = list(self._index.keys())
            raise ValueError(f"Node {node_index} not found. Available nodes: {available}")
        
        # Normalize the path and determine the prefix
        if relative_path.startswith('outputs/'):
            filename = relative_path[8:]  # Remove 'outputs/' prefix
            prefix = 'outputs'
        elif relative_path.startswith('inputs/'):
            filename = relative_path[7:]  # Remove 'inputs/' prefix  
            prefix = 'inputs'
        else:
            # Default to outputs for backward compatibility
            filename = relative_path
            prefix = 'outputs'
        
        # Use new hierarchical structure: node_{idx}/outputs/ or node_{idx}/inputs/
        node_dir = self._cache_dir / f"node_{node_index}"
        staged_path = node_dir / prefix / filename
        
        if not staged_path.exists():
            # Try legacy flat structure for backward compatibility
            staged_name_alt = f"node{node_index}_{filename.replace('/', '_')}"
            staged_path_alt = self._cache_dir / staged_name_alt
            
            if staged_path_alt.exists():
                staged_path = staged_path_alt
            else:
                # File not found - could request it from host in future
                self._request_file_from_host(node_index, relative_path)
                return None
        
        return staged_path
    
    def _request_file_from_host(self, node_index: int, relative_path: str):
        """Request host to stage a file (for future implementation).
        
        Currently, files must be pre-staged by the executor.
        In the future, this could write a request that the host monitors.
        """
        # For now, just log the request
        try:
            request_file = Path("/workspace/output/_file_requests.json")
            request_file.parent.mkdir(parents=True, exist_ok=True)
            
            requests = []
            if request_file.exists():
                with open(request_file) as f:
                    requests = json.load(f)
            
            requests.append({
                'node_index': node_index,
                'relative_path': relative_path,
                'timestamp': datetime.now().isoformat()
            })
            
            with open(request_file, 'w') as f:
                json.dump(requests, f, indent=2)
        except Exception:
            # If we can't write the request, just pass
            pass
    
    
    def get_all_files(self, node_index: int) -> Dict[str, Union[Path, Any]]:
        """Get all available files from a node.
        
        Args:
            node_index: 1-based index of the node
            
        Returns:
            Dictionary mapping filenames to parsed data or paths
            
        Example:
            # Get all files from node 1
            files = previous_nodes.get_all_files(1)
            for name, data in files.items():
                print(f"File: {name}, Type: {type(data)}")
        """
        if node_index not in self._index:
            raise ValueError(f"Node {node_index} not found")
        
        files = {}
        node_info = self._index[node_index]
        
        # Get all staged files for this node
        for file_info in node_info.get('available_files', []):
            if isinstance(file_info, dict):
                original_path = file_info.get('original', '')
                staged_name = file_info.get('staged', '')
                # Also check for 'path' key in new format
                full_path = file_info.get('path', '')
            else:
                # Backward compatibility
                continue
                
            # Try new hierarchical path first
            if full_path:
                staged_path = self._cache_dir / full_path
                if staged_path.exists():
                    files[original_path] = staged_path
                    continue
                    
            # Fall back to staged name
            if staged_name:
                staged_path = self._cache_dir / staged_name
                if staged_path.exists():
                    files[original_path] = staged_path
        
        return files
    
    def __repr__(self):
        """String representation."""
        node_count = len(self._index)
        return f"<PreviousNodes: {node_count} nodes available>"


# Global instance available to function blocks
previous_nodes = PreviousNodes()


# Export the main interface
__all__ = ['previous_nodes', 'PreviousNodes']