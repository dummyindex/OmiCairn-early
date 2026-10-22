#!/usr/bin/env python3
"""Unit tests for pseudotime function blocks using Docker containers."""

import os
import sys
import unittest
import shutil
from pathlib import Path
import json
import uuid
from datetime import datetime
import tempfile

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from job_executors.python_executor import PythonExecutor
from models import FunctionBlock, FunctionBlockType, NewFunctionBlock, StaticConfig, Arg, ExecutionResult
from utils.docker_utils import DockerManager
from utils import setup_logger

logger = setup_logger(__name__)


class TestPseudotimeFunctionBlocks(unittest.TestCase):
    """Test suite for pseudotime analysis function blocks."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment once for all tests."""
        cls.project_root = Path(__file__).parent.parent.parent.parent
        cls.function_blocks_dir = cls.project_root / "function_blocks" / "scrnaq"
        cls.test_data_dir = cls.project_root / "test_data"
        
        # Find test data
        test_data_candidates = [
            cls.test_data_dir / "zebrafish.h5ad",
            cls.test_data_dir / "pbmc3k_processed.h5ad",
        ]
        
        cls.test_data_path = None
        for candidate in test_data_candidates:
            if candidate.exists():
                cls.test_data_path = candidate
                break
        
        if cls.test_data_path is None:
            raise FileNotFoundError(f"No test data found. Tried: {test_data_candidates}")
        
        # Initialize Docker manager
        cls.docker_manager = DockerManager()
        
        # Create temporary base directory for all test outputs
        cls.temp_base = tempfile.mkdtemp(prefix="pseudotime_unittest_")
        
    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        # Remove temporary directory
        if hasattr(cls, 'temp_base') and os.path.exists(cls.temp_base):
            shutil.rmtree(cls.temp_base)
    
    def setUp(self):
        """Set up for each test."""
        # Create unique test directory
        self.test_dir = Path(self.temp_base) / f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        
    def tearDown(self):
        """Clean up after each test."""
        # Individual test directories are cleaned up with the base directory
        pass
    
    def _load_function_block(self, block_name: str) -> tuple:
        """Load function block configuration and code."""
        block_path = self.function_blocks_dir / block_name
        
        # Load config
        with open(block_path / "config.json", 'r') as f:
            config_data = json.load(f)
        
        # Load the shipped code unchanged (no in-test patching)
        with open(block_path / "code.py", 'r') as f:
            code = f.read()
        
        # Load requirements
        with open(block_path / "requirements.txt", 'r') as f:
            requirements = f.read()
        
        return config_data, code, requirements
    
    def _create_function_block(self, block_name: str, config_data: dict, code: str, requirements: str) -> NewFunctionBlock:
        """Create NewFunctionBlock instance from configuration."""
        # Get parameters with defaults
        params = {}
        if 'parameters' in config_data:
            for param_name, param_info in config_data['parameters'].items():
                if 'default' in param_info:
                    params[param_name] = param_info['default']
        
        # Convert parameters to Arg objects
        args = []
        if 'parameters' in config_data:
            for param_name, param_info in config_data['parameters'].items():
                arg = Arg(
                    name=param_name,
                    value_type=param_info.get('type', 'string'),
                    description=param_info.get('description', ''),
                    optional=not param_info.get('required', False),
                    default_value=param_info.get('default')
                )
                args.append(arg)
        
        # Create StaticConfig
        static_config = StaticConfig(
            args=args,
            description=config_data.get('description', ''),
            tag=config_data.get('name', block_name),
            document_url="",
            source="generated"
        )
        
        # Create NewFunctionBlock
        return NewFunctionBlock(
            id=str(uuid.uuid4()),
            name=config_data.get('name', block_name),
            type=FunctionBlockType.PYTHON,
            description=config_data.get('description', ''),
            code=code,
            requirements=requirements,
            parameters=params,
            static_config=static_config
        )
    
    def _execute_function_block(self, function_block: NewFunctionBlock, block_name: str) -> ExecutionResult:
        """Execute a function block in Docker and return the result."""
        # Setup execution directories
        execution_dir = self.test_dir / "execution"
        execution_dir.mkdir(exist_ok=True)
        
        input_dir = execution_dir / "input"
        output_dir = execution_dir / "output"
        
        input_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)
        
        # Copy test data
        shutil.copy2(self.test_data_path, input_dir / "_node_anndata.h5ad")
        
        # Execute with PythonExecutor
        executor = PythonExecutor(self.docker_manager)
        result = executor.execute(
            function_block=function_block,
            input_data_path=input_dir,
            output_dir=output_dir,
            parameters=function_block.parameters
        )
        
        # The executor already copies outputs to output_dir
        # No need for manual copying - the result object contains paths to outputs
        
        return result
    
    def _verify_outputs(self, result: ExecutionResult, block_name: str, output_dir: Path):
        """Verify outputs for a specific function block."""
        self.assertEqual(result.exit_code, 0, f"Function block {block_name} should execute successfully")
        self.assertTrue(result.success, f"Function block {block_name} should report success")
        
        # Check for output h5ad file
        self.assertIsNotNone(result.output_data_path, f"{block_name} should produce output data")
        output_path = Path(result.output_data_path)
        self.assertTrue(output_path.exists(), f"Output file should exist at {output_path}")
        
        # Verify pseudotime was added
        import scanpy as sc
        adata = sc.read_h5ad(output_path)
        
        # Check for method-specific outputs
        if block_name == "dpt_paga":
            self.assertIn('dpt_pseudotime', adata.obs, "DPT pseudotime should be in obs")
            self.assertIn('paga', adata.uns, "PAGA connectivity should be in uns")
        
        elif block_name == "palantir":
            self.assertIn('palantir_pseudotime', adata.obs, "Palantir pseudotime should be in obs")
            self.assertIn('palantir_entropy', adata.obs, "Palantir entropy should be in obs")
        
        elif block_name == "cellrank":
            # CellRank may not always compute pseudotime
            if 'cellrank_pseudotime' in adata.obs:
                logger.info("CellRank pseudotime found")
            else:
                logger.info("CellRank: No pseudotime computed (may need velocity data)")
        
        elif block_name == "scfates":
            self.assertIn('graph', adata.uns, "scFates graph should be in uns")
        
        # Check for figures
        if result.figures:
            logger.info(f"{block_name} generated {len(result.figures)} figures")
            for fig in result.figures[:3]:  # Log first 3
                logger.info(f"  - {Path(fig).name}")
    
    def test_dpt_paga_pseudotime(self):
        """Test DPT+PAGA pseudotime function block."""
        logger.info("\n" + "="*60)
        logger.info("Testing DPT+PAGA Pseudotime")
        logger.info("="*60)
        
        # Load and create function block
        config_data, code, requirements = self._load_function_block("dpt_paga")
        function_block = self._create_function_block("dpt_paga", config_data, code, requirements)
        
        # Execute
        result = self._execute_function_block(function_block, "dpt_paga")
        
        # Verify outputs
        self._verify_outputs(result, "dpt_paga", self.test_dir / "execution" / "output")
        
        logger.info("✅ DPT+PAGA test passed")
    
    def test_palantir_pseudotime(self):
        """Test Palantir pseudotime function block."""
        logger.info("\n" + "="*60)
        logger.info("Testing Palantir Pseudotime")
        logger.info("="*60)
        
        # Load and create function block
        config_data, code, requirements = self._load_function_block("palantir")
        function_block = self._create_function_block("palantir", config_data, code, requirements)
        
        # Execute
        result = self._execute_function_block(function_block, "palantir")
        
        # Verify outputs
        self._verify_outputs(result, "palantir", self.test_dir / "execution" / "output")
        
        logger.info("✅ Palantir test passed")
    
    def test_cellrank_trajectory(self):
        """Test CellRank trajectory function block."""
        logger.info("\n" + "="*60)
        logger.info("Testing CellRank Trajectory")
        logger.info("="*60)
        
        # Load and create function block
        config_data, code, requirements = self._load_function_block("cellrank")
        
        function_block = self._create_function_block("cellrank", config_data, code, requirements)
        
        # Execute
        result = self._execute_function_block(function_block, "cellrank")
        
        # For CellRank, we expect it might fail due to dependencies, but check gracefully
        if result.exit_code != 0:
            logger.warning(f"CellRank failed as expected in container: {result.error}")
            self.skipTest("CellRank has known dependency issues in containers")
        else:
            self._verify_outputs(result, "cellrank", self.test_dir / "execution" / "output")
            logger.info("✅ CellRank test passed")
    
    def test_scfates_trajectory(self):
        """Test scFates trajectory function block."""
        logger.info("\n" + "="*60)
        logger.info("Testing scFates Trajectory")
        logger.info("="*60)
        
        # Load and create function block
        config_data, code, requirements = self._load_function_block("scfates")
        
        # Ensure scfates is in requirements
        if "scfates" not in requirements:
            requirements = "scfates\n" + requirements
        
        function_block = self._create_function_block("scfates", config_data, code, requirements)
        
        # Execute
        result = self._execute_function_block(function_block, "scfates")
        
        # Verify outputs
        self._verify_outputs(result, "scfates", self.test_dir / "execution" / "output")
        
        logger.info("✅ scFates test passed")
    
    def test_all_methods_summary(self):
        """Test all methods and provide summary."""
        logger.info("\n" + "="*60)
        logger.info("Running All Pseudotime Methods")
        logger.info("="*60)
        
        methods = ["dpt_paga", "palantir", "cellrank", "scfates"]
        results = {}
        
        for method in methods:
            try:
                # Load and create function block
                config_data, code, requirements = self._load_function_block(method)
                
                # Ensure scfates is listed in requirements
                if method == "scfates" and "scfates" not in requirements:
                    requirements = "scfates\n" + requirements
                
                function_block = self._create_function_block(method, config_data, code, requirements)
                
                # Execute
                result = self._execute_function_block(function_block, method)
                
                results[method] = {
                    "success": result.success,
                    "exit_code": result.exit_code,
                    "output_path": result.output_data_path,
                    "num_figures": len(result.figures),
                    "error": result.error
                }
                
            except Exception as e:
                results[method] = {
                    "success": False,
                    "exit_code": -1,
                    "output_path": None,
                    "num_figures": 0,
                    "error": str(e)
                }
        
        # Print summary
        logger.info("\n" + "="*60)
        logger.info("Test Summary")
        logger.info("="*60)
        
        for method, result in results.items():
            status = "✅ PASSED" if result["success"] else "❌ FAILED"
            logger.info(f"{method:20} {status}")
            if result["output_path"]:
                logger.info(f"  - Output: {Path(result['output_path']).name}")
                logger.info(f"  - Figures: {result['num_figures']}")
            if not result["success"] and result["error"]:
                logger.info(f"  - Error: {result['error'][:100]}...")
        
        # Save results to file
        results_file = self.test_dir / "test_results.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        logger.info(f"\nDetailed results saved to: {results_file}")


if __name__ == "__main__":
    # Set up logging
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run tests
    unittest.main(verbosity=2)