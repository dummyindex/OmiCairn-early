"""Utility to load function blocks from directory structure."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Union
import logging

from models import (
    NewFunctionBlock, FunctionBlockType, StaticConfig, 
    InputSpecification, OutputSpecification, Arg
)

logger = logging.getLogger(__name__)


class FunctionBlockLoader:
    """Load function blocks from directory structure."""
    
    def __init__(self, base_dir: Union[str, Path]):
        """Initialize loader with base directory."""
        self.base_dir = Path(base_dir)
        if not self.base_dir.exists():
            raise ValueError(f"Base directory does not exist: {self.base_dir}")
    
    def load_function_block(self, block_path: Union[str, Path]) -> Optional[NewFunctionBlock]:
        """Load a single function block from directory."""
        block_dir = Path(block_path)
        if not block_dir.is_absolute():
            block_dir = self.base_dir / block_dir
        
        if not block_dir.exists():
            logger.error(f"Function block directory not found: {block_dir}")
            return None
        
        # Required files
        config_file = block_dir / "config.json"
        code_file = block_dir / "code.py"  # or code.R
        
        if not config_file.exists():
            logger.error(f"Config file not found: {config_file}")
            return None
        
        # Load config
        try:
            with open(config_file, 'r') as f:
                config_data = json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return None
        
        # Determine code file
        if not code_file.exists():
            code_file = block_dir / "code.R"
            if not code_file.exists():
                logger.error(f"Code file not found in: {block_dir}")
                return None
        
        # Load code
        try:
            with open(code_file, 'r') as f:
                code = f.read()
        except Exception as e:
            logger.error(f"Error loading code: {e}")
            return None
        
        # Load requirements if exists
        requirements = ""
        req_file = block_dir / "requirements.txt"
        if req_file.exists():
            try:
                with open(req_file, 'r') as f:
                    requirements = f.read()
            except Exception as e:
                logger.warning(f"Error loading requirements: {e}")
        
        # Build function block
        try:
            # Parse static config
            static_config_data = config_data.get('static_config', {})
            
            # Parse args
            args = []
            for arg_data in static_config_data.get('args', []):
                args.append(Arg(**arg_data))
            
            # Parse input/output specifications
            input_spec = None
            if 'input_specification' in static_config_data:
                input_spec = InputSpecification(**static_config_data['input_specification'])
            
            output_spec = None
            if 'output_specification' in static_config_data:
                output_spec = OutputSpecification(**static_config_data['output_specification'])
            
            # Create static config
            static_config = StaticConfig(
                args=args,
                description=static_config_data.get('description', config_data.get('description', '')),
                tag=static_config_data.get('tag', ''),
                document_url=static_config_data.get('document_url', ''),
                source=static_config_data.get('source', 'loaded'),
                preset_env=static_config_data.get('preset_env'),
                input_specification=input_spec,
                output_specification=output_spec
            )
            
            # Create function block
            fb = NewFunctionBlock(
                name=config_data['name'],
                type=FunctionBlockType(config_data['type']),
                description=config_data['description'],
                static_config=static_config,
                code=code,
                requirements=requirements,
                parameters={}  # Default empty parameters
            )
            
            logger.info(f"Loaded function block: {fb.name}")
            return fb
            
        except Exception as e:
            logger.error(f"Error creating function block: {e}")
            return None
    
    def list_available_blocks(self) -> List[Dict[str, str]]:
        """List all available function blocks."""
        blocks = []
        
        # Search for config.json files
        for config_file in self.base_dir.rglob("config.json"):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                
                block_info = {
                    "name": config.get("name", "unknown"),
                    "type": config.get("type", "unknown"),
                    "description": config.get("description", ""),
                    "path": str(config_file.parent.relative_to(self.base_dir)),
                    "tags": config.get("tags", [])
                }
                blocks.append(block_info)
                
            except Exception as e:
                logger.warning(f"Error reading config {config_file}: {e}")
                continue
        
        return blocks
    
    def load_blocks_by_tag(self, tag: str) -> List[NewFunctionBlock]:
        """Load all function blocks with a specific tag."""
        blocks = []
        
        for block_info in self.list_available_blocks():
            if tag in block_info.get("tags", []):
                block = self.load_function_block(block_info["path"])
                if block:
                    blocks.append(block)
        
        return blocks
    
    def load_all_blocks(self) -> Dict[str, NewFunctionBlock]:
        """Load all available function blocks."""
        blocks = {}
        
        for block_info in self.list_available_blocks():
            block = self.load_function_block(block_info["path"])
            if block:
                blocks[block.name] = block
        
        return blocks