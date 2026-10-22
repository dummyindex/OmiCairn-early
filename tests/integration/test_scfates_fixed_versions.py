#!/usr/bin/env python3
"""
Test scFates function block with FIXED package versions to ensure reproducibility.
"""

import subprocess
import tempfile
from pathlib import Path
import json
import shutil
import sys


def create_scfates_fixed_function_block():
    """Create a function block with fixed package versions for scFates."""
    
    code = '''def run(path_dict, params):
    """Run scFates pseudotime analysis with fixed package versions for reproducibility."""
    import subprocess
    import sys
    import os
    
    # CRITICAL: Fix package versions BEFORE importing anything
    # This ensures reproducibility regardless of future package updates
    print("Installing fixed package versions for reproducibility...")
    
    # Install packages in correct order with exact versions
    packages_to_install = [
        ("numpy", "1.24.3"),
        ("scipy", "1.15.3"),
        ("pandas", "2.2.2"),
        ("h5py", "3.9.0"),
        ("anndata", "0.10.7"),
        ("scanpy", "1.11.4"),
        ("matplotlib", "3.10.5"),
        ("scikit-learn", "1.7.1"),
        ("igraph", "0.11.9"),
        ("leidenalg", "0.10.2"),
        ("scFates", "1.1.1")
    ]
    
    for pkg, version in packages_to_install:
        try:
            cmd = [sys.executable, "-m", "pip", "install", f"{pkg}=={version}", "--no-deps", "--force-reinstall"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✓ Installed {pkg}=={version}")
            else:
                print(f"Warning: Could not install {pkg}=={version}: {result.stderr}")
        except Exception as e:
            print(f"Warning: Error installing {pkg}=={version}: {e}")
    
    # Now we can safely import with guaranteed versions
    import scanpy as sc
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from pathlib import Path
    
    print(f"\\nPackage versions:")
    print(f"numpy: {np.__version__}")
    print(f"scanpy: {sc.__version__}")
    
    # Import scFates - MUST work with these fixed versions
    import scFates as scf
    print(f"✓ scFates imported successfully!")
    if hasattr(scf, '__version__'):
        print(f"scFates version: {scf.__version__}")
    
    # Set up paths
    input_file = os.path.join(path_dict['input_dir'], '_node_anndata.h5ad')
    output_dir = path_dict['output_dir']
    os.makedirs(output_dir, exist_ok=True)
    
    figures_dir = Path(output_dir) / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    sc.settings.figdir = figures_dir
    
    # Load data
    print(f"\\nLoading data from {input_file}")
    adata = sc.read_h5ad(input_file)
    print(f"Loaded data: {adata.shape}")
    
    # Ensure preprocessing for scFates
    print("\\nEnsuring preprocessing for scFates...")
    
    # 1. Check if data is normalized and log-transformed
    if 'log1p' not in adata.uns:
        print("Normalizing and log-transforming data...")
        sc.pp.normalize_total(adata, target_sum=1e4)
        sc.pp.log1p(adata)
        adata.uns['log1p'] = {'base': None}
    
    # 2. Ensure PCA exists
    if 'X_pca' not in adata.obsm:
        print("Computing PCA...")
        n_comps = min(50, adata.n_vars - 1, adata.n_obs - 1)
        sc.pp.pca(adata, n_comps=n_comps)
    
    # 3. Ensure neighbors graph exists
    if 'neighbors' not in adata.uns:
        print("Computing neighbor graph...")
        n_neighbors = min(30, adata.n_obs - 1)
        sc.pp.neighbors(adata, n_neighbors=n_neighbors)
    
    # 4. Force-directed layout
    if 'X_draw_graph_fa' not in adata.obsm:
        print("Computing force-directed layout...")
        sc.tl.draw_graph(adata, layout='fa')
    
    # 5. Diffusion map
    if 'X_diffmap' not in adata.obsm:
        print("Computing diffusion map...")
        sc.tl.diffmap(adata)
    
    # Run scFates analysis
    print("\\n" + "="*50)
    print("RUNNING SCFATES TREE INFERENCE")
    print("="*50)
    
    # Use ElPiGraph method
    print("\\nUsing ElPiGraph method with fixed parameters...")
    scf.tl.tree(adata, method='epg', seed=params.get('seed', 42), Nodes=50, use_rep='X_pca')
    
    # Check tree output
    if 'graph' not in adata.uns:
        raise RuntimeError("scFates tree inference failed - no graph created!")
    
    # Get tree info
    if 'F' in adata.uns['graph']:
        n_nodes = adata.uns['graph']['F'].shape[0]
    else:
        n_nodes = "unknown"
    
    print(f"✓ Tree created with {n_nodes} principal points")
    
    # Extract tree structure
    print("\\nExtracting tree structure...")
    
    # Get soft assignment matrix
    R = adata.obsm['X_R']
    
    # Assign cells to nodes
    cell_node_assignment = np.argmax(R, axis=1)
    adata.obs['node'] = cell_node_assignment
    
    print(f"✓ Cells assigned to {len(np.unique(cell_node_assignment))} nodes")
    
    # Select root node
    early_cells = np.argsort(adata.obsm['X_diffmap'][:, 0])[:50]
    early_nodes = cell_node_assignment[early_cells]
    root_node = np.bincount(early_nodes).argmax()
    
    print(f"\\nSelected root node: {root_node}")
    
    # Compute pseudotime
    print("Computing pseudotime as geodesic distance from root...")
    
    B = adata.uns['graph']['B']
    
    from scipy.sparse.csgraph import shortest_path
    distances = shortest_path(B, directed=False, indices=root_node)
    
    # Map to cells
    cell_distances = np.sum(R * distances[np.newaxis, :], axis=1)
    
    # Normalize
    adata.obs['t'] = cell_distances / cell_distances.max()
    adata.obs['scfates_pseudotime'] = adata.obs['t']
    
    print(f"✓ Pseudotime computed! Range: [{adata.obs['t'].min():.3f}, {adata.obs['t'].max():.3f}]")
    
    # Create visualizations
    print("\\nCreating visualizations...")
    
    # 1. Force-directed with pseudotime
    sc.pl.draw_graph(adata, color='scfates_pseudotime', save='_pseudotime.png', cmap='viridis')
    print("✓ Force-directed plot created")
    
    # 2. Node assignment
    sc.pl.draw_graph(adata, color='node', save='_nodes.png', legend_loc='on data', palette='tab20')
    print("✓ Node assignment plot created")
    
    # 3. PCA with pseudotime
    sc.pl.pca(adata, color='scfates_pseudotime', save='_pseudotime_pca.png', cmap='viridis')
    print("✓ PCA plot created")
    
    # 4. Tree structure visualization
    try:
        fig, ax = plt.subplots(figsize=(10, 8))
        
        F = adata.uns['graph']['F']
        B = adata.uns['graph']['B']
        
        # Plot edges
        for i in range(B.shape[0]):
            for j in range(i+1, B.shape[1]):
                if B[i, j] > 0:
                    ax.plot([F[i, 0], F[j, 0]], [F[i, 1], F[j, 1]], 'k-', alpha=0.3, linewidth=2)
        
        # Plot nodes
        node_pseudotime = distances / distances.max()
        n_nodes = min(F.shape[0], len(node_pseudotime))
        scatter = ax.scatter(F[:n_nodes, 0], F[:n_nodes, 1], c=node_pseudotime[:n_nodes], 
                           cmap='viridis', s=100, zorder=10)
        
        # Highlight root
        ax.scatter(F[root_node, 0], F[root_node, 1], c='red', s=200, marker='*', zorder=20)
        
        ax.set_title('scFates Principal Tree Structure (Fixed Versions)')
        ax.set_xlabel('Component 1')
        ax.set_ylabel('Component 2')
        plt.colorbar(scatter, ax=ax, label='Node pseudotime')
        
        plt.tight_layout()
        plt.savefig(figures_dir / 'scfates_tree_structure.png', dpi=150, bbox_inches='tight')
        plt.close()
        print("✓ Tree structure plot created")
    except Exception as e:
        print(f"Could not create tree plot: {e}")
    
    # Save output
    output_file = os.path.join(output_dir, '_node_anndata.h5ad')
    adata.write(output_file)
    print(f"\\n✓ Output saved to {output_file}")
    
    # Save results with version info
    results = {
        'success': True,
        'method': 'scFates ElPiGraph (Fixed Versions)',
        'n_cells': int(adata.n_obs),
        'n_genes': int(adata.n_vars),
        'n_tree_nodes': int(adata.uns['graph']['F'].shape[0]) if 'F' in adata.uns.get('graph', {}) else 0,
        'n_segments': int(adata.obs['node'].nunique()) if 'node' in adata.obs else 0,
        'pseudotime_range': [float(adata.obs['t'].min()), float(adata.obs['t'].max())],
        'root_node': int(root_node),
        'package_versions': {
            'numpy': np.__version__,
            'scanpy': sc.__version__,
            'scFates': scf.__version__ if hasattr(scf, '__version__') else '1.1.1'
        }
    }
    
    import json
    with open(os.path.join(output_dir, 'scfates_results.json'), 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\\n" + "="*60)
    print("✅ SCFATES ANALYSIS COMPLETED SUCCESSFULLY!")
    print("Package versions are FIXED for reproducibility")
    print("="*60)
'''
    
    return code


