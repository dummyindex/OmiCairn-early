# Code Quality Best Practices for Function Blocks

## Python Function Blocks

### Code Completeness
- NEVER use placeholder comments like '# ... (rest of code remains unchanged)'
- ALWAYS provide complete, runnable code - no abbreviations or omissions
- If suggesting fixes, include the ENTIRE function, not just snippets
- Do NOT use ellipsis (...) to abbreviate code sections

### Import Requirements
- Every used module must be imported at the function start (common issue: missing 'import os')
- Standard libraries like os, json, pathlib should be imported before third-party libraries
- Avoid star imports (from module import *) - use specific imports
- Import statements should be at the top of the run() function

### Error Handling
- File operations should handle FileNotFoundError and PermissionError
- API calls should have appropriate try/catch blocks
- Always check if files exist before reading them

### Data Science Specific
- Always check if data is empty before processing (e.g., adata.n_obs > 0)
- Handle missing values appropriately in data analysis
- Validate array/matrix shapes before operations
- Use scanpy.settings.verbosity to control output
- Create output directory with os.makedirs(path_dict['output_dir'], exist_ok=True)

### Function Structure Requirements
- Function must be named 'run' and accept (path_dict, params) arguments
- Must read from path_dict['input_dir'] and write to path_dict['output_dir']
- For root nodes: read original data files
- For child nodes: use previous_nodes interface to access parent outputs
- Always save main output with descriptive names in output directory

## R Function Blocks

### Code Completeness
- NEVER use placeholder comments like '# ... (rest of code remains unchanged)'
- ALWAYS provide complete, runnable code - no abbreviations or omissions
- If suggesting fixes, include the ENTIRE function, not just snippets
- Do NOT use ellipsis (...) to abbreviate code sections

### Package Management
- Use library() for each required package at function start
- Check if package is installed before loading with require()
- Load packages in logical order (base packages first)

### Error Handling
- Use tryCatch for error-prone operations
- Check file existence with file.exists() before reading
- Handle missing packages gracefully

### Data Science Specific
- Always validate data dimensions before processing
- Handle missing values (NA) appropriately
- Use appropriate file I/O functions (readRDS, saveRDS for Seurat objects)
- Check object class before operations (e.g., is(obj, 'Seurat'))

### Function Structure Requirements
- Function must be named 'run' and accept path_dict and params arguments
- Must read from path_dict$input_dir and write to path_dict$output_dir
- Create output directory with dir.create(path_dict$output_dir, recursive=TRUE, showWarnings=FALSE)
- Save outputs with descriptive names