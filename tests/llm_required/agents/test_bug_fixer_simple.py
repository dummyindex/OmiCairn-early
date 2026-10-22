#!/usr/bin/env python3
"""Simple test for bug fixer agent without Docker."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from omicairn_agent_local.models import NewFunctionBlock, FunctionBlockType, StaticConfig
from omicairn_agent_local.agents import BugFixerAgent, TaskManager, TaskType
from omicairn_agent_local.llm_service import OpenAIService


def test_bug_fixer_with_llm():
    """Test bug fixer with actual LLM service."""
    print("\n=== Testing Bug Fixer with LLM Service ===")
    
    # Setup
    output_dir = Path("test_output_bug_fixer_llm")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create components
    task_manager = TaskManager(output_dir)
    llm_service = OpenAIService()
    bug_fixer = BugFixerAgent(llm_service=llm_service, task_manager=task_manager)
    
    # Create a function block with intentional error
    config = StaticConfig(
        args=[],
        description="Calculate gene statistics",
        tag="statistics",
        source="test"
    )
    
    code = '''
def run(path_dict, params):
    """Calculate gene statistics with error."""
    import scanpy as sc
    import pandas as pd
    
    # Load data from path_dict
    input_path = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    if not os.path.exists(input_path):
        h5ad_files = [f for f in os.listdir(path_dict["input_dir"]) if f.endswith(".h5ad")]
        if h5ad_files:
            input_path = os.path.join(path_dict["input_dir"], h5ad_files[0])
    adata = sc.read_h5ad(input_path) if "sc" in locals() or "sc" in globals() else None

    print("Calculating gene statistics...")
    
    # This will fail - using wrong attribute
    gene_means = adata.X.mean(axis=0)
    gene_vars = adata.X.var(axis=0)  # Wrong! var() doesn't exist for numpy arrays
    
    # Create dataframe
    stats_df = pd.DataFrame({
        'mean': gene_means,
        'variance': gene_vars,
        'cv': gene_vars / gene_means
    })
    
    # Save to adata
    adata.var['gene_mean'] = stats_df['mean']
    adata.var['gene_variance'] = stats_df['variance']
    adata.var['gene_cv'] = stats_df['cv']
    
    print(f"Calculated statistics for {len(stats_df)} genes")
    
    return adata
'''
    
    block = NewFunctionBlock(
        name="gene_statistics_calculator",
        type=FunctionBlockType.PYTHON,
        description="Calculate gene statistics",
        code=code,
        requirements="scanpy>=1.9.0\npandas>=2.0.0\nnumpy>=1.24.0",
        parameters={},
        static_config=config
    )
    
    # Create parent task
    parent_task = task_manager.create_task(
        task_type=TaskType.ORCHESTRATION,
        agent_name="test_orchestrator",
        description="Test gene statistics calculation",
        context={'analysis_id': 'test-llm-001', 'node_id': 'test-node-llm-001'}
    )
    
    # Simulate error
    error_context = {
        'function_block': block,
        'error_message': "AttributeError: 'numpy.ndarray' object has no attribute 'var'",
        'stdout': 'Calculating gene statistics...',
        'stderr': "Traceback (most recent call last):\n  File 'function_block.py', line 10\n    gene_vars = adata.X.var(axis=0)\nAttributeError: 'numpy.ndarray' object has no attribute 'var'",
        'parent_task_id': parent_task.task_id,
        'analysis_id': 'test-llm-001',
        'node_id': 'test-node-llm-001',
        'job_id': 'test-job-llm-001'
    }
    
    print("\n1. Testing with LLM debugging...")
    print(f"   Original error: {error_context['error_message']}")
    
    result = bug_fixer.process(error_context)
    
    print(f"\n   Success: {result['success']}")
    print(f"   Reasoning: {result['reasoning']}")
    
    if result['success'] and result.get('fixed_code'):
        print("\n2. Fixed code preview:")
        lines = result['fixed_code'].split('\n')
        for i, line in enumerate(lines[7:12], 8):  # Show lines around the fix
            print(f"   {i:3d}: {line}")
    
    if result.get('task_id'):
        # Check LLM interactions were logged
        task = task_manager.get_task(result['task_id'])
        print(f"\n3. Task tracking:")
        print(f"   Task ID: {task.task_id}")
        print(f"   Status: {task.status}")
        print(f"   LLM interactions logged: {len(task.llm_interactions)}")
        
        # Check artifacts
        task_dir = output_dir / "agent_tasks" / task.task_id
        artifacts = list(task_dir.glob("*"))
        print(f"   Artifacts saved: {len(artifacts)}")
        for artifact in artifacts:
            print(f"     - {artifact.name}")
    
    print("\n✓ LLM bug fixer test complete!")
    return result['success']


def test_bug_fixer_without_llm():
    """Test bug fixer with common patterns only."""
    print("\n=== Testing Bug Fixer without LLM ===")
    
    # Setup
    output_dir = Path("test_output_bug_fixer_patterns")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create components (no LLM service)
    task_manager = TaskManager(output_dir)
    bug_fixer = BugFixerAgent(task_manager=task_manager)
    
    # Test various common error patterns
    test_cases = [
        {
            'name': 'Missing numpy import',
            'code': '''
def run(path_dict, params):
    """Process data."""
    # Missing import for np
    # Load data from path_dict
    input_path = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    if not os.path.exists(input_path):
        h5ad_files = [f for f in os.listdir(path_dict["input_dir"]) if f.endswith(".h5ad")]
        if h5ad_files:
            input_path = os.path.join(path_dict["input_dir"], h5ad_files[0])
    adata = sc.read_h5ad(input_path) if "sc" in locals() or "sc" in globals() else None

    data = np.array(adata.X)
    return adata
''',
            'error': "NameError: name 'np' is not defined",
            'expected_fix': 'import numpy as np'
        },
        {
            'name': 'Missing scFates module',
            'code': '''
def run(path_dict, params):
    """Run trajectory."""
    import scFates as scf
    # Load data from path_dict
    input_path = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    if not os.path.exists(input_path):
        h5ad_files = [f for f in os.listdir(path_dict["input_dir"]) if f.endswith(".h5ad")]
        if h5ad_files:
            input_path = os.path.join(path_dict["input_dir"], h5ad_files[0])
    adata = sc.read_h5ad(input_path) if "sc" in locals() or "sc" in globals() else None

    scf.tl.curve(adata)
    return adata
''',
            'error': "ModuleNotFoundError: No module named 'scFates'",
            'expected_requirements': 'scFates'
        },
        {
            'name': 'Wrong scanpy function',
            'code': '''
def run(path_dict, params):
    """Highly variable genes."""
    import scanpy as sc
    # Load data from path_dict
    input_path = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    if not os.path.exists(input_path):
        h5ad_files = [f for f in os.listdir(path_dict["input_dir"]) if f.endswith(".h5ad")]
        if h5ad_files:
            input_path = os.path.join(path_dict["input_dir"], h5ad_files[0])
    adata = sc.read_h5ad(input_path) if "sc" in locals() or "sc" in globals() else None

    sc.pp.highly_variable_genes(adata)
    return adata
''',
            'error': "TypeError: highly_variable_genes() missing 1 required positional argument: 'flavor'",
            'expected_fix': 'flavor="seurat"'
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: {test_case['name']}")
        
        block = NewFunctionBlock(
            name=f"test_block_{i}",
            type=FunctionBlockType.PYTHON,
            description=test_case['name'],
            code=test_case['code'],
            requirements="scanpy>=1.9.0",
            parameters={},
            static_config=StaticConfig(args=[], description=test_case['name'], tag="test", source="test")
        )
        
        error_context = {
            'function_block': block,
            'error_message': test_case['error'],
            'stdout': '',
            'stderr': test_case['error']
        }
        
        result = bug_fixer.process(error_context)
        
        print(f"   Success: {result['success']}")
        print(f"   Reasoning: {result['reasoning']}")
        
        if result['success']:
            if 'expected_fix' in test_case and result.get('fixed_code'):
                if test_case['expected_fix'] in result['fixed_code']:
                    print(f"   ✓ Contains expected fix: {test_case['expected_fix']}")
                else:
                    print(f"   ✗ Missing expected fix: {test_case['expected_fix']}")
            
            if 'expected_requirements' in test_case and result.get('fixed_requirements'):
                if test_case['expected_requirements'] in result['fixed_requirements']:
                    print(f"   ✓ Added to requirements: {test_case['expected_requirements']}")
                else:
                    print(f"   ✗ Not in requirements: {test_case['expected_requirements']}")
    
    print("\n✓ Pattern-based bug fixer test complete!")
    return True


def main():
    """Run bug fixer tests."""
    print("=== Bug Fixer Agent Tests ===")
    
    # Test without LLM (using patterns)
    success1 = test_bug_fixer_without_llm()
    
    # Test with LLM if API key is available
    import os
    if os.getenv('OPENAI_API_KEY'):
        success2 = test_bug_fixer_with_llm()
    else:
        print("\n⚠️  Skipping LLM test - no OPENAI_API_KEY found")
        success2 = True
    
    print("\n=== Test Summary ===")
    print(f"Pattern-based test: {'✓ Passed' if success1 else '✗ Failed'}")
    print(f"LLM-based test: {'✓ Passed' if success2 else '✗ Failed'}")
    
    return success1 and success2


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)