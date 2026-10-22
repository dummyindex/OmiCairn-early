"""
Example: How Function Blocks Access Previous Nodes' Files
=========================================================

This example shows how a function block at node 3 can access files
from nodes 1 and 2 in the analysis pipeline.
"""

def run(path_dict, params):
    """Example function block that uses files from previous nodes."""
    import os
    import scanpy as sc
    import pandas as pd
    import matplotlib.pyplot as plt
    
    # Import the previous nodes interface
    from function_block_runtime import previous_nodes
    
    # 1. List all available previous nodes
    print("\n=== Available Previous Nodes ===")
    nodes = previous_nodes.list()
    for node in nodes:
        print(f"Node {node['index']}: {node['name']} (Level {node['level']})")
        print(f"  Description: {node['description']}")
        print(f"  Available files: {len(node['files'])}")
        if node['is_parent']:
            print("  [This is the direct parent node]")
        print()
    
    # 2. Load the current input (from parent node)
    print("=== Loading Current Input ===")
    current_data = sc.read_h5ad(os.path.join(path_dict['input_dir'], '_node_anndata.h5ad'))
    print(f"Current data shape: {current_data.shape}")
    
    # 3. Access QC metrics from node 1 (preprocessing step)
    print("\n=== Accessing QC Metrics from Node 1 ===")
    try:
        qc_metrics = previous_nodes.get_file(1, 'outputs/qc_metrics.csv')
        if qc_metrics is not None:
            print("QC Metrics from preprocessing:")
            print(qc_metrics)
            
            # Use the metrics for comparison
            original_cells = qc_metrics.loc[qc_metrics['metric'] == 'n_cells', 'value'].iloc[0]
            current_cells = current_data.n_obs
            print(f"\nCell count comparison:")
            print(f"  Original: {original_cells}")
            print(f"  Current: {current_cells}")
            print(f"  Retained: {current_cells/original_cells*100:.1f}%")
    except Exception as e:
        print(f"Could not load QC metrics: {e}")
    
    # 4. Access normalization info from node 2
    print("\n=== Accessing Normalization Info from Node 2 ===")
    try:
        norm_info = previous_nodes.get_file(2, 'outputs/normalization_info.csv')
        if norm_info is not None:
            print("Normalization parameters used:")
            print(norm_info)
    except Exception as e:
        print(f"Could not load normalization info: {e}")
    
    # 5. Access highly variable genes from node 2
    print("\n=== Accessing HVG List from Node 2 ===")
    try:
        hvg_genes = previous_nodes.get_file(2, 'outputs/hvg_genes.csv')
        if hvg_genes is not None:
            print(f"Number of highly variable genes: {len(hvg_genes)}")
            print(f"Top 5 HVGs: {list(hvg_genes.index[:5])}")
            
            # Use HVG info for current analysis
            if 'highly_variable' in current_data.var.columns:
                hvg_overlap = set(hvg_genes.index) & set(
                    current_data.var_names[current_data.var['highly_variable']]
                )
                print(f"HVG overlap with current data: {len(hvg_overlap)} genes")
    except Exception as e:
        print(f"Could not load HVG list: {e}")
    
    # 6. Get raw file path without auto-parsing
    print("\n=== Accessing Raw File Path ===")
    try:
        plot_path = previous_nodes.get_file(1, 'outputs/qc_plots.pdf', auto_parse=False)
        if plot_path:
            print(f"QC plots available at: {plot_path}")
            print(f"File size: {plot_path.stat().st_size} bytes")
    except Exception as e:
        print(f"Could not access plot file: {e}")
    
    # 7. Get all files from a specific node
    print("\n=== Getting All Files from Node 1 ===")
    try:
        all_files = previous_nodes.get_all_files(1)
        print(f"Total files from node 1: {len(all_files)}")
        for file_path, data in all_files.items():
            print(f"  - {file_path}: {type(data).__name__}")
    except Exception as e:
        print(f"Could not get all files: {e}")
    
    # 8. Perform analysis using information from multiple nodes
    print("\n=== Integrated Analysis ===")
    
    # Create a summary combining info from multiple nodes
    summary = {
        'current_node': {
            'n_cells': current_data.n_obs,
            'n_genes': current_data.n_vars
        },
        'previous_nodes': {
            'qc_metrics_available': qc_metrics is not None,
            'normalization_info_available': norm_info is not None,
            'hvg_list_available': hvg_genes is not None
        }
    }
    
    # Save outputs
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    
    # Save processed data
    output_file = os.path.join(path_dict['output_dir'], '_node_anndata.h5ad')
    current_data.write(output_file)
    
    # Save summary
    summary_df = pd.DataFrame.from_dict(summary, orient='index')
    summary_df.to_csv(os.path.join(path_dict['output_dir'], 'integrated_summary.csv'))
    
    print("\n=== Analysis Complete ===")
    print(f"Output saved to: {path_dict['output_dir']}")


# Error Handling Best Practices
def safe_access_example(path_dict, params):
    """Example showing safe file access with error handling."""
    from function_block_runtime import previous_nodes
    
    # Always check if nodes are available
    nodes = previous_nodes.list()
    if not nodes:
        print("No previous nodes available - this must be the root node")
        return
    
    # Safe file access with fallbacks
    for node_idx in range(1, len(nodes) + 1):
        try:
            data = previous_nodes.get_file(node_idx, 'outputs/_node_anndata.h5ad')
            if data is not None:
                print(f"Successfully loaded data from node {node_idx}")
                # Process the data
                break
        except ValueError as e:
            print(f"Node {node_idx} not accessible: {e}")
        except Exception as e:
            print(f"Error accessing node {node_idx}: {e}")
    else:
        print("Could not load data from any previous node")
        # Implement fallback logic


# Advanced Usage: Conditional Processing
def conditional_processing_example(path_dict, params):
    """Example of conditional processing based on previous nodes."""
    from function_block_runtime import previous_nodes
    import scanpy as sc
    import os
    
    # Load current data
    adata = sc.read_h5ad(os.path.join(path_dict['input_dir'], '_node_anndata.h5ad'))
    
    # Check what processing has been done
    nodes = previous_nodes.list()
    
    # Look for specific processing steps
    has_normalization = any('normali' in node['name'].lower() for node in nodes)
    has_clustering = any('cluster' in node['name'].lower() for node in nodes)
    
    print(f"Previous processing detected:")
    print(f"  Normalization: {has_normalization}")
    print(f"  Clustering: {has_clustering}")
    
    # Conditionally apply processing
    if not has_normalization:
        print("No normalization detected, applying normalization...")
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
    
    if has_clustering:
        # Try to load cluster labels from previous node
        for node in nodes:
            if 'cluster' in node['name'].lower():
                try:
                    cluster_data = previous_nodes.get_file(
                        node['index'], 
                        'outputs/cluster_labels.csv'
                    )
                    if cluster_data is not None:
                        print(f"Loading clusters from node {node['index']}")
                        adata.obs['previous_clusters'] = cluster_data['cluster']
                        break
                except:
                    pass
    
    # Continue with analysis...
    os.makedirs(path_dict['output_dir'], exist_ok=True)
    adata.write(os.path.join(path_dict['output_dir'], '_node_anndata.h5ad'))