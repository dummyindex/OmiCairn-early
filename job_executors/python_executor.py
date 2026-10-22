"""Python function block executor."""

from pathlib import Path
from typing import Dict, Any, List, Optional
import shutil
import json

from .base_executor import BaseExecutor
from models import BaseFunctionBlock, FunctionBlockType, NewFunctionBlock
from utils.logger import get_logger
from utils.node_file_access import FUNCTION_BLOCK_RUNTIME_CODE
from config import config

logger = get_logger(__name__)


class PythonExecutor(BaseExecutor):
    """Executor for Python function blocks."""
    
    @property
    def block_type(self) -> FunctionBlockType:
        return FunctionBlockType.PYTHON
    
    @property
    def docker_image(self) -> str:
        return config.python_image
    
    def prepare_execution_dir(
        self, 
        execution_dir: Path,
        function_block: BaseFunctionBlock,
        input_data_path: Path,
        parameters: Dict[str, Any],
        previous_nodes_metadata: Optional[Dict[str, Any]] = None,
        propagated_failure_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Prepare execution directory for Python function block."""
        
        # Create directory structure
        (execution_dir / "input").mkdir(exist_ok=True)
        (execution_dir / "output").mkdir(exist_ok=True)
        (execution_dir / "output" / "figures").mkdir(exist_ok=True)
        
        # Copy ALL files from parent's outputs folder to child's input folder
        input_path = Path(input_data_path)
        if input_path.exists():
            if input_path.is_dir():
                # If input_data_path is a directory (parent's outputs folder), copy ALL files
                for item in input_path.glob("*"):
                    if item.is_file():
                        # Copy with original name to maintain consistency
                        shutil.copy2(item, execution_dir / "input" / item.name)
                    elif item.is_dir():
                        # Copy entire subdirectory including previous_nodes
                        shutil.copytree(item, execution_dir / "input" / item.name, dirs_exist_ok=True)
            else:
                # If it's a single file, copy with its original name
                shutil.copy2(input_path, execution_dir / "input" / input_path.name)
        
        # Handle previous nodes metadata if provided
        if previous_nodes_metadata:
            self._stage_previous_nodes_files(execution_dir / "input", previous_nodes_metadata)
        
        # Write propagated failure context if provided
        if propagated_failure_context:
            with open(execution_dir / "input" / "_node_failure_context.json", 'w') as f:
                json.dump(propagated_failure_context, f, indent=2)
        
        # Write parameters
        self.write_parameters(execution_dir / "parameters.json", parameters)
        
        # Write function block code
        if isinstance(function_block, NewFunctionBlock):
            # Write the function block code
            with open(execution_dir / "function_block.py", "w") as f:
                f.write(function_block.code)
            
            # Write requirements
            with open(execution_dir / "requirements.txt", "w") as f:
                f.write(function_block.requirements)
        else:
            # For existing function blocks, we would fetch from storage
            # For now, raise an error as we don't have function block storage yet
            raise NotImplementedError("Existing function block execution not yet implemented")
        
        # Write the execution wrapper
        wrapper_code = self._generate_wrapper_code()
        with open(execution_dir / "run.py", "w") as f:
            f.write(wrapper_code)
    
    def get_execution_command(self) -> List[str]:
        """Get Python execution command."""
        return [
            "bash", "-c",
            "cd /workspace && " +
            "pip install -r requirements.txt && " +
            "python run.py"
        ]
    
    def _stage_previous_nodes_files(self, input_dir: Path, previous_nodes_metadata: Dict[str, Any]) -> None:
        """Stage files from previous nodes based on metadata."""
        prev_nodes_dir = input_dir / "previous_nodes"
        prev_nodes_dir.mkdir(exist_ok=True)
        
        # Process each previous node
        for idx, node_info in previous_nodes_metadata.items():
            node_dir = prev_nodes_dir / f"node_{idx}"
            node_outputs_dir = node_dir / "outputs"
            node_outputs_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy output files from their actual locations
            for file_info in node_info.get('files', []):
                if file_info['type'] == 'output':
                    source_path = Path(file_info['path'])
                    if source_path.exists():
                        dest_path = node_outputs_dir / file_info['name']
                        shutil.copy2(source_path, dest_path)
                        logger.debug(f"Staged {file_info['name']} from node {idx}")
        
        # Write the metadata index for the runtime
        index_file = input_dir / "previous_nodes_index.json"
        with open(index_file, 'w') as f:
            json.dump(previous_nodes_metadata, f, indent=2)
        
        # Write the runtime interface
        runtime_file = input_dir / "function_block_runtime.py"
        runtime_file.write_text(FUNCTION_BLOCK_RUNTIME_CODE)
        logger.info(f"Staged previous nodes files for {len(previous_nodes_metadata)} nodes")
    
    def _generate_wrapper_code(self) -> str:
        """Generate wrapper code for function block execution."""
        return '''#!/usr/bin/env python3
"""Wrapper script for function block execution."""

import os
import sys
import json
import logging
import traceback
import subprocess
from pathlib import Path

# Ensure output directory exists before setting up logging
Path('/workspace/output').mkdir(parents=True, exist_ok=True)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/workspace/output/execution.log')
    ]
)
logger = logging.getLogger('function_block_wrapper')

def export_conda_environment():
    """Export the current conda environment to yaml file."""
    try:
        logger.info("Exporting conda environment...")
        # Export full environment with versions
        result = subprocess.run(
            ["conda", "env", "export", "--no-builds"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            with open('/workspace/output/conda_environment.yml', 'w') as f:
                f.write(result.stdout)
            logger.info("✓ Exported conda environment to conda_environment.yml")
            
            # Also export just the packages that were explicitly installed
            result2 = subprocess.run(
                ["conda", "env", "export", "--from-history"],
                capture_output=True,
                text=True
            )
            if result2.returncode == 0:
                with open('/workspace/output/conda_environment_history.yml', 'w') as f:
                    f.write(result2.stdout)
                    
            # Export pip freeze for reference
            result3 = subprocess.run(
                [sys.executable, "-m", "pip", "freeze"],
                capture_output=True,
                text=True
            )
            if result3.returncode == 0:
                with open('/workspace/output/pip_freeze.txt', 'w') as f:
                    f.write(result3.stdout)
                logger.info("✓ Exported pip freeze to pip_freeze.txt")
        else:
            logger.warning(f"Could not export conda environment: {result.stderr}")
    except Exception as e:
        logger.warning(f"Failed to export conda environment: {e}")

def main():
    """Main execution function."""
    try:
        logger.info("Starting function block execution")
        
        # Load parameters
        with open('/workspace/parameters.json') as f:
            params = json.load(f)
        logger.info(f"Loaded parameters: {params}")
        
        # Create path dictionary with only directories
        path_dict = {
            "input_dir": "/workspace/input",
            "output_dir": "/workspace/output"
        }
        
        logger.info(f"Path dictionary: {path_dict}")
        logger.info(f"Parameters: {params}")
        
        # Import and run function block with path_dict and params
        logger.info("Importing function block")
        
        # Force reload in case the module was modified by bug fixer
        import sys
        if 'function_block' in sys.modules:
            del sys.modules['function_block']
        
        # Add input directory to Python path for runtime modules
        sys.path.insert(0, '/workspace/input')
            
        from function_block import run
        
        logger.info("Executing function block with path_dict and params")
        run(path_dict, params)  # Pass both path_dict and params
        
        # Check for any output files
        import glob
        output_files = glob.glob(os.path.join(path_dict["output_dir"], "*"))
        if output_files:
            logger.info(f"Found {len(output_files)} output files")
            for f in output_files[:5]:  # Log first 5
                logger.info(f"  - {os.path.basename(f)}")
                
            # Try to inspect h5ad files for data structure information
            for f in output_files:
                if f.endswith('.h5ad'):
                    try:
                        import scanpy as sc
                        adata = sc.read_h5ad(f)
                        
                        # Save data structure information for next nodes
                        data_info = {
                            "filename": os.path.basename(f),
                            "shape": f"{adata.shape[0]} cells x {adata.shape[1]} genes",
                            "obs_columns": list(adata.obs.columns),
                            "var_columns": list(adata.var.columns),
                            "obsm_keys": list(adata.obsm.keys()),
                            "varm_keys": list(adata.varm.keys()),
                            "uns_keys": list(adata.uns.keys()),
                            "layers": list(adata.layers.keys()) if adata.layers else []
                        }
                        
                        # Save to JSON for next node (use filename to make it unique)
                        base_name = os.path.splitext(os.path.basename(f))[0]
                        info_file = os.path.join(path_dict["output_dir"], f"_data_structure_{base_name}.json")
                        with open(info_file, 'w') as info_f:
                            json.dump(data_info, info_f, indent=2)
                        
                        logger.info(f"Output data structure for {os.path.basename(f)}: {json.dumps(data_info, indent=2)}")
                        break  # Only process first h5ad file for logging
                        
                    except Exception as e:
                        logger.warning(f"Could not inspect output data structure for {os.path.basename(f)}: {e}")
        else:
            logger.warning(f"No output files found in {path_dict['output_dir']}")
        
        logger.info("Function block execution completed successfully")
        
        # Export conda environment at the end if requested
        if params.get('export_environment', False):
            export_conda_environment()
        
    except Exception as e:
        logger.error(f"Error during execution: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Ensure logs are flushed to disk
        for handler in logger.handlers:
            handler.flush()
        
        # Also write error to a separate file for debugging
        try:
            with open('/workspace/output/error_details.txt', 'w') as f:
                f.write("Error: " + str(e) + "\\n\\n")
                f.write(traceback.format_exc())
        except:
            pass
            
        sys.exit(1)

if __name__ == "__main__":
    main()
'''