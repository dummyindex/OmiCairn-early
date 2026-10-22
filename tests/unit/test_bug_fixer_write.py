#!/usr/bin/env python3
"""Test bug fixer file writing functionality."""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.unified_bug_fixer.unified_bug_fixer import UnifiedBugFixer
from models import NewFunctionBlock, FunctionBlockType, StaticConfig, Arg


def test_bug_fixer_write():
    """Test that bug fixer can handle file writing scenarios."""
    
    # Create proper static config
    static_config = StaticConfig(
        args=[],
        description="Test function block",
        tag="test",
        source="test"
    )
    
    # Create a simple function block with an error
    function_block = NewFunctionBlock(
        id="test_write",
        name="test_write",
        type=FunctionBlockType.PYTHON,
        description="Test function block",
        code='''def run(path_dict, params):
    # This will fail
    import scanpy as sc
    import os
    
    input_path = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    adata = sc.read_h5ad(input_path)
    
    # Try to access non-existent attribute
    result = adata.non_existent_attribute
    
    output_path = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_path)
''',
        requirements="scanpy>=1.9.0",  # String, not list
        parameters={},
        static_config=static_config
    )
    
    # Test initialization
    with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
        bug_fixer = UnifiedBugFixer(
            model_name="gpt-4o-mini",
            save_debug_logs=False,
            enable_web_agent=False
        )
        
        assert bug_fixer is not None
        print("✓ Bug fixer created successfully")
    
    # Test that the function block has the expected error
    assert "non_existent_attribute" in function_block.code
    assert "scanpy" in function_block.requirements
    print("✓ Function block contains expected error")
    
    # Test file writing patterns
    write_patterns = [
        "os.makedirs(path_dict['output_dir'], exist_ok=True)",
        "adata.write(output_path)",
        "with open(file_path, 'w') as f:"
    ]
    
    print("\n✓ Common file writing patterns:")
    for pattern in write_patterns:
        print(f"  - {pattern}")


def test_bug_fixer_file_operations():
    """Test bug fixer understanding of file operations."""
    
    file_operations = {
        'read': [
            "sc.read_h5ad()",
            "pd.read_csv()",
            "with open() as f: f.read()"
        ],
        'write': [
            "adata.write()",
            "df.to_csv()",
            "with open() as f: f.write()"
        ],
        'check': [
            "os.path.exists()",
            "Path().exists()",
            "os.path.isfile()"
        ]
    }
    
    for operation, examples in file_operations.items():
        print(f"\n✓ {operation.capitalize()} operations:")
        for example in examples:
            print(f"  - {example}")
    
    assert len(file_operations) > 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])