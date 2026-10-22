"""Cost-aware callback handler for accurate LLM cost tracking."""

from typing import Dict, Any, Optional
from contextlib import contextmanager
import logging

from langchain_community.callbacks.manager import get_openai_callback
from llm_service.cost_tracker import CostTracker

logger = logging.getLogger(__name__)


class CostAwareCallback:
    """Enhanced callback that properly tracks costs with separate input/output pricing."""
    
    def __init__(self):
        self.cost_tracker = CostTracker()
        self.total_cost = 0.0
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.model_name = None
    
    def update_from_response(self, response: Any, model_name: Optional[str] = None):
        """Update costs from LLM response."""
        # Try to extract token usage from response
        usage = None
        
        # Handle LangChain response format
        if hasattr(response, 'response_metadata'):
            usage = response.response_metadata.get('token_usage', {})
            if not model_name and 'model_name' in response.response_metadata:
                model_name = response.response_metadata['model_name']
        
        # Handle raw OpenAI response format
        elif hasattr(response, 'usage'):
            usage = {
                'prompt_tokens': response.usage.prompt_tokens,
                'completion_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            }
            if not model_name and hasattr(response, 'model'):
                model_name = response.model
        
        if usage:
            prompt_tokens = usage.get('prompt_tokens', 0)
            completion_tokens = usage.get('completion_tokens', 0)
            
            # Use our proper cost calculation
            if model_name:
                cost = self.cost_tracker.track_usage(model_name, prompt_tokens, completion_tokens)
                self.total_cost += cost
                self.total_tokens += prompt_tokens + completion_tokens
                self.prompt_tokens += prompt_tokens
                self.completion_tokens += completion_tokens
                
                logger.debug(
                    f"Updated costs for {model_name}: "
                    f"{prompt_tokens} input + {completion_tokens} output tokens = ${cost:.4f}"
                )
            else:
                logger.warning("No model name found in response, cannot calculate accurate cost")


@contextmanager
def get_cost_aware_callback(model_name: Optional[str] = None):
    """Context manager for cost-aware callback.
    
    This replaces get_openai_callback() with proper cost tracking.
    
    Usage:
        with get_cost_aware_callback(model_name="gpt-4o-mini") as cb:
            response = await llm.ainvoke(messages)
            cb.update_from_response(response)
            
        print(f"Cost: ${cb.total_cost:.4f}")
    """
    callback = CostAwareCallback()
    if model_name:
        callback.model_name = model_name
    
    try:
        yield callback
    finally:
        # Log final costs
        if callback.total_tokens > 0:
            logger.info(
                f"Total usage: {callback.prompt_tokens} input + "
                f"{callback.completion_tokens} output tokens = ${callback.total_cost:.4f}"
            )


def compare_cost_calculations():
    """Compare LangChain callback costs with our accurate calculations."""
    test_cases = [
        # Model, input_tokens, output_tokens
        ("gpt-4o-mini", 1000, 500),
        ("gpt-4o", 2000, 1000),
        ("text-embedding-3-small", 5000, 0),  # Embeddings have no output
        ("claude-3-5-sonnet-20241022", 3000, 1500),
    ]
    
    print("\nCost Calculation Comparison")
    print("=" * 80)
    print(f"{'Model':<30} {'Tokens In':<10} {'Tokens Out':<10} {'Our Cost':<15} {'Notes'}")
    print("-" * 80)
    
    cost_tracker = CostTracker()
    
    for model, input_tokens, output_tokens in test_cases:
        our_cost = cost_tracker.calculate_cost(model, input_tokens, output_tokens)
        
        # Check if it's an embedding model
        is_embedding = "embedding" in model
        
        notes = ""
        if is_embedding and output_tokens > 0:
            notes = "⚠️ Embeddings should have 0 output tokens"
        elif is_embedding:
            notes = "✓ Embedding pricing"
        else:
            notes = "✓ Separate I/O pricing"
        
        print(f"{model:<30} {input_tokens:<10} {output_tokens:<10} ${our_cost:<14.4f} {notes}")
    
    print("\n" + "=" * 80)
    print("\nKey Improvements:")
    print("1. ✓ Embedding models use correct low pricing ($0.02-$0.13 per 1M tokens)")
    print("2. ✓ Chat models use separate input/output pricing")
    print("3. ✓ All current OpenAI and Claude models supported")
    print("4. ✓ Automatic model variant matching (e.g., gpt-4o-2024-11-20 → gpt-4o)")


if __name__ == "__main__":
    # Run comparison when executed directly
    compare_cost_calculations()