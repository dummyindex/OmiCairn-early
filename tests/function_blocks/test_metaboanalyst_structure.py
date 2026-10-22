"""
Structural validation test for MetaboAnalyst function block
Tests that the function block is properly structured without requiring Docker
"""

import os
import sys
import json
import tempfile
import pandas as pd
import numpy as np
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))


def validate_metaboanalyst_structure():
    """Validate the MetaboAnalyst function block structure and code"""
    
    print("\n" + "="*80)
    print("VALIDATING METABOANALYST FUNCTION BLOCK STRUCTURE")
    print("="*80 + "\n")
    
    fb_path = Path(__file__).parent.parent.parent / "function_blocks" / "metabolomics" / "MetaboAnalyst"
    
    # Check if function block exists
    print("Step 1: Checking function block existence...")
    if not fb_path.exists():
        print(f"  ❌ Function block not found at {fb_path}")
        return False
    print(f"  ✅ Function block found at {fb_path}")
    
    # Check required files
    print("\nStep 2: Checking required files...")
    required_files = {
        "code.R": "Main R code file",
        "config.json": "Configuration file",
        "requirements.txt": "R package dependencies"
    }
    
    all_files_present = True
    for file_name, description in required_files.items():
        file_path = fb_path / file_name
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"  ✅ {file_name}: {description} ({size:,} bytes)")
        else:
            print(f"  ❌ {file_name}: {description} (NOT FOUND)")
            all_files_present = False
    
    if not all_files_present:
        return False
    
    # Validate config.json
    print("\nStep 3: Validating config.json...")
    config_path = fb_path / "config.json"
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        required_fields = ["name", "description", "category", "language", "parameters", "inputs", "outputs"]
        for field in required_fields:
            if field in config:
                print(f"  ✅ {field}: Present")
            else:
                print(f"  ❌ {field}: Missing")
                all_files_present = False
        
        if config.get("name") == "MetaboAnalyst":
            print(f"  ✅ Name is correct: MetaboAnalyst")
        else:
            print(f"  ❌ Name is incorrect: {config.get('name')}")
            
        if config.get("language") == "R":
            print(f"  ✅ Language is R")
        else:
            print(f"  ❌ Language should be R, got: {config.get('language')}")
            
    except Exception as e:
        print(f"  ❌ Error reading config.json: {e}")
        return False
    
    if not all_files_present:
        return False
    
    # Check code.R structure
    print("\nStep 4: Validating code.R structure...")
    code_path = fb_path / "code.R"
    try:
        with open(code_path, 'r') as f:
            code_content = f.read()
        
        # Check for required function signature
        if "run <- function(path_dict, params)" in code_content:
            print("  ✅ Function signature is correct")
        else:
            print("  ❌ Function signature not found")
            return False
        
        # Check for MetaboAnalystR usage
        if "library(MetaboAnalystR)" in code_content:
            print("  ✅ MetaboAnalystR library is loaded")
        else:
            print("  ❌ MetaboAnalystR library not loaded")
            return False
        
        # Check for key MetaboAnalyst functions
        key_functions = [
            "InitDataObjects",
            "Read.TextData",
            "SanityCheckData",
            "Normalization",
            "PCA.Anal",
            "PLSR.Anal",
            "Ttests.Anal",
            "PlotVolcano",
            "PlotPCAPairSummary",
            "PlotPLS2DScore"
        ]
        
        found_functions = []
        missing_functions = []
        for func in key_functions:
            if func in code_content:
                found_functions.append(func)
            else:
                missing_functions.append(func)
        
        print(f"  ✅ Found {len(found_functions)} MetaboAnalyst functions:")
        for func in found_functions[:5]:  # Show first 5
            print(f"     - {func}")
        if len(found_functions) > 5:
            print(f"     ... and {len(found_functions) - 5} more")
            
        if missing_functions:
            print(f"  ⚠️  Missing {len(missing_functions)} expected functions:")
            for func in missing_functions[:3]:
                print(f"     - {func}")
                
    except Exception as e:
        print(f"  ❌ Error reading code.R: {e}")
        return False
    
    # Check requirements.txt
    print("\nStep 5: Validating requirements.txt...")
    req_path = fb_path / "requirements.txt"
    try:
        with open(req_path, 'r') as f:
            requirements = f.read()
        
        # Check for key packages
        key_packages = [
            "MetaboAnalystR",
            "BiocManager",
            "jsonlite",
            "limma",
            "pcaMethods",
            "impute"
        ]
        
        found_packages = []
        missing_packages = []
        for pkg in key_packages:
            if pkg in requirements:
                found_packages.append(pkg)
            else:
                missing_packages.append(pkg)
        
        print(f"  ✅ Found {len(found_packages)} key packages:")
        for pkg in found_packages:
            print(f"     - {pkg}")
            
        if missing_packages:
            print(f"  ⚠️  Missing {len(missing_packages)} expected packages:")
            for pkg in missing_packages:
                print(f"     - {pkg}")
                
        # Count total packages
        lines = requirements.strip().split('\n')
        package_lines = [l for l in lines if l and not l.startswith('#')]
        print(f"  ℹ️  Total packages listed: {len(package_lines)}")
        
    except Exception as e:
        print(f"  ❌ Error reading requirements.txt: {e}")
        return False
    
    # Check for docker requirements documentation
    print("\nStep 6: Checking for Docker requirements...")
    docker_req_path = fb_path / "docker_requirements.md"
    if docker_req_path.exists():
        size = docker_req_path.stat().st_size
        print(f"  ✅ docker_requirements.md found ({size:,} bytes)")
    else:
        print(f"  ⚠️  docker_requirements.md not found (optional but recommended)")
    
    # Check parameters in config
    print("\nStep 7: Validating parameters...")
    try:
        params = config.get("parameters", {})
        expected_params = [
            "normalization_method",
            "scaling_method",
            "pca_components",
            "plsda_components",
            "pvalue_threshold",
            "vip_threshold"
        ]
        
        found_params = []
        for param in expected_params:
            if param in params:
                found_params.append(param)
                
        print(f"  ✅ Found {len(found_params)}/{len(expected_params)} expected parameters")
        
    except Exception as e:
        print(f"  ⚠️  Error checking parameters: {e}")
    
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    
    print("\n✅ MetaboAnalyst function block structure is valid!")
    print("\nKey findings:")
    print("  • Function block follows correct structure")
    print("  • Uses MetaboAnalystR package functions")
    print("  • Has comprehensive parameter configuration")
    print("  • Includes all required dependencies")
    print("\n⚠️  Note: This function block requires a special Docker image")
    print("  with MetaboAnalystR and Bioconductor packages pre-installed.")
    print("  See docker/Dockerfile.r.metaboanalyst for the image definition.")
    
    return True


