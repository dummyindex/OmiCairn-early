#!/usr/bin/env python3
"""Direct test for Slingshot R function block - create and execute manually."""

import os
import shutil
from pathlib import Path

from omicairn_agent_local.models import (
    NewFunctionBlock, FunctionBlockType, StaticConfig, Arg
)
from omicairn_agent_local.job_executors.r_executor import RExecutor
from omicairn_agent_local.utils.docker_utils import DockerManager


def create_slingshot_function_block():
    """Manually create a Slingshot function block."""
    
    code = '''run <- function(path_dict, params) {
    library(Seurat)
    library(slingshot)
    library(SingleCellExperiment)
    
    # Get input file - check multiple possible names
    input_files <- c(
        file.path(path_dict$input_dir, "_node_seuratObject.rds"),
        file.path(path_dict$input_dir, "pbmc3k_seurat_object.rds"),
        file.path(path_dict$input_dir, "seurat_object.rds")
    )
    
    input_file <- NULL
    for (f in input_files) {
        if (file.exists(f)) {
            input_file <- f
            cat("Found input file:", f, "\\n")
            break
        }
    }
    
    if (is.null(input_file)) {
        stop("No input file found. Searched for:", paste(input_files, collapse=", "))
    }
    
    # Read Seurat object
    cat("Loading Seurat object...\\n")
    seurat_obj <- readRDS(input_file)
    
    # Check if required data exists
    if (!"pca" %in% names(seurat_obj@reductions)) {
        cat("PCA not found, running PCA...\\n")
        seurat_obj <- NormalizeData(seurat_obj)
        seurat_obj <- FindVariableFeatures(seurat_obj)
        seurat_obj <- ScaleData(seurat_obj)
        seurat_obj <- RunPCA(seurat_obj, npcs = 20)
    }
    
    # Check for clusters
    if (!"seurat_clusters" %in% colnames(seurat_obj@meta.data)) {
        cat("Clusters not found, using simple clustering...\\n")
        # Create simple clusters based on first PC
        pca_data <- Embeddings(seurat_obj, "pca")
        seurat_obj$seurat_clusters <- factor(kmeans(pca_data[,1:5], centers = 3)$cluster)
    }
    
    # Convert to SingleCellExperiment
    cat("Converting to SingleCellExperiment...\\n")
    sce <- as.SingleCellExperiment(seurat_obj)
    
    # Run Slingshot
    cat("Running Slingshot...\\n")
    sce <- slingshot(sce, clusterLabels = 'seurat_clusters', reducedDim = 'PCA')
    
    # Extract pseudotime
    pseudotime <- slingPseudotime(sce)
    
    # Save results
    output_file <- file.path(path_dict$output_dir, "slingshot_pseudotime.csv")
    cat("Saving pseudotime to:", output_file, "\\n")
    
    # Convert to data frame
    if (is.matrix(pseudotime)) {
        pseudotime_df <- as.data.frame(pseudotime)
        pseudotime_df$Cell <- rownames(pseudotime_df)
        pseudotime_df <- pseudotime_df[, c("Cell", setdiff(names(pseudotime_df), "Cell"))]
    } else {
        pseudotime_df <- data.frame(
            Cell = names(pseudotime),
            Pseudotime = as.numeric(pseudotime)
        )
    }
    
    write.csv(pseudotime_df, output_file, row.names = FALSE)
    
    # Also save as RDS
    rds_output <- file.path(path_dict$output_dir, "slingshot_results.rds")
    saveRDS(list(sce = sce, pseudotime = pseudotime), rds_output)
    
    # Save updated Seurat object
    seurat_output <- file.path(path_dict$output_dir, "_node_seuratObject.rds")
    saveRDS(seurat_obj, seurat_output)
    
    cat("Analysis complete!\\n")
    cat("Files saved:\\n")
    cat("  -", output_file, "\\n")
    cat("  -", rds_output, "\\n")
    cat("  -", seurat_output, "\\n")
}'''
    
    # Create function block
    static_config = StaticConfig(
        args=[],
        description="Run Slingshot pseudotime analysis",
        tag="analysis"
    )
    
    fb = NewFunctionBlock(
        id="slingshot_test",
        name="run_slingshot_pseudotime",
        type=FunctionBlockType.R,
        description="Run Slingshot pseudotime analysis on Seurat object",
        code=code,
        requirements="Seurat\nslingshot\nBioconductor::SingleCellExperiment",
        parameters={},
        static_config=static_config
    )
    
    return fb


def test_slingshot_direct():
    """Test Slingshot execution directly."""
    
    print("\n=== Direct Slingshot Test ===\n")
    
    # Create output directory
    output_dir = Path("test_outputs/slingshot_direct")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Step 1: Create function block
        print("1. Creating Slingshot function block...")
        function_block = create_slingshot_function_block()
        print(f"✓ Created: {function_block.name} (type: {function_block.type})")
        
        # Step 2: Prepare input data
        print("\n2. Preparing input data...")
        input_dir = output_dir / "input"
        input_dir.mkdir(exist_ok=True)
        
        # Copy test data
        test_data = Path("test_data/pbmc3k_seurat_object.rds")
        if test_data.exists():
            shutil.copy(test_data, input_dir / "pbmc3k_seurat_object.rds")
            print(f"✓ Copied test data to {input_dir}")
        else:
            print("✗ Test data not found!")
            return
            
        # Step 3: Execute
        print("\n3. Executing Slingshot...")
        
        docker_manager = DockerManager()
        executor = RExecutor(docker_manager=docker_manager)
        
        job_dir = output_dir / "job"
        job_dir.mkdir(exist_ok=True)
        
        result = executor.execute(
            function_block=function_block,
            input_data_path=input_dir,
            output_dir=job_dir,
            parameters={}
        )
        
        # Step 4: Check results
        print("\n4. Results:")
        
        if result.success:
            print("✓ Execution successful!")
            
            # List output files
            output_files = list(job_dir.glob("*"))
            print(f"\nOutput files ({len(output_files)}):")
            for f in output_files:
                if f.is_file():
                    print(f"  - {f.name} ({f.stat().st_size} bytes)")
                    
            # Check for CSV output
            csv_files = list(job_dir.glob("*.csv"))
            if csv_files:
                print(f"\n✓ Found CSV output: {csv_files[0].name}")
                # Show first few lines
                with open(csv_files[0]) as f:
                    lines = f.readlines()[:5]
                    print("  First few lines:")
                    for line in lines:
                        print(f"    {line.strip()}")
            else:
                print("\n⚠️  No CSV output found")
                
        else:
            print(f"✗ Execution failed: {result.error}")
            if result.logs:
                print("\nLogs:")
                print("-" * 60)
                print(result.logs[:1500])
                print("-" * 60)
                
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        
    print("\n=== Test Complete ===")
    

if __name__ == "__main__":
    test_slingshot_direct()