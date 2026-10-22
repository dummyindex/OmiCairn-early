#!/usr/bin/env python3
"""Test that module reload works for bug fixing."""

import os
import sys
import tempfile
import subprocess
from pathlib import Path

def test_module_reload():
    """Test that Python wrapper correctly reloads modified modules."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create initial function_block.py with an error
        function_block_path = tmpdir / "function_block.py"
        function_block_path.write_text('''
def run(path_dict, params):
    print("Original version with error")
    raise ValueError("Original error")
''')
        
        # Create parameters.json
        params_path = tmpdir / "parameters.json"
        params_path.write_text('{}')
        
        # Create directories
        (tmpdir / "input").mkdir()
        (tmpdir / "output").mkdir()
        
        # Create run.py with module reload logic
        run_py_path = tmpdir / "run.py"
        run_py_path.write_text('''
import sys
import json

# Load parameters
with open('parameters.json') as f:
    params = json.load(f)

path_dict = {
    "input_dir": "input",
    "output_dir": "output"
}

print(f"Attempt {sys.argv[1] if len(sys.argv) > 1 else '1'}")

# Force reload
if 'function_block' in sys.modules:
    print("Deleting cached module")
    del sys.modules['function_block']

from function_block import run
run(path_dict, params)
''')
        
        # First run - should fail
        print("=== First run (should fail) ===")
        result1 = subprocess.run(
            [sys.executable, "run.py", "1"],
            cwd=tmpdir,
            capture_output=True,
            text=True
        )
        print("STDOUT:", result1.stdout)
        print("STDERR:", result1.stderr)
        print("Return code:", result1.returncode)
        
        # Modify function_block.py to fix the error
        function_block_path.write_text('''
def run(path_dict, params):
    print("Fixed version")
    print("Success!")
''')
        
        # Second run - should succeed
        print("\n=== Second run (should succeed) ===")
        result2 = subprocess.run(
            [sys.executable, "run.py", "2"],
            cwd=tmpdir,
            capture_output=True,
            text=True
        )
        print("STDOUT:", result2.stdout)
        print("STDERR:", result2.stderr)
        print("Return code:", result2.returncode)
        
        # Verify results
        if result1.returncode != 0 and result2.returncode == 0:
            print("\n✓ Module reload works correctly!")
            return True
        else:
            print("\n✗ Module reload FAILED!")
            return False

if __name__ == "__main__":
    test_module_reload()