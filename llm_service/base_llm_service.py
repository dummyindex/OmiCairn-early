"""Base LLM service interface for extensibility."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple


class BaseLLMService(ABC):
    """Abstract base class for LLM services."""
    
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.total_tokens_used = 0
        self.total_cost = 0.0
    
    @abstractmethod
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        **kwargs
    ) -> Dict[str, Any]:
        """Single turn chat completion."""
        pass
    
    @abstractmethod
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost based on model pricing."""
        pass
    
    def call_llm_json(
        self,
        messages: List[Dict[str, str]],
        json_schema: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        **kwargs
    ) -> Dict[str, Any]:
        """Call LLM with JSON response format.
        
        Default implementation uses chat_completion_json if available,
        otherwise falls back to regular chat_completion with parsing.
        """
        # Check if the service has chat_completion_json method
        if hasattr(self, 'chat_completion_json'):
            return self.chat_completion_json(
                messages=messages,
                json_schema=json_schema,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        else:
            # Fallback: Add JSON instruction to the last message
            import json
            messages_copy = messages.copy()
            if messages_copy:
                messages_copy[-1]['content'] += f"\n\nPlease respond with valid JSON that conforms to this schema:\n```json\n{json.dumps(json_schema, indent=2)}\n```"
            
            response = self.chat_completion(
                messages=messages_copy,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            # Try to parse JSON from the response
            try:
                content = response.get('content', '')
                # Look for JSON in code blocks
                import re
                json_match = re.search(r'```json?\s*({.*?})\s*```', content, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(1))
                else:
                    # Try to parse the entire response
                    return json.loads(content)
            except json.JSONDecodeError:
                # Return a default structure if parsing fails
                return {"error": "Failed to parse JSON response", "raw_response": content}
    
    def get_usage_summary(self) -> Dict[str, Any]:
        """Get usage summary for this session."""
        return {
            "total_tokens": self.total_tokens_used,
            "total_cost": self.total_cost,
            "model": self.model
        }
    
    def reset_usage(self):
        """Reset usage counters."""
        self.total_tokens_used = 0
        self.total_cost = 0.0
    
    def call_llm(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        **kwargs
    ) -> str:
        """Convenience method for getting string response from LLM.
        
        This is used by the debug session for simple text responses.
        """
        response = self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        return response.get('content', '')