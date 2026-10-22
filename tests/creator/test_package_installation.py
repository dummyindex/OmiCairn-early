#!/usr/bin/env python3
"""Test to show actual package installation timing and output."""

import time
from pathlib import Path
import shutil
from datetime import datetime

from omicairn_agent_local.models import NewFunctionBlock, FunctionBlockType, StaticConfig
from omicairn_agent_local.job_executors.r_executor import RExecutor
from omicairn_agent_local.utils.docker_utils import DockerManager
from omicairn_agent_local.config import config


def create_installation_monitor_block():
    """Create R function that monitors package installation."""
    
    code = '''run <- function(path_dict, params) {
    cat("\\n=== PACKAGE INSTALLATION MONITOR ===\\n")
    cat("Start time:", format(Sys.time()), "\\n\\n")
    
    # Function to time package installation
    time_install <- function(pkg_name, install_func) {
        cat("Installing", pkg_name, "...\\n")
        start <- Sys.time()
        
        # Capture installation output
        install_log <- capture.output({
            tryCatch({
                install_func()
                success <- TRUE
            }, error = function(e) {
                cat("ERROR:", e$message, "\\n")
                success <- FALSE
            })
        }, type = "message")
        
        end <- Sys.time()
        duration <- difftime(end, start, units = "secs")
        
        cat("  Duration:", round(duration, 1), "seconds\\n")
        if (length(install_log) > 0) {
            cat("  Messages:", length(install_log), "lines\\n")
        }
        cat("\\n")
        
        return(list(
            package = pkg_name,
            duration = as.numeric(duration),
            success = exists("success") && success,
            start_time = start,
            end_time = end
        ))
    }
    
    # Track all installations
    results <- list()
    
    # Test installing a small CRAN package
    cat("1. Testing small CRAN package (jsonlite)...\\n")
    results$jsonlite <- time_install("jsonlite", function() {
        install.packages("jsonlite", repos="https://cloud.r-project.org", quiet = TRUE)
    })
    
    # Test installing a medium package
    cat("2. Testing medium CRAN package (ggplot2)...\\n")
    results$ggplot2 <- time_install("ggplot2", function() {
        install.packages("ggplot2", repos="https://cloud.r-project.org", quiet = TRUE)
    })
    
    # Save timing report
    report_file <- file.path(path_dict$output_dir, "installation_timing.txt")
    sink(report_file)
    cat("Package Installation Timing Report\\n")
    cat("==================================\\n")
    cat("Generated:", format(Sys.time()), "\\n\\n")
    
    total_time <- 0
    for (res in results) {
        if (!is.null(res)) {
            cat(sprintf("%-20s: %6.1f seconds\\n", res$package, res$duration))
            total_time <- total_time + res$duration
        }
    }
    
    cat("\\nTotal installation time:", round(total_time, 1), "seconds\\n")
    cat("\\nNote: Full Seurat/Slingshot installation typically takes 10-15 minutes\\n")
    cat("due to many dependencies (100+ packages)\\n")
    sink()
    
    cat("\\nReport saved to:", report_file, "\\n")
    cat("End time:", format(Sys.time()), "\\n")
    cat("=== COMPLETE ===\\n")
}'''
    
    static_config = StaticConfig(
        args=[],
        description="Monitor package installation timing",
        tag="analysis"
    )
    
    return NewFunctionBlock(
        id="install_monitor",
        name="package_installation_monitor",
        type=FunctionBlockType.R,
        description="Monitor R package installation timing",
        code=code,
        requirements="",  # Will install packages in the function
        parameters={},
        static_config=static_config
    )


def test_package_installation():
    """Test package installation timing."""
    
    print("\n=== Package Installation Timing Test ===\n")
    
    output_dir = Path("test_outputs/package_timing")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    
    # Create monitoring function
    print("1. Creating installation monitor...")
    fb = create_installation_monitor_block()
    print(f"✓ Created: {fb.name}")
    
    # Prepare execution
    input_dir = output_dir / "input"
    input_dir.mkdir()
    (input_dir / "dummy.txt").write_text("test")
    
    # Execute with monitoring
    print("\n2. Running installation test (this will take a few minutes)...")
    print(f"   Start: {datetime.now()}")
    
    docker_manager = DockerManager()
    executor = RExecutor(docker_manager=docker_manager)
    
    job_dir = output_dir / "job"
    job_dir.mkdir()
    
    # Set reasonable timeout
    original_timeout = config.function_block_timeout
    config.function_block_timeout = 300  # 5 minutes
    
    start = time.time()
    result = executor.execute(
        function_block=fb,
        input_data_path=input_dir,
        output_dir=job_dir,
        parameters={}
    )
    duration = time.time() - start
    
    config.function_block_timeout = original_timeout
    
    print(f"   End: {datetime.now()}")
    print(f"   Total execution time: {duration:.1f} seconds")
    
    # Show results
    print("\n3. Results:")
    
    if result.success:
        print("   ✓ Success!")
        
        # Show timing report
        report_file = job_dir / "installation_timing.txt"
        if report_file.exists():
            print("\n   Installation Timing Report:")
            print("   " + "-" * 50)
            with open(report_file) as f:
                for line in f:
                    print(f"   {line.strip()}")
            print("   " + "-" * 50)
            
        # Extract key output from logs
        if result.logs:
            print("\n   Key installation events:")
            for line in result.logs.split('\n'):
                if any(keyword in line for keyword in ['Installing', 'Duration:', 'ERROR:', 'downloaded', 'DONE']):
                    print(f"   {line.strip()}")
                    
    else:
        print(f"   ✗ Failed: {result.error}")
        if result.stderr:
            print(f"\n   Error output:\n   {result.stderr[:500]}")
            
    # Explain the timing
    print("\n4. Why Slingshot takes so long:")
    print("   - BiocManager installation: ~30 seconds")
    print("   - Seurat dependencies: ~5-8 minutes (50+ packages)")
    print("   - SingleCellExperiment: ~2-3 minutes (Bioconductor packages)")
    print("   - Slingshot itself: ~1-2 minutes")
    print("   - Total: 10-15 minutes for first-time installation")
    print("\n   The Docker image doesn't have these pre-installed to keep it minimal.")
    
    print("\n=== Test Complete ===")


if __name__ == "__main__":
    test_package_installation()