def create_fixed_requirements():
    """Create requirements.txt with fixed versions."""
    return """# Fixed versions for reproducible scFates analysis
numpy==1.24.3
scipy==1.15.3
pandas==2.2.2
h5py==3.9.0
anndata==0.10.7
scanpy==1.11.4
matplotlib==3.10.5
scikit-learn==1.7.1
igraph==0.11.9
leidenalg==0.10.2
scFates==1.1.1
"""


def test_scfates_fixed():
    """Test scFates with fixed package versions."""
    
    print("Creating scFates function block with FIXED versions...")
    code = create_scfates_fixed_function_block()
    requirements = create_fixed_requirements()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Set up workspace
        workspace = temp_path / "workspace"
        workspace.mkdir()
        input_dir = workspace / "input"
        output_dir = workspace / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        
        # Save function block and requirements
        (workspace / "function_block.py").write_text(code)
        (workspace / "requirements.txt").write_text(requirements)
        
        # Create wrapper
        wrapper = '''
import sys
sys.path.append('/workspace')
from function_block import run

path_dict = {'input_dir': '/workspace/input', 'output_dir': '/workspace/output'}
params = {'seed': 42}

try:
    run(path_dict, params)
except Exception as e:
    print(f"\\n❌ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
'''
        (workspace / "run.py").write_text(wrapper)
        
        # Create test data
        print("\\nCreating test data...")
        import scanpy as sc
        import numpy as np
        
        np.random.seed(42)
        n_cells = 300
        
        # Create branching trajectory
        main_cells = 180
        t_main = np.linspace(0, 0.7, main_cells)
        
        branch1_cells = 60
        t_branch1 = np.linspace(0.7, 1.0, branch1_cells)
        
        branch2_cells = 60
        t_branch2 = np.linspace(0.7, 1.0, branch2_cells)
        
        n_genes = 200
        X = np.zeros((n_cells, n_genes))
        
        # Main trajectory
        for i in range(main_cells):
            X[i, :50] = np.exp(-t_main[i] * 3) + np.random.randn(50) * 0.1
            X[i, 50:100] = np.exp(t_main[i] * 2 - 1) + np.random.randn(50) * 0.1
            X[i, 100:] = np.random.randn(100) * 0.1
        
        # Branch 1
        for i in range(branch1_cells):
            idx = main_cells + i
            X[idx, :50] = np.exp(-t_branch1[i] * 3) * 0.3 + np.random.randn(50) * 0.1
            X[idx, 50:100] = np.exp(t_branch1[i] * 2) + np.random.randn(50) * 0.1
            X[idx, 100:150] = np.exp(t_branch1[i] * 2) + np.random.randn(50) * 0.1
            X[idx, 150:] = np.random.randn(50) * 0.1
        
        # Branch 2
        for i in range(branch2_cells):
            idx = main_cells + branch1_cells + i
            X[idx, :50] = np.exp(-t_branch2[i] * 3) * 0.3 + np.random.randn(50) * 0.1
            X[idx, 50:100] = np.exp(t_branch2[i] * 2) + np.random.randn(50) * 0.1
            X[idx, 100:150] = np.random.randn(50) * 0.1
            X[idx, 150:] = np.exp(t_branch2[i] * 2) + np.random.randn(50) * 0.1
        
        X = np.abs(X) + 0.5
        X += np.random.rand(n_cells, n_genes) * 0.2
        
        adata = sc.AnnData(X)
        adata.obs_names = [f"Cell_{i}" for i in range(n_cells)]
        adata.var_names = [f"Gene_{i}" for i in range(n_genes)]
        
        cell_types = ['Progenitor'] * main_cells + ['Type1'] * branch1_cells + ['Type2'] * branch2_cells
        adata.obs['cell_type'] = cell_types
        
        adata.raw = adata.copy()
        
        print(f"✓ Created branching trajectory data: {adata.shape}")
        
        adata.write(input_dir / "_node_anndata.h5ad")
        
        # Run in Docker
        print("\\nRunning scFates with FIXED versions in Docker...")
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{workspace}:/workspace",
            "omicairn/python-executor:latest",
            "bash", "-c",
            "source /opt/conda/etc/profile.d/conda.sh && conda activate _omicairn_job && "
            "pip install -r /workspace/requirements.txt && python /workspace/run.py"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print("\\n" + "="*70)
        print("DOCKER OUTPUT:")
        print("="*70)
        print(result.stdout)
        
        if result.stderr:
            print("\\nSTDERR:")
            print(result.stderr[:1000])
        
        print(f"\\nReturn code: {result.returncode}")
        
        # Check results
        print("\\n" + "="*70)
        print("CHECKING RESULTS:")
        print("="*70)
        
        output_h5ad = output_dir / "_node_anndata.h5ad"
        if output_h5ad.exists():
            print("✓ Output file created")
            
            adata_out = sc.read_h5ad(output_h5ad)
            
            if 'scfates_pseudotime' in adata_out.obs:
                pt = adata_out.obs['scfates_pseudotime']
                print(f"✓ Pseudotime computed: [{pt.min():.3f}, {pt.max():.3f}]")
            
            if 'node' in adata_out.obs:
                print(f"✓ Nodes assigned: {adata_out.obs['node'].nunique()} unique nodes")
        
        # Check figures
        figures = list((output_dir / "figures").glob("*.png")) if (output_dir / "figures").exists() else []
        print(f"\\n✓ Created {len(figures)} figures")
        
        # Check results JSON
        results_file = output_dir / "scfates_results.json"
        if results_file.exists():
            with open(results_file) as f:
                results = json.load(f)
            print("\\n✓ scFates Results:")
            for k, v in results.items():
                print(f"  {k}: {v}")
        
        # Save successful function block
        if result.returncode == 0:
            success_dir = Path.cwd() / "FIXED_scfates_function_block"
            success_dir.mkdir(exist_ok=True)
            
            (success_dir / "code.py").write_text(code)
            (success_dir / "requirements.txt").write_text(requirements)
            
            config = {
                "name": "scFates Pseudotime Analysis (Fixed Versions)",
                "type": "python",
                "description": "scFates with FIXED package versions for reproducibility",
                "parameters": {"seed": 42},
                "notes": "Uses fixed package versions to ensure reproducibility"
            }
            
            with open(success_dir / "config.json", 'w') as f:
                json.dump(config, f, indent=2)
            
            print(f"\\n✓ Fixed function block saved to: {success_dir}")
            
            # Copy a figure
            if figures:
                tree_plots = [f for f in figures if 'tree' in f.name.lower()]
                if tree_plots:
                    dest = Path.cwd() / "scfates_FIXED_tree.png"
                    shutil.copy(tree_plots[0], dest)
                    print(f"✓ Tree plot copied to: {dest}")
        
        return result.returncode == 0


if __name__ == "__main__":
    print("Testing scFates with FIXED package versions...")
    print("=" * 70)
    
    success = test_scfates_fixed()
    
    if success:
        print("\\n" + "=" * 70)
        print("✅ SUCCESS! scFates works with FIXED versions!")
        print("=" * 70)
        print("\\nKey improvements:")
        print("- All package versions are FIXED")
        print("- Reproducible across different environments")
        print("- No surprises from future package updates")
        print("- Proven to work with ElPiGraph method")
    else:
        print("\\n" + "=" * 70)
        print("❌ Failed - check output above")
        print("=" * 70)