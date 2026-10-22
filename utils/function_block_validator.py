"""Function block input/output validation module.

This module validates file existence only, not file contents.
Function blocks are responsible for their own data validation.
"""

from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import logging
import json

logger = logging.getLogger(__name__)


class FunctionBlockValidator:
    """Validates function block inputs and outputs against specifications.
    
    This validator only checks for file existence, not file contents.
    Data validation should be handled by function blocks themselves.
    """
    
    def __init__(self, static_config: Dict[str, Any]):
        """Initialize validator with function block static configuration.
        
        Args:
            static_config: The static configuration dictionary containing specifications
        """
        self.static_config = static_config
        self.input_spec = static_config.get('input_specification', {})
        self.output_spec = static_config.get('output_specification', {})
    
    def validate_input(self, input_dir: Path) -> Tuple[bool, List[str]]:
        """Validate input directory against specification.
        
        Only checks for file existence, not file contents.
        
        Args:
            input_dir: Path to input directory
            
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        if not self.input_spec:
            logger.debug("No input specification defined, skipping validation")
            return True, []
        
        logger.info(f"Validating inputs against specification: {self.input_spec}")
        
        # Check required files exist
        for file in self.input_spec.get('required_files', []):
            file_path = input_dir / file
            if not file_path.exists():
                errors.append(f"Required input file missing: {file}")
                logger.error(f"Missing required input file: {file_path}")
            else:
                logger.debug(f"Found required input file: {file_path}")
        
        # Note: We no longer validate AnnData contents here
        # Function blocks should handle their own data validation
        
        is_valid = len(errors) == 0
        if is_valid:
            logger.info("Input validation passed")
        else:
            logger.error(f"Input validation failed with {len(errors)} errors")
            
        return is_valid, errors
    
    def validate_output(self, output_dir: Path) -> Tuple[bool, List[str]]:
        """Validate output directory against specification.
        
        Only checks for file existence, not file contents.
        
        Args:
            output_dir: Path to output directory
            
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        if not self.output_spec:
            logger.debug("No output specification defined, skipping validation")
            return True, []
        
        logger.info(f"Validating outputs against specification: {self.output_spec}")
        
        # Check required files exist
        for file in self.output_spec.get('required_files', []):
            file_path = output_dir / file
            if not file_path.exists():
                errors.append(f"Required output file missing: {file}")
                logger.error(f"Missing required output file: {file_path}")
            else:
                logger.debug(f"Found required output file: {file_path}")
        
        # Note: We no longer validate AnnData contents here
        # Function blocks should handle their own data validation
        
        is_valid = len(errors) == 0
        if is_valid:
            logger.info("Output validation passed")
        else:
            logger.error(f"Output validation failed with {len(errors)} errors")
            
        return is_valid, errors
    
    def get_validation_report(self, input_dir: Path, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Generate a comprehensive validation report.
        
        Args:
            input_dir: Path to input directory
            output_dir: Optional path to output directory
            
        Returns:
            Dictionary containing validation results
        """
        report = {
            'input_validation': None,
            'output_validation': None,
            'summary': {
                'valid': False,
                'input_errors': [],
                'output_errors': []
            }
        }
        
        # Validate inputs
        input_valid, input_errors = self.validate_input(input_dir)
        report['input_validation'] = {
            'valid': input_valid,
            'errors': input_errors,
            'specification': self.input_spec
        }
        report['summary']['input_errors'] = input_errors
        
        # Validate outputs if directory provided
        if output_dir:
            output_valid, output_errors = self.validate_output(output_dir)
            report['output_validation'] = {
                'valid': output_valid,
                'errors': output_errors,
                'specification': self.output_spec
            }
            report['summary']['output_errors'] = output_errors
            report['summary']['valid'] = input_valid and output_valid
        else:
            report['summary']['valid'] = input_valid
        
        return report