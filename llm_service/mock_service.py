"""Mock OpenAI service for testing without API calls."""

import json
from typing import Dict, List, Optional, Any
from utils.logger import get_logger

logger = get_logger(__name__)


class MockOpenAIService:
    """Mock service that simulates OpenAI responses for testing."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or "mock-key"
        self.model = "gpt-4o-mini-mock"
        self.client = None  # Mock client
        
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        response_format: Optional[Dict[str, Any]] = None
    ) -> str:
        """Mock chat completion."""
        # Generate mock response based on the request
        if response_format and response_format.get("type") == "json_schema":
            # Return a valid JSON response matching the schema
            return self._generate_mock_json_response(response_format.get("json_schema", {}))
        return "Mock response"
    
    def chat_completion_json(
        self,
        messages: List[Dict[str, str]],
        json_schema: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> Dict[str, Any]:
        """Mock JSON chat completion."""
        response_format = {
            "type": "json_schema",
            "json_schema": json_schema
        }
        
        content = self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format
        )
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse mock JSON response: {e}")
            raise
    
    def _generate_mock_json_response(self, json_schema: Dict[str, Any]) -> str:
        """Generate a mock JSON response based on schema."""
        schema_name = json_schema.get("name", "")
        
        if schema_name == "function_block_creation":
            return json.dumps({
                "function_block": {
                    "name": "quality_control",
                    "description": "Apply quality control filters",
                    "code": """def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Read input
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    adata = sc.read_h5ad(input_file)
    
    # Get parameters
    min_genes = params.get('min_genes', 200)
    min_cells = params.get('min_cells', 3)
    
    # Calculate QC metrics
    sc.pp.calculate_qc_metrics(adata, inplace=True)
    
    # Apply filters
    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_genes(adata, min_cells=min_cells)
    
    print(f"Filtered to {adata.shape[0]} cells and {adata.shape[1]} genes")
    
    # Save output
    adata.write(output_file)
    print(f"Output saved to {output_file}")
""",
                    "requirements": ["scanpy", "anndata"],
                    "parameters": {
                        "min_genes": 200,
                        "min_cells": 3
                    },
                    "static_config": {
                        "args": [
                            {
                                "name": "min_genes",
                                "value_type": "int",
                                "description": "Minimum number of genes per cell",
                                "optional": True,
                                "default_value": 200
                            },
                            {
                                "name": "min_cells",
                                "value_type": "int",
                                "description": "Minimum number of cells per gene",
                                "optional": True,
                                "default_value": 3
                            }
                        ],
                        "description": "Quality control filtering",
                        "tag": "quality_control"
                    }
                },
                "reasoning": "Creating quality control function block to filter cells and genes"
            })
        
        elif schema_name == "bug_fix":
            return json.dumps({
                "analysis": {
                    "error_type": "AttributeError",
                    "root_cause": "Missing QC metrics calculation",
                    "fix_strategy": "Add sc.pp.calculate_qc_metrics before filtering"
                },
                "fixed_code": """def run(path_dict, params):
    import scanpy as sc
    import os
    
    # Fixed: Added proper imports and QC metrics calculation
    input_file = os.path.join(path_dict["input_dir"], "_node_anndata.h5ad")
    output_file = os.path.join(path_dict["output_dir"], "_node_anndata.h5ad")
    
    adata = sc.read_h5ad(input_file)
    
    # Calculate QC metrics first
    sc.pp.calculate_qc_metrics(adata, inplace=True)
    
    # Apply filters
    sc.pp.filter_cells(adata, min_genes=params.get('min_genes', 200))
    sc.pp.filter_genes(adata, min_cells=params.get('min_cells', 3))
    
    adata.write(output_file)
""",
                "changes_made": [
                    "Added sc.pp.calculate_qc_metrics before filtering",
                    "Fixed file path construction using os.path.join"
                ],
                "requirements_changes": []
            })
        
        # Default response
        return json.dumps({
            "result": "Mock response",
            "success": True
        })
    
    def extract_code_block(self, content: str, language: Optional[str] = None) -> Optional[str]:
        """Extract code block from markdown-formatted response."""
        if "```" not in content:
            return content.strip()
            
        parts = content.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 1:  # Code blocks are at odd indices
                lines = part.strip().split('\n')
                if lines:
                    first_line = lines[0].lower()
                    if language:
                        if first_line == language:
                            return '\n'.join(lines[1:])
                    else:
                        if first_line in ['python', 'r', 'bash', 'shell']:
                            return '\n'.join(lines[1:])
                        return part.strip()
        return None