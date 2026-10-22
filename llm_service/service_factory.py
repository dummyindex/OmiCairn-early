"""Factory for creating appropriate LLM services based on model name."""

import os
from typing import Optional
from .base_llm_service import BaseLLMService
from .openai_service import OpenAIService
from .claude_service import ClaudeService
from .claude_code_cli_service import ClaudeCodeCLIService
from config import config
from constants import ENV_OPENAI_API_KEY
import logging

logger = logging.getLogger(__name__)


def create_llm_service(
    model_name: str,
    api_key: Optional[str] = None,
    timeout: Optional[int] = None,
    seed: Optional[int] = None,
    enable_web_search: bool = False,
    **kwargs
) -> BaseLLMService:
    """Create appropriate LLM service based on model name.
    
    This factory method handles all model types including:
    - OpenAI models (gpt-*, o1-*)
    - Claude API models (claude-3-*)
    - Claude CLI models (claude-cli-*)
    
    Args:
        model_name: Model identifier
        api_key: Optional API key (not needed for CLI models)
        timeout: Timeout in seconds
        seed: Seed for reproducibility
        enable_web_search: Enable web search for supported models
        **kwargs: Additional service-specific arguments
        
    Returns:
        Appropriate LLM service instance
        
    Raises:
        ValueError: If model type is unknown
    """
    # Use config timeout if not specified
    if timeout is None:
        timeout = config.llm_timeout if hasattr(config, 'llm_timeout') else 300
    
    # Handle Claude CLI models
    if model_name.startswith('claude-cli'):
        # Extract the model alias (sonnet, opus, haiku)
        if model_name == 'claude-cli':
            cli_model = 'sonnet'  # Default
        else:
            cli_model = model_name.replace('claude-cli-', '')
        
        service = ClaudeCodeCLIService(
            model=cli_model,
            timeout=timeout,
            debug=kwargs.get('debug', False)
        )
        logger.info(f"Created Claude CLI service with model: {cli_model}")
        return service
    
    # Handle OpenAI models
    elif model_name.startswith('gpt') or model_name.startswith('o1'):
        service = OpenAIService(
            api_key=api_key or os.getenv(ENV_OPENAI_API_KEY),
            model=model_name,
            timeout=timeout,
            max_retries=kwargs.get('max_retries', 2),
            seed=seed
        )
        logger.info(f"Created OpenAI service with model: {model_name}")
        return service
    
    # Handle Claude API models
    elif model_name.startswith('claude'):
        service = ClaudeService(
            api_key=api_key or os.getenv('ANTHROPIC_API_KEY'),
            model=model_name,
            enable_web_search=enable_web_search
        )
        logger.info(f"Created Claude API service with model: {model_name}")
        return service
    
    else:
        raise ValueError(f"Unknown model type: {model_name}. Supported prefixes: gpt-, o1-, claude-, claude-cli-")


def is_cli_model(model_name: str) -> bool:
    """Check if model is a CLI model that doesn't need API keys.
    
    Args:
        model_name: Model identifier
        
    Returns:
        True if model uses CLI authentication, False otherwise
    """
    return model_name.startswith('claude-cli')


def get_required_api_key_type(model_name: str) -> Optional[str]:
    """Get the type of API key required for a model.
    
    Args:
        model_name: Model identifier
        
    Returns:
        'openai' for OpenAI models, 'anthropic' for Claude API models, 
        None for CLI models or unknown types
    """
    if model_name.startswith('claude-cli'):
        return None  # No API key needed
    elif model_name.startswith('gpt') or model_name.startswith('o1'):
        return 'openai'
    elif model_name.startswith('claude'):
        return 'anthropic'
    else:
        return None