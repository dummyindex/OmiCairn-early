"""Centralized pricing configuration for all LLM models.

This module provides a single source of truth for model pricing across all services.
Prices are in USD per 1M tokens.
"""

from typing import Dict, Any

# OpenAI Chat Models - Prices per 1M tokens
OPENAI_CHAT_PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-2024-11-20": {"input": 2.50, "output": 10.00},
    "gpt-4o-2024-08-06": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o-mini-2024-07-18": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4-turbo-preview": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-4-32k": {"input": 60.00, "output": 120.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "gpt-3.5-turbo-16k": {"input": 3.00, "output": 4.00},
}

# OpenAI Embedding Models - Prices per 1M tokens
OPENAI_EMBEDDING_PRICING = {
    "text-embedding-ada-002": {"input": 0.10, "output": 0.00},
    "text-embedding-3-small": {"input": 0.02, "output": 0.00},
    "text-embedding-3-large": {"input": 0.13, "output": 0.00},
}

# Claude Models - Prices per 1M tokens
CLAUDE_PRICING = {
    # Claude 3 models
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "claude-3-sonnet-20240229": {"input": 3.0, "output": 15.0},
    "claude-3-opus-20240229": {"input": 15.0, "output": 75.0},
    
    # Claude 3.5 models
    "claude-3-5-haiku-20241022": {"input": 1.0, "output": 5.0},
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-5-sonnet-20240620": {"input": 3.0, "output": 15.0},
    
    # Claude 2 models
    "claude-2.1": {"input": 8.0, "output": 24.0},
    "claude-2.0": {"input": 8.0, "output": 24.0},
    "claude-instant-1.2": {"input": 0.8, "output": 2.4}
}

# Combined pricing for all models
ALL_MODEL_PRICING = {
    **OPENAI_CHAT_PRICING,
    **OPENAI_EMBEDDING_PRICING,
    **CLAUDE_PRICING
}


def get_model_pricing(model_name: str) -> Dict[str, float]:
    """Get pricing for a specific model.
    
    Args:
        model_name: Name of the model
        
    Returns:
        Dict with 'input' and 'output' pricing per 1M tokens
        
    Raises:
        KeyError: If model is not found in pricing database
    """
    if model_name not in ALL_MODEL_PRICING:
        # Try to find a similar model or use default
        if model_name.startswith("gpt-4o"):
            return OPENAI_CHAT_PRICING["gpt-4o"]
        elif model_name.startswith("gpt-4"):
            return OPENAI_CHAT_PRICING["gpt-4"]
        elif model_name.startswith("gpt-3.5"):
            return OPENAI_CHAT_PRICING["gpt-3.5-turbo"]
        elif model_name.startswith("claude-3-5"):
            return CLAUDE_PRICING["claude-3-5-sonnet-20241022"]
        elif model_name.startswith("claude-3"):
            return CLAUDE_PRICING["claude-3-haiku-20240307"]
        elif model_name.startswith("claude"):
            return CLAUDE_PRICING["claude-3-haiku-20240307"]
        else:
            raise KeyError(f"No pricing information for model: {model_name}")
    
    return ALL_MODEL_PRICING[model_name]


def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate the cost for a specific model usage.
    
    Args:
        model_name: Name of the model
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        
    Returns:
        Total cost in USD
    """
    pricing = get_model_pricing(model_name)
    
    # Convert to cost per 1M tokens
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    
    return input_cost + output_cost