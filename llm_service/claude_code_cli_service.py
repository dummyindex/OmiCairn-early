"""Claude Code CLI backend for LLM interactions.

This backend calls a locally installed and authenticated Claude Code CLI
(`claude --print`) for LLM calls within the omicairn agent system. Usage and
billing follow your Claude Code account; make sure your use complies with
Anthropic's terms of service.
"""

import subprocess
import json
import logging
import os
import re
import time
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from .base_llm_service import BaseLLMService
from .pricing_config import calculate_cost
from utils.logger import get_logger

logger = get_logger(__name__)


class ClaudeCodeCLIService(BaseLLMService):
    """LLM service that calls the Claude Code CLI.
    
    This service provides the same interface as OpenAIService and ClaudeService,
    but sends prompts through the locally installed Claude Code CLI.
    
    Note: Requires Claude Code CLI to be installed and authenticated:
    - Install: npm install -g @anthropic-ai/claude-code
    - Authenticate: see the Claude Code documentation
    Usage and billing follow the account the CLI is authenticated with; ensure
    your use complies with Anthropic's terms of service.
    """
    
    # Model mapping for CLI (CLI uses aliases like 'sonnet', 'opus')
    MODEL_ALIASES = {
        'claude-3-5-sonnet-20241022': 'sonnet',
        'claude-3-5-sonnet': 'sonnet',
        'claude-3-opus-20240229': 'opus',
        'claude-3-opus': 'opus',
        'claude-3-5-haiku': 'haiku',
        'claude-3-haiku': 'haiku',
        # Default mappings
        'sonnet': 'sonnet',
        'opus': 'opus',
        'haiku': 'haiku'
    }
    
    def __init__(
        self, 
        api_key: Optional[str] = None,  # Ignored, kept for interface compatibility
        model: str = 'sonnet',
        timeout: int = 120,
        debug: bool = False,
        permission_mode: str = "default",
        allow_tools: bool = False,  # Whether to allow Claude to use tools
        seed: Optional[int] = None  # Seed for reproducibility (not supported by CLI yet)
    ):
        """Initialize Claude Code CLI service.
        
        Args:
            api_key: Ignored (kept for interface compatibility)
            model: Model alias ('sonnet', 'opus', 'haiku') or full name
            timeout: Command timeout in seconds
            debug: Enable debug logging
            permission_mode: Permission mode for CLI ('default', 'acceptEdits', 'bypassPermissions')
            allow_tools: Whether to allow Claude to use ANY tools (default: False for security)
                       When False, disables all tools except basic search (Glob, Grep, LS)
            seed: Seed for reproducibility (not yet supported by CLI)
        """
        # Initialize base class (api_key is dummy value)
        super().__init__(api_key or "subscription", model)
        
        # Map model to CLI alias if needed
        self.cli_model = self.MODEL_ALIASES.get(model, model)
        self.model = model  # Keep original for reporting
        self.timeout = timeout
        self.debug = debug
        self.permission_mode = permission_mode
        self.allow_tools = allow_tools
        self.seed = seed  # Store for future use when CLI supports it
        
        if debug:
            logging.basicConfig(level=logging.DEBUG)
        
        # Verify CLI is available and authenticated
        self._verify_cli()
        self._check_authentication()
        
        # Track approximate usage (CLI doesn't provide token counts)
        self.estimated_tokens = 0
    
    def _verify_cli(self):
        """Verify Claude Code CLI is installed."""
        try:
            result = subprocess.run(
                ['claude', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                raise RuntimeError("Claude Code CLI not working properly")
            logger.info(f"Claude Code CLI verified: {result.stdout.strip()}")
        except FileNotFoundError:
            raise RuntimeError(
                "Claude Code CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
            )
    
    def _check_authentication(self):
        """Check authentication status."""
        if "ANTHROPIC_API_KEY" in os.environ:
            logger.info("ANTHROPIC_API_KEY is set; the Claude Code CLI may authenticate with it.")
        
        # Try to verify authentication
        try:
            result = subprocess.run(
                ['claude', 'status'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            output = result.stdout.lower()
            if "not authenticated" in output or "not logged" in output:
                logger.warning(
                    "Claude Code may not be authenticated. Run: claude login"
                )
            else:
                logger.info("Claude Code CLI authentication verified")
                
        except Exception as e:
            logger.debug(f"Could not verify auth status (non-critical): {e}")
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)."""
        # Rough estimate: ~4 characters per token
        return len(text) // 4
    
    def _build_prompt_with_messages(self, messages: List[Dict[str, str]]) -> str:
        """Convert message list to a single prompt for CLI."""
        prompt_parts = []
        
        for msg in messages:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            
            if role == 'system':
                prompt_parts.append(f"System: {content}")
            elif role == 'assistant':
                prompt_parts.append(f"Assistant: {content}")
            elif role == 'user':
                prompt_parts.append(f"User: {content}")
            else:
                prompt_parts.append(content)
        
        return "\n\n".join(prompt_parts)
    
    def _extract_json_from_response(self, response: str) -> Dict[str, Any]:
        """Extract JSON from response text."""
        # First, try to parse the entire response as JSON
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON in code blocks (handle both ``` and ```json)
        json_patterns = [
            r'```json\s*\n(.*?)\n```',
            r'```\s*\n(.*?)\n```',
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```'
        ]
        
        for pattern in json_patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    continue
        
        # Try to find any JSON-like structure
        json_match = re.search(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # If the response itself looks like it should be JSON, try one more parse attempt
        if response.strip().startswith('{') and response.strip().endswith('}'):
            try:
                # Try parsing the clean response one more time
                return json.loads(response.strip())
            except json.JSONDecodeError as e:
                logger.warning(f"Response looks like JSON but failed to parse: {e}")
                logger.debug(f"Problematic response: {response.strip()[:500]}")
                # Return error structure that matches expected schema
                return {
                    "error": f"JSON parse failed: {e}",
                    "raw_response": response.strip()[:500],
                    "satisfied": False,
                    "reasoning": f"Claude CLI returned malformed JSON: {e}",
                    "next_actions": []
                }
        
        # Return structured error that matches expected schema
        return {
            "error": "Could not extract JSON from response",
            "raw_response": response[:500],
            "satisfied": False,
            "reasoning": "Claude CLI did not return valid JSON format",
            "next_actions": []
        }
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,  # Note: CLI doesn't support temperature
        max_tokens: int = 4000,  # Note: CLI doesn't support max_tokens directly
        **kwargs
    ) -> Dict[str, Any]:
        """Chat completion using Claude Code CLI.
        
        Returns:
            Dict with 'content', 'usage', 'cost', and 'model' keys
        """
        # Build command
        cmd = ['claude', '--print']
        
        # Disable ALL MCP servers (including Serena) by providing valid empty config
        # This completely overrides any default MCP servers
        empty_mcp_config = '{"mcpServers": {}}'  # Valid empty MCP config
        cmd.extend(['--mcp-config', empty_mcp_config])
        cmd.append('--strict-mcp-config')  # Use ONLY our empty config, ignore defaults
        
        # Add model if specified
        if self.cli_model:
            cmd.extend(['--model', self.cli_model])
        
        # Add permission mode
        if self.permission_mode == "bypassPermissions":
            cmd.append('--dangerously-skip-permissions')
        elif self.permission_mode != "default":
            cmd.extend(['--permission-mode', self.permission_mode])
        
        # Tool security: Use whitelist approach (more secure than blacklist)
        if not self.allow_tools:
            # WHITELIST: ONLY WebSearch allowed - no file system access at all
            allowed_tools = ['WebSearch']  # ONLY web search, nothing else
            # Using whitelist is more secure - only explicitly allowed tools can be used
            cmd.extend(['--allowed-tools', ','.join(allowed_tools)])
        # else: allow_tools=True means ALL tools are allowed (not recommended)
        
        # Add debug flag
        if self.debug:
            cmd.append('--debug')
        
        # Convert messages to prompt
        prompt = self._build_prompt_with_messages(messages)
        
        # Add instruction about response length if max_tokens is small
        if max_tokens < 1000:
            prompt += f"\n\nPlease keep your response concise (under {max_tokens*4} characters)."
        
        # Log command for debugging (truncate prompt for readability)
        logger.debug(f"Executing Claude CLI: {' '.join(cmd)} [prompt: {len(prompt)} chars via stdin]")
        
        try:
            # Execute command - pass prompt via stdin
            start_time = time.time()
            result = subprocess.run(
                cmd,
                input=prompt,  # Pass prompt via stdin instead of as argument
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            elapsed = time.time() - start_time
            
            if result.returncode != 0:
                error_msg = result.stderr or "Unknown error"
                logger.error(f"Claude CLI error: {error_msg}")
                raise RuntimeError(f"Claude CLI failed: {error_msg}")
            
            content = result.stdout.strip()
            
            if not content:
                raise ValueError("Empty response from Claude CLI")
            
            # Estimate tokens for usage tracking
            input_tokens = self._estimate_tokens(prompt)
            output_tokens = self._estimate_tokens(content)
            total_tokens = input_tokens + output_tokens
            
            # Per-token cost is not reported by the CLI backend; tokens above are estimates
            cost = 0.0
            
            # Update totals
            self.total_tokens_used += total_tokens
            self.estimated_tokens += total_tokens
            
            logger.debug(f"Claude CLI response: {len(content)} chars in {elapsed:.2f}s")
            
            return {
                "content": content,
                "usage": {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": total_tokens
                },
                "cost": cost,
                "model": self.model,
                "cli_model": self.cli_model,
                "cli_backend": True  # Indicates the Claude Code CLI backend was used
            }
            
        except subprocess.TimeoutExpired:
            logger.error(f"Claude CLI timeout after {self.timeout}s")
            raise TimeoutError(f"Claude CLI timed out after {self.timeout} seconds")
        except Exception as e:
            logger.error(f"Claude CLI error: {e}")
            raise
    
    def chat_completion_json(
        self,
        messages: List[Dict[str, str]],
        json_schema: Dict[str, Any],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        **kwargs
    ) -> Dict[str, Any]:
        """Chat completion with JSON response using Claude CLI.
        
        Instead of using --output-format json (which wraps the response),
        we instruct Claude to output pure JSON directly.
        """
        # Build command for text output (we'll get pure JSON as text)
        cmd = ['claude', '--print']
        
        # Disable ALL MCP servers (including Serena) by providing valid empty config
        # This completely overrides any default MCP servers
        empty_mcp_config = '{"mcpServers": {}}'  # Valid empty MCP config
        cmd.extend(['--mcp-config', empty_mcp_config])
        cmd.append('--strict-mcp-config')  # Use ONLY our empty config, ignore defaults
        
        # Add model
        if self.cli_model:
            cmd.extend(['--model', self.cli_model])
        
        # Add permission mode
        if self.permission_mode == "bypassPermissions":
            cmd.append('--dangerously-skip-permissions')
        elif self.permission_mode != "default":
            cmd.extend(['--permission-mode', self.permission_mode])
        
        # Tool security for JSON mode: Use even stricter whitelist
        # For JSON output, we want pure LLM responses, so limit tools further
        if not self.allow_tools:
            # WHITELIST for JSON: Only WebSearch for context, no file system access
            allowed_tools = ['WebSearch']  # Only web search for JSON mode
            cmd.extend(['--allowed-tools', ','.join(allowed_tools)])
        # else: allow_tools=True means ALL tools (not recommended for JSON)
        
        # Add debug
        if self.debug:
            cmd.append('--debug')
        
        # Build prompt with explicit instruction for pure JSON output
        prompt = self._build_prompt_with_messages(messages)
        prompt += f"\n\nIMPORTANT: Return ONLY valid JSON that matches this schema. Do not include any markdown formatting, code blocks, or explanatory text. Just output the raw JSON:\n\nSchema:\n{json.dumps(json_schema, indent=2)}\n\nRemember: Output ONLY the JSON object, nothing else."
        
        logger.debug(f"Executing Claude CLI for JSON: {' '.join(cmd)} [prompt via stdin]")
        
        try:
            # Execute command - pass prompt via stdin
            result = subprocess.run(
                cmd,
                input=prompt,  # Pass prompt via stdin instead of as argument
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or "Unknown error"
                logger.error(f"Claude CLI JSON error: {error_msg}")
                raise RuntimeError(f"Claude CLI failed: {error_msg}")
            
            response_text = result.stdout.strip()
            
            # Try to parse as pure JSON first
            try:
                parsed = json.loads(response_text)
                logger.debug("Successfully parsed pure JSON response")
                return parsed
                
            except json.JSONDecodeError as e:
                logger.debug(f"Response not pure JSON, attempting extraction: {e}")
                # If it's not pure JSON, try to extract it
                # This handles cases where Claude still adds formatting despite instructions
                extracted = self._extract_json_from_response(response_text)
                
                if 'error' in extracted:
                    logger.warning(f"Could not extract valid JSON: {extracted['error']}")
                    logger.debug(f"Raw response: {response_text[:500]}")
                
                return extracted
                
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Claude CLI timed out after {self.timeout} seconds")
        except Exception as e:
            logger.error(f"Claude CLI JSON error: {e}")
            raise
    
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Cost is not tracked for the CLI backend (returns 0.0)."""
        return 0.0
    
    def call_llm(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        **kwargs
    ) -> str:
        """Convenience method for getting string response."""
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
        """Call LLM with JSON response format."""
        return self.chat_completion_json(
            messages=messages,
            json_schema=json_schema,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
    
    def get_usage_summary(self) -> Dict[str, Any]:
        """Get usage summary."""
        return {
            "total_tokens": self.total_tokens_used,
            "estimated_tokens": self.estimated_tokens,
            "total_cost": 0.0,  # not tracked for the CLI backend
            "model": self.model,
            "cli_model": self.cli_model,
            "note": "Claude Code CLI backend; token counts are estimates and cost is not tracked"
        }
    
    def reset_usage(self):
        """Reset usage counters."""
        super().reset_usage()
        self.estimated_tokens = 0


# Convenience function for quick initialization
def create_cli_service(model: str = 'sonnet', **kwargs) -> ClaudeCodeCLIService:
    """Create a Claude Code CLI service instance.
    
    Args:
        model: Model to use ('sonnet', 'opus', 'haiku')
        **kwargs: Additional arguments for ClaudeCodeCLIService
    
    Returns:
        ClaudeCodeCLIService instance
    """
    return ClaudeCodeCLIService(model=model, **kwargs)