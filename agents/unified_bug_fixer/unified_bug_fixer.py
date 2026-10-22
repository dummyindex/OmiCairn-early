"""Unified LLM-agnostic bug fixer implementation."""

import os
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from .enhanced_debug_session import EnhancedDebugSession
from llm_service import BaseLLMService, create_llm_service
from utils import setup_logger
from utils.timing import TimingContext, time_operation, OperationTimer
from config import config
from constants import DEFAULT_OPENAI_MODEL, GPT_4O_MINI, ENV_OPENAI_API_KEY

logger = setup_logger(__name__)


class UnifiedBugFixer:
    """Unified LLM-agnostic bug fixer with multi-turn debugging."""
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        max_turns: int = 5,
        save_debug_logs: bool = True,
        llm_service: Optional[BaseLLMService] = None,
        enable_web_search: bool = False,
        enable_web_agent: bool = False,  # Disabled by default, enabled only when explicitly requested
        enable_domain_knowledge: bool = False,
        domain_knowledge_domains: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        seed: Optional[int] = None
    ):
        """Initialize unified bug fixer.
        
        Args:
            model_name: Model identifier (e.g., 'gpt-4', 'claude-3-5-sonnet-20241022')
            api_key: API key (uses env var if not provided)
            max_turns: Maximum debugging turns per session
            save_debug_logs: Whether to save debug session logs
            llm_service: Pre-initialized LLM service (if provided, model_name and api_key are ignored)
            enable_web_search: Enable web search capability for supported models
            enable_web_agent: Enable LangGraph web agent for enhanced research
            enable_domain_knowledge: Enable domain-specific knowledge injection
            domain_knowledge_domains: List of domain knowledge to inject
            timeout: Timeout in seconds for bug fixer execution (default: from config)
            seed: Seed for LLM reproducibility (optional)
        """
        self.max_turns = max_turns
        self.save_debug_logs = save_debug_logs
        self.enable_web_search = enable_web_search
        self.enable_web_agent = enable_web_agent
        self.enable_domain_knowledge = enable_domain_knowledge
        self.timeout = timeout
        self.domain_knowledge_domains = domain_knowledge_domains or []
        self.seed = seed
        
        # Initialize domain knowledge system if enabled
        self.knowledge_service = None
        self.prompt_injector = None
        if self.enable_domain_knowledge:
            from domain_knowledge import get_knowledge_service, PromptInjector
            self.knowledge_service = get_knowledge_service()
            self.prompt_injector = PromptInjector(self.knowledge_service)
            logger.info(f"Domain knowledge enabled for domains: {self.domain_knowledge_domains}")
                
        # Determine model name early for web agent initialization
        if llm_service:
            self.llm_service = llm_service
            self.model_name = getattr(llm_service, 'model', 'unknown')
            effective_model_name = self.model_name
        else:
            if not model_name:
                raise ValueError("Either model_name or llm_service must be provided")
            
            # Map to web search enabled model if requested
            effective_model_name = model_name
            if enable_web_search:
                original_model = model_name
                effective_model_name = self._get_web_search_model(model_name)
                if effective_model_name != original_model:
                    logger.info(f"Using web search enabled model: {effective_model_name} (from {original_model})")
            
            self.model_name = effective_model_name
            self.llm_service = self._create_llm_service(effective_model_name, api_key, seed)
        
        # Initialize web agent if enabled - use the same model as bug fixer
        self.web_agent_tool = None
        self.web_agent_timeout = int(os.environ.get('WEB_AGENT_TIMEOUT', '90'))  # Configurable timeout
        if enable_web_agent:
            try:
                from agents.web_agent_langgraph.web_agent_tool import WebAgentTool
                # Use the same model as bug fixer for consistency
                web_agent_model = effective_model_name if effective_model_name != 'unknown' else GPT_4O_MINI
                self.web_agent_tool = WebAgentTool(
                    model_name=web_agent_model,
                    embedding_model="text-embedding-3-small",
                    enable_crawling=True,
                    crawl_limit=3,  # Limit crawling for cost
                    timeout_seconds=self.web_agent_timeout  # Configurable timeout
                )
                logger.info(f"Web agent tool initialized with model {web_agent_model} and {self.web_agent_timeout}s timeout")
            except Exception as e:
                logger.warning(f"Failed to initialize web agent tool: {e}")
                self.enable_web_agent = False
            
        logger.info(f"Initialized UnifiedBugFixer with model: {self.model_name}")
            
        # Track all sessions
        self.debug_sessions = []
        self.timer = OperationTimer()
        
    @time_operation("UnifiedBugFixer.fix_bug")
    def fix_bug(
        self,
        node_name: str,
        error_message: str,
        working_directory: Path,
        stdout: str = "",
        stderr: str = "",
        max_turns: int = None,
        attempt_number: int = 1,
        previous_attempts: Optional[list] = None,
        node_description: Optional[str] = None,
        bug_fixer_attempt_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Fix bug using multi-turn action-based debugging.
        
        Args:
            node_name: Name of the function block
            error_message: Error message to fix
            working_directory: Path to working directory
            stdout: Standard output from failed execution
            stderr: Standard error from failed execution
            max_turns: Override max turns for this session
            attempt_number: Current attempt number
            previous_attempts: List of previous fix attempts
            node_description: Description of what the function block should do
            
        Returns:
            Debug session result
        """
        logger.info(f"Starting bug fix for {node_name} (attempt {attempt_number})")
        
        # Create action executor for the session
        # WARNING: This creates a standalone ActionExecutor which is deprecated
        # This path should only be reached when not using in-container debugging
        logger.warning(
            "Creating standalone ActionExecutor - this is deprecated! "
            "Use enable_interactive_debug=True in MainAgent for proper debugging support."
        )
        
        from .action_executor import ActionExecutor
        # Pass None explicitly to trigger deprecation warning
        try:
            action_executor = ActionExecutor(
                working_directory, 
                interactive_executor=None,
                web_agent_tool=self.web_agent_tool if self.enable_web_agent else None
            )
        except DeprecationWarning as e:
            # Log the deprecation warning and re-raise as RuntimeError
            logger.error(str(e))
            raise RuntimeError(
                "Cannot use standalone bug fixing. Please enable interactive debugging:\n"
                "MainAgent(..., enable_interactive_debug=True)\n"
                "The standalone ActionExecutor is deprecated and will be removed."
            ) from e
        
        # Create enhanced debug session with domain knowledge if enabled
        session_kwargs = {
            "action_executor": action_executor,
            "llm_service": self.llm_service,
            "max_turns": max_turns or self.max_turns,
            "node_dir": Path(working_directory),  # Use working directory for logging
            "attempt_number": attempt_number,
            "bug_fixer_attempt_dir": bug_fixer_attempt_dir  # Pass attempt-specific directory
        }
        
        if self.enable_domain_knowledge:
            session_kwargs["enable_domain_knowledge"] = True
            session_kwargs["prompt_injector"] = self.prompt_injector
            session_kwargs["domain_knowledge_domains"] = self.domain_knowledge_domains
        
        # Enable action digester by default (can be disabled via config if needed)
        session_kwargs["enable_action_digester"] = True
            
        session = EnhancedDebugSession(**session_kwargs)
        
        # Run debugging session
        result = session.debug(
            node_name=node_name,
            error_message=error_message,
            stdout=stdout,
            stderr=stderr,
            attempt_number=attempt_number,
            previous_attempts=previous_attempts,
            node_description=node_description
        )
        
        # Add metadata
        result['model_name'] = self.model_name
        result['attempt_number'] = attempt_number
        result['timestamp'] = datetime.now().isoformat()
        
        # Save debug log if enabled
        if self.save_debug_logs:
            self._save_debug_log(node_name, attempt_number, result, working_directory)
            
        # Track session
        self.debug_sessions.append(result)
        
        # Log result
        if result['success']:
            logger.info(
                f"Successfully fixed {node_name} in {result['turn_count']} turns, "
                f"cost: ${result.get('cost', 0):.4f}"
            )
        else:
            logger.warning(
                f"Failed to fix {node_name} after {result['turn_count']} turns, "
                f"cost: ${result.get('cost', 0):.4f}"
            )
            
        return result
        
    def _save_debug_log(
        self,
        node_name: str,
        attempt_number: int,
        result: Dict[str, Any],
        working_directory: Path
    ) -> None:
        """Save debug session log.
        
        Args:
            node_name: Name of the function block
            attempt_number: Attempt number
            result: Debug session result
            working_directory: Working directory
        """
        try:
            # Create debug logs directory
            debug_dir = working_directory / "agent_tasks" / "unified_bug_fixer" / f"attempt_{attempt_number}"
            debug_dir.mkdir(parents=True, exist_ok=True)
            
            # Save full session log
            session_log = {
                'node_name': node_name,
                'attempt_number': attempt_number,
                'model_name': getattr(self.llm_service, 'model', self.model_name),
                'success': result.get('success', False),
                'turn_count': result.get('turn_count', 0),
                'duration_seconds': result.get('duration_seconds', 0.0),
                'cost': result.get('cost', 0),
                'tokens': result.get('tokens', {}),
                'files_modified': result.get('files_modified', []),
                'actions_taken': result.get('actions', []),
                'timestamp': result.get('timestamp', datetime.now().isoformat())
            }
            
            with open(debug_dir / "session_log.json", 'w') as f:
                json.dump(session_log, f, indent=2)
                
            # Save conversation history (only if the session returned it)
            if result.get('messages') is not None:
                with open(debug_dir / "conversation.json", 'w') as f:
                    json.dump(result['messages'], f, indent=2)
                
            logger.debug(f"Saved debug logs to {debug_dir}")
            
        except Exception as e:
            logger.error(f"Failed to save debug log: {e}")
            
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics for all debug sessions.
        
        Returns:
            Statistics dictionary
        """
        if not self.debug_sessions:
            return {
                'total_sessions': 0,
                'successful_sessions': 0,
                'success_rate': 0.0,
                'total_cost': 0.0,
                'total_tokens': 0,
                'average_turns': 0.0
            }
            
        successful = sum(1 for s in self.debug_sessions if s['success'])
        total_cost = sum(s['cost'] for s in self.debug_sessions)
        total_tokens = sum(s['tokens']['total'] for s in self.debug_sessions)
        avg_turns = sum(s['turn_count'] for s in self.debug_sessions) / len(self.debug_sessions)
        
        return {
            'total_sessions': len(self.debug_sessions),
            'successful_sessions': successful,
            'success_rate': successful / len(self.debug_sessions),
            'total_cost': total_cost,
            'total_tokens': total_tokens,
            'average_turns': avg_turns,
            'model_name': getattr(self.llm_service, 'model', self.model_name)
        }
        
    def _create_llm_service(self, model_name: str, api_key: Optional[str] = None, seed: Optional[int] = None) -> BaseLLMService:
        """Create appropriate LLM service based on model name.
        
        Args:
            model_name: Model identifier
            api_key: Optional API key
            seed: Optional seed for reproducibility
            
        Returns:
            LLM service instance
        """
        # Use the factory function from llm_service
        return create_llm_service(
            model_name=model_name,
            api_key=api_key,
            seed=seed,
            timeout=self.timeout,
            enable_web_search=self.enable_web_search
        )
    
    def _get_web_search_model(self, model_name: str) -> str:
        """Get web search enabled version of a model if available.
        
        Args:
            model_name: Base model name
            
        Returns:
            Web search enabled model name or original if not available
        """
        # Map to web search enabled models
        web_search_models = {
            # OpenAI models - keep original as search is via tools/functions
            'gpt-4o-mini': 'gpt-4o-mini',
            'gpt-4o': 'gpt-4o',
            
            # Claude models already support web search natively with Claude 3.5
            'claude-3-haiku': 'claude-3-5-haiku-20241022',  # Use latest version with search
            'claude-3-sonnet': 'claude-3-5-sonnet-20241022',  # Use latest version with search
            'claude-3-5-haiku': 'claude-3-5-haiku-20241022',
            'claude-3-5-sonnet': 'claude-3-5-sonnet-20241022'
        }
        
        # Return mapped model or original if no mapping exists
        return web_search_models.get(model_name, model_name)
    
