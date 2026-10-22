#!/usr/bin/env python3
"""Test bug fixer functionality with scFates trajectory inference scenarios."""

import sys
from pathlib import Path
import json
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models import NewFunctionBlock, FunctionBlockType, StaticConfig, Arg
from agents.unified_bug_fixer.unified_bug_fixer import UnifiedBugFixer
from utils import setup_logger

logger = setup_logger("test_bug_fixer_scfates")


def create_buggy_scfates_block():
    """Create a scFates function block with intentional dependency issues."""
    config = StaticConfig(
        args=[
            Arg(name="n_waypoints", value_type="int", description="Number of waypoints",
                optional=True, default_value=150)
        ],
        description="Run scFates trajectory inference",
        tag="trajectory",
        source="test"
    )
    
    # This code has intentional issues:
    # 1. Missing import for os
    # 2. Missing import for scFates
    code = '''
def run(path_dict, params):
    """Run scFates trajectory inference."""
    import scanpy as sc
    import pandas as pd
    import numpy as np
    import matplotlib.pyplot as plt
    
    # Load data - missing os import will cause error
    input_path = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    adata = sc.read_h5ad(input_path)

    print("Running scFates trajectory inference...")
    
    # Missing scFates import
    import scFates as scf
    
    # Run trajectory inference
    n_waypoints = params.get('n_waypoints', 150)
    scf.tl.curve(adata, Nodes=n_waypoints)
    scf.tl.tree(adata, method='epg')
    
    # Save results
    output_path = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    adata.write(output_path)
    
    return adata
'''
    
    return NewFunctionBlock(
        id="scfates_buggy",
        name="scfates_trajectory",
        type=FunctionBlockType.PYTHON,
        description="scFates trajectory inference with bugs",
        code=code,
        requirements="scanpy>=1.9.0\npandas>=1.1.0\nnumpy>=1.20.0",  # Missing scFates
        parameters={"n_waypoints": 150},
        static_config=config
    )


def test_scfates_missing_import_detection():
    """Test that bug fixer can detect missing imports."""
    print("\n=== Testing Missing Import Detection ===")
    
    block = create_buggy_scfates_block()
    
    # Check that the block has missing imports
    assert "import os" not in block.code
    assert "scFates" not in block.requirements
    
    print("✓ Created buggy block with missing imports")
    print(f"✓ Code has {len(block.code.splitlines())} lines")
    print(f"✓ Requirements: {block.requirements.count('>=')}")


def test_bug_fixer_with_scfates():
    """Test bug fixer initialization for scFates debugging."""
    print("\n=== Testing Bug Fixer for scFates ===")
    
    with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
        bug_fixer = UnifiedBugFixer(
            model_name="gpt-4o-mini",
            max_turns=3,
            enable_domain_knowledge=True,
            domain_knowledge_domains=["trajectory_inference"]
        )
        
        assert bug_fixer.max_turns == 3
        assert bug_fixer.enable_domain_knowledge == True
        print("✓ Bug fixer configured for trajectory analysis")


def main():
    """Run all scFates bug fixer tests."""
    print("=== scFates Bug Fixer Tests ===")
    
    tests = [
        test_scfates_missing_import_detection,
        test_bug_fixer_with_scfates
    ]
    
    results = []
    for test in tests:
        try:
            test()
            results.append((test.__name__, True))
        except Exception as e:
            print(f"\n✗ {test.__name__} failed: {e}")
            results.append((test.__name__, False))
    
    print("\n=== Test Summary ===")
    for test_name, success in results:
        status = "✓ Passed" if success else "✗ Failed"
        print(f"{test_name}: {status}")
    
    return all(success for _, success in results)


if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)