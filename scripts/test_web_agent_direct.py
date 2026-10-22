#!/usr/bin/env python3
"""Direct test of web agent integration with bug fixer."""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.unified_bug_fixer import UnifiedBugFixer


def test_web_agent_direct():
    """Test web agent directly with a known error."""
    
    print("\n" + "="*80)
    print("DIRECT WEB AGENT TEST")
    print("="*80 + "\n")
    
    # Check API key
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        print("Error: OPENAI_API_KEY not set")
        return False
    
    # Create output directory
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = Path(f"test_outputs/web_agent_direct_{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize bug fixer with web agent
    print("Initializing bug fixer with web agent...")
    bug_fixer = UnifiedBugFixer(
        model_name="gpt-4o-mini",
        api_key=openai_key,
        max_turns=3,
        enable_web_agent=True,
        save_debug_logs=True
    )
    
    if bug_fixer.web_agent_tool:
        print("✓ Web agent tool initialized")
    else:
        print("✗ Web agent tool failed to initialize")
        return False
    
    # Test with a known error that should trigger web research
    test_cases = [
        {
            "name": "Pandas append deprecation",
            "error": "AttributeError: 'DataFrame' object has no attribute 'append'",
            "stderr": """Traceback (most recent call last):
  File "test.py", line 5, in <module>
    df2 = df.append({'A': 4}, ignore_index=True)
AttributeError: 'DataFrame' object has no attribute 'append'""",
            "code": """
import pandas as pd
df = pd.DataFrame({'A': [1, 2, 3]})
df2 = df.append({'A': 4}, ignore_index=True)
"""
        },
        {
            "name": "Scanpy DPT error",
            "error": "AttributeError: module 'scanpy' has no attribute 'tl.dpt'",
            "stderr": """Traceback (most recent call last):
  File "test.py", line 3, in <module>
    sc.tl.dpt(adata)
AttributeError: module 'scanpy' has no attribute 'tl.dpt'""",
            "code": """
import scanpy as sc
adata = sc.read_h5ad('data.h5ad')
sc.tl.dpt(adata)
"""
        }
    ]
    
    results = []
    
    for i, test_case in enumerate(test_cases):
        print(f"\n{'='*60}")
        print(f"Test {i+1}: {test_case['name']}")
        print(f"{'='*60}\n")
        
        # Create test directory
        test_dir = output_dir / f"test_{i+1}"
        test_dir.mkdir(parents=True, exist_ok=True)
        
        # Save test code
        code_file = test_dir / "code.py"
        code_file.write_text(test_case['code'])
        
        # Run bug fixer
        print(f"Running bug fixer for: {test_case['error']}")
        
        fix_result = bug_fixer.fix_bug(
            node_name=f"test_{test_case['name']}",
            error_message=test_case['error'],
            working_directory=test_dir,
            stdout="",
            stderr=test_case['stderr'],
            attempt_number=1
        )
        
        # Analyze results
        result_info = {
            "test_name": test_case['name'],
            "success": fix_result.get('success', False),
            "actions_taken": len(fix_result.get('actions_taken', [])),
            "cost": fix_result.get('total_cost', 0.0),
            "web_agent_used": False,
            "web_agent_findings": 0,
            "web_agent_solutions": 0,
            "web_agent_confidence": 0.0,
            "web_agent_cost": 0.0
        }
        
        # Check for web agent outputs
        web_agent_dir = test_dir / "web_agent_research"
        if web_agent_dir.exists():
            result_info["web_agent_used"] = True
            print("\n✓ Web agent research found!")
            
            # Read research data
            research_data_path = web_agent_dir / "attempt_1" / "research_data.json"
            if research_data_path.exists():
                with open(research_data_path) as f:
                    research_data = json.load(f)
                    
                result_info["web_agent_findings"] = len(research_data.get('findings', []))
                result_info["web_agent_solutions"] = len(research_data.get('solutions', []))
                result_info["web_agent_confidence"] = research_data.get('confidence', 0)
                result_info["web_agent_cost"] = research_data.get('cost', 0)
                
                print(f"  Findings: {result_info['web_agent_findings']}")
                print(f"  Solutions: {result_info['web_agent_solutions']}")
                print(f"  Confidence: {result_info['web_agent_confidence']:.2f}")
                print(f"  Cost: ${result_info['web_agent_cost']:.4f}")
                
                # Show findings
                if research_data.get('findings'):
                    print("\n  Key findings:")
                    for finding in research_data['findings'][:3]:
                        print(f"    - {finding.get('finding', 'N/A')}")
                        
                # Show solutions
                if research_data.get('solutions'):
                    print("\n  Suggested solutions:")
                    for solution in research_data['solutions'][:3]:
                        print(f"    - {solution.get('solution', 'N/A')}")
        
        results.append(result_info)
        
        print(f"\nResult: {'SUCCESS' if result_info['success'] else 'FAILED'}")
        print(f"Total cost: ${fix_result.get('total_cost', 0):.4f}")
    
    # Create summary report
    summary = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": len(test_cases),
        "successful_fixes": sum(1 for r in results if r['success']),
        "web_agent_used_count": sum(1 for r in results if r['web_agent_used']),
        "total_cost": sum(r['cost'] for r in results),
        "web_agent_total_cost": sum(r['web_agent_cost'] for r in results),
        "test_results": results
    }
    
    # Save summary
    summary_path = output_dir / "test_summary.json"
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)
        
    # Print final summary
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    print(f"Total tests: {summary['total_tests']}")
    print(f"Successful fixes: {summary['successful_fixes']}")
    print(f"Web agent used: {summary['web_agent_used_count']} times")
    print(f"Total cost: ${summary['total_cost']:.4f}")
    print(f"Web agent cost: ${summary['web_agent_total_cost']:.4f}")
    print(f"\nFull report saved to: {summary_path}")
    
    return summary['successful_fixes'] > 0


if __name__ == "__main__":
    success = test_web_agent_direct()
    sys.exit(0 if success else 1)