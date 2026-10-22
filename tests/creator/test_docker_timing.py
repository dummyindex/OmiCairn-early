#!/usr/bin/env python3
"""Test to investigate Docker container execution timing."""

import time
from pathlib import Path
import shutil
from datetime import datetime

from omicairn_agent_local.models import NewFunctionBlock, FunctionBlockType, StaticConfig
from omicairn_agent_local.utils.docker_utils import DockerManager
from omicairn_agent_local.config import config


def create_timing_test_block():
    """Create R function block that shows timing information."""
    
    code = '''run <- function(path_dict, params) {
    cat("\\n=== EXECUTION TIMING TEST ===\\n")
    cat("Start time:", format(Sys.time()), "\\n\\n")
    
    # Show system info
    cat("System information:\\n")
    cat("  R version:", R.version.string, "\\n")
    cat("  Platform:", R.version$platform, "\\n")
    cat("  Available cores:", parallel::detectCores(), "\\n")
    cat("  Memory limit:", paste(round(memory.limit()/1024, 1), "GB"), "\\n")
    
    # Show installed packages
    cat("\\nChecking installed packages...\\n")
    installed_pkgs <- installed.packages()[,"Package"]
    cat("  Total installed packages:", length(installed_pkgs), "\\n")
    
    # Check if key packages are installed
    key_packages <- c("Seurat", "slingshot", "SingleCellExperiment", "ggplot2", "dplyr")
    for (pkg in key_packages) {
        if (pkg %in% installed_pkgs) {
            cat("  ✓", pkg, "is installed\\n")
        } else {
            cat("  ✗", pkg, "is NOT installed\\n")
        }
    }
    
    # Simple computation
    cat("\\nPerforming simple computation...\\n")
    start <- Sys.time()
    x <- matrix(rnorm(1000000), 1000, 1000)
    svd_result <- svd(x, nu = 10, nv = 10)
    end <- Sys.time()
    cat("  Matrix SVD completed in:", round(difftime(end, start, units = "secs"), 2), "seconds\\n")
    
    # Write output
    output_file <- file.path(path_dict$output_dir, "timing_results.txt")
    sink(output_file)
    cat("Docker Execution Timing Report\\n")
    cat("==============================\\n")
    cat("Generated:", format(Sys.time()), "\\n")
    cat("R version:", R.version.string, "\\n")
    cat("Installed packages:", length(installed_pkgs), "\\n")
    cat("Computation time:", round(difftime(end, start, units = "secs"), 2), "seconds\\n")
    sink()
    
    cat("\\nEnd time:", format(Sys.time()), "\\n")
    cat("=== TEST COMPLETE ===\\n")
}'''
    
    static_config = StaticConfig(
        args=[],
        description="Docker timing test",
        tag="analysis"
    )
    
    return NewFunctionBlock(
        id="timing_test",
        name="docker_timing_test",
        type=FunctionBlockType.R,
        description="Test Docker execution timing",
        code=code,
        requirements="",  # No requirements
        parameters={},
        static_config=static_config
    )


def test_docker_timing():
    """Test Docker container execution timing."""
    
    print("\n=== Docker Container Timing Investigation ===\n")
    
    output_dir = Path("test_outputs/docker_timing")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    
    # Create simple R function block
    print("1. Creating test function block...")
    fb = create_timing_test_block()
    print(f"✓ Created: {fb.name}")
    
    # Prepare input
    input_dir = output_dir / "input"
    input_dir.mkdir()
    (input_dir / "dummy.txt").write_text("test")
    
    # Test Docker directly
    print("\n2. Testing Docker container startup...")
    docker_manager = DockerManager()
    
    # Time container creation and startup
    start_time = time.time()
    
    print(f"   Starting at {datetime.now()}")
    
    # Create a test container
    volumes = {
        str(input_dir.absolute()): {"bind": "/workspace/input", "mode": "ro"},
        str(output_dir.absolute()): {"bind": "/workspace/output", "mode": "rw"}
    }
    
    # Run simple command
    print("   Running: R --version")
    container = docker_manager.client.containers.run(
        image=config.r_image,
        command="R --version",
        volumes=volumes,
        detach=True,
        remove=False
    )
    
    # Wait for completion
    result = container.wait()
    logs = container.logs().decode('utf-8')
    container.remove()
    
    startup_time = time.time() - start_time
    print(f"   Container startup took: {startup_time:.2f} seconds")
    print(f"\n   R version output:")
    print("   " + logs.replace("\n", "\n   "))
    
    # Now test with install_packages.R
    print("\n3. Testing package installation script generation...")
    
    # Create an R executor to see what it generates
    from omicairn_agent_local.job_executors.r_executor import RExecutor
    executor = RExecutor(docker_manager=docker_manager)
    
    # Check what install script is generated for empty requirements
    install_script = executor._generate_package_install_script("")
    print("   Install script for empty requirements:")
    print("   " + "-" * 60)
    for line in install_script.split('\n'):
        print(f"   {line}")
    print("   " + "-" * 60)
    
    # Test with Slingshot requirements
    slingshot_reqs = "Seurat\nslingshot\nBioconductor::SingleCellExperiment"
    install_script = executor._generate_package_install_script(slingshot_reqs)
    print("\n   Install script for Slingshot requirements:")
    print("   " + "-" * 60)
    for i, line in enumerate(install_script.split('\n')):
        if i < 20:  # First 20 lines
            print(f"   {line}")
    print("   ...")
    print("   " + "-" * 60)
    
    # Run the timing test
    print("\n4. Running timing test function block...")
    
    job_dir = output_dir / "job"
    job_dir.mkdir()
    
    start_exec = time.time()
    result = executor.execute(
        function_block=fb,
        input_data_path=input_dir,
        output_dir=job_dir,
        parameters={}
    )
    exec_time = time.time() - start_exec
    
    print(f"\n   Execution took: {exec_time:.2f} seconds")
    
    if result.success:
        print("   ✓ Success!")
        
        # Show timing results
        timing_file = job_dir / "timing_results.txt"
        if timing_file.exists():
            print("\n   Timing results:")
            with open(timing_file) as f:
                for line in f:
                    print(f"     {line.strip()}")
                    
        # Show execution logs
        if result.logs:
            print("\n   Container output:")
            print("   " + "=" * 60)
            for line in result.logs.split('\n'):
                if line.strip() and not line.startswith('*'):
                    print(f"   {line}")
            print("   " + "=" * 60)
    else:
        print(f"   ✗ Failed: {result.error}")
        
    print("\n=== Analysis Complete ===")
    

if __name__ == "__main__":
    test_docker_timing()