#!/usr/bin/env python
"""
Consolidated test for core OmiCairn Agent Local system functionality.
Tests essential components to ensure the system works correctly.
"""

import os
import sys
import tempfile
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Silence noisy loggers
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('docker').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)


def test_imports():
    """Test that all core modules can be imported."""
    logger.info("Testing core module imports...")
    
    try:
        from agents.main_agent import MainAgent
        from agents.orchestrator_agent import OrchestratorAgent
        from agents.function_creator_agent import FunctionCreatorAgent
        from analysis_tree_management.tree_manager import AnalysisTreeManager
        from analysis_tree_management.node_executor import NodeExecutor
        from job_executors.python_executor import PythonExecutor
        from llm_service.openai_service import OpenAIService
        from models import AnalysisTree, AnalysisNode
        logger.info("✅ All core modules imported successfully")
        return True
    except ImportError as e:
        logger.error(f"❌ Failed to import core modules: {e}")
        return False


def test_constants():
    """Test that required constants are defined."""
    logger.info("Testing constants...")
    
    try:
        from constants import ROOT_NODE_NAME
        from models import JobReviewStatus
        
        # Verify constants have expected values
        assert ROOT_NODE_NAME == "load_input_data"
        assert JobReviewStatus.PASSED == "passed"
        assert JobReviewStatus.FAILED == "failed"
        assert JobReviewStatus.NOT_REVIEWED == "not_reviewed"
        assert JobReviewStatus.SKIPPED == "skipped"
        
        logger.info("✅ All constants verified")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to verify constants: {e}")
        return False


def test_models():
    """Test that data models work correctly."""
    logger.info("Testing data models...")
    
    try:
        from models import AnalysisTree, AnalysisNode, NodeState
        
        # Create a simple tree with all required fields
        tree = AnalysisTree(
            user_request="Test request",
            input_data_path="test.h5ad",
            max_nodes=10,
            max_children_per_node=3,
            max_debug_trials=3
        )
        
        # Add a node
        node = AnalysisNode(
            id="test-node",
            name="test_node",
            task="Test task",
            language="python"
        )
        tree.add_node(node)
        
        # Verify tree structure
        assert len(tree.nodes) == 1
        assert tree.nodes["test-node"].name == "test_node"
        
        logger.info("✅ Data models working correctly")
        return True
    except Exception as e:
        logger.error(f"❌ Model test failed: {e}")
        return False


def test_tree_manager():
    """Test TreeManager functionality."""
    logger.info("Testing TreeManager...")
    
    try:
        from analysis_tree_management.tree_manager import AnalysisTreeManager
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test input file
            input_file = Path(temp_dir) / "test.h5ad"
            input_file.write_text("test data")
            
            # Initialize TreeManager
            manager = AnalysisTreeManager()
            
            # Create a tree
            tree = manager.create_tree(
                user_request="Test analysis",
                input_data_path=str(input_file),
                max_nodes=10
            )
            
            assert tree is not None
            assert tree.id is not None
            assert tree.user_request == "Test analysis"
            
            logger.info(f"✅ TreeManager working correctly, created tree: {tree.id}")
            return True
            
    except Exception as e:
        logger.error(f"❌ TreeManager test failed: {e}")
        return False


def test_docker():
    """Test Docker availability."""
    logger.info("Testing Docker availability...")
    
    try:
        import docker
        client = docker.from_env()
        
        # Test Docker connection
        version = client.version()
        logger.info(f"Docker version: {version.get('Version', 'unknown')}")
        
        # Check for required images
        images = client.images.list()
        python_executor = any('python-executor' in str(img.tags) for img in images)
        r_executor = any('r-executor' in str(img.tags) for img in images)
        
        if python_executor:
            logger.info("✅ Python executor image found")
        else:
            logger.warning("⚠️ Python executor image not found - run 'make docker-build'")
            
        if r_executor:
            logger.info("✅ R executor image found") 
        else:
            logger.warning("⚠️ R executor image not found - run 'make docker-build'")
            
        logger.info("✅ Docker is available")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ Docker test failed: {e}")
        logger.warning("Some features may not work without Docker")
        return False


def test_agent_initialization():
    """Test that MainAgent can be initialized."""
    logger.info("Testing MainAgent initialization...")
    
    try:
        from agents.main_agent import MainAgent
        
        # Initialize agent
        agent = MainAgent(
            openai_api_key=os.environ.get("OPENAI_API_KEY", "test-key"),
            bug_fixer_max_turns=1,
            enable_domain_knowledge=False
        )
        
        assert agent is not None
        logger.info("✅ MainAgent initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ MainAgent initialization failed: {e}")
        return False


def run_all_tests():
    """Run all core tests."""
    print("\n" + "="*60)
    print("CORE SYSTEM TESTS")
    print("="*60 + "\n")
    
    tests = [
        ("Module Imports", test_imports),
        ("Constants", test_constants),
        ("Data Models", test_models),
        ("Tree Manager", test_tree_manager),
        ("Docker", test_docker),
        ("Agent Initialization", test_agent_initialization)
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\nRunning: {name}")
        print("-" * 40)
        success = test_func()
        results.append((name, success))
        
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    failed = len(results) - passed
    
    for name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{name}: {status}")
        
    print(f"\nTotal: {len(results)} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n✅ All core tests passed!")
    else:
        print(f"\n❌ {failed} tests failed. Please review the output above.")
        
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)