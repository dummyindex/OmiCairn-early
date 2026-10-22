#!/usr/bin/env python3
"""Extended test for Slingshot with increased timeout and detailed logging."""

import os
import shutil
from pathlib import Path
from datetime import datetime

from omicairn_agent_local.models import (
    NewFunctionBlock, FunctionBlockType, StaticConfig, Arg
)
from omicairn_agent_local.job_executors.r_executor import RExecutor
from omicairn_agent_local.utils.docker_utils import DockerManager
from omicairn_agent_local.config import config


def create_slingshot_function_block():
    """Create a Slingshot function block with enhanced logging."""
    
    code = '''run <- function(path_dict, params) {
    # Log start time
    cat("\\n=== SLINGSHOT ANALYSIS STARTING ===\\n")
    cat("Start time:", format(Sys.time()), "\\n")
    cat("Working directory:", getwd(), "\\n")
    
    # Load libraries with progress messages
    cat("\\nLoading libraries...\\n")
    library(Seurat)
    cat("  ✓ Seurat loaded\\n")
    library(slingshot)
    cat("  ✓ Slingshot loaded\\n")
    library(SingleCellExperiment)
    cat("  ✓ SingleCellExperiment loaded\\n")
    
    # List input directory contents
    cat("\\nInput directory contents:\\n")
    input_files <- list.files(path_dict$input_dir, full.names = FALSE)
    for (f in input_files) {
        cat("  -", f, "\\n")
    }
    
    # Find input file
    input_file <- file.path(path_dict$input_dir, "pbmc3k_seurat_object.rds")
    if (!file.exists(input_file)) {
        # Try alternative name
        input_file <- file.path(path_dict$input_dir, "_node_seuratObject.rds")
    }
    
    if (!file.exists(input_file)) {
        stop("No input file found!")
    }
    
    cat("\\nUsing input file:", input_file, "\\n")
    file_info <- file.info(input_file)
    cat("File size:", file_info$size, "bytes\\n")
    
    # Load Seurat object
    cat("\\nLoading Seurat object...\\n")
    seurat_obj <- readRDS(input_file)
    cat("  ✓ Loaded Seurat object with", ncol(seurat_obj), "cells and", nrow(seurat_obj), "genes\\n")
    
    # Print object structure
    cat("\\nSeurat object structure:\\n")
    cat("  Assays:", names(seurat_obj@assays), "\\n")
    cat("  Reductions:", names(seurat_obj@reductions), "\\n")
    cat("  Metadata columns:", names(seurat_obj@meta.data), "\\n")
    
    # Check for PCA
    if (!"pca" %in% names(seurat_obj@reductions)) {
        cat("\\nPCA not found, computing...\\n")
        seurat_obj <- NormalizeData(seurat_obj, verbose = FALSE)
        seurat_obj <- FindVariableFeatures(seurat_obj, verbose = FALSE)
        seurat_obj <- ScaleData(seurat_obj, verbose = FALSE)
        seurat_obj <- RunPCA(seurat_obj, npcs = 20, verbose = FALSE)
        cat("  ✓ PCA computed\\n")
    }
    
    # Check for clusters
    cluster_col <- NULL
    if ("seurat_clusters" %in% names(seurat_obj@meta.data)) {
        cluster_col <- "seurat_clusters"
    } else if ("RNA_snn_res.0.8" %in% names(seurat_obj@meta.data)) {
        cluster_col <- "RNA_snn_res.0.8"
    } else {
        cat("\\nNo clusters found, creating simple clusters...\\n")
        pca_data <- Embeddings(seurat_obj, "pca")[, 1:5]
        clusters <- kmeans(pca_data, centers = 3)$cluster
        seurat_obj$simple_clusters <- factor(clusters)
        cluster_col <- "simple_clusters"
        cat("  ✓ Created", length(unique(clusters)), "clusters\\n")
    }
    
    cat("\\nUsing cluster column:", cluster_col, "\\n")
    cat("Number of clusters:", length(unique(seurat_obj@meta.data[[cluster_col]])), "\\n")
    
    # Convert to SingleCellExperiment
    cat("\\nConverting to SingleCellExperiment...\\n")
    sce <- as.SingleCellExperiment(seurat_obj)
    cat("  ✓ Converted to SCE\\n")
    
    # Run Slingshot
    cat("\\nRunning Slingshot analysis...\\n")
    cat("  This may take a few minutes...\\n")
    start_sling <- Sys.time()
    
    tryCatch({
        sce <- slingshot(sce, clusterLabels = cluster_col, reducedDim = 'PCA')
        cat("  ✓ Slingshot completed in", round(difftime(Sys.time(), start_sling, units = "secs"), 2), "seconds\\n")
    }, error = function(e) {
        cat("  ✗ Slingshot error:", e$message, "\\n")
        stop(e)
    })
    
    # Extract results
    cat("\\nExtracting pseudotime results...\\n")
    pseudotime <- slingPseudotime(sce)
    
    # Check pseudotime structure
    if (is.matrix(pseudotime)) {
        cat("  Pseudotime is a matrix with", ncol(pseudotime), "lineages\\n")
        lineage_names <- colnames(pseudotime)
        if (is.null(lineage_names)) {
            lineage_names <- paste0("Lineage", 1:ncol(pseudotime))
            colnames(pseudotime) <- lineage_names
        }
    } else {
        cat("  Pseudotime is a vector\\n")
        pseudotime <- matrix(pseudotime, ncol = 1)
        colnames(pseudotime) <- "Lineage1"
    }
    
    # Save outputs
    cat("\\nSaving outputs...\\n")
    
    # Save as CSV
    csv_file <- file.path(path_dict$output_dir, "slingshot_pseudotime.csv")
    pseudotime_df <- as.data.frame(pseudotime)
    pseudotime_df$Cell <- rownames(pseudotime_df)
    pseudotime_df <- pseudotime_df[, c("Cell", setdiff(names(pseudotime_df), "Cell"))]
    write.csv(pseudotime_df, csv_file, row.names = FALSE)
    cat("  ✓ Saved CSV:", csv_file, "\\n")
    
    # Save complete results as RDS
    rds_file <- file.path(path_dict$output_dir, "slingshot_results.rds")
    results <- list(
        sce = sce,
        pseudotime = pseudotime,
        cluster_labels = cluster_col,
        n_lineages = ncol(pseudotime),
        n_cells = nrow(pseudotime)
    )
    saveRDS(results, rds_file)
    cat("  ✓ Saved RDS:", rds_file, "\\n")
    
    # Create summary statistics
    cat("\\nSummary statistics:\\n")
    for (i in 1:ncol(pseudotime)) {
        lineage <- pseudotime[, i]
        valid <- !is.na(lineage)
        cat("  Lineage", i, ":\\n")
        cat("    - Cells:", sum(valid), "\\n")
        cat("    - Min pseudotime:", round(min(lineage[valid]), 3), "\\n")
        cat("    - Max pseudotime:", round(max(lineage[valid]), 3), "\\n")
        cat("    - Mean pseudotime:", round(mean(lineage[valid]), 3), "\\n")
    }
    
    # Save summary
    summary_file <- file.path(path_dict$output_dir, "slingshot_summary.txt")
    sink(summary_file)
    cat("Slingshot Analysis Summary\\n")
    cat("========================\\n")
    cat("Date:", format(Sys.time()), "\\n")
    cat("Input cells:", ncol(seurat_obj), "\\n")
    cat("Clustering:", cluster_col, "\\n")
    cat("Number of clusters:", length(unique(seurat_obj@meta.data[[cluster_col]])), "\\n")
    cat("Number of lineages:", ncol(pseudotime), "\\n")
    cat("\\nLineage statistics:\\n")
    for (i in 1:ncol(pseudotime)) {
        lineage <- pseudotime[, i]
        valid <- !is.na(lineage)
        cat("  Lineage", i, ": n =", sum(valid), ", range = [", 
            round(min(lineage[valid]), 3), ",", round(max(lineage[valid]), 3), "]\\n")
    }
    sink()
    cat("  ✓ Saved summary:", summary_file, "\\n")
    
    cat("\\n=== SLINGSHOT ANALYSIS COMPLETE ===\\n")
    cat("End time:", format(Sys.time()), "\\n")
}'''
    
    # Create function block
    static_config = StaticConfig(
        args=[],
        description="Run Slingshot pseudotime analysis with detailed logging",
        tag="analysis"
    )
    
    fb = NewFunctionBlock(
        id="slingshot_extended",
        name="run_slingshot_extended",
        type=FunctionBlockType.R,
        description="Run Slingshot pseudotime analysis on Seurat object",
        code=code,
        requirements="Seurat\nslingshot\nBioconductor::SingleCellExperiment",
        parameters={},
        static_config=static_config
    )
    
    return fb


