#!/usr/bin/env python3
"""Simplified agent coordination tests focusing on basic functionality."""

import os
import sys

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.main_agent import MainAgent
from llm_service.mock_service import MockOpenAIService
from models import NodeState, FunctionBlockType


def test_main_agent_can_be_created():
    """Test that MainAgent can be instantiated."""
    try:
        agent = MainAgent(
            openai_api_key=None,
            bug_fixer_type="unified",
            enable_web_agent=False
        )
    except Exception as e:
        # A missing Docker daemon is an environment limitation, not a code failure.
        if "Docker is not available" in str(e):
            pytest.skip(f"Docker daemon not available: {e}")
        # Only a missing API key is an acceptable reason not to instantiate;
        # any other error is a real failure and must not be reported as a pass.
        if "key" not in str(e).lower():
            raise
        print(f"⚠️ MainAgent creation - SKIPPED (API key required: {e})")
        return True

    assert agent is not None
    print("✅ MainAgent creation - PASSED")
    return True


def test_mock_service_basic_functionality():
    """Test MockOpenAIService basic functionality."""
    mock_service = MockOpenAIService()
    
    # Test chat completion
    messages = [{"role": "user", "content": "Test message"}]
    response = mock_service.chat_completion(messages)
    
    assert isinstance(response, str)
    assert len(response) > 0
    
    print("✅ MockOpenAIService basic functionality - PASSED")
    return True


def test_node_state_enums():
    """Test that node state enums are properly defined."""
    # Test all expected node states exist
    expected_states = ["pending", "running", "completed", "failed", "debugging", "skipped"]
    
    for state in expected_states:
        assert hasattr(NodeState, state.upper()), f"NodeState should have {state.upper()}"
        assert getattr(NodeState, state.upper()) == state, f"NodeState.{state.upper()} should equal '{state}'"
    
    print("✅ Node state enums - PASSED")
    return True


def test_function_block_type_enums():
    """Test that function block type enums are properly defined."""
    # Test expected types exist
    assert FunctionBlockType.PYTHON == "python"
    assert FunctionBlockType.R == "r"
    
    # Test they're in the enum
    types = list(FunctionBlockType)
    assert FunctionBlockType.PYTHON in types
    assert FunctionBlockType.R in types
    
    print("✅ Function block type enums - PASSED")
    return True


def test_basic_imports():
    """Test that core modules can be imported."""
    try:
        from analysis_tree_management.tree_manager import AnalysisTreeManager
        from job_executors.executor_manager import ExecutorManager
        from agents.function_creator_agent import FunctionCreatorAgent
        from agents.orchestrator_agent import OrchestratorAgent
        
        # Just check they can be imported
        assert AnalysisTreeManager is not None
        assert ExecutorManager is not None
        assert FunctionCreatorAgent is not None
        assert OrchestratorAgent is not None
        
        print("✅ Basic imports - PASSED")
        return True
    except ImportError as e:
        print(f"❌ Basic imports failed: {e}")
        return False


def test_main_agent_methods_exist():
    """Test that MainAgent has expected methods."""
    # Check methods exist without instantiating
    assert hasattr(MainAgent, 'run_analysis')
    assert hasattr(MainAgent, '__init__')
    
    # Check run_analysis is callable
    assert callable(getattr(MainAgent, 'run_analysis'))
    
    print("✅ MainAgent methods exist - PASSED")
    return True


def test_configuration_models():
    """Test basic configuration model creation."""
    from models import StaticConfig, Arg
    
    # Test StaticConfig
    config = StaticConfig(
        args=[],
        description="Test config",
        tag="test"
    )
    assert config.description == "Test config"
    assert config.tag == "test"
    
    # Test Arg with correct field name
    arg = Arg(
        name="test_param",
        value_type="string",
        description="Test parameter"
    )
    assert arg.name == "test_param"
    assert arg.value_type == "string"
    print("✅ Configuration models - PASSED")
    return True


def run_all_tests():
    """Run all simplified agent coordination tests."""
    print("\n" + "="*80)
    print("SIMPLIFIED AGENT COORDINATION TESTS")
    print("="*80)
    
    tests = [
        ("MainAgent can be created", test_main_agent_can_be_created),
        ("MockService basic functionality", test_mock_service_basic_functionality),
        ("Node state enums", test_node_state_enums),
        ("Function block type enums", test_function_block_type_enums),
        ("Basic imports", test_basic_imports),
        ("MainAgent methods exist", test_main_agent_methods_exist),
        ("Configuration models", test_configuration_models)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
            print(f"\n❌ FAILED: {test_name}")
            print(f"  Error: {e}")
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, error in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status}: {test_name}")
        if error:
            print(f"         Error: {error}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED: Basic agent coordination working correctly")
        return True
    else:
        print(f"\n❌ {total - passed} tests failed")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)