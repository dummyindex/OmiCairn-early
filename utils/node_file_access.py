"""Utilities for accessing files from previous nodes in the analysis tree.

This module provides functions to retrieve files from previous nodes in a way
that's friendly for LLMs to use and safe for container execution.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime

from models import AnalysisTree, AnalysisNode, NodeState
from utils.logger import get_logger

logger = get_logger(__name__)


# Note: The old PREVIOUS_NODES_INTERFACE_CODE has been removed.
# Function blocks should use the function_block_runtime.py module instead.


class NodeFileAccessor:
    """Provides access to files from previous nodes in the analysis tree."""
    
    def __init__(self, tree: AnalysisTree, tree_dir: Path):
        """Initialize the file accessor.
        
        Args:
            tree: The analysis tree
            tree_dir: Base directory containing the tree structure
        """
        self.tree = tree
        self.tree_dir = Path(tree_dir)
        self.nodes_dir = self.tree_dir / "nodes"
        
    def get_node_index_map(self, current_node_id: str) -> Dict[int, Dict[str, Any]]:
        """Create an index map of accessible nodes for LLM-friendly reference.
        
        Args:
            current_node_id: ID of the current node
            
        Returns:
            Dictionary mapping simple indices to node information
        """
        index_map = {}
        index = 1
        
        # Get all nodes in the same branch (ancestors and siblings)
        accessible_nodes = self._get_accessible_nodes(current_node_id)
        
        # Sort by level (root first) then by creation order
        sorted_nodes = sorted(
            accessible_nodes,
            key=lambda n: (n.level, n.start_time or datetime.min)
        )
        
        for node in sorted_nodes:
            if node.state == NodeState.COMPLETED and node.id != current_node_id:
                node_dir = self.nodes_dir / f"node_{node.id}"
                outputs_dir = node_dir / "outputs"
                
                # Get available files
                output_files = []
                if outputs_dir.exists():
                    output_files = [
                        f.name for f in outputs_dir.iterdir() 
                        if f.is_file() and not f.name.startswith('.')
                    ]
                
                index_map[index] = {
                    'node_id': node.id,
                    'node_name': node.function_block.name,
                    'level': node.level,
                    'description': node.function_block.description,
                    'output_files': output_files,
                    'is_parent': node.id == self._get_parent_id(current_node_id),
                    'is_ancestor': self._is_ancestor(node.id, current_node_id)
                }
                index += 1
                
        return index_map
    
    def retrieve_node_file(
        self,
        node_index: int,
        filename: str,
        index_map: Dict[int, Dict[str, Any]],
        destination_dir: Path
    ) -> Tuple[bool, str, Optional[Path]]:
        """Retrieve a file from a previous node by index.
        
        Args:
            node_index: Simple index of the node (1-based)
            filename: Name of the file to retrieve
            index_map: The index map from get_node_index_map
            destination_dir: Where to copy the file
            
        Returns:
            Tuple of (success, message, file_path)
        """
        # Validate index
        if node_index not in index_map:
            available_indices = sorted(index_map.keys())
            return (
                False,
                f"Invalid node index {node_index}. Available indices: {available_indices}",
                None
            )
        
        node_info = index_map[node_index]
        node_id = node_info['node_id']
        
        # Check if file exists
        if filename not in node_info['output_files']:
            return (
                False,
                f"File '{filename}' not found in node {node_index} ({node_info['node_name']}). "
                f"Available files: {node_info['output_files']}",
                None
            )
        
        # Copy the file
        source_path = self.nodes_dir / f"node_{node_id}" / "outputs" / filename
        dest_path = destination_dir / f"node{node_index}_{filename}"
        
        try:
            shutil.copy2(source_path, dest_path)
            return (
                True,
                f"Successfully retrieved '{filename}' from node {node_index} ({node_info['node_name']})",
                dest_path
            )
        except Exception as e:
            return (
                False,
                f"Error copying file: {str(e)}",
                None
            )
    
    def retrieve_multiple_files(
        self,
        file_requests: List[Dict[str, Any]],
        index_map: Dict[int, Dict[str, Any]],
        destination_dir: Path
    ) -> Dict[str, Any]:
        """Retrieve multiple files from different nodes in one batch.
        
        Args:
            file_requests: List of dicts with 'node_index' and 'filename'
            index_map: The index map from get_node_index_map
            destination_dir: Where to copy the files
            
        Returns:
            Dictionary with results for each file request
        """
        results = {
            'success': True,
            'retrieved_files': [],
            'failed_files': [],
            'messages': []
        }
        
        for request in file_requests:
            node_index = request.get('node_index')
            filename = request.get('filename')
            
            if node_index is None or filename is None:
                results['failed_files'].append({
                    'request': request,
                    'error': 'Missing node_index or filename'
                })
                results['messages'].append(f"Invalid request: {request}")
                continue
            
            success, message, file_path = self.retrieve_node_file(
                node_index, filename, index_map, destination_dir
            )
            
            if success:
                results['retrieved_files'].append({
                    'node_index': node_index,
                    'filename': filename,
                    'local_path': str(file_path),
                    'node_name': index_map[node_index]['node_name']
                })
            else:
                results['failed_files'].append({
                    'node_index': node_index,
                    'filename': filename,
                    'error': message
                })
                results['success'] = False
            
            results['messages'].append(message)
        
        return results
    
    def get_readable_node_list(self, current_node_id: str) -> str:
        """Get a human-readable list of available nodes and their files.
        
        Args:
            current_node_id: ID of the current node
            
        Returns:
            Formatted string describing available nodes
        """
        index_map = self.get_node_index_map(current_node_id)
        
        if not index_map:
            return "No previous nodes available."
        
        lines = ["Available previous nodes:"]
        for idx, info in sorted(index_map.items()):
            prefix = "  [PARENT]" if info['is_parent'] else "         "
            lines.append(f"{prefix} Node {idx}: {info['node_name']} (Level {info['level']})")
            lines.append(f"           Description: {info['description']}")
            if info['output_files']:
                lines.append(f"           Files: {', '.join(info['output_files'])}")
            else:
                lines.append(f"           Files: (no output files)")
            lines.append("")
        
        return "\n".join(lines)
    
    def _get_accessible_nodes(self, current_node_id: str) -> List[AnalysisNode]:
        """Get all nodes accessible from the current node (ancestors and their children)."""
        accessible = set()  # Use set to avoid duplicates
        
        current_node = self.tree.nodes.get(current_node_id)
        if not current_node:
            return []
        
        # Add all ancestors
        node = current_node
        while node.parent_id:
            parent = self.tree.nodes.get(node.parent_id)
            if parent:
                accessible.add(parent.id)
                node = parent
            else:
                break
        
        # Convert to list of nodes
        result = []
        for node_id in accessible:
            if node_id in self.tree.nodes:
                result.append(self.tree.nodes[node_id])
        
        return result
    
    def _is_ancestor(self, potential_ancestor_id: str, node_id: str) -> bool:
        """Check if a node is an ancestor of another node."""
        node = self.tree.nodes.get(node_id)
        while node and node.parent_id:
            if node.parent_id == potential_ancestor_id:
                return True
            node = self.tree.nodes.get(node.parent_id)
        return False
    
    def _is_in_same_branch(self, node1_id: str, node2_id: str) -> bool:
        """Check if two nodes are in the same branch (share a common ancestor)."""
        # Get all ancestors of both nodes
        ancestors1 = set()
        node = self.tree.nodes.get(node1_id)
        while node:
            ancestors1.add(node.id)
            node = self.tree.nodes.get(node.parent_id) if node.parent_id else None
        
        # Check if node2 or any of its ancestors are in ancestors1
        node = self.tree.nodes.get(node2_id)
        while node:
            if node.id in ancestors1:
                return True
            node = self.tree.nodes.get(node.parent_id) if node.parent_id else None
        
        return False
    
    def _get_parent_id(self, node_id: str) -> Optional[str]:
        """Get the parent ID of a node."""
        node = self.tree.nodes.get(node_id)
        return node.parent_id if node else None


def prepare_previous_nodes_context(
    tree: AnalysisTree,
    tree_dir: Path,
    current_node_id: str,
    staging_dir: Path
) -> Dict[str, Any]:
    """Prepare context about previous nodes for LLM consumption.
    
    Args:
        tree: The analysis tree
        tree_dir: Base directory containing the tree structure
        current_node_id: ID of the current node
        staging_dir: Directory to stage any retrieved files
        
    Returns:
        Dictionary with previous nodes context
    """
    accessor = NodeFileAccessor(tree, tree_dir)
    index_map = accessor.get_node_index_map(current_node_id)
    
    # Create a simple summary for LLM
    summary = {
        'total_previous_nodes': len(index_map),
        'node_list': accessor.get_readable_node_list(current_node_id),
        'index_map': index_map,
        'instructions': (
            "To access files from previous nodes, use:\n"
            "1. Single file: {'type': 'retrieve_previous_node_file', 'node_index': 1, 'filename': 'preprocessed.h5ad'}\n"
            "2. Multiple files: {'type': 'retrieve_previous_node_files', 'files': ["
            "{'node_index': 1, 'filename': 'data.h5ad'}, {'node_index': 2, 'filename': 'results.csv'}]}\n"
            "3. List available: {'type': 'list_previous_nodes'}"
        )
    }
    
    return summary


def prepare_previous_nodes_for_container(
    tree: AnalysisTree,
    tree_dir: Path,
    current_node_id: str,
    container_input_dir: Path,
    requested_files: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Prepare previous nodes' files for container execution.
    
    This function stages files outside the container and prepares them for mounting.
    
    Args:
        tree: The analysis tree
        tree_dir: Base directory containing the tree structure
        current_node_id: ID of the current node
        container_input_dir: Host directory that will be mounted to container
        requested_files: Optional list of specific files to retrieve
        
    Returns:
        Dictionary with staging results and prepared context
    """
    accessor = NodeFileAccessor(tree, tree_dir)
    index_map = accessor.get_node_index_map(current_node_id)
    
    # Create previous_nodes subdirectory
    prev_nodes_dir = container_input_dir / "previous_nodes"
    prev_nodes_dir.mkdir(exist_ok=True)
    
    # Save index map for the Python interface
    index_map_file = prev_nodes_dir / "index_map.json"
    with open(index_map_file, 'w') as f:
        json.dump(index_map, f, indent=2)
    
    # Note: The old Python interface code has been removed.
    # Function blocks now use function_block_runtime.py instead.
    
    # Stage requested files if any
    staged_files = []
    if requested_files:
        results = accessor.retrieve_multiple_files(
            requested_files, index_map, prev_nodes_dir
        )
        staged_files = results.get('retrieved_files', [])
    
    return {
        'previous_nodes_dir': str(prev_nodes_dir),
        'index_map': index_map,
        'staged_files': staged_files,
        'interface_available': True,
        'usage_example': (
            "# In your function block code:\n"
            "from function_block_runtime import previous_nodes\n"
            "nodes = previous_nodes.list()\n"
            "# Find nodes with h5ad files dynamically\n"
            "for node in nodes:\n"
            "    h5ad_files = [f for f in node['files'] if f.endswith('.h5ad')]\n"
            "    if h5ad_files:\n"
            "        path = previous_nodes.get_file_path(node['index'], h5ad_files[0])\n"
            "        if path:\n"
            "            import scanpy as sc\n"
            "            adata = sc.read_h5ad(path)\n"
            "            break"
        )
    }


# Load the actual runtime code for embedding
import os
FUNCTION_BLOCK_RUNTIME_CODE = ""
runtime_path = os.path.join(os.path.dirname(__file__), 'function_block_runtime.py')
if os.path.exists(runtime_path):
    with open(runtime_path, 'r') as f:
        FUNCTION_BLOCK_RUNTIME_CODE = f.read()