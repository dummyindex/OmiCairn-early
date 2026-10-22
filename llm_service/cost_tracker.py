"""Cost tracking utility for LLM and embedding model usage."""

from typing import Dict, Optional, Tuple
import logging
from dataclasses import dataclass, field
from .pricing_config import (
    OPENAI_CHAT_PRICING, OPENAI_EMBEDDING_PRICING, CLAUDE_PRICING,
    ALL_MODEL_PRICING, get_model_pricing, calculate_cost as calc_cost
)
from constants import DEFAULT_OPENAI_MODEL

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Track token usage for a model."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    def add(self, input_tokens: int, output_tokens: int):
        """Add token usage."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens


@dataclass
class CostTracker:
    """Track costs for LLM and embedding model usage."""
    
    # Use centralized pricing from pricing_config
    OPENAI_CHAT_PRICING = OPENAI_CHAT_PRICING
    OPENAI_EMBEDDING_PRICING = OPENAI_EMBEDDING_PRICING
    CLAUDE_PRICING = CLAUDE_PRICING
    ALL_PRICING = ALL_MODEL_PRICING
    
    # Track usage by model
    usage_by_model: Dict[str, TokenUsage] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize usage tracking."""
        self.usage_by_model = {}
        self.total_cost = 0.0
    
    def track_usage(self, model: str, input_tokens: int, output_tokens: int = 0) -> float:
        """Track token usage and return cost for this usage.
        
        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens (0 for embeddings)
            
        Returns:
            Cost in dollars for this usage
        """
        # Initialize model usage if needed
        if model not in self.usage_by_model:
            self.usage_by_model[model] = TokenUsage()
        
        # Add usage
        self.usage_by_model[model].add(input_tokens, output_tokens)
        
        # Calculate cost
        cost = self.calculate_cost(model, input_tokens, output_tokens)
        self.total_cost += cost
        
        return cost
    
    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int = 0) -> float:
        """Calculate cost for given token usage.
        
        Args:
            model: Model name
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            
        Returns:
            Cost in dollars
        """
        # Find pricing for model
        pricing = self._get_pricing(model)
        if not pricing:
            logger.warning(f"Unknown model {model}, using default GPT-4o-mini pricing")
            pricing = self.OPENAI_CHAT_PRICING["gpt-4o-mini"]
        
        # Calculate costs separately
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        
        total_cost = input_cost + output_cost
        
        logger.debug(
            f"Cost for {model}: {input_tokens} input tokens (${input_cost:.4f}) + "
            f"{output_tokens} output tokens (${output_cost:.4f}) = ${total_cost:.4f}"
        )
        
        return total_cost
    
    def _get_pricing(self, model: str) -> Optional[Dict[str, float]]:
        """Get pricing for a model, handling variants."""
        # Direct lookup
        if model in self.ALL_PRICING:
            return self.ALL_PRICING[model]
        
        # Try to find by prefix match (e.g., gpt-4o-2024-11-20 matches gpt-4o)
        for pricing_model, pricing in self.ALL_PRICING.items():
            if model.startswith(pricing_model):
                return pricing
        
        return None
    
    def get_model_summary(self, model: str) -> Dict[str, any]:
        """Get usage summary for a specific model."""
        if model not in self.usage_by_model:
            return {
                "model": model,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost": 0.0
            }
        
        usage = self.usage_by_model[model]
        cost = self.calculate_cost(model, usage.input_tokens, usage.output_tokens)
        
        return {
            "model": model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "cost": cost
        }
    
    def get_summary(self) -> Dict[str, any]:
        """Get complete usage summary."""
        model_summaries = {}
        total_input_tokens = 0
        total_output_tokens = 0
        
        for model in self.usage_by_model:
            summary = self.get_model_summary(model)
            model_summaries[model] = summary
            total_input_tokens += summary["input_tokens"]
            total_output_tokens += summary["output_tokens"]
        
        return {
            "total_cost": self.total_cost,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "models": model_summaries
        }
    
    def reset(self):
        """Reset all tracking."""
        self.usage_by_model.clear()
        self.total_cost = 0.0


class OpenAICallbackHandler:
    """Custom callback handler for OpenAI that properly tracks costs."""
    
    def __init__(self):
        self.cost_tracker = CostTracker()
        self.total_cost = 0.0
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
    
    def on_llm_end(self, response, **kwargs):
        """Handle LLM response and track costs."""
        if hasattr(response, 'llm_output') and response.llm_output:
            usage = response.llm_output.get('token_usage', {})
            model = response.llm_output.get('model_name', 'gpt-4o-mini')
            
            prompt_tokens = usage.get('prompt_tokens', 0)
            completion_tokens = usage.get('completion_tokens', 0)
            
            # Track usage
            cost = self.cost_tracker.track_usage(model, prompt_tokens, completion_tokens)
            
            # Update totals for compatibility
            self.total_cost += cost
            self.total_tokens += prompt_tokens + completion_tokens
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
    
    def on_embed_end(self, response, **kwargs):
        """Handle embedding response and track costs."""
        if hasattr(response, 'llm_output') and response.llm_output:
            usage = response.llm_output.get('token_usage', {})
            model = response.llm_output.get('model_name', 'text-embedding-3-small')
            
            # Embeddings only have input tokens
            input_tokens = usage.get('prompt_tokens', usage.get('total_tokens', 0))
            
            # Track usage
            cost = self.cost_tracker.track_usage(model, input_tokens, 0)
            
            # Update totals
            self.total_cost += cost
            self.total_tokens += input_tokens
            self.prompt_tokens += input_tokens
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass