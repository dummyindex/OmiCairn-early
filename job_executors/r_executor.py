"""R function block executor."""

from pathlib import Path
from typing import Dict, Any, List, Optional
import shutil
import json

from .base_executor import BaseExecutor
from models import BaseFunctionBlock, FunctionBlockType, NewFunctionBlock
from utils.logger import get_logger
from config import config

logger = get_logger(__name__)


class RExecutor(BaseExecutor):
    """Executor for R function blocks."""
    
    @property
    def block_type(self) -> FunctionBlockType:
        return FunctionBlockType.R
    
    @property
    def docker_image(self) -> str:
        return config.r_image
    
    def prepare_execution_dir(
        self, 
        execution_dir: Path,
        function_block: BaseFunctionBlock,
        input_data_path: Path,
        parameters: Dict[str, Any],
        previous_nodes_metadata: Optional[Dict[str, Any]] = None,
        propagated_failure_context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Prepare execution directory for R function block."""
        
        # Create directory structure
        (execution_dir / "input").mkdir(exist_ok=True)
        (execution_dir / "output").mkdir(exist_ok=True)
        (execution_dir / "output" / "figures").mkdir(exist_ok=True)
        
        # Copy ALL files from parent's outputs folder to child's input folder
        input_path = Path(input_data_path)
        if input_path.is_dir():
            # If input_data_path is a directory (parent's outputs folder), copy ALL files
            for item in input_path.glob("*"):
                if item.is_file():
                    # Copy with original name to maintain consistency
                    shutil.copy2(item, execution_dir / "input" / item.name)
                elif item.is_dir():
                    # Copy entire subdirectory (e.g., figures/)
                    shutil.copytree(item, execution_dir / "input" / item.name, dirs_exist_ok=True)
        else:
            # If it's a single file, copy with its original name
            shutil.copy2(input_path, execution_dir / "input" / input_path.name)
        
        # Handle previous nodes metadata if provided
        if previous_nodes_metadata:
            self._stage_previous_nodes_files(execution_dir / "input", previous_nodes_metadata)
        
        # Write propagated failure context if provided
        if propagated_failure_context:
            with open(execution_dir / "input" / "_node_failure_context.json", 'w') as f:
                json.dump(propagated_failure_context, f, indent=2)
        
        # Write parameters as JSON
        self.write_parameters(execution_dir / "parameters.json", parameters)
        
        # Write function block code
        if isinstance(function_block, NewFunctionBlock):
            # Write the function block code
            with open(execution_dir / "function_block.R", "w") as f:
                f.write(function_block.code)
            
            # Write R package requirements
            with open(execution_dir / "install_packages.R", "w") as f:
                f.write(self._generate_package_install_script(function_block.requirements))
        else:
            raise NotImplementedError("Existing function block execution not yet implemented")
        
        # Write the execution wrapper
        wrapper_code = self._generate_wrapper_code()
        with open(execution_dir / "run.R", "w") as f:
            f.write(wrapper_code)
    
    def _stage_previous_nodes_files(self, input_dir: Path, previous_nodes_metadata: Dict[str, Any]) -> None:
        """Stage output files from previous nodes (same layout as the Python executor)."""
        prev_nodes_dir = input_dir / "previous_nodes"
        prev_nodes_dir.mkdir(exist_ok=True)

        for idx, node_info in previous_nodes_metadata.items():
            node_outputs_dir = prev_nodes_dir / f"node_{idx}" / "outputs"
            node_outputs_dir.mkdir(parents=True, exist_ok=True)
            for file_info in node_info.get('files', []):
                if file_info.get('type') == 'output':
                    source_path = Path(file_info['path'])
                    if source_path.exists():
                        shutil.copy2(source_path, node_outputs_dir / file_info['name'])

        with open(input_dir / "previous_nodes_index.json", 'w') as f:
            json.dump(previous_nodes_metadata, f, indent=2)
        logger.info(f"Staged previous nodes files for {len(previous_nodes_metadata)} nodes")

    def get_execution_command(self) -> List[str]:
        """Get R execution command."""
        return [
            "bash", "-c",
            "cd /workspace && " +
            "Rscript install_packages.R && " +
            "Rscript run.R"
        ]
    
    def _generate_package_install_script(self, requirements: str) -> str:
        """Generate R package installation script from requirements."""
        lines = requirements.strip().split('\n')
        bioc_packages = []
        cran_packages = []
        github_packages = []
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            if '::' in line:
                # Bioconductor or specific repo package
                if line.startswith('Bioconductor::'):
                    pkg = line.split('::')[1]
                    bioc_packages.append(pkg)
                else:
                    github_packages.append(line)
            elif '/' in line:
                # GitHub package in user/repo format
                github_packages.append(line)
            else:
                # CRAN package
                cran_packages.append(line)
        
        # Build install commands
        install_commands = []
        
        # Install CRAN packages first (faster)
        if cran_packages:
            pkgs_str = ', '.join([f'"{pkg}"' for pkg in cran_packages])
            install_commands.append(f'''
# Install CRAN packages
cat("Installing CRAN packages: {', '.join(cran_packages)}\\n")
for (pkg in c({pkgs_str})) {{
    if (!requireNamespace(pkg, quietly = TRUE)) {{
        cat("Installing", pkg, "from CRAN...\\n")
        install.packages(pkg, repos="https://cloud.r-project.org", quiet = TRUE)
    }} else {{
        cat(pkg, "already installed\\n")
    }}
}}''')
        
        # Install Bioconductor packages
        if bioc_packages:
            pkgs_str = ', '.join([f'"{pkg}"' for pkg in bioc_packages])
            install_commands.append(f'''
# Install Bioconductor packages
cat("Installing Bioconductor packages: {', '.join(bioc_packages)}\\n")
for (pkg in c({pkgs_str})) {{
    if (!requireNamespace(pkg, quietly = TRUE)) {{
        cat("Installing", pkg, "from Bioconductor...\\n")
        BiocManager::install(pkg, ask = FALSE, update = FALSE, quiet = TRUE)
    }} else {{
        cat(pkg, "already installed\\n")
    }}
}}''')
        
        # Install GitHub packages
        if github_packages:
            for pkg in github_packages:
                install_commands.append(f'''
cat("Installing {pkg} from GitHub...\\n")
remotes::install_github("{pkg}", quiet = TRUE, upgrade = "never")''')
        
        return f'''#!/usr/bin/env Rscript
# Install required packages

# Set options for non-interactive installation
options(repos = c(CRAN = "https://cloud.r-project.org"))
options(install.packages.check.source = "no")
options(install.packages.compile.from.source = "never")

# Ensure BiocManager is installed
if (!requireNamespace("BiocManager", quietly = TRUE)) {{
    cat("Installing BiocManager...\\n")
    install.packages("BiocManager", quiet = TRUE)
}}

# Ensure remotes is installed for GitHub packages
if (!requireNamespace("remotes", quietly = TRUE)) {{
    cat("Installing remotes...\\n")
    install.packages("remotes", quiet = TRUE)
}}

# Set Bioconductor to not ask questions
BiocManager::install(ask = FALSE, update = FALSE)

{"".join(install_commands)}

cat("\\nPackage installation completed\\n")

# Verify critical packages
critical_pkgs <- c({', '.join([f'"{pkg}"' for pkg in bioc_packages + cran_packages])})
missing_pkgs <- critical_pkgs[!sapply(critical_pkgs, requireNamespace, quietly = TRUE)]
if (length(missing_pkgs) > 0) {{
    cat("WARNING: The following packages could not be installed:", paste(missing_pkgs, collapse=", "), "\\n")
    cat("The function may not work correctly without these packages.\\n")
}}
'''
    
    def _generate_wrapper_code(self) -> str:
        """Generate wrapper code for R function block execution."""
        return '''#!/usr/bin/env Rscript
# Wrapper script for function block execution

library(jsonlite)

# Set up logging
log_file <- file("/workspace/output/execution.log", open = "wt")
sink(log_file, type = "output")
sink(log_file, type = "message")

tryCatch({
    cat("Starting function block execution\\n")
    
    # Load parameters
    params <- fromJSON("/workspace/parameters.json")
    cat("Loaded parameters:\\n")
    print(params)
    
    # Create path list with only directories
    path_dict <- list(
        input_dir = "/workspace/input",
        output_dir = "/workspace/output"
    )
    
    cat("\\nPath dictionary:\\n")
    print(path_dict)
    cat("\\nParameters:\\n")
    print(params)
    
    # Source function block
    cat("\\nLoading function block\\n")
    source("/workspace/function_block.R")
    
    # Execute function block with path_dict and params
    cat("\\nExecuting function block with path_dict and params\\n")
    run(path_dict, params)  # Pass both path_dict and params
    
    # Check for any output files
    all_files <- list.files(path_dict$output_dir, full.names = FALSE)
    if (length(all_files) > 0) {
        cat(sprintf("\\nFound %d output files:\\n", length(all_files)))
        for (f in head(all_files, 5)) {  # Show first 5
            cat(sprintf("  - %s\\n", f))
        }
    } else {
        cat(sprintf("\\nWarning: No output files found in %s\\n", path_dict$output_dir))
    }
    
    cat("\\nFunction block execution completed successfully\\n")
    
}, error = function(e) {
    cat("\\nError during execution:\\n")
    cat(conditionMessage(e), "\\n")
    print(traceback())
    quit(status = 1)
})

# Close log file
sink(type = "output")
sink(type = "message")
close(log_file)
'''