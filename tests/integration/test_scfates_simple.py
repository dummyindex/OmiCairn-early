#!/usr/bin/env python3
"""
Simple test to verify scFates is properly installed in our Docker image.
"""

import subprocess
import sys

def test_scfates_in_docker():
    """Test if scFates can be imported in Docker container."""
    
    print("Testing scFates in Docker container...")
    print("=" * 60)
    
    # Test command that imports scFates and checks version
    test_script = """
import sys
print(f"Python version: {sys.version}")
print("-" * 40)

try:
    import scFates as scfates
    print("✓ scFates imported successfully!")
    
    # Check version if available
    if hasattr(scfates, '__version__'):
        print(f"  Version: {scfates.__version__}")
    
    # Check available modules
    print("\\nAvailable scFates modules:")
    for attr in dir(scfates):
        if not attr.startswith('_'):
            print(f"  - scfates.{attr}")
    
    # Test basic functionality
    print("\\nTesting basic imports:")
    try:
        import scfates.tl
        print("  ✓ scfates.tl imported")
    except Exception as e:
        print(f"  ✗ scfates.tl failed: {e}")
    
    try:
        import scfates.pp
        print("  ✓ scfates.pp imported")
    except Exception as e:
        print(f"  ✗ scfates.pp failed: {e}")
    
    try:
        import scfates.pl
        print("  ✓ scfates.pl imported")
    except Exception as e:
        print(f"  ✗ scfates.pl failed: {e}")
    
    print("\\n✅ scFates is properly installed!")
    
except ImportError as e:
    print(f"❌ Failed to import scFates: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    sys.exit(1)
"""
    
    # Run in Docker container
    cmd = [
        "docker", "run", "--rm",
        "omicairn/python-executor:latest",
        "/workspace/run_with_conda.sh",
        "python", "-c", test_script
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print("=== STDOUT ===")
        print(result.stdout)
        
        if result.stderr:
            print("\n=== STDERR ===")
            print(result.stderr)
        
        if result.returncode == 0:
            print("\n✅ Test passed! scFates is working in Docker.")
            return True
        else:
            print(f"\n❌ Test failed with return code {result.returncode}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Docker execution failed: {e}")
        if e.stdout:
            print(f"STDOUT: {e.stdout}")
        if e.stderr:
            print(f"STDERR: {e.stderr}")
        return False


if __name__ == "__main__":
    success = test_scfates_in_docker()
    sys.exit(0 if success else 1)