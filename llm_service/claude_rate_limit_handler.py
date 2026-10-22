"""
Rate limit handler for Claude API with exponential backoff and token bucket algorithm.

Based on Anthropic's official documentation and best practices for handling 429 errors.
"""

import time
import random
import logging
from typing import Optional, Dict, Any, Callable
from threading import Lock
from functools import wraps
from anthropic import RateLimitError

logger = logging.getLogger(__name__)


class TokenBucket:
    """
    Token bucket implementation for rate limiting.
    Refills tokens continuously at a specified rate.
    """
    
    def __init__(self, tokens_per_minute: int, max_tokens: Optional[int] = None):
        """
        Initialize token bucket.
        
        Args:
            tokens_per_minute: Rate at which tokens are added
            max_tokens: Maximum tokens that can be stored (defaults to tokens_per_minute)
        """
        self.tokens_per_second = tokens_per_minute / 60.0
        self.max_tokens = max_tokens or tokens_per_minute
        self.tokens = self.max_tokens
        self.last_refill = time.time()
        self.lock = Lock()
    
    def _refill(self):
        """Refill tokens based on time elapsed."""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.tokens_per_second
        
        self.tokens = min(self.max_tokens, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def get_tokens(self, num_tokens: int = 1) -> bool:
        """
        Try to consume tokens from the bucket.
        
        Args:
            num_tokens: Number of tokens to consume
            
        Returns:
            True if tokens were available, False otherwise
        """
        with self.lock:
            self._refill()
            if self.tokens >= num_tokens:
                self.tokens -= num_tokens
                return True
            return False
    
    def wait_for_tokens(self, num_tokens: int = 1, timeout: float = 60.0) -> bool:
        """
        Wait for tokens to become available.
        
        Args:
            num_tokens: Number of tokens needed
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if tokens became available, False if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.get_tokens(num_tokens):
                return True
            
            # Calculate wait time
            with self.lock:
                self._refill()
                if self.tokens < num_tokens:
                    tokens_needed = num_tokens - self.tokens
                    wait_time = tokens_needed / self.tokens_per_second
                    wait_time = min(wait_time, 0.1)  # Cap at 100ms per check
                else:
                    wait_time = 0.01
            
            time.sleep(wait_time)
        
        return False


class ClaudeRateLimitHandler:
    """
    Handles rate limiting for Claude API with exponential backoff and retry logic.
    """
    
    def __init__(
        self,
        max_retries: int = 5,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        """
        Initialize rate limit handler.
        
        Args:
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay in seconds for exponential backoff
            max_delay: Maximum delay in seconds
            exponential_base: Base for exponential backoff calculation
            jitter: Whether to add random jitter to delays
        """
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        
        # Token buckets for different rate limit types
        # These are conservative defaults - adjust based on your tier
        self.request_bucket = TokenBucket(tokens_per_minute=50)  # 50 RPM
        self.input_token_bucket = TokenBucket(tokens_per_minute=40000)  # 40K ITPM
        self.output_token_bucket = TokenBucket(tokens_per_minute=8000)  # 8K OTPM
    
    def calculate_delay(self, retry_attempt: int, retry_after: Optional[float] = None) -> float:
        """
        Calculate delay for retry attempt.
        
        Args:
            retry_attempt: Current retry attempt number (0-indexed)
            retry_after: Optional retry-after value from API response header
            
        Returns:
            Delay in seconds
        """
        if retry_after is not None:
            # Use the server-specified retry-after value
            delay = retry_after
        else:
            # Calculate exponential backoff
            delay = min(
                self.initial_delay * (self.exponential_base ** retry_attempt),
                self.max_delay
            )
        
        if self.jitter:
            # Add random jitter (0-25% of delay)
            delay = delay * (1 + random.random() * 0.25)
        
        return delay
    
    def extract_retry_after(self, error: RateLimitError) -> Optional[float]:
        """
        Extract retry-after value from rate limit error.
        
        Args:
            error: RateLimitError from Anthropic API
            
        Returns:
            Retry-after value in seconds, or None if not available
        """
        # Check if error has response attribute with headers
        if hasattr(error, 'response') and hasattr(error.response, 'headers'):
            retry_after = error.response.headers.get('retry-after')
            if retry_after:
                try:
                    return float(retry_after)
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse retry-after header: {retry_after}")
        
        # Also check error message for rate limit info
        error_str = str(error)
        if 'retry-after' in error_str.lower():
            # Try to extract seconds from error message
            import re
            match = re.search(r'retry[- ]after[:\s]+(\d+(?:\.\d+)?)', error_str, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except (ValueError, TypeError):
                    pass
        
        return None
    
    def parse_rate_limit_type(self, error: RateLimitError) -> str:
        """
        Determine which type of rate limit was hit.
        
        Args:
            error: RateLimitError from Anthropic API
            
        Returns:
            Type of rate limit: 'requests', 'input_tokens', 'output_tokens', 'usage_increase', or 'unknown'
        """
        error_message = str(error).lower()
        
        if 'usage increase rate' in error_message:
            return 'usage_increase'  # Special handling for gradual scaling requirement
        elif 'request tokens' in error_message or 'input tokens' in error_message:
            return 'input_tokens'
        elif 'output tokens' in error_message:
            return 'output_tokens'
        elif 'number of requests' in error_message:
            return 'requests'
        else:
            return 'unknown'
    
    def with_retry(self, func: Callable) -> Callable:
        """
        Decorator to add retry logic with rate limit handling.
        
        Args:
            func: Function to wrap with retry logic
            
        Returns:
            Wrapped function
        """
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(self.max_retries):
                try:
                    # Check token buckets before making request
                    if not self.request_bucket.wait_for_tokens(1, timeout=30):
                        logger.warning("Request rate limit pre-check: waiting for capacity")
                    
                    # Execute the function
                    result = func(*args, **kwargs)
                    
                    # Success - return result
                    return result
                    
                except RateLimitError as e:
                    last_exception = e
                    
                    # Log the rate limit error
                    rate_limit_type = self.parse_rate_limit_type(e)
                    logger.warning(
                        f"Rate limit hit (type: {rate_limit_type}), "
                        f"attempt {attempt + 1}/{self.max_retries}"
                    )
                    
                    # Check if we've exhausted retries
                    if attempt >= self.max_retries - 1:
                        logger.error(f"Max retries ({self.max_retries}) exceeded for rate limit")
                        raise
                    
                    # Calculate delay
                    retry_after = self.extract_retry_after(e)
                    delay = self.calculate_delay(attempt, retry_after)
                    
                    # Special handling for usage increase rate errors - need longer delays
                    if rate_limit_type == 'usage_increase':
                        # For usage increase errors, use much longer delays
                        min_delay = 30.0  # At least 30 seconds
                        delay = max(delay, min_delay) * (attempt + 1)  # Increase with each attempt
                        logger.info(f"Usage increase rate limit - using extended delay of {delay:.1f}s")
                    
                    logger.info(f"Waiting {delay:.2f} seconds before retry...")
                    time.sleep(delay)
                    
                except Exception as e:
                    # Non-rate-limit error - re-raise immediately
                    raise
            
            # If we get here, we've exhausted all retries
            if last_exception:
                raise last_exception
            
        return wrapper


def create_rate_limited_client(
    client,
    requests_per_minute: int = 50,
    input_tokens_per_minute: int = 40000,
    output_tokens_per_minute: int = 8000,
    max_retries: int = 5
) -> Any:
    """
    Wrap a Claude client with rate limit handling.
    
    Args:
        client: Anthropic client instance
        requests_per_minute: RPM limit for your tier
        input_tokens_per_minute: ITPM limit for your tier
        output_tokens_per_minute: OTPM limit for your tier
        max_retries: Maximum retry attempts
        
    Returns:
        Wrapped client with rate limit handling
    """
    handler = ClaudeRateLimitHandler(max_retries=max_retries)
    
    # Update token buckets with actual limits
    handler.request_bucket = TokenBucket(tokens_per_minute=requests_per_minute)
    handler.input_token_bucket = TokenBucket(tokens_per_minute=input_tokens_per_minute)
    handler.output_token_bucket = TokenBucket(tokens_per_minute=output_tokens_per_minute)
    
    # Wrap the messages.create method
    original_create = client.messages.create
    client.messages.create = handler.with_retry(original_create)
    
    return client


# Example usage with tenacity library (alternative approach)
def get_tenacity_retry_decorator(max_attempts: int = 5):
    """
    Get a tenacity retry decorator for Claude API calls.
    
    This is an alternative approach using the tenacity library.
    Install with: pip install tenacity
    """
    try:
        from tenacity import (
            retry,
            stop_after_attempt,
            wait_random_exponential,
            retry_if_exception_type,
            before_sleep_log
        )
        
        return retry(
            retry=retry_if_exception_type(RateLimitError),
            wait=wait_random_exponential(multiplier=1, max=60),
            stop=stop_after_attempt(max_attempts),
            before_sleep=before_sleep_log(logger, logging.INFO)
        )
    except ImportError:
        logger.warning("Tenacity library not installed. Using basic retry logic.")
        return lambda f: f  # No-op decorator if tenacity not available