"""
JSON parser for bug fixer - Pure JSON parsing without workarounds.

This module implements the only parser for bug fixer actions:
1. Parse the response as pure JSON (as requested in prompt)
2. If parsing fails, return detailed error information
3. Pass error details to next turn for LLM to correct

No hardcoded patterns, no workarounds, just JSON parsing.
"""

import json
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class JSONParser:
    """JSON parser for bug fixer actions - the only parser used."""
    
    @classmethod
    def parse_action(cls, text: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """
        Parse action from LLM response as pure JSON only.
        
        Args:
            text: The raw LLM response text
            
        Returns:
            Tuple of (parsed_action, error_message)
            - parsed_action: The parsed action dict if successful, None otherwise
            - error_message: Empty string if successful, detailed error otherwise
        """
        if not text or not text.strip():
            return None, "Empty response received from LLM"
        
        # Clean only basic whitespace - no other modifications
        cleaned_text = text.strip()
        
        # Try to parse as pure JSON - exactly as we asked for in the prompt
        try:
            data = json.loads(cleaned_text)
            
            # Validate it's a dict with required fields
            if not isinstance(data, dict):
                return None, f"Response is not a JSON object (got {type(data).__name__})"
            
            if 'type' not in data:
                return None, "JSON object missing required 'type' field"
            
            # Validate action type is a string
            if not isinstance(data['type'], str):
                return None, f"'type' field must be a string (got {type(data['type']).__name__})"
            
            # Ensure params is a dict if present
            if 'params' in data and not isinstance(data.get('params'), dict):
                return None, f"'params' field must be a dict (got {type(data['params']).__name__})"
            
            # Normalize to consistent format
            action = {
                'type': data['type'],
                'params': data.get('params', {}),
                'explanation': data.get('explanation', ''),
                'confidence': data.get('confidence', 0.5)
            }
            
            logger.info(f"Successfully parsed action: {action['type']}")
            return action, ""
            
        except json.JSONDecodeError as e:
            # Return detailed error information for debugging
            error_msg = f"JSON parsing failed at position {e.pos}: {e.msg}"
            
            # Add context around the error position
            if hasattr(e, 'pos') and e.pos is not None:
                start = max(0, e.pos - 50)
                end = min(len(cleaned_text), e.pos + 50)
                context = cleaned_text[start:end]
                error_msg += f"\nContext around error: ...{context}..."
            
            # Log the first part of the response for debugging
            logger.error(f"JSON parsing failed: {error_msg}")
            logger.error(f"First 500 chars of response: {cleaned_text[:500]}")
            
            return None, error_msg
        except Exception as e:
            # Catch any other unexpected errors
            error_msg = f"Unexpected error parsing JSON: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
    
    @classmethod
    def validate_action_params(cls, action: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate that action parameters are appropriate for the action type.
        
        Args:
            action: The parsed action dictionary
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        action_type = action.get('type', '')
        params = action.get('params', {})
        
        # Define required parameters for each action type
        required_params = {
            'read_file': ['path'],
            'write_file': ['path', 'content'],
            'execute_command': ['command'],
            'install_package': ['package'],
            'update_function_block': ['code', 'requirements'],
            'list_directory': ['path'],
            'create_directory': ['path'],
            'check_file_exists': ['path'],
            'head_file': ['path'],
            'tail_file': ['path'],
            'grep_file': ['path', 'pattern'],
            'write_and_run': ['files', 'run_script']
        }
        
        # Check if action type is known
        if action_type not in required_params:
            # Unknown action type - but we'll allow it
            logger.warning(f"Unknown action type: {action_type}")
            return True, ""
        
        # Check required parameters
        missing_params = []
        for param in required_params[action_type]:
            if param not in params:
                missing_params.append(param)
        
        if missing_params:
            error_msg = f"Action '{action_type}' missing required parameters: {', '.join(missing_params)}"
            return False, error_msg
        
        return True, ""