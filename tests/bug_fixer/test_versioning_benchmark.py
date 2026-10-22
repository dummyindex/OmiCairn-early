"""Benchmark test to verify code versioning works with the clustering pipeline."""

import os
import json
from pathlib import Path
from datetime import datetime
import pytest

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from agents.main_agent import MainAgent
from utils.logger import get_logger

logger = get_logger(__name__)


@pytest.mark.slow
@pytest.mark.benchmark
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
def test_versioning_with_simple_bug():
    """Test that code versioning works when bug fixer fixes a simple syntax error."""
    
    # Get API key
    api_key = os.environ.get("OPENAI_API_KEY")
        
    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"test_outputs/versioning_benchmark_{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create test data with intentional bug in function block
    test_data = Path("test_data/zebrafish.h5ad")
    
    # Create main agent
    agent = MainAgent(
        openai_api_key=api_key,
        bug_fixer_type="unified",
        bug_fixer_model="gpt-4o-mini",
        enable_web_agent=False
    )
    
    # Simple request that should trigger a bug (incomplete code generation)
    user_request = """
    Load the data and print a summary of it. 
    Then calculate QC metrics but make sure to print the root cell index.
    """
    
    logger.info(f"Running versioning benchmark test to: {output_dir}")
    
    try:
        result = agent.run_analysis(
            input_data_path=test_data,
            user_request=user_request,
            output_dir=output_dir,
            max_iterations=10,
            max_debug_trials=3,
            max_nodes=5
        )
        
        # Check results - analysis is successful if no nodes failed
        if result["failed_nodes"] == 0:
            logger.info("Analysis completed successfully")
            
            # Check if versioning was created for any nodes
            tree_dir = output_dir / result["tree_id"]
            nodes_dir = tree_dir / "nodes"
            
            versioning_found = False
            for node_dir in nodes_dir.iterdir():
                if node_dir.is_dir():
                    versions_dir = node_dir / "agent_tasks" / "bug_fixer" / "code_versions"
                    if versions_dir.exists() and list(versions_dir.glob("*.py")):
                        versioning_found = True
                        logger.info(f"Found code versioning in node: {node_dir.name}")
                        
                        # List versions
                        versions = sorted(versions_dir.glob("*.py"))
                        logger.info(f"  Found {len(versions)} code versions:")
                        for v in versions:
                            logger.info(f"    - {v.name}")
                            
                        # Check if function_block folder was updated
                        fb_dir = node_dir / "function_block"
                        if fb_dir.exists():
                            code_file = fb_dir / "code.py"
                            if code_file.exists():
                                # Compare with latest version
                                if versions:
                                    latest_version = versions[-1]
                                    latest_content = latest_version.read_text()
                                    current_content = code_file.read_text()
                                    
                                    if latest_content.strip() == current_content.strip():
                                        logger.info("  ✓ function_block/code.py matches latest version")
                                    else:
                                        logger.warning("  ✗ function_block/code.py does NOT match latest version")
            
            if versioning_found:
                logger.info("✅ Code versioning is working correctly!")
            else:
                logger.warning("⚠️ No code versioning found - bug fixer may not have been triggered")
                
        else:
            logger.error(f"Analysis failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Benchmark test failed: {e}")
        raise
        
    logger.info(f"Benchmark results saved to: {output_dir}")
    
    # Write summary
    summary = {
        "timestamp": timestamp,
        "success": (result["failed_nodes"] == 0) if 'result' in locals() else False,
        "output_dir": str(output_dir),
        "versioning_found": versioning_found if 'versioning_found' in locals() else False
    }
    
    with open(output_dir / "versioning_benchmark_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
        

if __name__ == "__main__":
    test_versioning_with_simple_bug()