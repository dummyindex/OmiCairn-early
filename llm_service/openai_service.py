"""OpenAI service for LLM interactions."""

import json
import logging
import re
from typing import Dict, List, Optional, Any
import httpx
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, APITimeoutError

from utils.logger import get_logger
from config import config
from constants import DEFAULT_OPENAI_MODEL
from .pricing_config import get_model_pricing, calculate_cost

logger = get_logger(__name__)


class OpenAIService:
    """Simple service for OpenAI API interactions."""
    
    # Use centralized pricing - keeping for backward compatibility
    @property
    def PRICING(self):
        """Get pricing information (deprecated - use pricing_config module)."""
        from .pricing_config import OPENAI_CHAT_PRICING, OPENAI_EMBEDDING_PRICING
        return {**OPENAI_CHAT_PRICING, **OPENAI_EMBEDDING_PRICING}
    
    def __init__(
        self, 
        api_key: Optional[str] = None, 
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 2,
        seed: Optional[int] = None
    ):
        self.api_key = api_key or config.openai_api_key
        if not self.api_key:
            raise ValueError("OpenAI API key not provided")
        
        # Configure timeout - default to 5 minutes (300 seconds)
        if timeout is None:
            timeout = getattr(config, 'llm_timeout', 300.0)
        
        # Create timeout configuration
        # httpx.Timeout uses positional arg for default timeout, then named args for specific timeouts
        timeout_config = httpx.Timeout(
            timeout,  # Default timeout for all operations
            connect=10.0,  # 10 seconds to establish connection
            read=timeout,  # Full timeout for reading response (LLM responses can be slow)
            write=10.0  # 10 seconds for writing request
        )
        
        logger.info(f"Initializing OpenAI client with timeout={timeout}s, max_retries={max_retries}")
        
        # Ensure OpenAI service logging doesn't clutter stdout
        # Set this service logger to INFO level to prevent DEBUG logs from showing
        openai_service_logger = logging.getLogger('omicairn_agent.llm_service.openai_service')
        openai_service_logger.setLevel(logging.INFO)
        
        # Also quiet the openai client library itself
        openai_client_logger = logging.getLogger('openai')
        openai_client_logger.setLevel(logging.WARNING)
        
        # Quiet httpx library (used by openai client)
        httpx_logger = logging.getLogger('httpx')
        httpx_logger.setLevel(logging.WARNING)
        
        self.client = OpenAI(
            api_key=self.api_key,
            timeout=timeout_config,
            max_retries=max_retries
        )
        self.model = model or config.openai_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.seed = seed
        
        # Track usage
        self.total_tokens_used = 0
        self.total_cost = 0.0
        
    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate cost based on model pricing."""
        try:
            # Use centralized pricing calculation
            cost = calculate_cost(self.model, prompt_tokens, completion_tokens)
            return cost
        except KeyError:
            # Fallback for unknown models
            logger.warning(f"Unknown model {self.model}, using default pricing")
            return calculate_cost(DEFAULT_OPENAI_MODEL, prompt_tokens, completion_tokens)
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        response_format: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """Chat completion API call with usage tracking.
        
        Returns:
            Dict with 'content', 'usage', 'cost', and 'model' keys
        """
        # Use provided seed or instance default
        effective_seed = seed if seed is not None else self.seed
        
        # Log request details for debugging
        logger.debug(f"OpenAI request: model={self.model}, messages={len(messages)}, "
                    f"temperature={temperature}, max_tokens={max_tokens}, "
                    f"timeout={self.timeout}s, seed={effective_seed}")
        
        try:
            kwargs = {
                "model": self.model,
                "messages": messages
            }
            
            # GPT-5 models have specific requirements
            if self.model.startswith('gpt-5'):
                # GPT-5 uses max_completion_tokens instead of max_tokens
                # GPT-5 models use reasoning tokens, so need higher limits for structured outputs
                gpt5_max_tokens = max(max_tokens * 3, 1500)  # At least 3x the requested tokens, minimum 1500
                kwargs["max_completion_tokens"] = gpt5_max_tokens
                logger.debug(f"GPT-5 model: increased max_tokens from {max_tokens} to {gpt5_max_tokens} for reasoning tokens")
                
                # GPT-5 models only support default temperature (1.0)
                if temperature != 1.0:
                    logger.debug(f"GPT-5 models only support temperature=1.0, ignoring temperature={temperature}")
                # Don't include temperature parameter for GPT-5
            else:
                kwargs["temperature"] = temperature
                kwargs["max_tokens"] = max_tokens
            
            if response_format:
                kwargs["response_format"] = response_format
            
            # Add seed for reproducibility if provided
            if effective_seed is not None:
                kwargs["seed"] = effective_seed
            
            # Make the API call
            logger.debug("Sending request to OpenAI API...")
            response = self.client.chat.completions.create(**kwargs)
            logger.debug("Received response from OpenAI API")
            
            # Check if response has content
            if not response.choices or not response.choices[0].message:
                logger.error(f"Empty response from {self.model}")
                raise ValueError(f"Empty response from {self.model}")
                
            content = response.choices[0].message.content
            
            # Check for empty content
            if not content:
                logger.error(f"Empty content from {self.model}, response: {response}")
                raise ValueError(f"Empty content from {self.model}")
            
            # Extract usage information
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
            
            # Calculate cost
            cost = self.calculate_cost(usage["prompt_tokens"], usage["completion_tokens"])
            
            # Update totals
            self.total_tokens_used += usage["total_tokens"]
            self.total_cost += cost
            
            logger.debug(f"OpenAI response: {len(content)} chars, tokens: {usage['total_tokens']}, cost: ${cost:.4f}")
            
            return {
                "content": content,
                "usage": usage,
                "cost": cost,
                "model": self.model
            }
            
        except APITimeoutError as e:
            # Specific timeout error handling
            logger.error(f"OpenAI API timeout after {self.timeout}s: {e}")
            logger.error(f"Request details: model={self.model}, message_count={len(messages)}, "
                        f"temperature={temperature}, max_tokens={max_tokens}")
            logger.error("Consider increasing timeout or reducing request size")
            raise
            
        except RateLimitError as e:
            # Rate limit error handling
            logger.error(f"OpenAI API rate limit exceeded: {e}")
            logger.error("Consider implementing exponential backoff or reducing request frequency")
            raise
            
        except APIConnectionError as e:
            # Connection error handling
            logger.error(f"OpenAI API connection error: {e}")
            logger.error("Check network connectivity and API endpoint availability")
            raise
            
        except APIError as e:
            # General API error handling
            logger.error(f"OpenAI API error: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise
            
        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"Unexpected error in OpenAI API call: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
    
    def chat_completion_json(
        self,
        messages: List[Dict[str, str]],
        json_schema: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """Chat completion with structured JSON response format.
        
        Uses OpenAI's structured outputs with strict schema enforcement for supported models.
        Falls back to JSON mode for models that don't support json_schema.
        """
        # Models that support json_schema response format (as of late 2024)
        SUPPORTS_JSON_SCHEMA = ['gpt-4o', 'gpt-4o-mini', 'gpt-4o-2024-08-06', 'gpt-5', 'gpt-5-mini', 'gpt-5-nano']
        
        # Check if current model supports json_schema
        model_supports_schema = any(supported in self.model for supported in SUPPORTS_JSON_SCHEMA)
        
        if model_supports_schema:
            # Use structured outputs with json_schema
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response_schema",
                    "strict": True,
                    "schema": json_schema
                }
            }
            logger.debug(f"Using json_schema response format for model {self.model}")
        else:
            # Fallback to JSON mode for models like gpt-3.5-turbo and gpt-4-turbo
            response_format = {"type": "json_object"}
            logger.debug(f"Model {self.model} doesn't support json_schema, using json_object mode")
            
            # Add schema information to the prompt for better compliance
            schema_prompt = f"\n\nPlease return a JSON object that exactly matches this schema:\n```json\n{json.dumps(json_schema, indent=2)}\n```\n\nReturn ONLY the JSON object, no additional text."
            messages = messages.copy()
            messages[-1]['content'] += schema_prompt
        
        response = self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            seed=seed
        )
        
        # Extract content string from response dict
        content = response['content'] if isinstance(response, dict) else response
        
        # Parse JSON response
        try:
            parsed = json.loads(content)
            logger.debug(f"Successfully parsed JSON response from {self.model}")
            return parsed
        except json.JSONDecodeError as e:
            if model_supports_schema:
                # This should not happen with structured outputs (strict=True)
                logger.error(f"Unexpected JSON decode error with structured outputs: {e}")
            else:
                # More expected with json_object mode
                logger.error(f"JSON decode error in fallback mode: {e}")
            logger.error(f"Model: {self.model}, Response content: {content}")
            raise ValueError(f"Failed to produce valid JSON: {e}")
    
    def extract_code_block(self, content: str, language: Optional[str] = None) -> Optional[str]:
        """Extract code block from markdown-formatted response."""
        if "```" not in content:
            return content.strip()
            
        parts = content.split("```")
        for i, part in enumerate(parts):
            if i % 2 == 1:  # Code blocks are at odd indices
                lines = part.strip().split('\n')
                if lines:
                    # Check if first line is a language identifier
                    first_line = lines[0].lower()
                    if language:
                        # If specific language requested, only return matching blocks
                        if first_line == language:
                            return '\n'.join(lines[1:])
                    else:
                        # Return first code block, removing language identifier if present
                        if first_line in ['python', 'r', 'bash', 'shell']:
                            return '\n'.join(lines[1:])
                        return part.strip()
        
        return None
    
    def get_usage_summary(self) -> Dict[str, Any]:
        """Get usage summary for the session.
        
        Returns:
            Dict with total_tokens, total_cost, and breakdown
        """
        return {
            "total_tokens": self.total_tokens_used,
            "total_cost": self.total_cost,
            "model": self.model
        }
    
    def call_llm(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        **kwargs
    ) -> str:
        """Convenience method for getting string response from LLM."""
        response = self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        return response.get('content', '')
    
    def call_llm_json(
        self,
        messages: List[Dict[str, str]],
        json_schema: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        **kwargs
    ) -> Dict[str, Any]:
        """Call LLM with JSON response format using OpenAI's JSON mode."""
        # Check if we have the JSON schema method
        if hasattr(self, 'chat_completion_json'):
            return self.chat_completion_json(
                messages=messages,
                json_schema=json_schema,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        else:
            # Use response_format for JSON mode
            response = self.chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}
            )
            
            # Parse JSON from response
            try:
                return json.loads(response.get('content', '{}'))
            except json.JSONDecodeError:
                return {"error": "Failed to parse JSON response", "raw_response": response.get('content', '')}