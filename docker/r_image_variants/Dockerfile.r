# R execution environment for omicairn-agent-local
FROM r-base:4.4.3

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    libfontconfig1-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libfreetype6-dev \
    libpng-dev \
    libtiff5-dev \
    libjpeg-dev \
    libhdf5-dev \
    libgit2-dev \
    libglpk-dev \
    libgmp3-dev \
    libicu-dev \
    libblas-dev \
    liblapack-dev \
    libopenblas-dev \
    libpcre2-dev \
    libreadline-dev \
    libxt-dev \
    libcairo2-dev \
    libxt-dev \
    libx11-dev \
    libmagick++-dev \
    libgsl-dev \
    python3 \
    python3-pip \
    python3-dev \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages for anndata bridge
RUN pip3 install "anndata>=0.9.0" h5py numpy pandas scipy

# Set CRAN mirror
RUN R -e "options(repos = c(CRAN = 'https://cloud.r-project.org'))"

# Install basic R packages
RUN R -e "install.packages(c('devtools', 'remotes', 'BiocManager'), repos='https://cloud.r-project.org')"
RUN R -e "install.packages(c('tidyverse', 'Matrix', 'data.table', 'jsonlite', 'R6', 'httr'), repos='https://cloud.r-project.org')"

# Install visualization packages
RUN R -e "install.packages(c('ggplot2', 'patchwork', 'viridis', 'RColorBrewer', 'pheatmap', 'circlize'), repos='https://cloud.r-project.org')"
RUN R -e "install.packages(c('plotly', 'ggrepel', 'cowplot', 'ggpubr', 'ggsci'), repos='https://cloud.r-project.org')"

# Install Bioconductor packages
RUN R -e "BiocManager::install(c('SingleCellExperiment', 'scater', 'scran', 'edgeR', 'limma', 'DESeq2'), update=FALSE, ask=FALSE)"
RUN R -e "BiocManager::install(c('clusterProfiler', 'org.Hs.eg.db', 'org.Mm.eg.db', 'DOSE', 'enrichplot'), update=FALSE, ask=FALSE)"
RUN R -e "BiocManager::install(c('monocle3', 'slingshot', 'tradeSeq'), update=FALSE, ask=FALSE)"

# Install Seurat and related packages
RUN R -e "install.packages('Seurat', repos='https://cloud.r-project.org')"
RUN R -e "install.packages(c('SeuratObject', 'SeuratData', 'SeuratWrappers'), repos='https://cloud.r-project.org')"

# Install additional single-cell packages
RUN R -e "devtools::install_github('immunogenomics/presto')"
RUN R -e "devtools::install_github('jokergoo/ComplexHeatmap')"
RUN R -e "devtools::install_github('jinworks/CellChat')"
RUN R -e "devtools::install_github('cole-trapnell-lab/monocle3')"
RUN R -e "devtools::install_github('velocyto-team/velocyto.R')"

# Install anndata interface
RUN R -e "install.packages('reticulate', repos='https://cloud.r-project.org')"
RUN R -e "devtools::install_github('mojaveazure/seurat-disk')"
RUN R -e "install.packages('anndata', repos='https://cloud.r-project.org')"

# Configure reticulate to use system Python
RUN R -e "reticulate::use_python('/usr/bin/python3', required=TRUE)"

# Create necessary directories
RUN mkdir -p /workspace/input /workspace/output/figures /workspace/tmp

# Set working directory
WORKDIR /workspace

# Copy R library installation script (build from the repository root with context docker/: docker build -f docker/r_image_variants/Dockerfile.r docker/)
COPY install-image-builtin-libs.R /workspace/
RUN Rscript /workspace/install-image-builtin-libs.R

# Default command
CMD ["Rscript", "/workspace/run.R"]