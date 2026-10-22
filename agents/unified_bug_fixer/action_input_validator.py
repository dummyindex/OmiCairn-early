"""
Action Input Validator for Bug Fixer

Validates all LLM action inputs to prevent crashes from None values, missing parameters,
and malformed data. Provides clear error logging for debugging LLM output issues.
"""

import logging
from typing import Dict, Any, Optional, List, Union
from utils.logger import get_logger

logger = get_logger(__name__)

class ActionInputValidator:
    """Validates action inputs from LLM to prevent system crashes."""
    
    # Define required parameters for each action type
    ACTION_REQUIREMENTS = {
        'read_file': {
            'required': ['path'],
            'optional': []
        },
        'write_file': {
            'required': ['path', 'content'],
            'optional': []
        },
        'execute_command': {
            'required': ['command'],
            'optional': []
        },
        'install_package': {
            'required': ['package'],
            'optional': []
        },
        'update_function_block': {
            'required': ['code'],
            'optional': ['requirements', 'language', 'confidence']
        },
        'list_directory': {
            'required': [],
            'optional': ['path']
        },
        'check_file_exists': {
            'required': ['path'],
            'optional': []
        },
        'head_file': {
            'required': ['path'],
            'optional': ['lines']
        },
        'tail_file': {
            'required': ['path'],
            'optional': ['lines']
        },
        'grep_file': {
            'required': ['path', 'pattern'],
            'optional': []
        },
        'create_directory': {
            'required': ['path'],
            'optional': []
        },
        'list_previous_nodes': {
            'required': [],
            'optional': []
        },
        'retrieve_previous_node_file': {
            'required': ['node_index', 'filename'],
            'optional': []
        },
        'retrieve_previous_node_files': {
            'required': ['files'],
            'optional': []
        },
        'write_and_run': {
            'required': ['files', 'run_script'],
            'optional': ['description']
        },
        'research_online': {
            'required': ['query'],
            'optional': ['research_type']
        },
        # Output collector specific actions
        'tree_directory': {
            'required': ['path'],
            'optional': ['max_depth']
        },
        'find_files': {
            'required': ['pattern'],
            'optional': ['path', 'type']
        },
        'copy_file': {
            'required': ['source', 'destination'],
            'optional': []
        },
        'move_file': {
            'required': ['source', 'destination'],
            'optional': []
        },
        'get_file_info': {
            'required': ['path'],
            'optional': []
        }
    }

    @classmethod
    def validate_action(cls, action: Dict[str, Any], original_llm_response: str = "") -> Dict[str, Any]:
        """
        Validate an action dictionary from LLM.
        
        Args:
            action: The action dictionary to validate
            original_llm_response: Original LLM response for error logging
            
        Returns:
            Dict with validation results:
            {
                'valid': bool,
                'action': Dict (validated/sanitized action),
                'errors': List[str],
                'warnings': List[str]
            }
        """
        errors = []
        warnings = []
        validated_action = action.copy() if action else {}
        
        # Basic structure validation
        if not isinstance(action, dict):
            errors.append(f"Action must be a dictionary, got {type(action)}")
            cls._log_validation_error("INVALID_TYPE", action, original_llm_response, errors)
            return {'valid': False, 'action': {}, 'errors': errors, 'warnings': warnings}
        
        # Check action type
        action_type = action.get('type')
        if not action_type:
            errors.append("Missing required field 'type'")
        elif not isinstance(action_type, str):
            errors.append(f"Action type must be string, got {type(action_type)}")
        elif action_type not in cls.ACTION_REQUIREMENTS:
            errors.append(f"Unknown action type: {action_type}")
        
        if errors:
            cls._log_validation_error("INVALID_ACTION_TYPE", action, original_llm_response, errors)
            return {'valid': False, 'action': validated_action, 'errors': errors, 'warnings': warnings}
        
        # Validate parameters
        params_result = cls._validate_parameters(action, action_type, original_llm_response)
        validated_action['type'] = action_type
        validated_action.update(params_result['params'])
        errors.extend(params_result['errors'])
        warnings.extend(params_result['warnings'])
        
        # Validate confidence if present
        confidence = action.get('confidence')
        if confidence is not None:
            if not isinstance(confidence, (int, float)):
                warnings.append(f"Confidence should be numeric, got {type(confidence)}. Setting to 0.5")
                validated_action['confidence'] = 0.5
            elif not (0.0 <= confidence <= 1.0):
                warnings.append(f"Confidence should be between 0.0 and 1.0, got {confidence}. Clamping to range")
                validated_action['confidence'] = max(0.0, min(1.0, float(confidence)))
            else:
                validated_action['confidence'] = float(confidence)
        
        # Validate explanation if present
        explanation = action.get('explanation')
        if explanation is not None and not isinstance(explanation, str):
            warnings.append(f"Explanation should be string, got {type(explanation)}. Converting to string")
            validated_action['explanation'] = str(explanation)
        
        is_valid = len(errors) == 0
        
        if not is_valid:
            cls._log_validation_error("PARAMETER_VALIDATION_FAILED", action, original_llm_response, errors)
        elif warnings:
            cls._log_validation_warning("PARAMETER_WARNINGS", action, original_llm_response, warnings)
        
        return {
            'valid': is_valid,
            'action': validated_action,
            'errors': errors,
            'warnings': warnings
        }
    
    @classmethod
    def _validate_parameters(cls, action: Dict[str, Any], action_type: str, original_llm_response: str) -> Dict[str, Any]:
        """Validate action parameters."""
        errors = []
        warnings = []
        validated_params = {}
        
        requirements = cls.ACTION_REQUIREMENTS[action_type]
        
        # Extract parameters from various possible locations
        params = {}
        if 'params' in action:
            params.update(action.get('params', {}))
        if 'parameters' in action:
            params.update(action.get('parameters', {}))
        
        # Also check direct properties for backward compatibility
        for req_param in requirements['required'] + requirements['optional']:
            if req_param in action and req_param not in params:
                params[req_param] = action[req_param]
        
        # Validate required parameters
        for param_name in requirements['required']:
            param_value = params.get(param_name)
            
            # Check if parameter exists at all
            if param_name not in params:
                errors.append(f"Missing required parameter '{param_name}' for action '{action_type}'")
            else:
                # Validate parameter value (including None values)
                validated_value = cls._validate_parameter_value(param_name, param_value, action_type)
                if validated_value['valid']:
                    validated_params[param_name] = validated_value['value']
                    if validated_value['warnings']:
                        warnings.extend(validated_value['warnings'])
                else:
                    errors.extend(validated_value['errors'])
        
        # Validate optional parameters
        for param_name in requirements['optional']:
            param_value = params.get(param_name)
            
            if param_value is not None:
                validated_value = cls._validate_parameter_value(param_name, param_value, action_type)
                if validated_value['valid']:
                    validated_params[param_name] = validated_value['value']
                    if validated_value['warnings']:
                        warnings.extend(validated_value['warnings'])
                else:
                    # For optional parameters, warn but don't fail
                    warnings.extend([f"Optional parameter '{param_name}': {err}" for err in validated_value['errors']])
        
        return {
            'params': validated_params,
            'errors': errors,
            'warnings': warnings
        }
    
    @classmethod
    def _validate_parameter_value(cls, param_name: str, value: Any, action_type: str) -> Dict[str, Any]:
        """Validate a specific parameter value."""
        errors = []
        warnings = []
        
        # String parameters (most common)
        if param_name in ['path', 'content', 'command', 'package', 'code', 'pattern', 'filename', 'language']:
            if not isinstance(value, str):
                if value is None:
                    errors.append(f"Parameter '{param_name}' cannot be None")
                    return {'valid': False, 'value': None, 'errors': errors, 'warnings': warnings}
                else:
                    warnings.append(f"Parameter '{param_name}' should be string, got {type(value)}. Converting to string")
                    value = str(value)
            
            # Additional validation for paths
            if param_name == 'path':
                if not value.strip():
                    errors.append(f"Path parameter cannot be empty")
                    return {'valid': False, 'value': None, 'errors': errors, 'warnings': warnings}
                value = value.strip()
        
        # Numeric parameters
        elif param_name in ['lines', 'node_index']:
            if not isinstance(value, (int, float)):
                try:
                    value = int(value)
                    warnings.append(f"Parameter '{param_name}' converted to integer: {value}")
                except (ValueError, TypeError):
                    errors.append(f"Parameter '{param_name}' must be numeric, got {type(value)}")
                    return {'valid': False, 'value': None, 'errors': errors, 'warnings': warnings}
            else:
                value = int(value)
            
            # Validate ranges
            if param_name == 'lines' and value <= 0:
                warnings.append(f"Lines parameter should be positive, got {value}. Setting to 20")
                value = 20
            elif param_name == 'node_index' and value < 0:
                errors.append(f"Node index must be non-negative, got {value}")
                return {'valid': False, 'value': None, 'errors': errors, 'warnings': warnings}
        
        # List parameters
        elif param_name in ['requirements', 'files']:
            if not isinstance(value, list):
                if value is None:
                    value = []
                    warnings.append(f"Parameter '{param_name}' was None, setting to empty list")
                else:
                    errors.append(f"Parameter '{param_name}' must be a list, got {type(value)}")
                    return {'valid': False, 'value': None, 'errors': errors, 'warnings': warnings}
            
            # Validate list contents
            if param_name == 'requirements':
                # Ensure all requirements are strings
                validated_reqs = []
                for i, req in enumerate(value):
                    if not isinstance(req, str):
                        warnings.append(f"Requirement {i} should be string, got {type(req)}. Converting to string")
                        validated_reqs.append(str(req))
                    else:
                        validated_reqs.append(req)
                value = validated_reqs
            
            elif param_name == 'files':
                # Validate file specification format based on action type
                for i, file_spec in enumerate(value):
                    if not isinstance(file_spec, dict):
                        errors.append(f"File specification {i} must be a dictionary")
                        return {'valid': False, 'value': None, 'errors': errors, 'warnings': warnings}
                    
                    # Different validation for different actions
                    if action_type == 'write_and_run':
                        # write_and_run expects 'path' and 'content' in each file
                        if 'path' not in file_spec or 'content' not in file_spec:
                            errors.append(f"File specification {i} missing required fields 'path' or 'content'")
                            return {'valid': False, 'value': None, 'errors': errors, 'warnings': warnings}
                    elif action_type == 'retrieve_previous_node_files':
                        # retrieve_previous_node_files expects 'node_index' and 'filename'
                        if 'node_index' not in file_spec or 'filename' not in file_spec:
                            errors.append(f"File specification {i} missing required fields 'node_index' or 'filename'")
                            return {'valid': False, 'value': None, 'errors': errors, 'warnings': warnings}
        
        return {'valid': True, 'value': value, 'errors': errors, 'warnings': warnings}
    
    @classmethod
    def _log_validation_error(cls, error_type: str, action: Dict[str, Any], original_llm_response: str, errors: List[str]):
        """Log validation errors with full context."""
        logger.error("="*80)
        logger.error(f"ACTION VALIDATION ERROR: {error_type}")
        logger.error(f"Errors: {errors}")
        logger.error(f"Action received: {action}")
        logger.error("Original LLM Response:")
        logger.error(original_llm_response[:2000] + "..." if len(original_llm_response) > 2000 else original_llm_response)
        logger.error("="*80)
    
    @classmethod
    def _log_validation_warning(cls, warning_type: str, action: Dict[str, Any], original_llm_response: str, warnings: List[str]):
        """Log validation warnings with context."""
        logger.warning("="*60)
        logger.warning(f"ACTION VALIDATION WARNING: {warning_type}")
        logger.warning(f"Warnings: {warnings}")
        logger.warning(f"Action: {action}")
        logger.warning("="*60)
    
    @classmethod
    def format_actions_for_prompt(cls, allowed_actions: set = None) -> str:
        """
        Format action documentation for LLM prompts.
        
        Args:
            allowed_actions: Set of action types to document. If None, documents all.
            
        Returns:
            Formatted string with action documentation
        """
        lines = ["Available actions and their EXACT parameters:"]
        lines.append("")
        
        actions_to_document = allowed_actions if allowed_actions else cls.ACTION_REQUIREMENTS.keys()
        
        for i, action_type in enumerate(sorted(actions_to_document), 1):
            if action_type not in cls.ACTION_REQUIREMENTS:
                continue
                
            requirements = cls.ACTION_REQUIREMENTS[action_type]
            lines.append(f"{i}. **{action_type}**:")
            
            # Required parameters
            if requirements['required']:
                for param in requirements['required']:
                    lines.append(f"   - {param}: (required)")
            else:
                lines.append("   - No required parameters")
            
            # Optional parameters
            if requirements['optional']:
                for param in requirements['optional']:
                    lines.append(f"   - {param}: (optional)")
            
            lines.append("")
        
        lines.append("IMPORTANT: Use ONLY the parameters listed above for each action.")
        lines.append("Do NOT add extra parameters. The system will ignore unexpected parameters.")
        
        return "\n".join(lines)
    
    @classmethod
    def create_crash_report_action(cls, crash_type: str, original_action: Dict[str, Any], original_llm_response: str, error_details: str) -> Dict[str, Any]:
        """Create a standardized crash report action for logging purposes."""
        return {
            'type': 'SYSTEM_CRASH_REPORT',
            'crash_type': crash_type,
            'original_action': original_action,
            'original_llm_response': original_llm_response[:1000] + "..." if len(original_llm_response) > 1000 else original_llm_response,
            'error_details': error_details,
            'action_result': {
                'success': False,
                'error': f"SYSTEM CRASH: {crash_type} - {error_details}",
                'crash_report': True,
                'next_turn_instruction': "Previous action caused system crash. Please try a different approach."
            }
        }