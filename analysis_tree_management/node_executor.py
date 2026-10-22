"""Node executor for analysis tree nodes with comprehensive output management."""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any
from datetime import datetime

from models import (
    AnalysisNode, AnalysisTree, NodeState, FunctionBlockType,
    NewFunctionBlock, ExistingFunctionBlock, ExecutionResult
)
from models import (
    ExecutionContext, ExecutionRequest, ExecutionResponse, 
    FileInfo, FileType, NodeExecutionResult
)
from utils import setup_logger
from utils.node_file_access import NodeFileAccessor, FUNCTION_BLOCK_RUNTIME_CODE
from utils.file_staging_interface import get_default_file_stager

logger = setup_logger(__name__)


class NodeExecutor:
    """Executor for analysis tree nodes with comprehensive output management."""
    
    def __init__(self, executor_manager, cleanup_job_dirs: bool = False):
        """Initialize node executor.
        
        Args:
            executor_manager: Manager for executing function blocks
            cleanup_job_dirs: Whether to clean up job directories after successful execution
        """
        self.executor_manager = executor_manager
        self.cleanup_job_dirs = cleanup_job_dirs
    
    def execute_node(self, node: AnalysisNode, tree: AnalysisTree, 
                    input_path: Union[str, Path], 
                    output_base_dir: Path,
                    max_debug_attempts: int = 3) -> Tuple[NodeState, Optional[str], Optional['ExecutionResult']]:
        """
        Execute a single node in the analysis tree.
        
        Args:
            node: The node to execute
            tree: The analysis tree
            input_path: Path to input data
            output_base_dir: Base directory for outputs
            max_debug_attempts: Maximum debug attempts (not used in standard executor, for compatibility)
        
        Ensures all outputs are saved:
        - Job-level outputs in job directory
        - Node-level outputs in node directory
        - Follows new structure with nodes folder
        """
        logger.info(f"Executing node {node.id}: {node.function_block.name}")
        
        # Create directory structure following new specification
        tree_dir = output_base_dir / tree.id
        nodes_dir = tree_dir / "nodes"
        node_dir = nodes_dir / f"node_{node.id}"
        node_dir.mkdir(parents=True, exist_ok=True)
        
        # Create node subdirectories
        function_block_dir = node_dir / "function_block"
        jobs_dir = node_dir / "jobs"
        outputs_dir = node_dir / "outputs"
        agent_tasks_dir = node_dir / "agent_tasks"
        
        function_block_dir.mkdir(exist_ok=True)
        jobs_dir.mkdir(exist_ok=True)
        outputs_dir.mkdir(exist_ok=True)
        agent_tasks_dir.mkdir(exist_ok=True)
        
        # Save node info
        node_info = {
            "id": node.id,
            "name": node.function_block.name,
            "type": node.function_block.type.value if hasattr(node.function_block.type, 'value') else str(node.function_block.type),
            "parent_id": node.parent_id,
            "children_ids": node.children if hasattr(node, 'children') else [],
            "state": node.state.value if hasattr(node.state, 'value') else str(node.state),
            "created_at": datetime.now().isoformat(),
            "level": node.level,
            "debug_attempts": node.debug_attempts,
            "rework_attempts": getattr(node, 'rework_attempts', 0),
            "rework_of_node_id": getattr(node, 'rework_of_node_id', None),
            "rework_limit_reached": getattr(node, 'rework_limit_reached', False),
            "has_successful_rework": getattr(node, 'has_successful_rework', False)
        }
        with open(node_dir / "node_info.json", 'w') as f:
            json.dump(node_info, f, indent=2)
        
        # Save function block definition
        self._save_function_block(node.function_block, function_block_dir)
        
        # Create job directory in jobs folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_id = f"job_{timestamp}_{node.id[:8]}"
        job_dir = jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        # Create job subdirectories
        job_output_dir = job_dir / "output"
        job_figures_dir = job_output_dir / "figures"
        job_logs_dir = job_dir / "logs"
        
        job_output_dir.mkdir(exist_ok=True)
        job_figures_dir.mkdir(exist_ok=True)
        job_logs_dir.mkdir(exist_ok=True)
        
        try:
            # Determine the actual input path for this node
            if input_path is not None:
                actual_input_path = Path(input_path)
            else:
                actual_input_path = None
            
            # If this node has a parent, use the parent's outputs directory
            if node.parent_id:
                parent_node = tree.nodes.get(node.parent_id)
                if parent_node and parent_node.output_data_id:
                    # Use parent's outputs directory (which contains ALL output files)
                    parent_outputs = Path(parent_node.output_data_id)
                    if parent_outputs.exists():
                        actual_input_path = parent_outputs
                    else:
                        logger.warning(f"Parent outputs directory not found: {parent_outputs}")
            
            # NO MORE job_input_dir - pass paths directly to executor
            # The executor will stage files to its temp directory as needed
            
            # Write propagated failure context if available (save to job dir for reference)
            if hasattr(node, 'propagated_failure_context'):
                context_file = job_dir / "_node_failure_context.json"
                with open(context_file, 'w') as f:
                    json.dump(node.propagated_failure_context, f, indent=2)
                logger.info(f"Wrote propagated failure context to {context_file}")
            
            # Prepare metadata about previous nodes (no file copying)
            previous_nodes_metadata = None
            if node.parent_id:
                previous_nodes_metadata = self._prepare_previous_nodes_metadata(node, tree, job_dir, tree_dir)
            
            # Build execution context if using enhanced executor
            if hasattr(self, '_build_execution_context'):
                context = self._build_execution_context(node, tree, actual_input_path, output_base_dir)
            else:
                context = None
            
            # Pass actual input path directly - no staging
            execution_input_path = actual_input_path
            logger.info(f"Using parent output path directly: {actual_input_path}")
            
            # Use ExecutorManager to execute the function block
            # Pass the directory containing ALL parent outputs (or initial input file)
            result = self.executor_manager.execute(
                function_block=node.function_block,
                input_data_path=execution_input_path,
                output_dir=job_output_dir,
                parameters=node.function_block.parameters,
                previous_nodes_metadata=previous_nodes_metadata,
                propagated_failure_context=node.propagated_failure_context if hasattr(node, 'propagated_failure_context') else None
            )
            
            if result.success:
                # Save job-level outputs
                # Save stdout/stderr
                if result.stdout:
                    with open(job_logs_dir / "stdout.txt", 'w') as f:
                        f.write(result.stdout)
                if result.stderr:
                    with open(job_logs_dir / "stderr.txt", 'w') as f:
                        f.write(result.stderr)
                
                # Figures are already in job_output_dir/figures (job_figures_dir)
                # No need to copy to themselves
                
                # Save execution summary
                summary = {
                    "node_id": node.id,
                    "function_block": node.function_block.name,
                    "success": result.success,
                    "duration": result.duration,
                    "start_time": result.start_time.isoformat() if result.start_time else None,
                    "end_time": result.end_time.isoformat() if result.end_time else None,
                    "figures": result.figures,
                    "metadata": result.metadata
                }
                with open(job_dir / "execution_summary.json", 'w') as f:
                    json.dump(summary, f, indent=2)
                
                # Copy successful outputs to node outputs directory
                self._copy_to_node_outputs(job_output_dir, outputs_dir, job_figures_dir)
                
                # Create/update latest symlink in jobs directory
                latest_link = jobs_dir / "latest"
                if latest_link.exists():
                    latest_link.unlink()
                latest_link.symlink_to(job_id)
                
                # Update node state
                node.state = NodeState.COMPLETED
                node.output_data_id = str(job_output_dir)
                node.start_time = result.start_time
                node.end_time = result.end_time
                node.duration = result.duration
                
                # Store figures list
                node.figures = self._collect_figures(job_figures_dir, outputs_dir / "figures")
                
                logger.info(f"Node {node.id} completed successfully")
                logger.info(f"  Job outputs: {job_dir}")
                logger.info(f"  Node outputs: {outputs_dir}")
                logger.info(f"  Figures: {len(node.figures)}")
                
                # Clean up job directory if requested (outputs have been copied to node outputs)
                if self.cleanup_job_dirs:
                    try:
                        shutil.rmtree(job_dir)
                        logger.debug(f"Cleaned up job directory: {job_dir}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up job directory {job_dir}: {e}")
                
                # Return the node outputs directory instead of job output
                return NodeState.COMPLETED, str(outputs_dir), result
            else:
                # Save error information
                error_info = {
                    "node_id": node.id,
                    "error": result.error,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                    "debug_attempts": node.debug_attempts
                }
                with open(job_logs_dir / "error.json", 'w') as f:
                    json.dump(error_info, f, indent=2)
                
                # Save stdout even on failure - this is critical for debugging
                if result.stdout:
                    with open(job_logs_dir / "stdout.txt", 'w') as f:
                        f.write(result.stdout)
                
                if result.stderr:
                    with open(job_logs_dir / "stderr.txt", 'w') as f:
                        f.write(result.stderr)
                
                # Save logs which may contain execution.log
                if result.logs:
                    with open(job_logs_dir / "full_logs.txt", 'w') as f:
                        f.write(result.logs)
                
                node.state = NodeState.FAILED
                node.error = result.error
                logger.error(f"Node {node.id} failed: {result.error}")
                return NodeState.FAILED, None, result
                    
        except Exception as e:
            logger.error(f"Error executing node {node.id}: {str(e)}")
            
            # Save exception info
            error_file = job_logs_dir / "exception.txt"
            with open(error_file, 'w') as f:
                f.write(f"Exception: {str(e)}\n")
                import traceback
                f.write(traceback.format_exc())
            
            node.state = NodeState.FAILED
            node.error = str(e)
            return NodeState.FAILED, None, None
    
    def _save_job_outputs(self, result: NodeExecutionResult, job_dir: Path, 
                         logs_dir: Path, figures_dir: Path):
        """Save all job outputs."""
        # Save stdout/stderr
        if result.stdout:
            with open(logs_dir / "stdout.txt", 'w') as f:
                f.write(result.stdout)
        
        if result.stderr:
            with open(logs_dir / "stderr.txt", 'w') as f:
                f.write(result.stderr)
        
        # Save metadata
        if result.metadata:
            with open(job_dir / "metadata.json", 'w') as f:
                json.dump(result.metadata, f, indent=2, default=str)
        
        # Copy figures if they exist in output/figures
        output_figures = job_dir / "output" / "figures"
        if output_figures.exists():
            for fig in output_figures.glob("*"):
                if fig.is_file():
                    shutil.copy2(fig, figures_dir / fig.name)
        
        # Save execution summary
        summary = {
            "node_id": result.node_id,
            "state": result.state.value if hasattr(result.state, 'value') else str(result.state),
            "start_time": str(result.start_time),
            "end_time": str(result.end_time),
            "duration": result.duration,
            "output_files": len(result.output_files),
            "figures": len(result.figures),
            "has_metadata": bool(result.metadata)
        }
        
        with open(job_dir / "execution_summary.json", 'w') as f:
            json.dump(summary, f, indent=2)
    
    def _save_function_block(self, function_block, function_block_dir: Path):
        """Save function block definition to directory."""
        # Save code
        if hasattr(function_block, 'code'):
            with open(function_block_dir / "code.py", 'w') as f:
                f.write(function_block.code)
        
        # Save config
        config = {
            "name": function_block.name,
            "type": function_block.type.value if hasattr(function_block.type, 'value') else str(function_block.type),
            "description": function_block.description,
            "parameters": function_block.parameters
        }
        
        if hasattr(function_block, 'static_config'):
            config['static_config'] = {
                "description": function_block.static_config.description,
                "tag": function_block.static_config.tag,
                "args": [
                    {
                        "name": arg.name,
                        "value_type": arg.value_type,
                        "description": arg.description,
                        "optional": arg.optional,
                        "default_value": arg.default_value
                    }
                    for arg in function_block.static_config.args
                ]
            }
        
        with open(function_block_dir / "config.json", 'w') as f:
            json.dump(config, f, indent=2)
        
        # Save requirements
        if hasattr(function_block, 'requirements'):
            with open(function_block_dir / "requirements.txt", 'w') as f:
                f.write(function_block.requirements)
    
    def _copy_to_node_outputs(self, job_output_dir: Path, outputs_dir: Path, job_figures_dir: Path):
        """Copy successful job outputs to node outputs directory."""
        # Copy output data files and directories
        if job_output_dir.exists():
            for item in job_output_dir.glob("*"):
                if item.is_file():
                    shutil.copy2(item, outputs_dir / item.name)
                elif item.is_dir() and item.name != "figures":
                    # Copy entire directories (important for nested data structures like GEARS)
                    shutil.copytree(item, outputs_dir / item.name, dirs_exist_ok=True)
        
        # Create figures subdirectory in outputs
        outputs_figures_dir = outputs_dir / "figures"
        outputs_figures_dir.mkdir(exist_ok=True)
        
        # Copy figures from job output
        if job_figures_dir.exists():
            for fig in job_figures_dir.glob("*.png"):
                shutil.copy2(fig, outputs_figures_dir / fig.name)
    
    def _collect_figures(self, job_figures_dir: Path, outputs_figures_dir: Path) -> List[str]:
        """Collect all figure paths."""
        figures = []
        
        # Collect from job directory
        if job_figures_dir.exists():
            for fig in job_figures_dir.glob("*.png"):
                figures.append(str(fig))
        
        # Also check outputs directory
        if outputs_figures_dir.exists():
            for fig in outputs_figures_dir.glob("*.png"):
                fig_str = str(fig)
                if fig_str not in figures:
                    figures.append(fig_str)
        
        return figures
    
    def _save_error_info(self, response: ExecutionResponse, logs_dir: Path):
        """Save error information from failed execution."""
        if response.error:
            with open(logs_dir / "error.txt", 'w') as f:
                f.write(response.error)
        
        if response.job_info:
            info = response.job_info
            if info.stdout_path and Path(info.stdout_path).exists():
                shutil.copy2(info.stdout_path, logs_dir / "stdout.txt")
            if info.stderr_path and Path(info.stderr_path).exists():
                shutil.copy2(info.stderr_path, logs_dir / "stderr.txt")
    
    def _save_legacy_outputs(self, result: Dict, job_dir: Path, logs_dir: Path):
        """Save outputs from legacy executor."""
        if 'stdout' in result:
            with open(logs_dir / "stdout.txt", 'w') as f:
                f.write(result['stdout'])
        
        if 'stderr' in result:
            with open(logs_dir / "stderr.txt", 'w') as f:
                f.write(result['stderr'])
        
        if 'output_data' in result:
            with open(job_dir / "output_data.json", 'w') as f:
                json.dump(result['output_data'], f, indent=2)
    
    def _save_legacy_error(self, result: Dict, logs_dir: Path):
        """Save error from legacy executor."""
        with open(logs_dir / "error.txt", 'w') as f:
            f.write(result.get('error', 'Unknown error'))
        
        if 'stdout' in result:
            with open(logs_dir / "stdout.txt", 'w') as f:
                f.write(result['stdout'])
        
        if 'stderr' in result:
            with open(logs_dir / "stderr.txt", 'w') as f:
                f.write(result['stderr'])
    
    def _build_execution_context(self, node: AnalysisNode, tree: AnalysisTree,
                                input_path: Union[str, Path], 
                                output_base_dir: Path) -> ExecutionContext:
        """Build execution context for a node."""
        # Determine input files
        input_files = []
        available_files = []
        
        if node.parent_id:
            # Get outputs from parent node
            parent_node = tree.get_node_by_id(node.parent_id)
            if parent_node and parent_node.output_data_id:
                parent_output = Path(parent_node.output_data_id)
                if parent_output.exists():
                    # Look for h5ad files
                    for h5ad in parent_output.glob("*.h5ad"):
                        input_files.append(FileInfo(
                            filename=h5ad.name,
                            filepath=str(h5ad),
                            filetype=FileType.ANNDATA,
                            created_by_node=parent_node.id
                        ))
                    
                    # Look for other files
                    for file in parent_output.glob("*"):
                        if file.is_file() and not file.suffix == ".h5ad":
                            input_files.append(FileInfo(
                                filename=file.name,
                                filepath=str(file),
                                filetype=self._determine_file_type(file),
                                created_by_node=parent_node.id
                            ))
        else:
            # Root node - use initial input
            input_path = Path(input_path)
            if input_path.is_file():
                input_files.append(FileInfo(
                    filename=input_path.name,
                    filepath=str(input_path),
                    filetype=self._determine_file_type(input_path),
                    description="Initial input file"
                ))
            elif input_path.is_dir():
                for file in input_path.glob("*"):
                    if file.is_file():
                        input_files.append(FileInfo(
                            filename=file.name,
                            filepath=str(file),
                            filetype=self._determine_file_type(file),
                            description="Initial input file"
                        ))
        
        # Collect available files from all completed nodes
        for node_id, other_node in tree.nodes.items():
            if other_node.state == NodeState.COMPLETED and node_id != node.id:
                if other_node.output_data_id:
                    output_path = Path(other_node.output_data_id)
                    if output_path.exists():
                        for file in output_path.glob("*"):
                            if file.is_file():
                                available_files.append(FileInfo(
                                    filename=file.name,
                                    filepath=str(file),
                                    filetype=self._determine_file_type(file),
                                    created_by_node=node_id
                                ))
        
        # Build context with new structure
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_id = f"job_{timestamp}_{node.id[:8]}"
        
        tree_dir = output_base_dir / tree.id
        node_dir = tree_dir / "nodes" / f"node_{node.id}"
        job_dir = node_dir / "jobs" / job_id
        
        context = ExecutionContext(
            node_id=node.id,
            tree_id=tree.id,
            input_files=input_files,
            available_files=available_files,
            input_dir=str(job_dir / "input"),
            output_dir=str(job_dir / "output"),
            figures_dir=str(job_dir / "output" / "figures"),
            tree_metadata={
                "user_request": tree.user_request,
                "total_nodes": tree.total_nodes,
                "completed_nodes": tree.completed_nodes
            },
            previous_results=self._get_previous_results(node, tree)
        )
        
        return context
    
    def _determine_file_type(self, file_path: Path) -> FileType:
        """Determine file type from path."""
        suffix = file_path.suffix.lower()
        type_mapping = {
            '.h5ad': FileType.ANNDATA,
            '.csv': FileType.CSV,
            '.tsv': FileType.TSV,
            '.json': FileType.JSON,
            '.parquet': FileType.PARQUET,
            '.h5': FileType.H5,
            '.zarr': FileType.ZARR,
            '.png': FileType.IMAGE,
            '.jpg': FileType.IMAGE,
            '.jpeg': FileType.IMAGE,
            '.pdf': FileType.PDF,
            '.txt': FileType.TEXT
        }
        return type_mapping.get(suffix, FileType.OTHER)
    
    def _get_previous_results(self, node: AnalysisNode, tree: AnalysisTree) -> List[Dict]:
        """Get results from previous nodes for context."""
        results = []
        
        # Get ancestry path
        ancestry = tree.get_ancestry_path(node.id)
        
        for node_id in ancestry[:-1]:  # Exclude current node
            prev_node = tree.get_node_by_id(node_id)
            if prev_node and prev_node.state == NodeState.COMPLETED:
                result_summary = {
                    "node_id": node_id,
                    "node_name": prev_node.function_block.name,
                    "output_data_id": prev_node.output_data_id,
                    "duration": prev_node.duration,
                    "figures_count": len(prev_node.figures) if prev_node.figures else 0
                }
                results.append(result_summary)
        
        return results
    
    def _prepare_previous_nodes_metadata(self, node: AnalysisNode, tree: AnalysisTree, 
                                         job_dir: Path, tree_dir: Path) -> Dict[str, Any]:
        """Prepare metadata about previous nodes files (no copying)."""
        logger.info("Preparing previous nodes metadata")
        
        # Create metadata structure
        metadata = {}
        
        # No staging needed - just collect metadata
        
        # Create node file accessor
        accessor = NodeFileAccessor(tree, tree_dir)
        index_map = accessor.get_node_index_map(node.id)
        
        # Build metadata for each previous node
        for idx, info in index_map.items():
            node_metadata = {
                'node_id': info['node_id'],
                'node_name': info.get('node_name', f'node_{idx}'),
                'files': []  # Will contain actual file paths
            }
                
            # Collect output files metadata
            source_outputs_dir = tree_dir / "nodes" / f"node_{info['node_id']}" / "outputs"
            if source_outputs_dir.exists():
                for output_file in source_outputs_dir.glob("*"):
                    if output_file.is_file():
                        node_metadata['files'].append({
                            'type': 'output',
                            'name': output_file.name,
                            'path': str(output_file.resolve()),  # Absolute path
                            'relative': f"outputs/{output_file.name}"
                        })
                        logger.debug(f"Found output file: {output_file.name} from node {idx}")
            
            # Optionally collect input files metadata (if needed for debugging)
            # Skip for now as outputs are usually sufficient
            
            metadata[str(idx)] = node_metadata
        
        # Save metadata to job directory for reference
        metadata_file = job_dir / "previous_nodes_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        logger.info(f"Saved previous nodes metadata for {len(metadata)} nodes")
        
        return metadata