def test_slingshot_extended():
    """Test Slingshot with extended timeout and monitoring."""
    
    print("\n=== Extended Slingshot Test ===")
    print(f"Start time: {datetime.now()}")
    
    # Create output directory
    output_dir = Path("test_outputs/slingshot_extended")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Step 1: Create function block
        print("\n1. Creating Slingshot function block...")
        function_block = create_slingshot_function_block()
        print(f"✓ Created: {function_block.name}")
        
        # Step 2: Prepare input data
        print("\n2. Preparing input data...")
        input_dir = output_dir / "input"
        input_dir.mkdir(exist_ok=True)
        
        # Copy test data
        test_data = Path("test_data/pbmc3k_seurat_object.rds")
        if test_data.exists():
            shutil.copy(test_data, input_dir / "pbmc3k_seurat_object.rds")
            print(f"✓ Copied test data ({test_data.stat().st_size:,} bytes)")
        else:
            print("✗ Test data not found!")
            return
            
        # Step 3: Configure extended timeout
        print("\n3. Configuring execution...")
        original_timeout = config.function_block_timeout
        config.function_block_timeout = 1200  # 20 minutes
        print(f"✓ Set timeout to {config.function_block_timeout} seconds")
        
        # Step 4: Execute
        print("\n4. Executing Slingshot (this may take several minutes)...")
        print(f"   Start: {datetime.now()}")
        
        docker_manager = DockerManager()
        executor = RExecutor(docker_manager=docker_manager)
        
        job_dir = output_dir / "job"
        job_dir.mkdir(exist_ok=True)
        
        # Execute with monitoring
        result = executor.execute(
            function_block=function_block,
            input_data_path=input_dir,
            output_dir=job_dir,
            parameters={}
        )
        
        print(f"   End: {datetime.now()}")
        
        # Step 5: Analyze results
        print("\n5. Results:")
        
        if result.success:
            print("✓ Execution successful!")
            print(f"  Duration: {result.duration:.2f} seconds")
            
            # List all output files
            output_files = list(job_dir.glob("*"))
            print(f"\n  Output files ({len(output_files)}):")
            for f in sorted(output_files):
                if f.is_file():
                    size = f.stat().st_size
                    print(f"    - {f.name} ({size:,} bytes)")
            
            # Check specific outputs
            csv_file = job_dir / "slingshot_pseudotime.csv"
            if csv_file.exists():
                print(f"\n✓ Pseudotime CSV found!")
                with open(csv_file) as f:
                    lines = f.readlines()
                    print(f"  Total rows: {len(lines)}")
                    print(f"  Header: {lines[0].strip()}")
                    print(f"  First data row: {lines[1].strip()}")
                    if len(lines) > 2:
                        print(f"  Last data row: {lines[-1].strip()}")
                        
            # Check summary
            summary_file = job_dir / "slingshot_summary.txt"
            if summary_file.exists():
                print(f"\n✓ Summary file found!")
                print("  Contents:")
                with open(summary_file) as f:
                    for line in f:
                        print(f"    {line.rstrip()}")
                        
        else:
            print(f"✗ Execution failed: {result.error}")
            
            # Show logs
            if result.logs:
                print("\nExecution logs:")
                print("=" * 70)
                # Show all logs for debugging
                for i, line in enumerate(result.logs.split('\n')):
                    if line.strip():
                        print(f"{i+1:4d}: {line}")
                print("=" * 70)
                
            if result.stderr:
                print("\nError output:")
                print("=" * 70)
                print(result.stderr)
                print("=" * 70)
                
        # Restore timeout
        config.function_block_timeout = original_timeout
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        
    print(f"\nEnd time: {datetime.now()}")
    print("=== Test Complete ===")
    

if __name__ == "__main__":
    test_slingshot_extended()