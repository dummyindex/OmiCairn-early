
# Single-Cell Genomics Analysis: Pseudotime and Trajectory Methods

## Key Principles

- **Preserve method identity**. Don’t substitute intended analysis pipelines.
- **Load, don’t reapply**. Use processed results from preceding methods.
- **Validate prerequisites**. Each method has essential upstream steps (e.g., PCA, neighbors, pseudotime).

---

## 1. Palantir

**Critical Fixes**
- Ensure unique cell names:  
  ```python
  adata.obs_names_make_unique()
  ```

* Import palantir package:

  ```python
  import palantir
  ```
* Plot using the correct diffusion map key:

  ```python
  plt.scatter(
      adata.obsm['DM_EigenVectors'][:, 0],
      adata.obsm['DM_EigenVectors'][:, 1]
  )
  ```

**Minimal Block**

```python
adata = sc.read_h5ad(input_file)
adata.obs_names_make_unique()

if "X_pca" not in adata.obsm:
    sc.pp.pca(adata, n_comps=50)

palantir.utils.run_diffusion_maps(adata, n_components=10, knn=30)
palantir.utils.determine_multiscale_space(adata)

start_cell = adata.obs.index[0]
palantir.core.run_palantir(adata, start_cell, num_waypoints=1200)

plt.scatter(
    adata.obsm['DM_EigenVectors'][:, 0],
    adata.obsm['DM_EigenVectors'][:, 1],
    c=adata.obs['palantir_pseudotime'], cmap='viridis'
)
plt.colorbar(label='Pseudotime')

adata.write(output_file)
```

---

## 2. CellRank (PseudotimeKernel)

**Key Principle**: Requires precomputed pseudotime (e.g., DPT).

```python
from cellrank.kernels import PseudotimeKernel
pk = PseudotimeKernel(adata, time_key="dpt_pseudotime")
pk.compute_transition_matrix()
```

**Minimal Block**

```python
adata = sc.read_h5ad(input_file)

time_key = params.get("pseudotime_key", "dpt_pseudotime")
if time_key not in adata.obs:
    raise ValueError("CellRank PseudotimeKernel requires precomputed pseudotime")

if 'neighbors' not in adata.uns:
    sc.pp.neighbors(adata, n_neighbors=30)

from cellrank.kernels import PseudotimeKernel
from cellrank.estimators import GPCCA

pk = PseudotimeKernel(adata, time_key=time_key)
pk.compute_transition_matrix()
adata.obsp['cellrank_transition_matrix'] = pk.transition_matrix

g = GPCCA(pk)
g.fit(cluster_key="leiden", n_states=5)
g.predict_terminal_states()
adata.obs['cellrank_terminal_states'] = g.terminal_states

adata.write(output_file)
```

---

## 3. scFates

**Critical Fixes**

* Import correctly:

  ```python
  import scFates as scf
  ```
* Ensure PCA if using `"X_pca"`
* Ensure UMAP before visualization

**Minimal Block**

```python
import scFates as scf

adata = sc.read_h5ad(input_file)

use_rep = params.get("use_rep", "X_pca")
if use_rep == "X_pca" and "X_pca" not in adata.obsm:
    sc.pp.pca(adata, n_comps=50)

scf.tl.curve(adata, Nodes=10, use_rep=use_rep, device="cpu")

if 'X_umap' not in adata.obsm:
    sc.pp.neighbors(adata, n_neighbors=15, n_pcs=40)
    sc.tl.umap(adata)

scf.pl.graph(adata, basis="umap", show=False)

adata.write(output_file)
```

---

## 4. DPT + PAGA (Scanpy)

**Sequence**: neighbors → clustering → PAGA → diffmap → root cell → DPT.

**Minimal Block**

```python
adata = sc.read_h5ad(input_file)

if 'neighbors' not in adata.uns:
    sc.pp.neighbors(adata, n_neighbors=15)

cluster_key = params.get("clustering_key", "leiden")
if cluster_key not in adata.obs:
    sc.tl.leiden(adata, key_added=cluster_key)

sc.tl.paga(adata, groups=cluster_key)
sc.tl.diffmap(adata, n_comps=15)

root_cluster = adata.obs[cluster_key].cat.categories[0]
root_mask = adata.obs[cluster_key] == root_cluster
root_idx = np.where(root_mask)[0][0]
adata.uns['iroot'] = root_idx

sc.tl.dpt(adata)

adata.write(output_file)
```

---

## Dependencies

* **Palantir**: requires Scanpy preprocessing (`PCA`).
* **CellRank**: pseudotime (e.g., DPT) required for `PseudotimeKernel`.
* **scFates**: `pip install scFates`. Some functions require R (`rpy2`, `mgcv`).
* **Scanpy DPT**: requires `neighbors`, `diffmap`, and `iroot`.

---

## Important Notes on Scanpy Figure Saving

**Scanpy's default behavior for saving figures:**
- When using `save` parameter (e.g., `sc.pl.umap(adata, save='filename.png')`), scanpy saves figures to `./figures/` relative to the **current working directory**, NOT the specified output directory
- This means figures often end up in `/workspace/figures/` instead of the intended output location
- The `save` parameter appends the filename to scanpy's `settings.figdir` which defaults to `./figures/`

**Recommended approaches:**
1. **Configure scanpy's figure directory** before plotting:
   ```python
   import scanpy as sc
   sc.settings.figdir = os.path.join(path_dict['output_dir'], 'figures')
   os.makedirs(sc.settings.figdir, exist_ok=True)
   ```

2. **Use matplotlib directly** for more control:
   ```python
   import matplotlib.pyplot as plt
   plt.figure()
   sc.pl.umap(adata, show=False)  # Don't use save parameter
   plt.savefig(os.path.join(path_dict['output_dir'], 'figures', 'umap.png'))
   plt.close()
   ```

**For Output Collector Agent:**
- Always check `/workspace/figures/` for any `.png`, `.pdf`, `.svg` files
- Also check the current working directory root for figures
- Preserve the `figures/` subdirectory structure when copying to output directory

---
