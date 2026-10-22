"""Analysis tree manager for orchestrating hierarchical analysis."""

import json
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from models import (
    AnalysisTree, AnalysisNode, NodeState, GenerationMode,
    NewFunctionBlock, ExistingFunctionBlock
)
from utils.logger import get_logger
from config import config
from constants import ROOT_NODE_NAME, DEFAULT_OPENAI_MODEL
from models import JobReviewStatus

logger = get_logger(__name__)


class AnalysisTreeManager:
    """Manages the hierarchical analysis tree structure."""
    
    def __init__(self, tree: Optional[AnalysisTree] = None):
        self.tree = tree
        
    def create_tree(
        self,
        user_request: str,
        input_data_path: str,
        max_nodes: int = 20,
        max_children_per_node: int = 3,
        max_debug_trials: int = 3,
        generation_mode: GenerationMode = GenerationMode.MIXED,
        llm_model: str = DEFAULT_OPENAI_MODEL
    ) -> AnalysisTree:
        """Create a new analysis tree with data loading root node."""
        
        self.tree = AnalysisTree(
            user_request=user_request,
            input_data_path=input_data_path,
            max_nodes=max_nodes,
            max_children_per_node=max_children_per_node,
            max_debug_trials=max_debug_trials,
            generation_mode=generation_mode,
            llm_model=llm_model
        )
        
        logger.info(f"Created new analysis tree: {self.tree.id}")
        
        # Always add a data loading root node that just passes through the input data
        data_loading_block = self._create_data_loading_block()
        root_node = self.add_root_node(data_loading_block)
        logger.info(f"Added data loading root node: {root_node.id}")
        
        return self.tree
    
    def _create_data_loading_block(self) -> Any:
        """Create a simple data loading function block that passes through input data."""
        from models import NewFunctionBlock, FunctionBlockType, StaticConfig
        
        # Enhanced pass-through code that handles both files and directories with nested structures
        code = '''def run(path_dict, params):
    import os
    import shutil
    import glob
    
    # Get input and output directories
    input_dir = path_dict['input_dir']
    output_dir = path_dict['output_dir']
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Find all items in input directory (both files and directories)
    input_items = []
    for item in os.listdir(input_dir):
        item_path = os.path.join(input_dir, item)
        input_items.append((item, item_path, os.path.isdir(item_path)))
    
    if not input_items:
        raise FileNotFoundError(f"No input files or directories found in {input_dir}")
    
    print(f"Found {len(input_items)} input item(s):")
    for name, path, is_dir in input_items:
        if is_dir:
            # Count files in directory recursively
            file_count = sum(1 for _ in glob.glob(os.path.join(path, '**/*'), recursive=True) if os.path.isfile(_))
            print(f"  - {name}/ (directory with {file_count} files)")
        else:
            print(f"  - {name} (file)")
    
    # Copy all items to output directory unchanged
    copied_items = []
    total_files = 0
    
    for name, src_path, is_dir in input_items:
        dst_path = os.path.join(output_dir, name)
        
        if is_dir:
            print(f"Copying directory {name} and all its contents to output...")
            # Copy entire directory tree
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            # Count files copied
            files_in_dir = sum(1 for _ in glob.glob(os.path.join(dst_path, '**/*'), recursive=True) if os.path.isfile(_))
            total_files += files_in_dir
            copied_items.append((name, 'directory', files_in_dir))
        else:
            print(f"Copying file {name} to output directory...")
            shutil.copy2(src_path, dst_path)
            total_files += 1
            copied_items.append((name, 'file', 1))
    
    print(f"\\nSuccessfully copied {len(copied_items)} item(s) with {total_files} total file(s) to output directory")
    
    # List what's in output directory (including nested structures)
    print(f"\\nOutput directory contents:")
    for name, item_type, count in copied_items:
        if item_type == 'directory':
            print(f"  - {name}/ ({count} files)")
            # Show first few files in nested directories
            nested_files = glob.glob(os.path.join(output_dir, name, '**/*.h5ad'), recursive=True)
            for f in nested_files[:3]:  # Show first 3 h5ad files found
                rel_path = os.path.relpath(f, output_dir)
                size = os.path.getsize(f)
                print(f"      → {rel_path} ({size:,} bytes)")
            if len(nested_files) > 3:
                print(f"      → ... and {len(nested_files)-3} more .h5ad files")
        else:
            size = os.path.getsize(os.path.join(output_dir, name))
            print(f"  - {name} ({size:,} bytes)")
    
    return {"copied_items": copied_items, "total_files": total_files, "output_dir": output_dir}
'''
        
        return NewFunctionBlock(
            name=ROOT_NODE_NAME,
            type=FunctionBlockType.PYTHON,
            description="Pass-through node that copies input data to output directory, preserving directory structures",
            parameters={},
            static_config=StaticConfig(
                args=[],
                description="Data loading node that reads input data and passes it through, handling both files and nested directories",
                tag="data_loading",
                document_url="",
                source="generated"
            ),
            code=code,
            requirements="",  # No dependencies needed for file copying
            new=True,
            output_description="This node copies all input files and directories to the output directory without any modifications. All original filenames and directory structures are preserved, including nested subdirectories."
        )
    
    def add_root_node(self, function_block: Any) -> AnalysisNode:
        """Add root node to the tree."""
        
        if not self.tree:
            raise ValueError("No tree initialized")
        
        # Extract rework attempts BEFORE creating the node
        rework_attempts = 0
        if hasattr(function_block, '_rework_attempts'):
            rework_attempts = function_block._rework_attempts
            logger.info(f"Root function block has rework_attempts={rework_attempts}")
        
        # Pass rework_attempts directly to the constructor    
        root_node = AnalysisNode(
            analysis_id=self.tree.id,
            function_block=function_block,
            level=0,
            job_review_status=JobReviewStatus.NOT_REVIEWED,
            rework_attempts=rework_attempts  # Pass it here!
        )
        
        # Log if this is a rework root node
        if rework_attempts > 0:
            from constants import MAX_REWORK_ATTEMPTS
            root_node.rework_limit_reached = (rework_attempts >= MAX_REWORK_ATTEMPTS)
            logger.info(
                f"Created rework root node {root_node.id[:8]}: attempt #{rework_attempts} "
                f"for task '{function_block.name}' (limit reached: {root_node.rework_limit_reached})"
            )
        
        self.tree.add_node(root_node)
        self.tree.root_node_id = root_node.id
        
        logger.info(f"Added root node: {root_node.id} (rework_attempts={rework_attempts})")
        return root_node
    
    def add_child_nodes(
        self, 
        parent_node_id: str, 
        function_blocks: List[Any]
    ) -> List[AnalysisNode]:
        """Add child nodes to a parent node."""
        
        if not self.tree:
            raise ValueError("No tree initialized")
            
        parent_node = self.tree.get_node(parent_node_id)
        if not parent_node:
            raise ValueError(f"Parent node not found: {parent_node_id}")
        
        # Check constraints - only count SUCCESSFUL children
        successful_children = [
            child_id for child_id in parent_node.children
            if self.tree.nodes.get(child_id) and self.tree.nodes[child_id].state == NodeState.COMPLETED
        ]
        
        if len(successful_children) + len(function_blocks) > self.tree.max_children_per_node:
            logger.warning(
                f"Cannot add {len(function_blocks)} children to node {parent_node_id}. "
                f"Would exceed max children limit of {self.tree.max_children_per_node} "
                f"(currently has {len(successful_children)} successful children)"
            )
            function_blocks = function_blocks[:self.tree.max_children_per_node - len(successful_children)]
        
        if self.tree.total_nodes + len(function_blocks) > self.tree.max_nodes:
            logger.warning(
                f"Cannot add {len(function_blocks)} nodes. "
                f"Would exceed max nodes limit of {self.tree.max_nodes}"
            )
            function_blocks = function_blocks[:self.tree.max_nodes - self.tree.total_nodes]
        
        child_nodes = []
        for fb in function_blocks:
            # Extract rework attempts BEFORE creating the node
            rework_attempts = 0
            if hasattr(fb, '_rework_attempts'):
                rework_attempts = fb._rework_attempts
                logger.info(f"Function block has rework_attempts={rework_attempts}")
            
            # Extract rework_of_node_id if this is a rework
            rework_of_node_id = None
            if hasattr(fb, '_rework_of_node_id'):
                rework_of_node_id = fb._rework_of_node_id
                logger.info(f"Function block is rework of node {rework_of_node_id}")
            
            # Pass rework_attempts and rework_of_node_id directly to the constructor
            child_node = AnalysisNode(
                parent_id=parent_node_id,
                analysis_id=self.tree.id,
                function_block=fb,
                level=parent_node.level + 1,
                job_review_status=JobReviewStatus.NOT_REVIEWED,
                rework_attempts=rework_attempts,  # Pass it here!
                rework_of_node_id=rework_of_node_id  # Track which node this is reworking
            )
            
            # Log if this is a rework node
            if rework_attempts > 0:
                from constants import MAX_REWORK_ATTEMPTS
                child_node.rework_limit_reached = (rework_attempts >= MAX_REWORK_ATTEMPTS)
                logger.info(
                    f"Created rework node {child_node.id[:8]}: attempt #{rework_attempts} "
                    f"for task '{fb.name}' (limit reached: {child_node.rework_limit_reached})"
                )
            
            self.tree.add_node(child_node)
            child_nodes.append(child_node)
            
        logger.info(f"Added {len(child_nodes)} child nodes to {parent_node_id}")
        return child_nodes
    
    def get_execution_order(self) -> List[AnalysisNode]:
        """Get nodes in execution order (breadth-first)."""
        
        if not self.tree:
            logger.warning("get_execution_order called with no tree initialized")
            return []
        
        if not self.tree.root_node_id:
            logger.error("Tree exists but has no root_node_id - tree is corrupted")
            raise ValueError("Tree is missing root_node_id")
        
        execution_order = []
        queue = [self.tree.root_node_id]
        
        while queue:
            node_id = queue.pop(0)
            node = self.tree.get_node(node_id)
            
            if node and node.state == NodeState.PENDING:
                execution_order.append(node)
                
            if node:
                queue.extend(node.children)
        
        return execution_order
    
    def get_parent_chain(self, node_id: str) -> List[AnalysisNode]:
        """Get all parent nodes up to root."""
        
        if not self.tree:
            logger.debug(f"get_parent_chain called for {node_id} with no tree")
            return []
            
        chain = []
        current_id = node_id
        
        while current_id:
            node = self.tree.get_node(current_id)
            if not node:
                break
                
            if node.parent_id:  # Don't include the node itself
                parent = self.tree.get_node(node.parent_id)
                if parent:
                    chain.insert(0, parent)
                    current_id = node.parent_id
                else:
                    break
            else:
                break
        
        return chain
    
    def update_node_execution(
        self,
        node_id: str,
        state: NodeState,
        output_data_id: Optional[str] = None,
        figures: Optional[List[str]] = None,
        logs: Optional[List[str]] = None,
        error: Optional[str] = None,
        duration: Optional[float] = None
    ) -> None:
        """Update node after execution."""
        
        if not self.tree:
            return
            
        node = self.tree.get_node(node_id)
        if not node:
            return
        
        # Update state
        self.tree.update_node_state(node_id, state)
        
        # Update execution info
        if state == NodeState.RUNNING:
            node.start_time = datetime.now()
        elif state in [NodeState.COMPLETED, NodeState.FAILED]:
            node.end_time = datetime.now()
            if duration:
                node.duration = duration
            elif node.start_time:
                node.duration = (node.end_time - node.start_time).total_seconds()
        
        # Update results
        if output_data_id:
            node.output_data_id = output_data_id
        if figures:
            node.figures.extend(figures)
        if logs:
            node.logs.extend(logs)
        if error:
            node.error = error
        
        node.updated_at = datetime.now()
        
        logger.info(f"Updated node {node_id} to state {state}")
    
    def increment_debug_attempts(self, node_id: str) -> int:
        """Increment debug attempts for a node."""
        
        if not self.tree:
            return 0
            
        node = self.tree.get_node(node_id)
        if node:
            node.debug_attempts += 1
            return node.debug_attempts
        
        return 0
    
    def can_continue_expansion(self) -> bool:
        """Check if tree can continue expanding."""
        
        if not self.tree:
            return False
            
        # Check node limit
        if self.tree.total_nodes >= self.tree.max_nodes:
            logger.info("Reached maximum node limit")
            return False
        
        # Check if there are pending nodes
        has_pending = any(
            node.state == NodeState.PENDING 
            for node in self.tree.nodes.values()
        )
        
        return has_pending
    
    def get_latest_data_path(self, node_id: str) -> Optional[Path]:
        """Get the latest data path from node or its parents."""
        
        if not self.tree:
            logger.warning(f"get_latest_data_path called for {node_id} with no tree")
            return None
            
        # Check current node
        node = self.tree.get_node(node_id)
        if node and node.output_data_id:
            return Path(node.output_data_id)
        
        # Check parent chain
        parents = self.get_parent_chain(node_id)
        for parent in reversed(parents):
            if parent.output_data_id:
                return Path(parent.output_data_id)
        
        # Fall back to input data
        return Path(self.tree.input_data_path)
    
    def save_tree(self, path: Path) -> None:
        """Save tree to JSON file and create directory tree markdown."""
        
        if not self.tree:
            logger.warning(f"Cannot save tree to {path} - tree is None")
            return
            
        path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(path, "w") as f:
                json.dump(self.tree.model_dump(), f, indent=2, default=str)
            
            logger.info(f"Saved analysis tree to {path}")
            
            # Also create directory tree markdown file
            tree_md_path = path.parent / "directory_tree.md"
            self._create_directory_tree_md(path.parent, tree_md_path)
            
        except Exception as e:
            logger.error(f"Failed to save analysis tree to {path}: {e}")
    
    def _create_directory_tree_md(self, base_dir: Path, output_path: Path) -> None:
        """Create a markdown file with the directory tree structure."""
        try:
            lines = []
            lines.append("# Analysis Tree Directory Structure\n")
            lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            lines.append(f"**Location:** `{base_dir}`\n")
            
            # Add node relationship tree as first section
            if self.tree and self.tree.nodes:
                lines.append("\n## Node Execution Tree\n")
                lines.append("This shows the hierarchical execution relationship between nodes:\n")
                lines.append("```\n")
                
                def add_node_tree(node_id: str, prefix: str = "", is_last: bool = True, depth: int = 0):
                    """Add node to the tree visualization."""
                    if node_id not in self.tree.nodes:
                        return
                    
                    node = self.tree.nodes[node_id]
                    connector = "└── " if is_last else "├── "
                    
                    # Format node display with both execution and review status
                    exec_symbol = "✅" if node.state == NodeState.COMPLETED else "❌" if node.state == NodeState.FAILED else "⏳"
                    
                    # Add review status if available
                    review_symbol = ""
                    if node.job_review_status == JobReviewStatus.PASSED:
                        review_symbol = " ✓"
                    elif node.job_review_status == JobReviewStatus.FAILED:
                        review_symbol = " ⚠️"
                        if node.needs_rework:
                            review_symbol = " 🔄"  # Needs rework
                    elif node.job_review_status == JobReviewStatus.SKIPPED:
                        review_symbol = " ⏭️"
                    
                    # Show shortened ID (first 8 chars) for readability
                    short_id = node_id[:8]
                    node_name = f"{node.function_block.name} [{exec_symbol}{review_symbol}] (node_{short_id}...)"
                    
                    # Add node to tree
                    if depth == 0:
                        lines.append(f"{node_name}\n")
                    else:
                        lines.append(f"{prefix}{connector}{node_name}\n")
                    
                    # Process children
                    children = [nid for nid, n in self.tree.nodes.items() if n.parent_id == node_id]
                    for i, child_id in enumerate(children):
                        is_last_child = (i == len(children) - 1)
                        if depth == 0:
                            child_prefix = ""
                        else:
                            extension = "    " if is_last else "│   "
                            child_prefix = prefix + extension
                        add_node_tree(child_id, child_prefix, is_last_child, depth + 1)
                
                # Find root node(s) and build tree
                root_nodes = [nid for nid, node in self.tree.nodes.items() if node.parent_id is None]
                for i, root_id in enumerate(root_nodes):
                    if i > 0:
                        lines.append("\n")
                    add_node_tree(root_id, "", True, 0)
                
                lines.append("```\n")
            
            # Add directory structure section
            lines.append("\n## Directory Structure\n")
            lines.append("```\n")
            
            # Build the tree structure with better formatting
            def add_item(path: Path, prefix: str = "", is_last: bool = True, depth: int = 0):
                """Recursively add items to the tree."""
                # Skip __pycache__ and .pyc files
                if path.name == "__pycache__" or path.suffix == ".pyc":
                    return
                
                # Skip deep nesting for readability
                if depth > 4 and path.is_dir():
                    # Just show that there are more items
                    connector = "└── " if is_last else "├── "
                    items = list(path.iterdir()) if path.is_dir() else []
                    items = [i for i in items if i.name != "__pycache__" and i.suffix != ".pyc"]
                    if items:
                        lines.append(f"{prefix}{connector}{path.name}/ ... ({len(items)} items)\n")
                    return
                
                # Determine the connector
                connector = "└── " if is_last else "├── "
                
                # Format the item name with appropriate info
                if path.is_file():
                    size = path.stat().st_size
                    if size < 1024:
                        size_str = f"{size}B"
                    elif size < 1024 * 1024:
                        size_str = f"{size/1024:.1f}KB"
                    else:
                        size_str = f"{size/(1024*1024):.1f}MB"
                    lines.append(f"{prefix}{connector}{path.name} ({size_str})\n")
                else:
                    # For directories, show cleaner format
                    lines.append(f"{prefix}{connector}{path.name}/\n")
                
                # Process children for directories
                if path.is_dir() and depth < 4:
                    # Get children, excluding hidden files
                    children = sorted([p for p in path.iterdir() 
                                     if not p.name.startswith('.') 
                                     and p.name != "__pycache__"])
                    
                    # Group files and directories
                    dirs = [c for c in children if c.is_dir()]
                    files = [c for c in children if c.is_file()]
                    
                    # Show directories first, then files
                    all_children = dirs + files
                    
                    for i, child in enumerate(all_children):
                        is_last_child = (i == len(all_children) - 1)
                        extension = "    " if is_last else "│   "
                        add_item(child, prefix + extension, is_last_child, depth + 1)
            
            # Start with the base directory
            lines.append(f"{base_dir.name}/\n")
            
            # Process main items with better organization
            main_items = sorted([p for p in base_dir.iterdir() 
                                if not p.name.startswith('.')])
            
            # Group items by type
            json_files = []
            md_files = []
            data_files = []
            main_dirs = []
            tree_dir = None
            
            for item in main_items:
                if item.suffix == '.json':
                    json_files.append(item)
                elif item.suffix == '.md':
                    md_files.append(item)
                elif item.suffix in ['.h5ad', '.csv', '.h5']:
                    data_files.append(item)
                elif item.name.startswith('main_'):
                    main_dirs.append(item)
                elif self.tree and item.name == self.tree.id:
                    tree_dir = item
            
            # Show in organized order
            all_items = json_files + md_files + data_files + main_dirs
            if tree_dir:
                all_items.append(tree_dir)
            
            for i, item in enumerate(all_items):
                is_last = (i == len(all_items) - 1)
                add_item(item, "", is_last, 0)
            
            lines.append("```\n")
            
            # Add summary statistics
            if self.tree:
                lines.append("\n## Analysis Summary\n")
                lines.append(f"- **Tree ID**: {self.tree.id}\n")
                lines.append(f"- **Total Nodes**: {self.tree.total_nodes}\n")
                lines.append(f"- **Completed Nodes**: {self.tree.completed_nodes}\n")
                lines.append(f"- **Failed Nodes**: {self.tree.failed_nodes}\n")
                lines.append(f"- **User Request**: {self.tree.user_request}\n")
                
                # Add node details
                lines.append("\n## Node Details\n")
                for node_id, node in self.tree.nodes.items():
                    # Show execution status
                    exec_emoji = "✅" if node.state == NodeState.COMPLETED else "❌" if node.state == NodeState.FAILED else "⏳"
                    
                    # Show review status
                    review_info = ""
                    if node.job_review_status:
                        if node.job_review_status == JobReviewStatus.PASSED:
                            review_info = " | Review: ✓ Passed"
                        elif node.job_review_status == JobReviewStatus.FAILED:
                            if node.needs_rework:
                                review_info = " | Review: 🔄 Needs Rework"
                            else:
                                review_info = " | Review: ⚠️ Failed (non-critical)"
                        elif node.job_review_status == JobReviewStatus.SKIPPED:
                            review_info = " | Review: ⏭️ Skipped"
                    
                    lines.append(f"- **{node.function_block.name}** ({exec_emoji} {node.state.value}{review_info})")
                    lines.append(f"  - ID: `{node_id}`")
                    lines.append(f"  - Directory: `nodes/node_{node_id}/`")
                    if node.state == NodeState.FAILED and node.error:
                        lines.append(f"  - Error: {node.error[:100]}...")
                    if node.job_review_summary and node.job_review_status == JobReviewStatus.FAILED:
                        lines.append(f"  - Review: {node.job_review_summary[:100]}...")
            
            # Write to file
            with open(output_path, 'w') as f:
                f.writelines(lines)
            
            logger.info(f"Created directory tree markdown at {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to create directory tree markdown: {e}")
    
    def load_tree(self, path: Path) -> AnalysisTree:
        """Load tree from JSON file."""
        
        with open(path) as f:
            data = json.load(f)
        
        self.tree = AnalysisTree(**data)
        logger.info(f"Loaded analysis tree from {path}")
        
        return self.tree
    
    def get_summary(self) -> Dict[str, Any]:
        """Get tree execution summary."""
        
        if not self.tree:
            logger.debug("get_summary called with no tree")
            return {"error": "no_tree", "message": "Tree not initialized"}
            
        # Calculate statistics
        completed_nodes = [n for n in self.tree.nodes.values() if n.state == NodeState.COMPLETED]
        failed_nodes = [n for n in self.tree.nodes.values() if n.state == NodeState.FAILED]
        total_duration = sum(n.duration or 0 for n in completed_nodes)
        
        return {
            "tree_id": self.tree.id,
            "user_request": self.tree.user_request,
            "total_nodes": self.tree.total_nodes,
            "completed_nodes": len(completed_nodes),
            "failed_nodes": len(failed_nodes),
            "pending_nodes": self.tree.total_nodes - len(completed_nodes) - len(failed_nodes),
            "total_duration_seconds": total_duration,
            "created_at": self.tree.created_at,
            "updated_at": self.tree.updated_at,
            "max_depth": max((n.level for n in self.tree.nodes.values()), default=0)
        }
    
    def update_node_state(self, node_id: str, state: NodeState, output_data_id: Optional[str] = None, error: Optional[str] = None):
        """Update the state of a node in the tree.
        
        Args:
            node_id: ID of the node to update
            state: New state for the node
            output_data_id: Output data path if completed
            error: Error message if failed
        """
        if not self.tree or node_id not in self.tree.nodes:
            return
        
        node = self.tree.nodes[node_id]
        
        # Store error if provided
        if error:
            node.error = error
        
        if output_data_id:
            node.output_data_id = output_data_id
        
        # Use the tree's update_node_state method which properly maintains statistics
        self.tree.update_node_state(node_id, state)
        
        # Tree will be saved by caller if needed
    
    def create_output_structure(self, output_dir: Path) -> Dict[str, Path]:
        """Create the standardized output directory structure.
        
        Args:
            output_dir: Base output directory
            
        Returns:
            Dictionary with paths to key directories
        """
        if not self.tree:
            raise ValueError("No tree initialized")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tree_id_short = self.tree.id[:8]
        
        # Don't create main agent task folder - that's separate from the tree structure
        # The analysis_tree.json should be at the base output directory level
        
        # Create tree folder (just the ID, no "tree_" prefix per docs)
        tree_dir = output_dir / self.tree.id
        tree_dir.mkdir(parents=True, exist_ok=True)
        
        nodes_dir = tree_dir / "nodes"
        nodes_dir.mkdir(exist_ok=True)
        
        # Save analysis tree at base output directory level (per docs)
        self.save_tree(output_dir / "analysis_tree.json")
        
        logger.info(f"Created output structure in {output_dir}")
        
        return {
            "output_dir": output_dir,
            "tree_dir": tree_dir,
            "nodes_dir": nodes_dir,
            "analysis_tree_path": output_dir / "analysis_tree.json"
        }
    
    def create_node_directory(self, node_id: str, nodes_dir: Path) -> Dict[str, Path]:
        """Create directory structure for a single node.
        
        Args:
            node_id: Node ID
            nodes_dir: Base nodes directory
            
        Returns:
            Dictionary with paths to node directories
        """
        if not self.tree or node_id not in self.tree.nodes:
            raise ValueError(f"Node {node_id} not found in tree")
        
        node = self.tree.nodes[node_id]
        node_dir = nodes_dir / f"node_{node_id}"
        node_dir.mkdir(exist_ok=True)
        
        # Create subdirectories
        function_block_dir = node_dir / "function_block"
        function_block_dir.mkdir(exist_ok=True)
        
        jobs_dir = node_dir / "jobs"
        jobs_dir.mkdir(exist_ok=True)
        
        outputs_dir = node_dir / "outputs"
        outputs_dir.mkdir(exist_ok=True)
        (outputs_dir / "figures").mkdir(exist_ok=True)
        
        agent_tasks_dir = node_dir / "agent_tasks"
        agent_tasks_dir.mkdir(exist_ok=True)
        
        # Save node info
        node_info = {
            "id": node.id,
            "name": node.function_block.name if node.function_block else "unknown",
            "type": node.function_block.type.value if node.function_block and hasattr(node.function_block.type, 'value') else "python",
            "parent_id": node.parent_id,
            "children_ids": node.children,
            "state": node.state.value if hasattr(node.state, 'value') else str(node.state),
            "job_review_status": node.job_review_status,
            "needs_rework": node.needs_rework,
            "job_review_summary": node.job_review_summary,
            "level": node.level,
            "created_at": node.created_at.isoformat() if node.created_at else datetime.now().isoformat(),
            "last_execution": node.updated_at.isoformat() if node.updated_at else None,
            "execution_count": 1,
            "debug_attempts": node.debug_attempts,
            "rework_attempts": getattr(node, 'rework_attempts', 0),
            "rework_limit_reached": getattr(node, 'rework_limit_reached', False),
            "rework_of_node_id": getattr(node, 'rework_of_node_id', None)
        }
        with open(node_dir / "node_info.json", "w") as f:
            json.dump(node_info, f, indent=2)
        
        # Save function block if present
        if node.function_block:
            self.save_function_block(node.function_block, function_block_dir)
        
        logger.info(f"Created node directory for {node_id}")
        
        return {
            "node_dir": node_dir,
            "function_block_dir": function_block_dir,
            "jobs_dir": jobs_dir,
            "outputs_dir": outputs_dir,
            "agent_tasks_dir": agent_tasks_dir
        }
    
    def save_function_block(self, function_block: Any, function_block_dir: Path) -> None:
        """Save function block to directory.
        
        Args:
            function_block: Function block object
            function_block_dir: Directory to save to
        """
        # Save code
        if hasattr(function_block, 'code'):
            with open(function_block_dir / "code.py", "w") as f:
                f.write(function_block.code)
        
        # Save config
        config = {
            "name": function_block.name,
            "description": function_block.description if hasattr(function_block, 'description') else "",
            "parameters": function_block.parameters if hasattr(function_block, 'parameters') else {},
            "static_config": function_block.static_config.model_dump() if hasattr(function_block, 'static_config') and hasattr(function_block.static_config, 'model_dump') else {}
        }
        with open(function_block_dir / "config.json", "w") as f:
            json.dump(config, f, indent=2)
        
        # Save requirements
        if hasattr(function_block, 'requirements'):
            with open(function_block_dir / "requirements.txt", "w") as f:
                f.write(function_block.requirements)
    
    def create_job_directory(self, node_id: str, node_dir: Path) -> Path:
        """Create a new job directory for node execution.
        
        Args:
            node_id: Node ID
            node_dir: Node directory
            
        Returns:
            Path to the new job directory
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_id = f"job_{timestamp}_{node_id[:8]}"
        job_dir = node_dir / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories per docs structure
        (job_dir / "input").mkdir(exist_ok=True)  # Added input directory
        (job_dir / "logs").mkdir(exist_ok=True)
        (job_dir / "output").mkdir(exist_ok=True)
        (job_dir / "output" / "figures").mkdir(exist_ok=True)
        # NOTE: No past_jobs directory - each job is its own directory under jobs/
        
        # Update latest symlink
        latest_link = node_dir / "jobs" / "latest"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(job_id)
        
        logger.info(f"Created job directory {job_id} for node {node_id}")
        
        return job_dir
    
    def save_job_execution_summary(self, job_dir: Path, node_id: str, state: str, 
                                    start_time: datetime, end_time: datetime,
                                    input_path: str, output_path: str,
                                    exit_code: int = 0, error_message: Optional[str] = None) -> None:
        """Save job execution summary.
        
        Args:
            job_dir: Job directory
            node_id: Node ID
            state: Execution state (success/failed)
            start_time: Job start time
            end_time: Job end time
            input_path: Input data path
            output_path: Output data path
            exit_code: Process exit code
            error_message: Error message if failed
        """
        summary = {
            "job_id": job_dir.name,
            "node_id": node_id,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": (end_time - start_time).total_seconds(),
            "exit_code": exit_code,
            "state": state,
            "input_path": input_path,
            "output_path": output_path,
            "error_message": error_message
        }
        
        with open(job_dir / "execution_summary.json", "w") as f:
            json.dump(summary, f, indent=2)
    
    def copy_outputs_to_node(self, job_dir: Path, node_dir: Path) -> None:
        """Copy job outputs to node outputs directory.
        
        Args:
            job_dir: Job directory with outputs
            node_dir: Node directory
        """
        import shutil
        
        job_output_dir = job_dir / "output"
        node_output_dir = node_dir / "outputs"
        
        # Copy all output files from job to node outputs
        if job_output_dir.exists():
            for item in job_output_dir.iterdir():
                if item.is_file():
                    shutil.copy2(item, node_output_dir / item.name)
        
        # Copy figures
        job_figures_dir = job_output_dir / "figures"
        if job_figures_dir.exists():
            node_figures_dir = node_output_dir / "figures"
            if node_figures_dir.exists():
                shutil.rmtree(node_figures_dir)
            shutil.copytree(job_figures_dir, node_figures_dir)
        
        logger.info(f"Copied outputs from {job_dir} to {node_output_dir}")
    
    def get_tree_visualization(self) -> str:
        """Generate a text visualization of the tree.
        
        Returns:
            String representation of the tree structure
        """
        if not self.tree or not self.tree.root_node_id:
            return "Empty tree"
        
        lines = []
        
        def add_node(node_id: str, indent: int = 0):
            node = self.tree.nodes.get(node_id)
            if not node:
                return
            
            prefix = "  " * indent + ("└─ " if indent > 0 else "")
            state_str = node.state.value if hasattr(node.state, 'value') else str(node.state)
            
            # Add review status if available
            review_str = ""
            if node.job_review_status:
                if node.job_review_status == JobReviewStatus.PASSED:
                    review_str = ", review: passed"
                elif node.job_review_status == JobReviewStatus.FAILED:
                    if node.needs_rework:
                        review_str = ", review: needs rework"
                    else:
                        review_str = ", review: failed"
                elif node.job_review_status == JobReviewStatus.SKIPPED:
                    review_str = ", review: skipped"
            
            lines.append(f"{prefix}{node.function_block.name} ({state_str}{review_str})")
            
            for child_id in node.children:
                add_node(child_id, indent + 1)
        
        add_node(self.tree.root_node_id)
        return "\n".join(lines)