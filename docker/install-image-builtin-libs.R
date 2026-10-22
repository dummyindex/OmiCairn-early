# Additional R libraries installation for omicairn minimal image
# Optimized for faster build times with essential packages only

# Set options for faster installation
options(repos = c(CRAN = 'https://cloud.r-project.org'))
options(timeout = 600)
options(Ncpus = 4)  # Use multiple cores for compilation

# Essential packages for single-cell analysis
message("Installing essential packages...")

# Core dependencies
install.packages(c(
  "Matrix", "irlba", "igraph", "RANN", 
  "RcppAnnoy", "uwot", "FNN", "leiden",
  "fitdistrplus", "lmtest", "MASS", "mgcv",
  "pbapply", "future", "future.apply"
))

# Seurat is already installed in Dockerfile
message("Seurat already installed")

# Install essential Bioconductor packages
if (!requireNamespace("BiocManager", quietly = TRUE)) {
  install.packages("BiocManager")
}

# Set Bioconductor version
BiocManager::install(version = "3.19", ask = FALSE, update = FALSE)

# Essential single-cell packages
message("Installing essential Bioconductor packages...")
BiocManager::install(c(
  'SingleCellExperiment', 'SummarizedExperiment',
  'S4Vectors', 'BiocGenerics', 'DelayedArray',
  'HDF5Array', 'rhdf5', 'limma', 'edgeR'
), ask = FALSE, update = FALSE)

# Trajectory analysis essentials
message("Installing trajectory analysis packages...")
BiocManager::install(c('slingshot', 'TrajectoryUtils'), ask = FALSE, update = FALSE)

# Try to install optional packages (don't fail if these don't work)
message("Installing optional packages...")
tryCatch({
  # Visualization
  install.packages(c("ggridges", "ggforce", "ggrastr"), quiet = TRUE)
  
  # Additional analysis
  install.packages(c("ranger", "glmnet"), quiet = TRUE)
  
  # Monocle3 dependencies (simplified)
  BiocManager::install(c('lme4', 'batchelor'), ask = FALSE, update = FALSE)
  
  message("Optional packages installed")
}, error = function(e) {
  message("Some optional packages failed to install (continuing...)")
})

# Test core functionality
message("\nTesting core packages...")
essential_packages <- c(
  "Seurat", "SingleCellExperiment", "slingshot", 
  "ggplot2", "reticulate"
)

for (pkg in essential_packages) {
  if (requireNamespace(pkg, quietly = TRUE)) {
    message(paste("✓", pkg, "installed"))
  } else {
    warning(paste("✗", pkg, "NOT installed"))
  }
}

message("\nPackage installation completed!")