#!/usr/bin/env python3
"""Quick test of select_root_cell bug fixing."""

import os
import sys
from pathlib import Path
import tempfile
import shutil

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from models import NewFunctionBlock, FunctionBlockType
from job_executors.interactive_executor import InteractiveExecutor
from agents.unified_bug_fixer.unified_bug_fixer import UnifiedBugFixer
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_select_root_cell():
    """Test select_root_cell with bug fixing."""
    
    # Create function block that expects 'cell_type' but data has 'Cell_type'
    function_block = NewFunctionBlock(
        name="select_root_cell",
        type=FunctionBlockType.PYTHON,
        description="Select root cell for pseudotime",
        code='''def run(path_dict, params):
    import scanpy as sc
    import os
    import numpy as np
    
    # Load data
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    
    adata = sc.read_h5ad(input_file)
    
    # Perform leiden clustering if not already done
    if 'leiden' not in adata.obs.columns:
        sc.tl.leiden(adata)
    
    # THIS WILL FAIL - expects 'cell_type' but data has 'Cell_type'
    if 'cell_type' not in adata.obs.columns:
        raise ValueError('cell_type column not found in adata.obs')
    
    # Select root cell
    earliest_cell_type = adata.obs['cell_type'].value_counts().idxmin()
    root_cells = adata[adata.obs['cell_type'] == earliest_cell_type]
    
    if root_cells.n_obs == 0:
        raise ValueError('No root cells found')
        
    root_cell_index = np.random.choice(root_cells.obs.index)
    adata.uns['iroot'] = root_cell_index
    
    # Save
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    adata.write(output_file)
    
    print(f"Selected root cell: {root_cell_index}")
''',
        requirements=["scanpy", "numpy"],
        static_config={
            "input_data_type": "AnnData",
            "output_data_type": "AnnData"
        }
    )
    
    # Create bug fixer
    bug_fixer = UnifiedBugFixer(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini",
        save_debug_logs=False,
        enable_web_agent=False,
        max_turns=3  # Fewer turns for faster test
    )
    
    # Create interactive executor
    executor = InteractiveExecutor(
        docker_manager=None,
        bug_fixer=bug_fixer
    )
    
    # Use existing test data
    input_path = Path("test_data/zebrafish.h5ad")
    if not input_path.exists():
        logger.error(f"Test data not found at {input_path}")
        return
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output"
        output_dir.mkdir(parents=True)
        
        logger.info("Starting execution with bug fixing...")
        
        # Execute with debugging
        result = executor.execute_with_debugging(
            function_block=function_block,
            input_data_path=input_path.parent,
            output_dir=output_dir,
            parameters={},
            max_debug_attempts=2,
            debug_callback=lambda msg: logger.info(f"Debug: {msg}")
        )
        
        logger.info(f"\nExecution result: {result.success}")
        logger.info(f"Debug attempts: {result.metadata.get('debug_attempts', 0)}")
        
        if result.success:
            logger.info("✓ Bug fixer successfully fixed the issue!")
            
            # Check if output was created
            output_file = output_dir / "_node_anndata.h5ad"
            if output_file.exists():
                logger.info(f"✓ Output file created: {output_file}")
            else:
                logger.error("✗ Output file not created")
        else:
            logger.error(f"✗ Execution failed: {result.error}")
            
        return result.success


if __name__ == "__main__":
    success = test_select_root_cell()
    sys.exit(0 if success else 1)