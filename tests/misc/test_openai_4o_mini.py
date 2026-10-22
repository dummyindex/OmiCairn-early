#!/usr/bin/env python3
"""
Test enhanced prompts and metadata features with OpenAI 4o-mini.

This test validates that our enhancements work correctly with a real LLM.
"""

import os
import sys
import tempfile
import shutil
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.main_agent import MainAgent
from models import AnalysisTree


def test_openai_4o_mini_integration():
    """Test enhanced features with OpenAI 4o-mini."""
    
    # Check for API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY not found. Skipping OpenAI 4o-mini test.")
        return False
    
    print("🧪 Testing enhanced prompts with OpenAI 4o-mini...")
    
    # Create temporary test environment
    with tempfile.TemporaryDirectory() as temp_dir:
        test_path = Path(temp_dir)
        
        # Create mock zebrafish data file
        input_file = test_path / "zebrafish_test.h5ad"
        input_file.write_text("mock anndata content")
        
        # Create additional files to test directory tree gathering
        data_dir = test_path / "additional_files"
        data_dir.mkdir()
        (data_dir / "metadata.csv").write_text("cell_id,cell_type,condition\nc1,neuron,control")
        (data_dir / "analysis_config.json").write_text('{"version": "2.0", "method": "leiden"}')
        
        output_dir = test_path / "output"
        output_dir.mkdir()
        
        try:
            # Initialize agent with 4o-mini
            agent = MainAgent(
                openai_api_key=api_key,
                llm_model="gpt-4o-mini",
                bug_fixer_model="gpt-4o-mini",
                enable_interactive_debug=False  # Use standard execution for testing
            )
            
            print("✅ Agent initialized successfully")
            
            # Test 1: Enhanced Function Creator Prompts
            print("\n📝 Testing enhanced function creator prompts...")
            
            # Create context with directory tree and parent info
            context = {
                'task_description': 'Perform basic preprocessing on zebrafish data',
                'user_request': 'Load and preprocess the zebrafish single-cell data',
                'input_context': {
                    'is_root_node': True,
                    'available_files': ['zebrafish_test.h5ad', 'additional_files/'],
                    'directory_tree': f'├── zebrafish_test.h5ad (19B)\n├── additional_files/\n│   ├── metadata.csv (38B)\n│   └── analysis_config.json (46B)',
                    'parent_node_name': None,
                    'parent_output_description': None,
                    'parent_data_structure': None
                }
            }
            
            # Test function creation with enhanced prompts
            try:
                print("  Calling function creator with enhanced context...")
                result = agent.function_creator.create_function_block(context)
                print(f"  Raw result: {result}")
                
                if result:
                    # Result is a NewFunctionBlock object, not a dictionary
                    block = result
                    print(f"✅ Function block created: {block.name}")
                    
                    # Check for enhanced prompt features
                    code = block.code
                    output_desc = block.output_description
                    
                    # Verify file convention awareness
                    if '_node_anndata.h5ad' in code:
                        print("✅ Code follows naming conventions")
                    else:
                        print("⚠️  Code may not follow naming conventions")
                    
                    # Verify output description is present
                    if output_desc and len(output_desc) > 20:
                        print(f"✅ Output description provided: {output_desc[:50]}...")
                    else:
                        print("⚠️  Output description missing or too short")
                    
                    # Verify directory awareness in code
                    if 'input_dir' in code and 'output_dir' in code:
                        print("✅ Code uses proper path_dict structure")
                    else:
                        print("⚠️  Code may not use proper path structure")
                    
                else:
                    print("❌ Function block creation failed - no valid result")
                    if result:
                        print(f"  Result was: {result}")
                    return False
                    
            except Exception as e:
                print(f"❌ Function creator test failed: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                return False
            
            # Test 2: Directory Tree Gathering
            print("\n📁 Testing directory tree gathering...")
            try:
                tree_str = agent._get_directory_tree(test_path, max_depth=2)
                print(f"✅ Directory tree gathered: {len(tree_str)} chars")
                
                # Verify it includes expected files
                if 'zebrafish_test.h5ad' in tree_str and 'metadata.csv' in tree_str:
                    print("✅ Directory tree includes expected files")
                else:
                    print("⚠️  Directory tree may be missing files")
                    
            except Exception as e:
                print(f"❌ Directory tree test failed: {e}")
                return False
            
            # Test 3: Parent Output Description Flow
            print("\n🔗 Testing parent output description flow...")
            try:
                # Create a second context simulating a child node
                child_context = {
                    'task_description': 'Perform clustering on preprocessed data',
                    'user_request': 'Run Leiden clustering on the data',
                    'input_context': {
                        'is_root_node': False,
                        'available_files': ['_node_anndata.h5ad'],
                        'directory_tree': '├── _node_anndata.h5ad (processed)',
                        'parent_node_name': 'preprocess_data',
                        'parent_output_description': 'Preprocessed zebrafish data with QC metrics in adata.obs["n_genes", "n_counts", "pct_mito"]',
                        'parent_data_structure': {
                            'shape': '(1000, 2000)',
                            'obs_columns': ['n_genes', 'n_counts', 'pct_mito'],
                            'obsm_keys': ['X_pca'],
                            'uns_keys': ['log1p']
                        }
                    }
                }
                
                child_result = agent.function_creator.create_function_block(child_context)
                
                if child_result:
                    child_block = child_result
                    child_code = child_block.code
                    print("✅ Child node created successfully")
                    
                    # Check if parent information influenced the code
                    if 'QC metrics' in child_code or 'n_genes' in child_code or 'leiden' in child_code:
                        print("✅ Parent output description influenced child node")
                    else:
                        print("⚠️  Parent information may not have been utilized")
                        
                else:
                    print("❌ Child node creation failed")
                    return False
                    
            except Exception as e:
                print(f"❌ Parent-child flow test failed: {e}")
                return False
            
            print("\n🎉 All OpenAI 4o-mini tests passed!")
            return True
            
        except Exception as e:
            print(f"❌ Agent initialization failed: {e}")
            return False


def test_validation_enforcement():
    """Test optional validation enforcement feature."""
    
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY not found. Skipping validation test.")
        return False
    
    print("\n🛡️  Testing optional validation enforcement...")
    
    # This would require setting up a more complex test with actual validation
    # For now, just verify the config option exists
    from models import StaticConfig
    
    # Test default behavior (enforcement disabled)
    config_default = StaticConfig(args=[], description="test", tag="test")
    if hasattr(config_default, 'enforce_validation') and not config_default.enforce_validation:
        print("✅ Default validation enforcement is disabled")
    else:
        print("❌ Default validation enforcement setting incorrect")
        return False
    
    # Test explicit enforcement
    config_enforced = StaticConfig(args=[], description="test", tag="test", enforce_validation=True)
    if config_enforced.enforce_validation:
        print("✅ Validation enforcement can be enabled")
    else:
        print("❌ Validation enforcement setting failed")
        return False
    
    return True


def main():
    """Run all OpenAI 4o-mini tests."""
    print("=" * 60)
    print("OpenAI 4o-mini Integration Tests")
    print("=" * 60)
    
    tests_passed = 0
    total_tests = 2
    
    # Test 1: Enhanced prompts integration
    if test_openai_4o_mini_integration():
        tests_passed += 1
        
    # Test 2: Validation enforcement
    if test_validation_enforcement():
        tests_passed += 1
    
    print("\n" + "=" * 60)
    print("OPENAI 4O-MINI TESTS SUMMARY")
    print("=" * 60)
    print(f"Tests passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("✅ All OpenAI 4o-mini tests passed!")
        print("\nChecked: the function creator returns a block with a real LLM call,")
        print("and the validation-enforcement config flag exists (feature checks are warnings only).")
        return True
    else:
        print("❌ Some tests failed. Please review the errors above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)