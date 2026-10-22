#!/usr/bin/env Rscript
# Convert Seurat object to _node_sc_matrix format
#
# This function block converts a Seurat object to a structured format that can be
# read by both Python and R. It creates a _node_sc_matrix folder with subfolders
# following the AnnData structure (obs, var, obsm, varm, layers, etc.).

run <- function(path_dict, params) {
    # Load required libraries
    library(Seurat)
    library(Matrix)
    library(jsonlite)
    
    input_dir <- path_dict$input_dir
    output_dir <- path_dict$output_dir
    
    # Find Seurat object file
    rds_files <- list.files(input_dir, pattern = "_node_seuratObject\\.rds$", full.names = TRUE)
    if (length(rds_files) == 0) {
        stop("No _node_seuratObject.rds file found in input directory")
    }
    
    seurat_path <- rds_files[1]
    cat("Loading Seurat object from:", seurat_path, "\n")
    
    # Load Seurat object
    srt <- readRDS(seurat_path)
    cat("Loaded Seurat object with", ncol(srt), "cells and", nrow(srt), "features\n")
    
    # Create output structure
    sc_matrix_dir <- file.path(output_dir, "_node_sc_matrix")
    dir.create(sc_matrix_dir, showWarnings = FALSE)
    
    # Helper function to write matrix
    write_matrix <- function(mat, path, name) {
        if (inherits(mat, "sparseMatrix")) {
            # Write as MTX format for sparse matrices
            writeMM(mat, file.path(path, paste0(name, ".mtx")))
            return(list(type = "sparse", format = "mtx", shape = dim(mat)))
        } else {
            # Write as CSV for dense matrices
            write.csv(mat, file.path(path, paste0(name, ".csv")), row.names = FALSE)
            return(list(type = "dense", format = "csv", shape = dim(mat)))
        }
    }
    
    # Create metadata list
    metadata <- list(
        source = "seurat",
        shape = c(ncol(srt), nrow(srt)),
        components = list()
    )
    
    # 1. Write cell and gene names
    writeLines(colnames(srt), file.path(sc_matrix_dir, "obs_names.txt"))
    writeLines(rownames(srt), file.path(sc_matrix_dir, "var_names.txt"))
    
    # 2. Write main expression matrix (use counts or data)
    # Get the default assay
    default_assay <- DefaultAssay(srt)
    assay_obj <- srt[[default_assay]]
    
    # Try to get counts first, then data
    if (length(GetAssayData(assay_obj, slot = "counts")) > 0) {
        X <- GetAssayData(assay_obj, slot = "counts")
    } else {
        X <- GetAssayData(assay_obj, slot = "data")
    }
    
    # Transpose to match AnnData format (cells x genes)
    X <- t(X)
    x_info <- write_matrix(X, sc_matrix_dir, "X")
    metadata$components$X <- x_info
    
    # 3. Write obs (cell metadata)
    if (ncol(srt@meta.data) > 0) {
        obs_dir <- file.path(sc_matrix_dir, "obs")
        dir.create(obs_dir, showWarnings = FALSE)
        
        obs_info <- list()
        for (col in colnames(srt@meta.data)) {
            df <- data.frame(srt@meta.data[[col]])
            colnames(df) <- col
            write.csv(df, file.path(obs_dir, paste0(col, ".csv")), row.names = FALSE)
            obs_info[[col]] <- list(
                dtype = class(srt@meta.data[[col]])[1],
                shape = nrow(srt@meta.data)
            )
        }
        metadata$components$obs <- obs_info
    }
    
    # 4. Write var (gene metadata)
    # Get feature metadata from the assay
    feature_meta <- assay_obj@meta.features
    if (ncol(feature_meta) > 0) {
        var_dir <- file.path(sc_matrix_dir, "var")
        dir.create(var_dir, showWarnings = FALSE)
        
        var_info <- list()
        for (col in colnames(feature_meta)) {
            df <- data.frame(feature_meta[[col]])
            colnames(df) <- col
            write.csv(df, file.path(var_dir, paste0(col, ".csv")), row.names = FALSE)
            var_info[[col]] <- list(
                dtype = class(feature_meta[[col]])[1],
                shape = nrow(feature_meta)
            )
        }
        metadata$components$var <- var_info
    }
    
    # 5. Write obsm (cell embeddings/reductions)
    if (length(srt@reductions) > 0) {
        obsm_dir <- file.path(sc_matrix_dir, "obsm")
        dir.create(obsm_dir, showWarnings = FALSE)
        
        obsm_info <- list()
        for (reduction_name in names(srt@reductions)) {
            reduction <- srt@reductions[[reduction_name]]
            embeddings <- Embeddings(reduction)
            
            # Convert reduction name to AnnData format
            anndata_key <- paste0("X_", tolower(reduction_name))
            
            # Write embeddings as dense matrix
            write.csv(embeddings, file.path(obsm_dir, paste0(anndata_key, ".csv")), 
                     row.names = FALSE)
            obsm_info[[anndata_key]] <- list(
                type = "dense",
                format = "csv",
                shape = dim(embeddings)
            )
        }
        metadata$components$obsm <- obsm_info
    }
    
    # 6. Write layers (additional assays)
    # Get all assays except the default one
    all_assays <- Assays(srt)
    other_assays <- setdiff(all_assays, default_assay)
    
    if (length(other_assays) > 0) {
        layers_dir <- file.path(sc_matrix_dir, "layers")
        dir.create(layers_dir, showWarnings = FALSE)
        
        layers_info <- list()
        for (assay_name in other_assays) {
            assay_data <- GetAssayData(srt[[assay_name]], slot = "counts")
            if (length(assay_data) == 0) {
                assay_data <- GetAssayData(srt[[assay_name]], slot = "data")
            }
            
            # Transpose to match AnnData format
            assay_data <- t(assay_data)
            layer_info <- write_matrix(assay_data, layers_dir, assay_name)
            layers_info[[assay_name]] <- layer_info
        }
        metadata$components$layers <- layers_info
    }
    
    # 7. Write metadata file
    write(toJSON(metadata, pretty = TRUE, auto_unbox = TRUE), 
          file.path(sc_matrix_dir, "metadata.json"))
    
    # Copy original files to output
    file.copy(seurat_path, file.path(output_dir, "_node_seuratObject.rds"))
    
    # Check if AnnData exists and copy it
    h5ad_files <- list.files(input_dir, pattern = "_node_anndata\\.h5ad$", full.names = TRUE)
    if (length(h5ad_files) > 0) {
        file.copy(h5ad_files[1], file.path(output_dir, "_node_anndata.h5ad"))
    }
    
    cat("Successfully converted Seurat object to _node_sc_matrix format\n")
    cat("Output directory:", sc_matrix_dir, "\n")
    cat("Components written:", paste(names(metadata$components), collapse = ", "), "\n")
    
    return(list(
        status = "success",
        sc_matrix_path = sc_matrix_dir,
        components = names(metadata$components),
        shape = metadata$shape
    ))
}