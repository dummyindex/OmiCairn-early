"""Interactive node executor with in-container debugging support."""

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
from utils import setup_logger
from utils.node_file_access import NodeFileAccessor, FUNCTION_BLOCK_RUNTIME_CODE
from utils.file_staging_interface import get_default_file_stager
from job_executors.interactive_executor import InteractiveExecutor

logger = setup_logger(__name__)


class InteractiveNodeExecutor:
    """Node executor with in-container debugging capabilities."""
    
    def __init__(self, executor_manager, bug_fixer=None, enable_interactive_debug=True, output_collector_llm=None, cleanup_job_dirs: bool = True, docker_execution_timeout: Optional[int] = None):
        """Initialize interactive node executor.
        
        Args:
            executor_manager: Manager for executors
            bug_fixer: Optional bug fixer agent
            enable_interactive_debug: Whether to use interactive debugging
            output_collector_llm: Optional LLM service for output collector
            cleanup_job_dirs: Whether to clean up job directories after successful execution
            docker_execution_timeout: Docker execution timeout in seconds (default: 30 minutes)
        """
        self.executor_manager = executor_manager
        self.bug_fixer = bug_fixer
        self.enable_interactive_debug = enable_interactive_debug
        self.output_collector_llm = output_collector_llm
        self.cleanup_job_dirs = cleanup_job_dirs
        self.docker_execution_timeout = docker_execution_timeout
        
        # Create interactive executor if enabled
        if enable_interactive_debug and bug_fixer:
            self.interactive_executor = InteractiveExecutor(
                docker_manager=executor_manager.docker_manager,
                bug_fixer=bug_fixer,
                output_collector=output_collector_llm,
                llm_service=output_collector_llm,  # Pass LLM service for code checker
                docker_execution_timeout=docker_execution_timeout
            )
        else:
            self.interactive_executor = None
    
    def update_bug_fixer(self, bug_fixer):
        """Update the bug fixer and create interactive executor if needed."""
        self.bug_fixer = bug_fixer
        
        # Create interactive executor if it wasn't created before
        if self.enable_interactive_debug and bug_fixer and not self.interactive_executor:
            self.interactive_executor = InteractiveExecutor(
                docker_manager=self.executor_manager.docker_manager,
                bug_fixer=bug_fixer,
                output_collector=self.output_collector_llm,
                llm_service=self.output_collector_llm,  # Pass LLM service for code checker
                docker_execution_timeout=self.docker_execution_timeout
            )
            logger.info("Created interactive executor after bug fixer update")
    
    def execute_node(
        self, 
        node: AnalysisNode, 
        tree: AnalysisTree, 
        input_path: Union[str, Path], 
        output_base_dir: Path,
        max_debug_attempts: int = 3
    ) -> Tuple[NodeState, Optional[str], Optional[ExecutionResult]]:
        """Execute a node with optional in-container debugging.
        
        If interactive debugging is enabled and a bug fixer is available,
        execution failures will trigger in-container debugging sessions.
        """
        logger.info(f"Executing node {node.id}: {node.function_block.name}")
        
        # Create directory structure
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
            "interactive_debug_enabled": self.enable_interactive_debug and self.interactive_executor is not None,
            "rework_attempts": getattr(node, 'rework_attempts', 0),
            "rework_of_node_id": getattr(node, 'rework_of_node_id', None),
            "rework_limit_reached": getattr(node, 'rework_limit_reached', False),
            "has_successful_rework": getattr(node, 'has_successful_rework', False)
        }
        with open(node_dir / "node_info.json", 'w') as f:
            json.dump(node_info, f, indent=2)
        
        # Save function block definition
        self._save_function_block(node.function_block, function_block_dir)
        
        # Create job directory
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
            # Determine input path
            actual_input_path = Path(input_path)
            
            if node.parent_id:
                parent_node = tree.nodes.get(node.parent_id)
                if parent_node and parent_node.output_data_id:
                    parent_outputs = Path(parent_node.output_data_id)
                    if parent_outputs.exists():
                        actual_input_path = parent_outputs
                    else:
                        logger.warning(f"Parent outputs directory not found: {parent_outputs}")
            
            # Ensure job input directory exists
            job_input_dir = job_dir / "input"
            job_input_dir.mkdir(exist_ok=True)
            
            # Write propagated failure context if available
            if hasattr(node, 'propagated_failure_context'):
                context_file = job_input_dir / "_node_failure_context.json"
                with open(context_file, 'w') as f:
                    json.dump(node.propagated_failure_context, f, indent=2)
                logger.info(f"Wrote propagated failure context to {context_file}")
            
            # Copy parent's output files to job input directory
            if actual_input_path.exists():
                if actual_input_path.is_file():
                    # Single file - copy it
                    shutil.copy2(actual_input_path, job_input_dir / actual_input_path.name)
                    logger.info(f"Copied input file: {actual_input_path.name}")
                elif actual_input_path.is_dir():
                    # Directory - copy all files
                    for item in actual_input_path.glob("*"):
                        if item.is_file():
                            shutil.copy2(item, job_input_dir / item.name)
                        elif item.is_dir() and item.name != "previous_nodes":
                            shutil.copytree(item, job_input_dir / item.name, dirs_exist_ok=True)
                    logger.info(f"Copied input files from: {actual_input_path}")
            
            # Pre-stage previous nodes files if needed
            self._pre_stage_previous_nodes_files(node, tree, job_dir, tree_dir)
            
            # Always use job input directory for execution (it has everything)
            execution_input_path = job_input_dir
            logger.info(f"Using job input directory: {job_input_dir}")
            
            # Execute with interactive debugging if enabled
            if self.interactive_executor:
                logger.info("Using interactive executor with in-container debugging")
                
                # Set tree context for previous nodes access
                self.interactive_executor.set_tree_context(
                    tree=tree,
                    tree_dir=tree_dir,
                    current_node_id=node.id
                )
                
                # Define debug callback
                def debug_callback(message):
                    # Log debug progress to bug_fixer subdirectory
                    bug_fixer_dir = agent_tasks_dir / "bug_fixer"
                    bug_fixer_dir.mkdir(exist_ok=True)
                    debug_log = bug_fixer_dir / "debug_progress.txt"
                    with open(debug_log, 'a') as f:
                        f.write(f"[{datetime.now().isoformat()}] {message}\n")
                
                # Execute with debugging
                result = self.interactive_executor.execute_with_debugging(
                    function_block=node.function_block,
                    input_data_path=execution_input_path,
                    output_dir=job_output_dir,
                    parameters=node.function_block.parameters,
                    max_debug_attempts=max_debug_attempts - node.debug_attempts,
                    debug_callback=debug_callback,
                    node_dir=node_dir
                )
                
                # Update debug attempts from metadata
                if hasattr(result, 'metadata') and 'debug_attempts' in result.metadata:
                    node.debug_attempts += result.metadata['debug_attempts']
                
                # CRITICAL FIX: Update function block code after successful bug fixes
                # This ensures job reviewer sees the corrected code, not the original
                if result.success:
                    logger.info("Updating function block code after successful debugging")
                    self._update_function_block_from_filesystem(node, function_block_dir)
                
            else:
                # Use standard execution
                logger.info("Using standard executor (no interactive debugging)")
                result = self.executor_manager.execute(
                    function_block=node.function_block,
                    input_data_path=execution_input_path,
                    output_dir=job_output_dir,
                    parameters=node.function_block.parameters
                )
            
            # Process results (same as original node executor)
            if result.success:
                # Save logs
                if result.stdout:
                    with open(job_logs_dir / "stdout.txt", 'w') as f:
                        f.write(result.stdout)
                if result.stderr:
                    with open(job_logs_dir / "stderr.txt", 'w') as f:
                        f.write(result.stderr)
                
                # Save execution summary
                summary = {
                    "node_id": node.id,
                    "function_block": node.function_block.name,
                    "success": result.success,
                    "duration": result.duration,
                    "start_time": result.start_time.isoformat() if result.start_time else None,
                    "end_time": result.end_time.isoformat() if result.end_time else None,
                    "figures": result.figures if hasattr(result, 'figures') else [],
                    "metadata": result.metadata if hasattr(result, 'metadata') else {},
                    "debug_attempts": node.debug_attempts,
                    "interactive_debug_used": self.interactive_executor is not None
                }
                with open(job_dir / "execution_summary.json", 'w') as f:
                    json.dump(summary, f, indent=2)
                
                # Copy outputs to node directory
                self._copy_to_node_outputs(job_output_dir, outputs_dir, job_figures_dir)
                
                # Create latest symlink
                latest_link = jobs_dir / "latest"
                if latest_link.exists():
                    latest_link.unlink()
                latest_link.symlink_to(job_id)
                
                # Update node metadata
                node.output_data_id = str(outputs_dir)  # Use node outputs dir
                node.start_time = result.start_time
                node.end_time = result.end_time
                node.duration = result.duration
                
                # Update node state through tree (this updates both state and statistics)
                if hasattr(tree, 'update_node_state'):
                    tree.update_node_state(node.id, NodeState.COMPLETED)
                else:
                    # Fallback if tree not available
                    node.state = NodeState.COMPLETED
                
                # Collect figures
                node.figures = self._collect_figures(job_figures_dir, outputs_dir / "figures")
                
                # Generate comprehensive execution metadata
                self._save_execution_metadata(node, node_dir, outputs_dir, job_dir, tree)
                
                logger.info(f"Node {node.id} completed successfully")
                if hasattr(result, 'debug_attempts') and result.debug_attempts > 0:
                    logger.info(f"  Succeeded after {result.debug_attempts} debug attempts")
                logger.info(f"  Job outputs: {job_dir}")
                logger.info(f"  Node outputs: {outputs_dir}")
                logger.info(f"  Figures: {len(node.figures)}")
                
                # Set final state and output for return
                final_state = NodeState.COMPLETED
                final_output = str(outputs_dir)
                
            else:
                # Save error information
                error_info = {
                    "node_id": node.id,
                    "error": result.error,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code if hasattr(result, 'exit_code') else -1,
                    "debug_attempts": node.debug_attempts,
                    "interactive_debug_enabled": self.interactive_executor is not None
                }
                with open(job_logs_dir / "error.json", 'w') as f:
                    json.dump(error_info, f, indent=2)
                
                # Save logs even on failure
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
                
                # Update node metadata
                node.error = result.error
                logger.error(f"Node {node.id} failed: {result.error}")
                
                # Update node state through tree (this updates both state and statistics)
                if hasattr(tree, 'update_node_state'):
                    tree.update_node_state(node.id, NodeState.FAILED)
                else:
                    # Fallback if tree not available
                    node.state = NodeState.FAILED
                
                # Set final state and error for return
                final_state = NodeState.FAILED
                final_output = result.error
            
            # ALWAYS clean up job input directory regardless of success/failure
            # This is done after processing results but before returning
            if self.cleanup_job_dirs:
                try:
                    # Delete job input directory to save disk space
                    # This includes previous_nodes which can be very large
                    job_input_dir = job_dir / "input"
                    if job_input_dir.exists():
                        import os
                        # Calculate size before deletion for logging
                        size = sum(os.path.getsize(os.path.join(dirpath,filename)) 
                                 for dirpath, _, filenames in os.walk(job_input_dir) 
                                 for filename in filenames)
                        
                        # Delete the input directory
                        shutil.rmtree(job_input_dir)
                        status = "successful" if final_state == NodeState.COMPLETED else "failed"
                        logger.info(f"Cleaned up job input directory after {status} execution, freed {size/(1024*1024):.1f}MB: {job_input_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up job input directory: {e}")
            
            return final_state, final_output, result
                
        except Exception as e:
            logger.error(f"Error executing node {node.id}: {e}")
            import traceback
            error_details = traceback.format_exc()
            
            # Save exception details
            error_info = {
                "node_id": node.id,
                "error": str(e),
                "traceback": error_details,
                "timestamp": datetime.now().isoformat()
            }
            with open(job_logs_dir / "exception.json", 'w') as f:
                json.dump(error_info, f, indent=2)
            
            # Update node metadata
            node.error = str(e)
            
            # Update node state through tree (this updates both state and statistics)
            if hasattr(tree, 'update_node_state'):
                tree.update_node_state(node.id, NodeState.FAILED)
            else:
                # Fallback if tree not available
                node.state = NodeState.FAILED
            
            # Clean up job input directory even after exceptions
            if self.cleanup_job_dirs:
                try:
                    job_input_dir = job_dir / "input"
                    if job_input_dir.exists():
                        import os
                        size = sum(os.path.getsize(os.path.join(dirpath,filename)) 
                                 for dirpath, _, filenames in os.walk(job_input_dir) 
                                 for filename in filenames)
                        shutil.rmtree(job_input_dir)
                        logger.info(f"Cleaned up job input directory after exception, freed {size/(1024*1024):.1f}MB: {job_input_dir}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up job input directory after exception: {cleanup_error}")
            
            return NodeState.FAILED, str(e), None
    
    def _update_function_block_from_filesystem(self, node: AnalysisNode, function_block_dir: Path):
        """Update function block code from filesystem after successful bug fixes.
        
        This method reads the corrected code from the filesystem and updates
        the in-memory function block, ensuring the job reviewer sees the
        bug-fixed version rather than the original broken code.
        
        The bug fixer's CodeVersionManager already saves updated code to the
        function_block directory, so we just need to read it back.
        """
        try:
            function_block = node.function_block
            
            # Determine file extensions based on language type
            is_r = function_block.type == FunctionBlockType.R
            code_ext = '.R' if is_r else '.py'
            
            # The CodeVersionManager saves to both code.{ext} and function_block.{ext}
            # Try function_block.{ext} first for consistency
            function_block_file = function_block_dir / f"function_block{code_ext}"
            code_file = function_block_dir / f"code{code_ext}"
            
            updated_code = None
            code_source = None
            
            if function_block_file.exists():
                updated_code = function_block_file.read_text()
                code_source = function_block_file
            elif code_file.exists():
                updated_code = code_file.read_text()
                code_source = code_file
            else:
                logger.warning(f"No updated code files found in {function_block_dir}")
                return
            
            # Only update if code actually changed
            if updated_code and updated_code != function_block.code:
                logger.info(f"Updating in-memory function block code for '{function_block.name}'")
                logger.info(f"  Source: {code_source}")
                logger.info(f"  Original code length: {len(function_block.code)} chars")
                logger.info(f"  Updated code length: {len(updated_code)} chars")
                
                # Update the in-memory function block code
                function_block.code = updated_code
                
                # Also update requirements if they were modified
                requirements_file = function_block_dir / "requirements.txt"
                if requirements_file.exists():
                    requirements_text = requirements_file.read_text().strip()
                    if requirements_text and requirements_text != function_block.requirements:
                        logger.info(f"Updating function block requirements")
                        logger.info(f"  Original: {len(function_block.requirements.split())} lines")
                        logger.info(f"  Updated: {len(requirements_text.split())} lines")
                        function_block.requirements = requirements_text
                
                logger.info(f"✓ Successfully synchronized function block code after bug fixes")
            else:
                logger.info(f"Function block code unchanged after debugging")
                        
        except Exception as e:
            logger.error(f"Failed to update function block from filesystem: {e}", exc_info=True)
            # Non-fatal error - continue with original code
    
    def _save_function_block(self, function_block, function_block_dir: Path):
        """Save function block code and configuration."""
        # Save code
        if isinstance(function_block, NewFunctionBlock):
            # Determine file extensions based on language type
            is_r = function_block.type == FunctionBlockType.R
            code_ext = '.R' if is_r else '.py'
            
            # Save as both code.{ext} and function_block.{ext} for compatibility
            code_file = function_block_dir / f"code{code_ext}"
            with open(code_file, 'w') as f:
                f.write(function_block.code)
            
            function_block_file = function_block_dir / f"function_block{code_ext}"
            with open(function_block_file, 'w') as f:
                f.write(function_block.code)
            
            # Save dependencies - always use requirements.txt for both Python and R
            # The R executor reads from the requirements field in the function block
            deps_file = function_block_dir / "requirements.txt"
            with open(deps_file, 'w') as f:
                f.write(function_block.requirements)
        
        # Save config
        config_data = {
            "name": function_block.name,
            "type": function_block.type.value if hasattr(function_block.type, 'value') else str(function_block.type),
            "description": function_block.description,
            "parameters": function_block.parameters if hasattr(function_block, 'parameters') else {},
            "static_config": function_block.static_config.model_dump() if hasattr(function_block, 'static_config') and hasattr(function_block.static_config, 'model_dump') else {}
        }
        
        config_file = function_block_dir / "config.json"
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)
    
    def _copy_to_node_outputs(self, job_output_dir: Path, outputs_dir: Path, job_figures_dir: Path):
        """Copy job outputs to node outputs directory."""
        # Copy all files from job output to node output
        for item in job_output_dir.glob("*"):
            if item.is_file():
                shutil.copy2(item, outputs_dir / item.name)
            elif item.is_dir() and item.name != "figures":
                shutil.copytree(item, outputs_dir / item.name, dirs_exist_ok=True)
        
        # Handle figures specially
        if job_figures_dir.exists():
            figures_dir = outputs_dir / "figures"
            figures_dir.mkdir(exist_ok=True)
            for fig in job_figures_dir.glob("*"):
                if fig.is_file():
                    shutil.copy2(fig, figures_dir / fig.name)
    
    def _save_execution_metadata(self, node: AnalysisNode, node_dir: Path, outputs_dir: Path, 
                                 job_dir: Path, tree: Optional[AnalysisTree] = None) -> None:
        """Save comprehensive metadata about node execution including all input/output files.
        
        This metadata will be used by orchestrator and function creator to understand
        what files are available without needing to run inside the container.
        """
        try:
            # Collect output files and directories information
            output_files = []
            if outputs_dir.exists():
                for item in outputs_dir.iterdir():
                    if item.is_file():
                        file_info = {
                            "name": item.name,
                            "path": str(item.relative_to(node_dir)),
                            "size": item.stat().st_size,
                            "type": self._guess_file_type(item)
                        }
                        # Add data structure info for h5ad files
                        if item.suffix == '.h5ad' and item.name.startswith('_data_structure_'):
                            # Skip data structure files themselves
                            continue
                        elif item.suffix == '.h5ad':
                            # Look for corresponding data structure file
                            data_struct_file = outputs_dir / f"_data_structure_{item.stem}.json"
                            if data_struct_file.exists():
                                with open(data_struct_file) as f:
                                    file_info["data_structure"] = json.load(f)
                        output_files.append(file_info)
                    elif item.is_dir() and item.name != 'figures':  # Skip figures dir as it's handled separately
                        # Add directory information with recursive file listing
                        # Calculate total size of all files in directory
                        total_size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
                        dir_info = {
                            "name": item.name,
                            "path": str(item.relative_to(node_dir)),
                            "type": "directory",
                            "size": total_size,  # Total size of all files in directory
                            "contents": []
                        }
                        # Recursively list files in subdirectory (up to 3 levels deep)
                        for sub_item in item.rglob("*"):
                            if sub_item.is_file():
                                # Calculate relative path from the directory
                                rel_path = str(sub_item.relative_to(item))
                                # Only include files up to 3 levels deep to avoid huge metadata
                                if len(Path(rel_path).parts) <= 3:
                                    dir_info["contents"].append({
                                        "name": sub_item.name,
                                        "relative_path": rel_path,
                                        "size": sub_item.stat().st_size,
                                        "type": self._guess_file_type(sub_item)
                                    })
                        output_files.append(dir_info)
            
            # Collect figure files
            figure_files = []
            figures_dir = outputs_dir / "figures"
            if figures_dir.exists():
                for fig in figures_dir.iterdir():
                    if fig.is_file() and fig.suffix.lower() in ['.png', '.jpg', '.jpeg', '.svg', '.pdf']:
                        figure_files.append({
                            "name": fig.name,
                            "path": str(fig.relative_to(node_dir)),
                            "size": fig.stat().st_size,
                            "type": "figure"
                        })
            
            # Get information about inputs that were available
            input_info = {}
            if job_dir.exists():
                # Check if there was a previous_nodes directory staged
                exec_dir = job_dir / "execution"
                if exec_dir.exists():
                    input_dir = exec_dir / "input"
                    if input_dir.exists():
                        # Check for previous_nodes
                        prev_nodes_dir = input_dir / "previous_nodes"
                        if prev_nodes_dir.exists():
                            input_info["has_previous_nodes"] = True
                            input_info["previous_nodes_structure"] = self._get_previous_nodes_structure(prev_nodes_dir)
                        
                        # List direct input files
                        direct_inputs = []
                        for item in input_dir.iterdir():
                            if item.is_file():
                                direct_inputs.append({
                                    "name": item.name,
                                    "size": item.stat().st_size,
                                    "type": self._guess_file_type(item)
                                })
                        if direct_inputs:
                            input_info["direct_input_files"] = direct_inputs
            
            # Get node's accessible nodes information
            from utils.node_file_access import NodeFileAccessor
            # Derive tree_dir from node_dir (node_dir is tree_dir/nodes/node_xxx)
            tree_dir = node_dir.parent.parent if node_dir.parent.name == "nodes" else None
            accessor = NodeFileAccessor(tree, tree_dir) if tree and tree_dir else None
            accessible_nodes = {}
            if accessor:
                try:
                    node_map = accessor.get_node_index_map(node.id)
                    accessible_nodes = {
                        "count": len(node_map),
                        "nodes": node_map
                    }
                except:
                    pass
            
            # Create comprehensive metadata
            metadata = {
                "node_id": node.id,
                "node_name": node.function_block.name,
                "execution_time": datetime.now().isoformat(),
                "state": "completed",
                "output_files": output_files,
                "figure_files": figure_files,
                "input_info": input_info,
                "accessible_nodes": accessible_nodes,
                "function_block": {
                    "name": node.function_block.name,
                    "type": node.function_block.type.value if hasattr(node.function_block.type, 'value') else str(node.function_block.type),
                    "description": node.function_block.description
                }
            }
            
            # Save the metadata
            metadata_file = node_dir / "execution_metadata.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Saved execution metadata to {metadata_file}")
            
        except Exception as e:
            logger.warning(f"Failed to save execution metadata: {e}")
    
    def _guess_file_type(self, file_path: Path) -> str:
        """Guess file type based on extension."""
        ext = file_path.suffix.lower()
        if ext == '.h5ad':
            return 'anndata'
        elif ext in ['.csv', '.tsv']:
            return 'table'
        elif ext == '.json':
            return 'json'
        elif ext in ['.png', '.jpg', '.jpeg', '.svg', '.pdf']:
            return 'figure'
        elif ext == '.log':
            return 'log'
        elif ext in ['.txt', '.md']:
            return 'text'
        else:
            return 'unknown'
    
    def _get_previous_nodes_structure(self, prev_nodes_dir: Path) -> Dict[str, Any]:
        """Get the structure of previous_nodes directory."""
        structure = {}
        try:
            for node_dir in prev_nodes_dir.iterdir():
                if node_dir.is_dir() and node_dir.name.startswith('node_'):
                    node_idx = node_dir.name
                    node_info = {
                        "outputs": [],
                        "inputs": []
                    }
                    
                    # Check outputs
                    outputs_dir = node_dir / "outputs"
                    if outputs_dir.exists():
                        for f in outputs_dir.iterdir():
                            if f.is_file():
                                node_info["outputs"].append(f.name)
                    
                    # NOTE: We no longer check for inputs directory as part of disk optimization
                    # Only outputs are staged from previous nodes
                    
                    structure[node_idx] = node_info
        except Exception as e:
            logger.warning(f"Error reading previous_nodes structure: {e}")
        
        return structure
    
    def _collect_figures(self, job_figures_dir: Path, node_figures_dir: Path) -> List[str]:
        """Collect list of figure paths."""
        figures = []
        if node_figures_dir.exists():
            for fig in node_figures_dir.glob("*"):
                if fig.is_file() and fig.suffix.lower() in ['.png', '.jpg', '.jpeg', '.svg', '.pdf']:
                    figures.append(str(fig))
        return figures
    
    def _pre_stage_previous_nodes_files(self, node: AnalysisNode, tree: AnalysisTree, 
                                       job_dir: Path, tree_dir: Path):
        """Pre-stage files from previous nodes for container access."""
        # Create input directory
        job_input_dir = job_dir / "input"
        job_input_dir.mkdir(exist_ok=True)
        
        # Only pre-stage previous nodes if this node has ancestors
        if not node.parent_id:
            logger.info("No parent node - skipping previous nodes file staging")
            return
            
        logger.info("Pre-staging previous nodes files for container access")
        
        # Create previous_nodes directory
        prev_nodes_dir = job_input_dir / "previous_nodes"
        prev_nodes_dir.mkdir(exist_ok=True)
        
        # Get file stager (modular interface for future changes)
        file_stager = get_default_file_stager()
        
        # Create node file accessor
        accessor = NodeFileAccessor(tree, tree_dir)
        index_map = accessor.get_node_index_map(node.id)
        
        # Save index map for runtime
        index_file = job_input_dir / "previous_nodes_index.json"
        with open(index_file, 'w') as f:
            # Add available files info to index map
            for idx, info in index_map.items():
                info['available_files'] = []
                
                # Create node-specific directory (only outputs, no inputs for disk efficiency)
                node_dir = prev_nodes_dir / f"node_{idx}"
                node_outputs_dir = node_dir / "outputs"
                node_outputs_dir.mkdir(parents=True, exist_ok=True)
                
                # OPTIMIZATION: Only pre-stage OUTPUT files from previous nodes
                # We don't need to copy inputs - this prevents exponential disk growth
                source_outputs_dir = tree_dir / "nodes" / f"node_{info['node_id']}" / "outputs"
                if source_outputs_dir.exists():
                    for output_file in source_outputs_dir.glob("*"):
                        if output_file.is_file():
                            # Stage to node-specific outputs directory
                            staged_path = node_outputs_dir / output_file.name
                            
                            if file_stager.stage_file(output_file, staged_path):
                                info['available_files'].append({
                                    'original': f"outputs/{output_file.name}",
                                    'staged': f"node_{idx}/outputs/{output_file.name}",
                                    'path': f"previous_nodes/node_{idx}/outputs/{output_file.name}"
                                })
                                logger.info(f"Pre-staged outputs/{output_file.name} from node {idx}")
                
                # NOTE: We intentionally DO NOT stage input files from previous nodes
                # This optimization prevents disk usage from growing exponentially
                # Function blocks only need outputs from previous computations, not their inputs
            json.dump(index_map, f, indent=2)
        
        # Copy runtime interface to the current job's input directory
        current_job_input_dir = job_dir / "input"
        runtime_file = current_job_input_dir / "function_block_runtime.py"
        runtime_file.write_text(FUNCTION_BLOCK_RUNTIME_CODE)
        logger.info(f"Created runtime interface at {runtime_file}")
        
        logger.info(f"Pre-staged {len(index_map)} previous nodes with files")