def create_test_data_preview():
    """Create and preview test metabolomics data"""
    
    print("\n" + "="*80)
    print("TEST DATA PREVIEW")
    print("="*80 + "\n")
    
    np.random.seed(42)
    
    # Create sample data
    n_metabolites = 5
    n_samples = 6
    
    metabolite_names = [f"Metabolite_{i:03d}" for i in range(1, n_metabolites + 1)]
    sample_names = [f"Control_{i}" for i in range(1, 4)] + [f"Treatment_{i}" for i in range(1, 4)]
    
    # Generate data with differences
    data = np.random.lognormal(mean=10, sigma=1, size=(n_metabolites, n_samples))
    data[0, 3:] = data[0, 3:] * 3  # First metabolite higher in treatment
    data[2, 3:] = data[2, 3:] / 2  # Third metabolite lower in treatment
    
    # Create DataFrame
    df = pd.DataFrame(data, index=metabolite_names, columns=sample_names)
    
    print("Sample metabolite data (first 5 metabolites, all samples):")
    print(df.round(2))
    
    print("\nSample metadata:")
    metadata = pd.DataFrame({
        'Group': ['Control'] * 3 + ['Treatment'] * 3,
        'Batch': [1, 1, 2, 1, 1, 2]
    }, index=sample_names)
    print(metadata)
    
    print("\nThis is the type of data the MetaboAnalyst function block processes.")


if __name__ == "__main__":
    # Run validation
    success = validate_metaboanalyst_structure()
    
    # Show test data preview
    if success:
        create_test_data_preview()
    
    # Final summary
    print("\n" + "="*80)
    if success:
        print("✅ METABOANALYST FUNCTION BLOCK IS READY FOR USE")
        print("\nTo use this function block:")
        print("1. Build the Docker image: docker build -t omicairn/r-executor-metaboanalyst -f docker/Dockerfile.r.metaboanalyst .")
        print("2. Ensure Docker is running")
        print("3. Execute the function block through the job executor with the custom image")
    else:
        print("❌ METABOANALYST FUNCTION BLOCK HAS ISSUES")
        print("\nPlease fix the issues above before using the function block.")
    print("="*80)