"""Simple test to validate InteractiveExecutor node_dir fix."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import Mock
from job_executors.interactive_executor import InteractiveExecutor
from utils.docker_utils import DockerManager


def test_interactive_executor_node_dir_attribute():
    """Test that InteractiveExecutor initializes node_dir attribute without error."""
    # Create mock DockerManager
    mock_docker_manager = Mock(spec=DockerManager)
    mock_docker_manager.client = Mock()
    
    # Create InteractiveExecutor - should not raise AttributeError
    try:
        executor = InteractiveExecutor(mock_docker_manager)
        
        # Verify node_dir attribute exists
        assert hasattr(executor, 'node_dir'), "InteractiveExecutor missing node_dir attribute"
        assert executor.node_dir is None, "node_dir should be initialized to None"
        
        # Test setting node_dir (simulating what happens during execution)
        test_path = Path("/test/node/path")
        executor.node_dir = test_path
        assert executor.node_dir == test_path, "node_dir should be settable"
        
        print("✅ InteractiveExecutor properly initializes node_dir attribute")
        return True
        
    except AttributeError as e:
        print(f"❌ AttributeError occurred: {e}")
        return False


def test_node_dir_in_execute_with_debugging():
    """Test that execute_with_debugging method signature includes node_dir parameter."""
    import inspect
    from job_executors.interactive_executor import InteractiveExecutor
    
    # Get the signature of execute_with_debugging
    sig = inspect.signature(InteractiveExecutor.execute_with_debugging)
    
    # Check if node_dir is in the parameters
    assert 'node_dir' in sig.parameters, "execute_with_debugging missing node_dir parameter"
    
    # Verify it's Optional[Path]
    param = sig.parameters['node_dir']
    assert param.default is None, "node_dir parameter should default to None"
    
    print("✅ execute_with_debugging has node_dir parameter")
    return True


if __name__ == "__main__":
    print("Testing InteractiveExecutor node_dir fix...\n")
    
    # Run tests
    test1_passed = test_interactive_executor_node_dir_attribute()
    test2_passed = test_node_dir_in_execute_with_debugging()
    
    if test1_passed and test2_passed:
        print("\n✅ All tests passed! The node_dir fix is working correctly.")
    else:
        print("\n❌ Some tests failed. The node_dir issue may not be fully fixed.")
        sys.exit(1)