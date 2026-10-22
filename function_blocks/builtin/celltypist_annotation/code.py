def run(path_dict, params):
    """
    Perform cell type annotation using CellTypist.
    
    This function block demonstrates the correct usage of CellTypist API.
    It handles model downloading, annotation, and saves results to the AnnData object.
    """
    import os
    import scanpy as sc
    import celltypist
    import logging
    from pathlib import Path
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Load input data
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    logger.info(f"Loading data from {input_file}")
    adata = sc.read_h5ad(input_file)
    logger.info(f"Loaded data with shape: {adata.shape}")
    
    # Get parameters
    model_name = params.get('model', 'Immune_All_Low.pkl')
    majority_voting = params.get('majority_voting', True)
    over_clustering = params.get('over_clustering', None)
    
    # IMPORTANT: CellTypist expects normalized and log-transformed data
    # Check if data is already normalized
    if 'normalized' not in adata.uns:
        logger.info("Normalizing and log-transforming data for CellTypist")
        # Store raw counts if not already stored
        if adata.raw is None:
            adata.raw = adata.copy()
        
        # Normalize to 10,000 counts per cell
        sc.pp.normalize_total(adata, target_sum=1e4)
        
        # Log transform
        sc.pp.log1p(adata)
        
        # Mark as normalized
        adata.uns['normalized'] = True
    else:
        logger.info("Data already normalized")
    
    # Download models if not already present
    # This is safe to call multiple times - it only downloads if needed
    logger.info("Ensuring CellTypist models are available")
    try:
        celltypist.models.download_models(force_update=False)
        logger.info("CellTypist models ready")
    except Exception as e:
        logger.warning(f"Could not download models: {e}")
        logger.info("Proceeding with annotation - model may be downloaded automatically")
    
    # List available models (optional, for debugging)
    try:
        available_models = celltypist.models.get_all_models()
        logger.info(f"Available CellTypist models: {list(available_models.keys())[:5]}...")  # Show first 5
    except Exception as e:
        logger.warning(f"Could not list models: {e}")
    
    # Perform annotation
    logger.info(f"Running CellTypist annotation with model: {model_name}")
    logger.info(f"Parameters: majority_voting={majority_voting}, over_clustering={over_clustering}")
    
    try:
        # Basic annotation
        if over_clustering:
            predictions = celltypist.annotate(
                adata,
                model=model_name,
                majority_voting=majority_voting,
                over_clustering=over_clustering
            )
        else:
            predictions = celltypist.annotate(
                adata,
                model=model_name,
                majority_voting=majority_voting
            )
        
        logger.info("CellTypist annotation completed successfully")
        
        # Extract predictions and add to AnnData object
        # The predictions object has a predicted_labels attribute
        adata.obs['celltypist_predicted'] = predictions.predicted_labels.predicted_labels
        
        # Add majority voting results if enabled
        if majority_voting and hasattr(predictions.predicted_labels, 'majority_voting'):
            adata.obs['celltypist_majority'] = predictions.predicted_labels.majority_voting
        
        # Add confidence scores if available
        if hasattr(predictions.predicted_labels, 'conf_score'):
            adata.obs['celltypist_conf'] = predictions.predicted_labels.conf_score
        
        # Log summary statistics
        cell_types = adata.obs['celltypist_predicted'].value_counts()
        logger.info(f"Found {len(cell_types)} cell types")
        logger.info(f"Top 5 cell types:\n{cell_types.head()}")
        
    except Exception as e:
        logger.error(f"CellTypist annotation failed: {e}")
        raise
    
    # Create output directory if needed
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    
    # Save the annotated data
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    adata.write(output_file)
    logger.info(f"Saved annotated data to {output_file}")
    
    # Create figures directory
    figures_dir = Path(path_dict['output_dir']) / 'figures'
    figures_dir.mkdir(parents=True, exist_ok=True)
    
    # Create visualization if UMAP exists
    if 'X_umap' in adata.obsm:
        import matplotlib.pyplot as plt
        plt.figure(figsize=(10, 8))
        
        # Plot UMAP colored by CellTypist predictions
        sc.pl.umap(adata, color='celltypist_predicted', 
                   legend_loc='on data', legend_fontsize=8,
                   show=False, save='_celltypist_predictions.pdf')
        
        logger.info("Saved UMAP plot with CellTypist predictions")
    
    # Return the annotated data
    return adata