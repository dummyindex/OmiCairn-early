"""Claude/Anthropic service for LLM interactions."""

import os
import json
from typing import Dict, List, Optional, Any, Generator
import httpx
from anthropic import Anthropic, APIError, APIConnectionError, RateLimitError, APITimeoutError

from .base_llm_service import BaseLLMService
from utils.logger import get_logger
from config import config
from constants import DEFAULT_CLAUDE_MODEL
from .pricing_config import get_model_pricing, calculate_cost
from .claude_rate_limit_handler import ClaudeRateLimitHandler

logger = get_logger(__name__)


class ClaudeService(BaseLLMService):
    """Service for Claude/Anthropic API interactions."""
    
    # Use centralized pricing - keeping for backward compatibility
    @property
    def PRICING(self):
        """Get pricing information (deprecated - use pricing_config module)."""
        from .pricing_config import CLAUDE_PRICING
        return CLAUDE_PRICING
    
    # Web search cost: $10 per 1,000 searches
    WEB_SEARCH_COST_PER_USE = 0.01  # $0.01 per search
    
    def __init__(
        self, 
        api_key: Optional[str] = None, 
        model: str = DEFAULT_CLAUDE_MODEL, 
        enable_web_search: bool = False,
        timeout: Optional[float] = None,
        max_retries: int = 2
    ):
        """Initialize Claude service.
        
        Args:
            api_key: Anthropic API key (uses config if not provided)
            model: Model to use (default: claude-3-haiku for cost efficiency)
            enable_web_search: Enable web search tool for supported models
            timeout: Request timeout in seconds (default: 300)
            max_retries: Number of retries for failed requests
        """
        api_key = api_key or getattr(config, 'claude_api_key', None)
        if not api_key:
            raise ValueError("Claude API key not provided")
            
        super().__init__(api_key, model)
        
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
        
        logger.info(f"Initializing Claude client with timeout={timeout}s, max_retries={max_retries}")
        
        self.client = Anthropic(
            api_key=api_key,
            timeout=timeout_config,
            max_retries=max_retries
        )
        self.enable_web_search = enable_web_search
        self.timeout = timeout
        self.max_retries = max_retries
        
        # Initialize rate limit handler with more aggressive settings for rate limits
        self.rate_limit_handler = ClaudeRateLimitHandler(
            max_retries=5,  # More retries for rate limits
            initial_delay=2.0,  # Start with 2 second delay
            max_delay=120.0,  # Allow up to 2 minute delays
            exponential_base=2.0,
            jitter=True
        )
        
        # Session tracking
        self.conversation_history = []
        self.web_search_count = 0
        
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost based on model pricing.
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            
        Returns:
            Cost in USD
        """
        try:
            # Use centralized pricing calculation
            cost = calculate_cost(self.model, input_tokens, output_tokens)
            return cost
        except KeyError:
            # Fallback for unknown models
            logger.warning(f"Unknown model {self.model}, using default Claude pricing")
            return calculate_cost(DEFAULT_CLAUDE_MODEL, input_tokens, output_tokens)
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        **kwargs
    ) -> Dict[str, Any]:
        """Single turn chat completion with cost tracking.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters for the API
            
        Returns:
            Dict with 'content', 'usage', and 'cost' keys
        """
        # Log request details for debugging
        logger.debug(f"Claude request: model={self.model}, messages={len(messages)}, "
                    f"temperature={temperature}, max_tokens={max_tokens}, "
                    f"timeout={self.timeout}s, web_search={self.enable_web_search}")
        
        try:
            # Convert messages to Claude format
            formatted_messages = self._format_messages(messages)
            
            # Build API call parameters
            api_params = {
                "model": self.model,
                "messages": formatted_messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            # Add web search tool if enabled and model supports it
            if self.enable_web_search and self.model.startswith('claude-3-5'):
                api_params["tools"] = [{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": 5
                }]
                logger.debug("Web search tool enabled for Claude")
            
            # Add any additional kwargs, but filter out unsupported parameters
            # Claude doesn't support 'seed' parameter like OpenAI does
            for key, value in kwargs.items():
                if key != 'seed':  # Filter out seed parameter
                    api_params[key] = value
                else:
                    logger.debug(f"Ignoring unsupported parameter for Claude API: {key}")
            
            # Make API call with rate limit handling
            logger.debug("Sending request to Claude API...")
            
            # Wrap the API call with rate limit handler
            @self.rate_limit_handler.with_retry
            def make_api_call():
                return self.client.messages.create(**api_params)
            
            response = make_api_call()
            logger.debug("Received response from Claude API")
            
            # Extract usage information
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens
            }
            
            # Calculate cost
            cost = self.calculate_cost(usage["input_tokens"], usage["output_tokens"])
            
            # Add web search cost if any searches were performed
            if hasattr(response, 'usage') and hasattr(response.usage, 'web_search_requests'):
                web_searches = getattr(response.usage, 'web_search_requests', 0)
                if web_searches > 0:
                    web_search_cost = web_searches * self.WEB_SEARCH_COST_PER_USE
                    cost += web_search_cost
                    usage["web_searches"] = web_searches
                    logger.debug(f"Web searches performed: {web_searches}, cost: ${web_search_cost:.4f}")
                    self.web_search_count += web_searches
            
            # Update session totals
            self.total_tokens_used += usage["total_tokens"]
            self.total_cost += cost
            
            # Extract content - handle multiple content blocks
            content_parts = []
            if response.content:
                for content_block in response.content:
                    if hasattr(content_block, 'text'):
                        content_parts.append(content_block.text)
                    elif hasattr(content_block, 'type'):
                        if content_block.type == 'tool_use':
                            # Tool use block
                            tool_info = f"[Tool: {getattr(content_block, 'name', 'unknown')}"
                            if hasattr(content_block, 'input'):
                                tool_info += f" - Input: {content_block.input}"
                            tool_info += "]"
                            content_parts.append(tool_info)
                        else:
                            content_parts.append(f"[{content_block.type}]")
                    else:
                        # Fallback
                        content_parts.append(str(content_block))
            
            content = "\n".join(content_parts)
            
            logger.debug(f"Claude response: {len(content)} chars, cost: ${cost:.4f}")
            
            return {
                "content": content,
                "usage": usage,
                "cost": cost,
                "model": self.model
            }
            
        except APITimeoutError as e:
            # Specific timeout error handling
            logger.error(f"Claude API timeout after {self.timeout}s: {e}")
            logger.error(f"Request details: model={self.model}, message_count={len(messages)}, "
                        f"temperature={temperature}, max_tokens={max_tokens}")
            logger.error("Consider increasing timeout or reducing request size")
            raise
            
        except RateLimitError as e:
            # Rate limit errors should be handled by the rate_limit_handler
            # If we get here, it means max retries were exceeded
            logger.error(f"Claude API rate limit exceeded after {self.max_retries} retries: {e}")
            logger.error("Rate limit handler exhausted all retry attempts")
            raise
            
        except APIConnectionError as e:
            # Connection error handling
            logger.error(f"Claude API connection error: {e}")
            logger.error("Check network connectivity and API endpoint availability")
            raise
            
        except APIError as e:
            # General API error handling
            logger.error(f"Claude API error: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            raise
            
        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"Unexpected error in Claude API call: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise
    
    def chat_completion_json(
        self,
        messages: List[Dict[str, str]],
        json_schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4000,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Chat completion with JSON response parsing.
        
        Args:
            messages: List of message dicts
            json_schema: Expected JSON schema (for prompt enhancement)
            temperature: Lower temperature for more consistent JSON
            max_tokens: Maximum tokens to generate
            
        Returns:
            Parsed JSON dict or None if parsing fails
        """
        # Add JSON instruction to the last user message
        if messages:
            # Always ask for JSON response
            messages_copy = [m.copy() for m in messages]
            if json_schema:
                # Handle both direct schema and wrapped schema formats
                if isinstance(json_schema, dict):
                    # Check if it's a wrapped format (has 'schema' key) or direct schema
                    if 'schema' in json_schema and isinstance(json_schema['schema'], dict):
                        # Wrapped format from OpenAI-style - extract the actual schema
                        actual_schema = json_schema['schema']
                    else:
                        # Direct schema format - use as is
                        actual_schema = json_schema
                    schema_str = json.dumps(actual_schema, indent=2)
                    # Add explicit instruction for proper JSON formatting
                    messages_copy[-1]["content"] += f"\n\nRespond with ONLY valid JSON matching this schema:\n{schema_str}"
                    messages_copy[-1]["content"] += "\n\nCRITICAL: Return ONLY the JSON object, no preamble or explanation. The response must be valid JSON that can be parsed with json.loads(). Multi-line strings must use \\n for newlines, not literal newlines."
                else:
                    messages_copy[-1]["content"] += "\n\nRespond with valid JSON."
            else:
                messages_copy[-1]["content"] += "\n\nRespond with valid JSON."
        
        response = self.chat_completion(messages_copy, temperature, max_tokens, **kwargs)
        
        try:
            # Extract JSON from response
            content = response["content"]
            
            # Try to find JSON in the response
            if "```json" in content:
                # Extract JSON from code block
                start = content.find("```json") + 7
                end = content.find("```", start)
                json_str = content[start:end].strip()
            elif "{" in content:
                # Try to extract JSON object from response
                # Find first { and matching }
                start = content.find("{")
                if start >= 0:
                    # Find the matching closing brace
                    brace_count = 0
                    end = start
                    for i in range(start, len(content)):
                        if content[i] == "{":
                            brace_count += 1
                        elif content[i] == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                end = i + 1
                                break
                    
                    if end > start:
                        json_str = content[start:end]
                        logger.debug(f"Extracted first JSON object: {len(json_str)} chars")
                    else:
                        json_str = content.strip()
                else:
                    json_str = content.strip()
            else:
                # Assume entire response is JSON
                json_str = content.strip()
            
            parsed = json.loads(json_str)
            
            # Add metadata
            parsed["_metadata"] = {
                "usage": response["usage"],
                "cost": response["cost"],
                "model": response["model"]
            }
            
            return parsed
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            content = response.get('content', '')
            content_preview = content[:500]
            logger.error(f"Response content preview: {content_preview}")
            
            # Log the full response for debugging
            logger.error(f"Full response length: {len(content)} chars")
            
            # Save the problematic response to a file for debugging
            import tempfile
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_file = os.path.join(tempfile.gettempdir(), f"claude_json_error_{timestamp}.txt")
            try:
                with open(debug_file, 'w') as f:
                    f.write(content)
                logger.error(f"Saved problematic response to {debug_file}")
            except OSError:
                pass
            
            # Just raise the error - no fallback parsing
            raise ValueError(f"Failed to parse Claude JSON response: {str(e)}")
    
    def multi_turn_conversation(
        self,
        initial_context: str,
        max_turns: int = 5,
        max_cost: float = 0.10,
        max_tokens_total: int = 50000,
        temperature: float = 0.7
    ) -> Generator[Dict[str, Any], str, None]:
        """Multi-turn conversation with limits.
        
        This is a generator that yields responses and accepts user inputs.
        
        Args:
            initial_context: Initial system/context message
            max_turns: Maximum number of turns
            max_cost: Maximum total cost in USD
            max_tokens_total: Maximum total tokens
            temperature: Sampling temperature
            
        Yields:
            Dict with turn results
            
        Example:
            conv = service.multi_turn_conversation("You are a helpful assistant")
            response1 = next(conv)
            response2 = conv.send("Tell me about Python")
        """
        # Initialize conversation
        self.conversation_history = [
            {"role": "system", "content": initial_context}
        ]
        
        turn = 0
        while turn < max_turns:
            # Check limits
            if self.total_cost >= max_cost:
                yield {
                    "turn": turn,
                    "status": "cost_limit_reached",
                    "message": f"Cost limit reached: ${self.total_cost:.4f} >= ${max_cost}"
                }
                break
                
            if self.total_tokens_used >= max_tokens_total:
                yield {
                    "turn": turn,
                    "status": "token_limit_reached",
                    "message": f"Token limit reached: {self.total_tokens_used} >= {max_tokens_total}"
                }
                break
            
            # Get user input (via send())
            user_input = yield {
                "turn": turn,
                "status": "waiting_for_input",
                "usage_so_far": {
                    "tokens": self.total_tokens_used,
                    "cost": self.total_cost
                }
            }
            
            if user_input is None:
                break
                
            # Add user message to history
            self.conversation_history.append({
                "role": "user",
                "content": user_input
            })
            
            # Get Claude's response
            response = self.chat_completion(
                self.conversation_history,
                temperature=temperature,
                max_tokens=min(4000, max_tokens_total - self.total_tokens_used)
            )
            
            # Add assistant response to history
            self.conversation_history.append({
                "role": "assistant",
                "content": response["content"]
            })
            
            # Yield response
            yield {
                "turn": turn,
                "status": "response",
                "content": response["content"],
                "usage": response["usage"],
                "cost": response["cost"],
                "total_usage": {
                    "tokens": self.total_tokens_used,
                    "cost": self.total_cost
                }
            }
            
            turn += 1
        
        # Final yield with conversation summary
        yield {
            "turn": turn,
            "status": "completed",
            "total_turns": turn,
            "total_usage": {
                "tokens": self.total_tokens_used,
                "cost": self.total_cost
            },
            "conversation_history": self.conversation_history
        }
    
    def _format_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Format messages for Claude API.
        
        Claude expects messages in a specific format with alternating user/assistant roles.
        """
        formatted = []
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            # Map roles to Claude format
            if role == "system":
                # Claude doesn't have a system role, prepend to first user message
                if not formatted:
                    formatted.append({"role": "user", "content": content})
                else:
                    # Prepend to next user message
                    formatted[0]["content"] = content + "\n\n" + formatted[0]["content"]
            elif role == "user":
                formatted.append({"role": "user", "content": content})
            elif role == "assistant":
                formatted.append({"role": "assistant", "content": content})
            else:
                logger.warning(f"Unknown role: {role}, treating as user")
                formatted.append({"role": "user", "content": content})
        
        # Ensure conversation starts with user message
        if formatted and formatted[0]["role"] != "user":
            formatted.insert(0, {"role": "user", "content": "Continue."})
            
        # Ensure alternating roles
        cleaned = []
        last_role = None
        
        for msg in formatted:
            if msg["role"] == last_role:
                # Merge with previous message
                cleaned[-1]["content"] += "\n\n" + msg["content"]
            else:
                cleaned.append(msg)
                last_role = msg["role"]
        
        return cleaned
    
    def get_usage_summary(self) -> Dict[str, Any]:
        """Get usage summary for the session.
        
        Returns:
            Dict with total_tokens, total_cost, and breakdown
        """
        summary = {
            "total_tokens": self.total_tokens_used,
            "total_cost": self.total_cost,
            "model": self.model
        }
        
        if self.web_search_count > 0:
            summary["web_searches"] = self.web_search_count
            summary["web_search_cost"] = self.web_search_count * self.WEB_SEARCH_COST_PER_USE
            
        return summary