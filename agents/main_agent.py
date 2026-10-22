"""Main agent that coordinates the entire analysis workflow."""

import os
import json
import re
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import uuid

from models import (
    NodeState, GenerationMode, AnalysisTree, AnalysisNode,
    NewFunctionBlock, ExistingFunctionBlock,
    FunctionBlockType, StaticConfig, Arg
)
from analysis_tree_management import AnalysisTreeManager, NodeExecutor
from job_executors import ExecutorManager
# LLM services are imported dynamically in __init__
from utils import setup_logger
from utils.timing import TimingContext, OperationTimer, time_operation
from utils.tee_logger import TeeLogger
from config import config
from .orchestrator_agent import OrchestratorAgent
from .function_creator_agent import FunctionCreatorAgent
from .failure_context_config import FailureContextConfig, get_failure_context_config
from constants import (
    ROOT_NODE_NAME, MAX_REWORK_ATTEMPTS,
    GPT_4, CLAUDE_3_5_SONNET, CLAUDE_3_5_HAIKU, GPT_4O_MINI,
    DEFAULT_OPENAI_MODEL, ENV_OPENAI_API_KEY
)
from models import JobReviewStatus

logger = setup_logger(__name__)


class MainAgent:
    """Main agent that coordinates the entire analysis workflow."""
    
    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        claude_api_key: Optional[str] = None,
        bug_fixer_type: str = "unified",
        bug_fixer_model: Optional[str] = None,
        llm_model: Optional[str] = None,
        enable_web_search: bool = False,
        enable_web_agent: bool = True,
        log_llm_to_stdout: bool = False,
        enable_domain_knowledge: bool = True,
        domain_knowledge_domains: Optional[List[str]] = None,
        bug_fixer_timeout: Optional[int] = None,
        llm_seed: Optional[int] = 31,
        bug_fixer_max_turns: Optional[int] = None,
        enable_output_collector: bool = True,
        failure_context_config: Optional[FailureContextConfig] = None,
        claude_code_allowed_tools: Optional[List[str]] = None,
        enable_claude_web_search: bool = False,
        docker_execution_timeout: Optional[int] = None,
        directory_tree_max_depth: int = 3
    ):
        """Initialize the main agent.

        Args:
            openai_api_key: OpenAI API key for LLM services
            claude_api_key: Claude API key for Claude bug fixer
            bug_fixer_type: Type of bug fixer ('unified', 'standard', 'claude', 'claude_code_sdk')
            bug_fixer_model: Model name for unified bug fixer (e.g., 'gpt-4', 'claude-3-5-sonnet-20241022')
            llm_model: OpenAI model to use (e.g., 'gpt-4o', 'gpt-4o-mini')
            enable_web_search: Enable web search in bug fixer
            enable_web_agent: Enable web agent for bug fixer research
            enable_domain_knowledge: Enable domain-specific knowledge injection
            domain_knowledge_domains: List of domain knowledge to inject (default: ['single_cell_genomics'])
            bug_fixer_timeout: Timeout in seconds for bug fixer execution (default: from config)
            llm_seed: Seed for LLM reproducibility (optional)
            bug_fixer_max_turns: Maximum number of debug turns for bug fixer (default: 5)
            enable_output_collector: Enable output collector to gather scattered outputs (default: True)
            failure_context_config: Configuration for failure context truncation (optional)
            claude_code_allowed_tools: List of allowed tools for Claude Code SDK (default: no tools for security)
            enable_claude_web_search: Enable Claude CLI web search (uses the local Claude Code CLI instead of OpenAI)
            docker_execution_timeout: Docker execution timeout in seconds (default: 1800 = 30 minutes)
            directory_tree_max_depth: Maximum depth for directory tree generation (default: 3)
        """
        # Initialize failure context configuration
        self.failure_context_config = failure_context_config or get_failure_context_config()
        
        # Store directory tree configuration
        self.directory_tree_max_depth = directory_tree_max_depth
        
        # Store the model being used
        self.llm_model = llm_model or DEFAULT_OPENAI_MODEL
        
        # Initialize LLM services based on the model type
        self.llm_service = None
        self.claude_service = None
        
        # Use the centralized factory to create LLM service
        from llm_service import create_llm_service, is_cli_model, get_required_api_key_type
        
        # Determine which API key to use based on model type
        api_key = None
        key_type = get_required_api_key_type(self.llm_model)
        
        if key_type == 'openai':
            api_key = openai_api_key
            if not api_key:
                logger.warning(f"OpenAI model {self.llm_model} specified but no OPENAI_API_KEY provided")
        elif key_type == 'anthropic':
            api_key = claude_api_key
            if not api_key:
                logger.warning(f"Claude model {self.llm_model} specified but no CLAUDE_API_KEY provided")
        # No API key needed for CLI models
        
        # Create the service if we have the necessary credentials (or if no credentials needed)
        if api_key or is_cli_model(self.llm_model):
            try:
                service = create_llm_service(
                    model_name=self.llm_model,
                    api_key=api_key,
                    timeout=config.llm_timeout,
                    seed=llm_seed,
                    enable_web_search=False  # Main agent doesn't need web search
                )
                
                # Set the appropriate service attribute based on model type
                if self.llm_model.startswith('claude'):
                    self.claude_service = service
                    # Also set llm_service for CLI models for compatibility
                    if is_cli_model(self.llm_model):
                        self.llm_service = service
                else:
                    self.llm_service = service
                
                logger.info(f"Initialized {type(service).__name__} with model: {self.llm_model}")

            except ValueError as e:
                # Re-raise validation errors directly (don't wrap)
                logger.error(f"Invalid model configuration: {e}")
                raise
            except Exception as e:
                logger.error(f"Failed to create LLM service: {e}")
                raise RuntimeError(f"LLM service initialization failed for model '{self.llm_model}': {e}") from e
        
        # Initialize managers
        self.tree_manager = AnalysisTreeManager()
        self.executor_manager = ExecutorManager()

        # Store settings
        self.enable_web_agent = enable_web_agent
        self.enable_claude_web_search = enable_claude_web_search
        self.log_llm_to_stdout = log_llm_to_stdout
        self.bug_fixer_timeout = bug_fixer_timeout
        self.llm_seed = llm_seed
        self.bug_fixer_max_turns = bug_fixer_max_turns or 5  # Default to 5 if not specified
        self.enable_output_collector = enable_output_collector
        self.docker_execution_timeout = docker_execution_timeout  # Will use default if None
        
        # Initialize domain knowledge system
        self.enable_domain_knowledge = enable_domain_knowledge
        self.domain_knowledge_domains = domain_knowledge_domains or ["function_block_complete_examples", "function_block_faq", "pseudotime_implementation", "single_cell_genomics", "cell_type_annotation", "package_validation"]
        
        if self.enable_domain_knowledge:
            from domain_knowledge import get_knowledge_service, PromptInjector
            self.knowledge_service = get_knowledge_service()
            self.prompt_injector = PromptInjector(self.knowledge_service)
            logger.info(f"Domain knowledge enabled for domains: {self.domain_knowledge_domains}")

        # Always use interactive node executor (modern approach)
        from analysis_tree_management.interactive_node_executor import InteractiveNodeExecutor
        self.node_executor = InteractiveNodeExecutor(
            self.executor_manager,
            bug_fixer=None,  # Will be set after bug fixer initialization
            enable_interactive_debug=True,
            output_collector_llm=self.llm_service if enable_output_collector else None,
            cleanup_job_dirs=True,  # Enable cleanup to save disk space
            docker_execution_timeout=self.docker_execution_timeout
        )
        logger.info("Using interactive node executor with in-container debugging")
        if enable_output_collector:
            logger.info("Output collector enabled for gathering scattered outputs")
        
        # Initialize specialized agents (orchestrator will be updated later with other agents)
        self.orchestrator = None
        
        # Initialize job reviewer
        self.job_reviewer = None
        if self.llm_service:
            try:
                from .job_reviewer_agent import JobReviewerAgent
                self.job_reviewer = JobReviewerAgent(self.llm_service, llm_seed=llm_seed)
                logger.info("Job reviewer agent initialized")
            except Exception as e:
                # Use ERROR level for component initialization failures
                logger.error(f"Failed to initialize job reviewer: {e}", extra={
                    'error_category': 'initialization',
                    'agent_type': 'main_agent',
                    'component': 'job_reviewer',
                    'context': {
                        'llm_model': llm_model,
                        'error_type': type(e).__name__
                    },
                    'recovery_hint': 'System will continue without job review quality checks'
                }, exc_info=True)
                
                # Log degraded mode
                logger.warning("MainAgent running in degraded mode without job reviewer")
        
        # Initialize function creator with domain knowledge if enabled
        # Use either OpenAI or Claude service
        active_llm_service = self.llm_service or self.claude_service
        if active_llm_service:
            if self.enable_domain_knowledge:
                self.function_creator = FunctionCreatorAgent(
                    active_llm_service,
                    enable_domain_knowledge=True,
                    domain_knowledge_domains=self.domain_knowledge_domains,
                    llm_seed=llm_seed,
                    enable_code_checker=True,
                    log_llm_to_stdout=self.log_llm_to_stdout
                )
            else:
                self.function_creator = FunctionCreatorAgent(
                    active_llm_service, 
                    llm_seed=llm_seed,
                    enable_code_checker=True,
                    log_llm_to_stdout=self.log_llm_to_stdout
                )
        else:
            self.function_creator = None
        
        # Select bug fixer based on type
        if bug_fixer_type == "unified":
            # New unified LLM-agnostic bug fixer
            from .unified_bug_fixer import UnifiedBugFixer
            if not bug_fixer_model:
                # Default to the same model as the main agent for consistency
                # This also allows service reuse
                bug_fixer_model = self.llm_model
                logger.info(f"Bug fixer model not specified, using same as main agent: {bug_fixer_model}")
            
            try:
                # Pass domain knowledge to bug fixer if enabled
                bug_fixer_kwargs = {
                    "max_turns": self.bug_fixer_max_turns,
                    "enable_web_search": enable_web_search,
                    "enable_web_agent": enable_web_agent,
                    "enable_claude_web_search": self.enable_claude_web_search,
                    "seed": llm_seed
                }
                
                # Check if we can reuse the main agent's LLM service
                # This saves memory and ensures consistent configuration
                if bug_fixer_model == self.llm_model:
                    # Reuse the existing service
                    existing_service = self.llm_service or self.claude_service
                    if existing_service:
                        bug_fixer_kwargs["llm_service"] = existing_service
                        logger.info(f"Bug fixer reusing main agent's LLM service for model: {bug_fixer_model}")
                    else:
                        # Create new service using factory
                        bug_fixer_api_key = openai_api_key if bug_fixer_model.startswith('gpt') else claude_api_key
                        bug_fixer_llm_service = create_llm_service(
                            model_name=bug_fixer_model,
                            api_key=bug_fixer_api_key,
                            timeout=self.bug_fixer_timeout if self.bug_fixer_timeout else 300,
                            seed=llm_seed,
                            enable_web_search=enable_web_search
                        )
                        bug_fixer_kwargs["llm_service"] = bug_fixer_llm_service
                        logger.info(f"Created new LLM service for bug fixer with model: {bug_fixer_model}")
                else:
                    # Different model than main agent - create new service using factory
                    bug_fixer_api_key = openai_api_key if bug_fixer_model.startswith('gpt') else claude_api_key
                    bug_fixer_llm_service = create_llm_service(
                        model_name=bug_fixer_model,
                        api_key=bug_fixer_api_key,
                        timeout=self.bug_fixer_timeout if self.bug_fixer_timeout else 300,
                        seed=llm_seed,
                        enable_web_search=enable_web_search
                    )
                    bug_fixer_kwargs["llm_service"] = bug_fixer_llm_service
                    logger.info(f"Created new LLM service for bug fixer with model: {bug_fixer_model}")
                
                if self.bug_fixer_timeout is not None:
                    bug_fixer_kwargs["timeout"] = self.bug_fixer_timeout
                
                if self.enable_domain_knowledge:
                    bug_fixer_kwargs["enable_domain_knowledge"] = True
                    bug_fixer_kwargs["domain_knowledge_domains"] = self.domain_knowledge_domains
                
                self.bug_fixer = UnifiedBugFixer(**bug_fixer_kwargs)
                logger.info(f"Using unified bug fixer with model: {bug_fixer_model}")

                # Update interactive node executor with bug fixer
                if hasattr(self.node_executor, 'update_bug_fixer'):
                    self.node_executor.update_bug_fixer(self.bug_fixer)
                    logger.info("Enabled in-container debugging for node executor")

            except ValueError as e:
                # Re-raise validation errors (don't catch and suppress)
                logger.error(f"Invalid bug fixer model configuration: {e}")
                raise
            except Exception as e:
                logger.error(f"Failed to initialize unified bug fixer: {e}")
                raise RuntimeError(f"Bug fixer initialization failed: {e}") from e
                
        elif bug_fixer_type == "claude_code_sdk":
            from .claude_code_sdk_bug_fixer import ClaudeCodeSDKBugFixer
            # Default to no tools for maximum security - users must explicitly enable tools
            allowed_tools = claude_code_allowed_tools or []
            self.bug_fixer = ClaudeCodeSDKBugFixer(
                api_key=claude_api_key,
                max_turns=self.bug_fixer_max_turns,
                allowed_tools=allowed_tools
            )
            logger.info(f"Using Claude Code SDK bug fixer with tools: {allowed_tools or 'none'}")
        else:
            # Invalid bug fixer type
            logger.error(f"Invalid bug fixer type: {bug_fixer_type}. Valid options are 'unified' or 'claude_code_sdk'")
            self.bug_fixer = None
        
        self.bug_fixer_type = bug_fixer_type
        
        # Initialize orchestrator with all agents
        # Use either OpenAI or Claude service
        active_llm_service = self.llm_service or self.claude_service
        if not active_llm_service:
            raise RuntimeError("No LLM service available for orchestrator initialization")
        
        self.orchestrator = OrchestratorAgent(
            llm_service=active_llm_service,
            function_creator=self.function_creator,
            bug_fixer=self.bug_fixer,
            job_reviewer=self.job_reviewer,
            llm_seed=llm_seed
        )
        logger.info("Orchestrator agent initialized with all sub-agents")
        
        # Initialize timing tracker
        self.timer = OperationTimer()
        logger.info(f"Main Agent initialized with bug_fixer_type={bug_fixer_type}, directory_tree_max_depth={directory_tree_max_depth}")

        # Log comprehensive agent configuration
        self._log_agent_configuration()
    
    def validate_environment(self) -> Dict[str, bool]:
        """Validate the execution environment.
        
        Returns:
            Dictionary with validation results for each component
        """
        return self.executor_manager.validate_environment()
    
    def _log_agent_configuration(self):
        """Log comprehensive configuration of all agents."""
        logger.info("=" * 80)
        logger.info("AGENT CONFIGURATION SUMMARY")
        logger.info("=" * 80)
        
        # Core configuration
        logger.info(f"🤖 LLM Service: {'OpenAI' if self.llm_service else 'None'}")
        if hasattr(self, 'llm_model'):
            logger.info(f"🧠 LLM Model: {getattr(self, 'llm_model', 'default')}")
        if hasattr(self, 'llm_seed'):
            logger.info(f"🎲 LLM Seed: {getattr(self, 'llm_seed', 'default')}")
        
        # Three new agents status
        logger.info("\n📋 NEW AGENT SYSTEM STATUS:")
        
        # 1. Code Checker Agent (via Function Creator)
        code_checker_enabled = False
        if self.function_creator and hasattr(self.function_creator, 'code_checker'):
            code_checker_enabled = self.function_creator.code_checker is not None
        
        logger.info(f"  🔍 Code Checker Agent: {'✅ ENABLED' if code_checker_enabled else '❌ DISABLED'}")
        if code_checker_enabled:
            logger.info("     - Validates function block code quality")
            logger.info("     - Checks for missing imports and best practices")
            logger.info("     - Provides auto-fix suggestions")
            logger.info("     - Integrated with Function Creator and Bug Fixer")
        
        # 2. Action Digester (via Bug Fixer)
        action_digester_enabled = False
        if hasattr(self, 'bug_fixer') and self.bug_fixer:
            # Check if it's the unified bug fixer which supports action digester
            action_digester_enabled = (
                hasattr(self.bug_fixer, 'enable_action_digester') or
                # Also check if it's the unified bug fixer type
                self.bug_fixer_type == "unified"
            )
        
        logger.info(f"  🗜️  Action Digester: {'✅ ENABLED' if action_digester_enabled else '❌ DISABLED'}")
        if action_digester_enabled:
            logger.info("     - Compresses long debug outputs (>5000 chars)")
            logger.info("     - Preserves critical error information")
            logger.info("     - Saves raw + digested outputs to files")
            logger.info("     - Integrated with Enhanced Debug Session")
        
        # 3. Job Reviewer Agent
        job_reviewer_enabled = self.job_reviewer is not None
        
        logger.info(f"  🔍 Job Reviewer Agent: {'✅ ENABLED' if job_reviewer_enabled else '❌ DISABLED'}")
        if job_reviewer_enabled:
            logger.info("     - Reviews completed function blocks for quality")
            logger.info("     - Detects cheating and placeholder code")  
            logger.info("     - Validates ML best practices")
            logger.info("     - Triggers rework when needed")
            logger.info("     - Integrated with Orchestrator Agent")
        
        # Other agent configurations
        logger.info("\n🔧 OTHER AGENT CONFIGURATIONS:")
        
        # Function Creator
        if self.function_creator:
            domain_knowledge = getattr(self.function_creator, 'enable_domain_knowledge', False)
            domains = getattr(self.function_creator, 'domain_knowledge_domains', [])
            logger.info(f"  📝 Function Creator: ✅ ENABLED")
            logger.info(f"     - Domain Knowledge: {'✅' if domain_knowledge else '❌'}")
            if domains:
                logger.info(f"     - Domains: {', '.join(domains)}")
        else:
            logger.info(f"  📝 Function Creator: ❌ DISABLED")
        
        # Orchestrator  
        if self.orchestrator:
            logger.info(f"  🎭 Orchestrator Agent: ✅ ENABLED")
            logger.info(f"     - Job Reviewer Integration: {'✅' if job_reviewer_enabled else '❌'}")
        else:
            logger.info(f"  🎭 Orchestrator Agent: ❌ DISABLED")
        
        # Bug Fixer
        bug_fixer_type = getattr(self, 'bug_fixer_type', 'unknown')
        logger.info(f"  🐛 Bug Fixer: {'✅ ENABLED' if self.bug_fixer else '❌ DISABLED'} (type: {bug_fixer_type})")
        if self.bug_fixer:
            if hasattr(self.bug_fixer, 'max_turns'):
                logger.info(f"     - Max Turns: {getattr(self.bug_fixer, 'max_turns', 'default')}")
            web_agent_enabled = getattr(self, 'enable_web_agent', False)
            logger.info(f"     - Web Agent: {'✅' if web_agent_enabled else '❌'}")
            logger.info(f"     - Interactive Debug: ✅ (always enabled)")
        
        # Summary - flexible approach without hardcoded numbers
        new_agents_status = {
            "Code Checker": code_checker_enabled,
            "Action Digester": action_digester_enabled, 
            "Job Reviewer": job_reviewer_enabled
        }
        
        enabled_agents = [name for name, enabled in new_agents_status.items() if enabled]
        disabled_agents = [name for name, enabled in new_agents_status.items() if not enabled]
        
        logger.info(f"\n📊 AGENT SUMMARY:")
        
        # Show which agents are enabled
        if enabled_agents:
            logger.info(f"  ✅ ENABLED AGENTS: {', '.join(enabled_agents)}")
        
        # Show which agents are disabled (if any)
        if disabled_agents:
            logger.info(f"  ❌ DISABLED AGENTS: {', '.join(disabled_agents)}")
        
        # Show capability enhancements
        logger.info(f"  - Code Quality: {'✅ Enhanced' if code_checker_enabled else '❌ Basic'}")
        logger.info(f"  - Debug Efficiency: {'✅ Enhanced' if action_digester_enabled else '❌ Basic'}")
        logger.info(f"  - Quality Assurance: {'✅ Enhanced' if job_reviewer_enabled else '❌ Basic'}")
        
        # Dynamic status message based on what's actually enabled
        if not enabled_agents:
            logger.info("⚠️  NO NEW AGENTS ACTIVE - BASIC SYSTEM")
        elif len(disabled_agents) == 0:
            logger.info("🎉 ALL NEW AGENTS ARE ACTIVE - FULL ENHANCED SYSTEM!")
        else:
            logger.info(f"⚡ ENHANCED SYSTEM - {len(enabled_agents)} agent(s) active, {len(disabled_agents)} disabled")
        
        logger.info("=" * 80)
    
    @time_operation("MainAgent.run_analysis")
    def run_analysis(
        self,
        input_data_path: Union[str, Path],
        user_request: str,
        output_dir: Optional[Union[str, Path]] = None,
        max_nodes: int = 20,
        max_children: int = 3,
        max_debug_trials: int = 3,
        max_iterations: int = 10,  # Planning iterations (orchestrator queries), NOT node execution iterations
        generation_mode: str = "mixed",
        llm_model: Optional[str] = None,  # Use instance model if not specified
        verbose: bool = False,
        # Timeout parameters
        function_block_timeout: Optional[int] = None,
        web_agent_timeout: Optional[int] = None,
        # Claude-specific parameters
        max_claude_turns: Optional[int] = None,
        max_claude_cost: Optional[float] = None,
        max_claude_tokens: Optional[int] = None,
        # Logging parameters
        capture_logs: bool = True,
        log_file_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run the complete analysis workflow.
        
        Args:
            input_data_path: Path to input data (file or directory)
            user_request: Natural language request from user
            output_dir: Output directory
            max_nodes: Maximum number of analysis nodes
            max_children: Maximum children per node
            max_debug_trials: Maximum debug attempts per node
            max_iterations: Maximum planning iterations (safeguard against infinite loops)
            generation_mode: "mixed", "only_new", or "only_existing"
            llm_model: OpenAI model to use
            verbose: Whether to print verbose output
            function_block_timeout: Timeout in seconds for each function block execution (default: 300)
            web_agent_timeout: Timeout in seconds for web agent research (default: 90)
            capture_logs: Whether to capture logs to file (default: True)
            log_file_name: Custom log file name (default: analysis_log_TIMESTAMP.log)
            
        Returns:
            Dictionary with results including output directory and execution statistics
        """
        # Validate input path
        input_path = Path(input_data_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input path not found: {input_path}")
        
        # Setup output directory
        if output_dir is None:
            output_dir = Path("outputs") / f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Set up log file path
        if capture_logs:
            if log_file_name:
                log_file_path = output_dir / log_file_name
            else:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                log_file_path = output_dir / f"analysis_log_{timestamp}.log"
        else:
            log_file_path = None
        
        # Use instance model if not specified
        if llm_model is None:
            llm_model = self.llm_model
            logger.info(f"Using instance model: {llm_model}")
        
        # Configure timeouts temporarily for this analysis
        if function_block_timeout is not None:
            config.function_block_timeout = function_block_timeout
            logger.info(f"Set function block timeout to {function_block_timeout} seconds for this analysis")
        
        if web_agent_timeout is not None and hasattr(self, '_web_agent_tool'):
            self._web_agent_tool.timeout_seconds = web_agent_timeout
            logger.info(f"Set web agent timeout to {web_agent_timeout} seconds for this analysis")
        
        # Create analysis tree
        logger.info(f"Creating analysis tree for request: {user_request}")
        self.timer.start("create_tree")
        tree = self.tree_manager.create_tree(
            user_request=user_request,
            input_data_path=str(input_path),
            max_nodes=max_nodes,
            max_children_per_node=max_children,
            max_debug_trials=max_debug_trials,
            generation_mode=GenerationMode(generation_mode),
            llm_model=llm_model
        )
        self.timer.stop("create_tree")
        
        # Create main agent task directory
        main_task_dir = output_dir / f"main_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{tree.id[:8]}"
        main_task_dir.mkdir(parents=True, exist_ok=True)
        
        # Store output_dir for use in other methods
        self.current_output_dir = output_dir
        
        # Start logging capture if enabled
        tee_logger = None
        if capture_logs and log_file_path:
            logger.info(f"Starting log capture to: {log_file_path}")
            # Use INFO level to avoid capturing DEBUG logs from HTTP libraries
            tee_logger = TeeLogger(log_file_path, level=logging.INFO)
            tee_logger.__enter__()
        
        # Add structured error handler for this analysis tree
        structured_handler = None
        from agents.utils.structured_error_handler import StructuredErrorHandler
        tree_dir = output_dir / tree.id
        structured_handler = StructuredErrorHandler(tree_dir)
        logging.getLogger().addHandler(structured_handler)
        logger.info(f"Structured error logging enabled at: {tree_dir}/error_logs/")
        
        # Save user request
        with open(main_task_dir / "user_request.txt", 'w') as f:
            f.write(user_request)
        
        # Note: Claude-specific parameters are deprecated
        # These are kept for backward compatibility but not used
        _ = (max_claude_turns, max_claude_cost, max_claude_tokens)
        
        # Save agent info with hyperparameters
        agent_info = {
            "agent_type": "main",
            "tree_id": tree.id,
            "input_path": str(input_path),
            "output_dir": str(output_dir),
            "created_at": datetime.now().isoformat(),
            "llm_model": llm_model,
            "generation_mode": generation_mode,
            "bug_fixer_type": self.bug_fixer_type,
            "enable_domain_knowledge": self.enable_domain_knowledge,
            "domain_knowledge_domains": self.domain_knowledge_domains,
            "llm_seed": self.llm_seed,
            "bug_fixer_max_turns": self.bug_fixer_max_turns,
            "enable_web_agent": self.enable_web_agent,
            "enable_output_collector": self.enable_output_collector,
            "hyperparameters": {
                "max_nodes": max_nodes,
                "max_children": max_children,
                "max_debug_trials": max_debug_trials,
                "max_iterations": max_iterations,
                "max_claude_turns": max_claude_turns,
                "max_claude_cost": max_claude_cost,
                "max_claude_tokens": max_claude_tokens,
                # Include key debug parameters for paper analysis
                "llm_seed": self.llm_seed,
                "bug_fixer_max_turns": self.bug_fixer_max_turns,
                "enable_domain_knowledge": self.enable_domain_knowledge,
                "domain_knowledge_domains": self.domain_knowledge_domains
            }
        }
        with open(main_task_dir / "agent_info.json", 'w') as f:
            json.dump(agent_info, f, indent=2)
        
        results = {}  # Initialize results
        try:
            # Generate and execute analysis plan
            if not self.orchestrator:
                raise ValueError("Orchestrator is required for analysis planning")
                
            with TimingContext("generate_and_execute_plan", logger):
                self._generate_and_execute_plan(
                    tree, input_path, output_dir, verbose, main_task_dir,
                    max_iterations=max_iterations
                )
            
            # Execute the tree
            with TimingContext("execute_tree", logger):
                results = self._execute_tree(tree, input_path, output_dir, verbose)
            
        finally:
            # Always save tree state, even if execution was interrupted
            with TimingContext("save_tree_state", logger):
                tree_file = output_dir / "analysis_tree.json"
                self.tree_manager.save_tree(tree_file)
            
            # Also save in tree directory
            tree_dir = output_dir / tree.id
            if tree_dir.exists():
                tree_file_in_tree = tree_dir / "analysis_tree.json"
                self.tree_manager.save_tree(tree_file_in_tree)
            
            # Create directory tree markdown
            tree_md_path = output_dir / "directory_tree.md"
            self.tree_manager._create_directory_tree_md(output_dir, tree_md_path)
            
            # Create analysis summary markdown
            summary_md_path = output_dir / "analysis_summary.md"
            self._create_analysis_summary_md(tree, summary_md_path, results)
            
            # Note: Docker containers are automatically cleaned up after each job execution
            # via the auto_remove=True default in DockerManager.run_container()
            # No additional cleanup needed here
            
            # Stop logging capture if enabled
            if tee_logger:
                logger.info(f"Stopping log capture. Log saved to: {log_file_path}")
                tee_logger.__exit__(None, None, None)
            
            # Clean up structured error handler
            if structured_handler:
                logging.getLogger().removeHandler(structured_handler)
                structured_handler.close()
                logger.info("Structured error handler closed")
        
        # Collect Claude usage statistics if using Claude bug fixer
        claude_usage = {}
        if self.bug_fixer_type == "claude" and hasattr(self.bug_fixer, 'claude_service'):
            claude_usage = {
                "total_cost": self.bug_fixer.claude_service.total_cost,
                "total_tokens": self.bug_fixer.claude_service.total_tokens_used,
                "model": self.bug_fixer.claude_service.model
            }
        elif self.bug_fixer_type == "claude_code_sdk" and hasattr(self.bug_fixer, 'get_stats'):
            stats = self.bug_fixer.get_stats()
            claude_usage = {
                "total_cost": stats.get('total_cost', 0.0),
                "total_tokens": stats.get('total_tokens', 0),
                "model": "claude-code-sdk",
                "sessions": stats.get('total_sessions', 0),
                "success_rate": stats.get('success_rate', 0.0)
            }
        elif self.bug_fixer_type == "unified" and hasattr(self.bug_fixer, 'get_statistics'):
            stats = self.bug_fixer.get_statistics()
            claude_usage = {
                "total_cost": stats.get('total_cost', 0.0),
                "total_tokens": stats.get('total_tokens', 0),
                "model": getattr(self.bug_fixer, 'model_name', 'unified'),
                "sessions": stats.get('total_sessions', 0),
                "success_rate": stats.get('success_rate', 0.0)
            }
        
        # Add timing summary
        timing_summary = self.timer.get_summary()
        self.timer.log_summary()
        
        # Build tree structure for return
        tree_structure = {
            "nodes": {},
            "root_nodes": []
        }
        
        for node_id, node in tree.nodes.items():
            node_info = {
                "id": node_id,
                "name": node.function_block.name,
                "state": node.state.value,
                "parent_id": node.parent_id,
                "children": node.children,
                "level": node.level
            }
            
            # Add error info for failed nodes
            if node.state == NodeState.FAILED:
                if hasattr(node, 'error_message'):
                    node_info["error"] = node.error_message
                elif node.execution_result and 'error' in node.execution_result:
                    node_info["error"] = node.execution_result['error']
            
            tree_structure["nodes"][node_id] = node_info
            
            # Track root nodes
            if node.parent_id is None:
                tree_structure["root_nodes"].append(node_id)
        
        # Return summary
        result = {
            "tree_id": tree.id,
            "output_dir": str(output_dir),
            "tree_file": str(tree_file),
            "total_nodes": tree.total_nodes,
            "completed_nodes": tree.completed_nodes,
            "failed_nodes": tree.failed_nodes,
            "pending_nodes": tree.total_nodes - tree.completed_nodes - tree.failed_nodes,
            "results": results,
            "timing_summary": timing_summary,
            "tree_structure": tree_structure,
            "log_file": str(log_file_path) if log_file_path else None
        }
        
        if claude_usage:
            result["claude_usage"] = claude_usage
            
        return result
    
    def _generate_and_execute_plan(
        self,
        tree: AnalysisTree,
        input_path: Path,
        output_dir: Path,
        verbose: bool,
        main_task_dir: Path,
        max_iterations: int = 10  # Add safeguard
    ):
        """Generate analysis plan using orchestrator and execute it.
        
        This method uses the orchestrator to create a plan and executes it:
        1. Get plan from orchestrator
        2. Create function blocks according to plan
        3. Execute nodes
        4. Repeat until satisfied or limits reached
        """
        orchestrator_dir = main_task_dir / "orchestrator_tasks"
        orchestrator_dir.mkdir(exist_ok=True)
        
        # Track execution state
        iteration = 0
        satisfied = False
        plan_actions = []  # Store remaining plan actions
        consecutive_no_attach = 0  # Track consecutive failures to attach nodes
        MAX_CONSECUTIVE_NO_ATTACH = 3
        
        while not satisfied and tree.total_nodes < tree.max_nodes and iteration < max_iterations:
            iteration += 1
            
            if verbose:
                logger.info(f"Planning iteration {iteration} (max: {max_iterations})")
                logger.info(f"  Satisfied: {satisfied}, Total nodes: {tree.total_nodes}, Max nodes: {tree.max_nodes}")
            
            # Execute any pending nodes first (including data loading root)
            pending_nodes = [node for node in tree.nodes.values() if node.state == NodeState.PENDING]
            if pending_nodes:
                if verbose:
                    logger.info(f"Executing {len(pending_nodes)} pending nodes before planning")
                for node in pending_nodes:
                    if verbose:
                        logger.info(f"  Executing: {node.function_block.name}")
                    success = self._execute_single_node(node, tree, input_path, output_dir, verbose)
                    if verbose:
                        logger.info(f"    Result: {'success' if success else 'failed'}")
            
            # Check if we have any successful nodes to work with
            if tree.total_nodes > 0:
                successful_leaf_nodes = [
                    (node_id, node) for node_id, node in tree.nodes.items()
                    if node.state == NodeState.COMPLETED and len(node.children) == 0
                ]
                
                if not successful_leaf_nodes:
                    # No successful nodes to expand from
                    if verbose:
                        logger.info("No successful leaf nodes to expand from. Letting orchestrator decide.")
                    # Don't break! Let orchestrator see the situation and decide
            
            # Get plan from orchestrator
            tree_state = self._get_tree_state_for_orchestrator(tree)
            
            # Always log tree statistics for debugging
            logger.info(f"\nTree Statistics - Iteration {iteration}:")
            logger.info(f"  Total nodes: {tree.total_nodes}")
            logger.info(f"  Completed nodes: {tree.completed_nodes}")
            logger.info(f"  Failed nodes: {tree.failed_nodes}")
            logger.info(f"  Tree state total/completed/failed: {tree_state['total_nodes']}/{tree_state['completed_nodes']}/{tree_state['failed_nodes']}")
            
            # Update all_tree_errors.json with any failed nodes
            if tree.failed_nodes > 0 and hasattr(self, 'current_output_dir'):
                tree_dir = Path(self.current_output_dir) / tree.id
                failed_contexts = []
                for node_info in tree_state['nodes']:
                    if node_info.get('failure_context'):
                        failed_contexts.append(node_info['failure_context'])
                if failed_contexts:
                    self._update_all_tree_errors(tree_dir, failed_contexts)
                    logger.debug(f"Updated all_tree_errors.json with {len(failed_contexts)} failed nodes")
            
            # Log actual node states for verification
            node_states = {}
            for node in tree.nodes.values():
                state_name = node.state.value if hasattr(node.state, 'value') else str(node.state)
                node_states[state_name] = node_states.get(state_name, 0) + 1
            logger.info(f"  Actual node states: {node_states}")
            
            # Collect and log job review statistics
            job_review_stats = self._collect_job_review_statistics(tree)
            logger.info(f"\nJob Review Statistics:")
            logger.info(f"  Review Passed: {job_review_stats['passed']}")
            logger.info(f"  Review Failed: {job_review_stats['failed']}")
            logger.info(f"  Not Reviewed: {job_review_stats['not_reviewed']}")
            logger.info(f"  Review Skipped: {job_review_stats['skipped']}")
            logger.info(f"  Needs Rework: {job_review_stats['needs_rework']}")
            logger.info(f"  Total Rework Attempts: {job_review_stats['total_rework_attempts']}")
            
            # Log execution vs review summary
            logger.info(f"\nExecution vs Review Summary:")
            logger.info(f"  Executed Successfully + Passed Review: {job_review_stats['executed_and_passed']}")
            logger.info(f"  Executed Successfully + Failed Review: {job_review_stats['executed_and_failed_review']}")
            logger.info(f"  Execution Failed (Not Reviewed): {job_review_stats['execution_failed']}")
            
            # Log LLM interaction if enabled
            if self.log_llm_to_stdout:
                logger.info("\n" + "="*80)
                logger.info("ORCHESTRATOR LLM INPUT:")
                logger.info(f"User request: {tree.user_request}")
                logger.info(f"Tree state: {json.dumps(tree_state, indent=2)}")
                logger.info(f"Iteration: {iteration}")
                logger.info("="*80 + "\n")
            
            plan_result = self.orchestrator.plan_next_steps({
                "user_request": tree.user_request,
                "tree_state": tree_state,
                "iteration": iteration,
                "output_dir": orchestrator_dir  # Pass output dir for logging
            })
            
            # Log orchestrator response if enabled
            if self.log_llm_to_stdout:
                logger.info("\n" + "="*80)
                logger.info("ORCHESTRATOR LLM OUTPUT:")
                logger.info(json.dumps(plan_result, indent=2))
                logger.info("="*80 + "\n")
            
            satisfied = plan_result.get("satisfied", False)
            new_actions = plan_result.get("next_actions", [])
            
            if verbose:
                logger.info(f"  Orchestrator planning: satisfied={satisfied}, actions={len(new_actions)}")
                if plan_result.get("reasoning"):
                    logger.info(f"  Reasoning: {plan_result['reasoning']}")
            
            if satisfied:
                if verbose:
                    logger.info("User request satisfied according to orchestrator")
                break
            
            if not new_actions:
                if verbose:
                    logger.info("No actions from orchestrator, continuing to next iteration")
                continue
            
            # Process each action from the plan
            for action in new_actions:
                if tree.total_nodes >= tree.max_nodes:
                    logger.warning(f"Reached max nodes limit: {tree.max_nodes}")
                    break
                    
                if action["type"] == "create_new":
                    # Create the function block specified in the plan
                    spec = action["specification"]
                    
                    # Check if this is a rework (must be explicitly specified by orchestrator)
                    source_node = None
                    is_rework = False
                    
                    if 'rework_of_node_id' in action:
                        # This is a rework - get the source node directly
                        rework_of_node_id = action['rework_of_node_id']
                        if rework_of_node_id in tree.nodes:
                            source_node = tree.nodes[rework_of_node_id]
                            is_rework = True
                            
                            # Use the attempt count from orchestrator if provided, otherwise calculate
                            if 'rework_attempts' in action:
                                next_rework_count = action['rework_attempts']
                            else:
                                next_rework_count = source_node.rework_attempts + 1
                            
                            if next_rework_count > MAX_REWORK_ATTEMPTS:
                                original_task = source_node.function_block.name
                                logger.warning(
                                    f"Rework limit reached for task '{original_task}': "
                                    f"attempt {next_rework_count} exceeds limit of {MAX_REWORK_ATTEMPTS}. "
                                    f"Skipping node creation."
                                )
                                continue  # Skip this action - don't create the node
                            
                            logger.info(f"Processing rework action for node {rework_of_node_id[:8]} (attempt {next_rework_count})")
                        else:
                            logger.error(f"Rework references non-existent node {rework_of_node_id}")
                            continue  # Skip this action if node doesn't exist
                    
                    # First, determine parent node
                    parent_node = None
                    if tree.total_nodes == 0:
                        # This is the root node
                        parent_node = None
                        is_root = True
                    else:
                        # Find appropriate parent - prefer leaf nodes, but fall back to internal nodes
                        successful_leaf_nodes = [
                            (node_id, node) for node_id, node in tree.nodes.items()
                            if node.state == NodeState.COMPLETED and len(node.children) == 0
                        ]
                        
                        if successful_leaf_nodes:
                            # Use most recent successful leaf
                            _, parent_node = successful_leaf_nodes[-1]
                            is_root = False
                        else:
                            # No successful leaf nodes - find any successful node to attach to
                            # This allows expanding from internal nodes when their children failed
                            successful_nodes = [
                                (node_id, node) for node_id, node in tree.nodes.items()
                                if node.state == NodeState.COMPLETED
                            ]
                            
                            if successful_nodes:
                                # Use the most recent successful node (even if it has children)
                                _, parent_node = successful_nodes[-1]
                                is_root = False
                                if verbose:
                                    logger.info(f"  No successful leaf nodes, attaching to internal node: {parent_node.function_block.name}")
                            else:
                                # No successful nodes at all - check if we can retry the root
                                if tree.total_nodes == 1 and tree.failed_nodes == 1:
                                    # Only the root failed - allow creating a new root
                                    logger.info("Root node failed, allowing new root creation")
                                    parent_node = None
                                    is_root = True
                                else:
                                    consecutive_no_attach += 1
                                    logger.warning(f"No successful nodes to attach to (attempt {consecutive_no_attach}/{MAX_CONSECUTIVE_NO_ATTACH})")
                                    
                                    if consecutive_no_attach >= MAX_CONSECUTIVE_NO_ATTACH:
                                        logger.error("Too many consecutive attempts with no successful nodes to attach to. Breaking out of planning loop.")
                                        satisfied = True  # Mark as satisfied to exit gracefully
                                        break
                                    continue
                    
                    # Prepare input context for function creator
                    input_context = {
                        'is_root_node': is_root,
                        'available_files': []
                    }
                    
                    # If this is a rework, add job review failure context from the source node
                    if is_rework and source_node:
                        if (source_node.job_review_status == JobReviewStatus.FAILED and
                            source_node.job_review_result):
                            # Add job review failure details to help avoid same issues
                            input_context['previous_implementation_failed'] = True
                            input_context['job_review_concerns'] = []
                            
                            # Extract concerns from the job review
                            if isinstance(source_node.job_review_result, dict):
                                concerns = source_node.job_review_result.get('concerns', [])
                                for concern in concerns:
                                    input_context['job_review_concerns'].append({
                                        'type': concern.get('type', 'unknown'),
                                        'severity': concern.get('severity', 'unknown'),
                                        'description': concern.get('description', ''),
                                        'suggested_fix': concern.get('suggested_fix', '')
                                    })
                            
                            # Add the failure summary
                            input_context['job_review_summary'] = source_node.job_review_summary or "Previous implementation had quality issues"
                            
                            # Add the previous code for reference (first 50 lines)
                            if hasattr(source_node.function_block, 'code'):
                                code_lines = source_node.function_block.code.split('\n')
                                input_context['previous_code_snippet'] = '\n'.join(code_lines[:50])
                                if len(code_lines) > 50:
                                    input_context['previous_code_snippet'] += '\n... (truncated)'
                            
                            logger.info(f"Adding job review failure context from source node {source_node.id[:8]}")
                        
                        # Also add execution failure context if applicable
                        if source_node.state == NodeState.FAILED and source_node.error:
                            input_context['previous_execution_error'] = source_node.error[:500]
                            logger.info(f"Adding execution failure context from source node {source_node.id[:8]}")
                    
                    # Add previous nodes context for all nodes (including root)
                    # This allows any node to access files from previous nodes
                    from utils.node_file_access import NodeFileAccessor
                    accessor = NodeFileAccessor(tree, output_dir)
                    
                    # For the node we're about to create, we need a temporary ID
                    # to determine which nodes it can access
                    temp_node_id = spec.get('temp_id', 'temp_node')
                    
                    # Get accessible nodes (will be empty for true root, but include
                    # data loading root outputs for subsequent nodes)
                    previous_nodes_map = accessor.get_node_index_map(temp_node_id)
                    
                    if previous_nodes_map:
                        input_context['previous_nodes'] = {
                            'count': len(previous_nodes_map),
                            'nodes': previous_nodes_map,
                            'access_info': accessor.get_readable_node_list(temp_node_id),
                            'python_interface': (
                                "# You can access files from previous nodes in your function block code:\n"
                                "from function_block_runtime import previous_nodes\n"
                                "\n"
                                "# List all available previous nodes\n"
                                "nodes = previous_nodes.list()\n"
                                "\n"
                                "# Access files from previous nodes dynamically\n"
                                "# Find nodes with the files we need\n"
                                "for node in nodes:\n"
                                "    # Look for h5ad files in outputs\n"
                                "    h5ad_files = [f for f in node['files'] if f.startswith('outputs/') and f.endswith('.h5ad')]\n"
                                "    if h5ad_files:\n"
                                "        file_path = previous_nodes.get_file_path(node['index'], h5ad_files[0])\n"
                                "        if file_path:\n"
                                "            import scanpy as sc\n"
                                "            data = sc.read_h5ad(file_path)\n"
                                "            break\n"
                                "\n"
                                "# Find CSV files from any node\n"
                                "for node in nodes:\n"
                                "    csv_files = [f for f in node['files'] if f.endswith('.csv')]\n"
                                "    if csv_files:\n"
                                "        csv_path = previous_nodes.get_file_path(node['index'], csv_files[0])\n"
                                "        if csv_path:\n"
                                "            import pandas as pd\n"
                                "            df = pd.read_csv(csv_path)\n"
                                "            break"
                            )
                        }
                        
                        # Enrich with runtime information from execution metadata
                        runtime_structure = {}
                        for idx, node_data in previous_nodes_map.items():
                            node_id = node_data.get('node_id')
                            if node_id and tree and node_id in tree.nodes:
                                node = tree.nodes[node_id]
                                if node.output_data_id:
                                    node_dir = Path(node.output_data_id).parent
                                    metadata_file = node_dir / "execution_metadata.json"
                                    if metadata_file.exists():
                                        try:
                                            with open(metadata_file) as f:
                                                exec_meta = json.load(f)
                                            runtime_structure[idx] = {
                                                "outputs": [f["name"] for f in exec_meta.get("output_files", [])],
                                                "figures": [f["name"] for f in exec_meta.get("figure_files", [])],
                                                "actual_staged_structure": exec_meta.get("input_info", {}).get("previous_nodes_structure", {})
                                            }
                                        except FileNotFoundError:
                                            logger.debug(f"No execution metadata found for node {idx}")
                                            # This is okay - not all nodes produce metadata
                                        except json.JSONDecodeError as e:
                                            logger.warning(f"Malformed execution metadata for node {idx}: {e}")
                                            # Include partial info in runtime structure
                                            runtime_structure[idx] = {"error": "malformed_metadata"}
                                        except Exception as e:
                                            logger.error(f"Unexpected error reading metadata for node {idx}: {e}")
                                            runtime_structure[idx] = {"error": str(e)}
                        
                        if runtime_structure:
                            input_context['previous_nodes']['runtime_file_structure'] = runtime_structure
                    
                    if is_root:
                        # For root nodes, check what files are in the input directory
                        if input_path and input_path.exists():
                            input_dir = input_path.parent
                            # Get list of relevant files
                            relevant_extensions = ['.h5ad', '.rds', '.csv', '.txt', '.json']
                            input_context['available_files'] = [
                                f.name for f in input_dir.iterdir()
                                if f.is_file() and f.suffix in relevant_extensions
                            ]
                            input_context['original_input_name'] = input_path.name
                            # Add directory tree with configurable depth
                            input_context['directory_tree'] = self._get_directory_tree(input_dir, max_depth=self.directory_tree_max_depth)
                    else:
                        # For child nodes, indicate parent node info
                        input_context['parent_node_name'] = parent_node.function_block.name
                        input_context['parent_node_id'] = parent_node.id

                        # Add parent's output description
                        parent_output_desc = self._get_parent_output_description(parent_node)
                        if parent_output_desc:
                            input_context['parent_output_description'] = parent_output_desc

                        # Get parent's output files for reference
                        if parent_node.output_data_id:
                            parent_output_dir = Path(parent_node.output_data_id)
                            if parent_output_dir.exists():
                                parent_files = [
                                    f.name for f in parent_output_dir.iterdir()
                                    if f.is_file()
                                ]
                                # Don't call these "available_files" - that's misleading!
                                input_context['parent_output_files'] = parent_files

                                # Try to load parent's execution metadata for more detailed info
                                parent_node_dir = parent_output_dir.parent
                                parent_metadata_file = parent_node_dir / "execution_metadata.json"
                                if parent_metadata_file.exists():
                                    try:
                                        with open(parent_metadata_file) as f:
                                            parent_metadata = json.load(f)

                                        # Include detailed file information
                                        if parent_metadata.get("output_files"):
                                            input_context['parent_output_files_detail'] = parent_metadata["output_files"]

                                        # Include the actual runtime structure that was used
                                        if parent_metadata.get("input_info", {}).get("previous_nodes_structure"):
                                            input_context['parent_runtime_previous_nodes'] = parent_metadata["input_info"]["previous_nodes_structure"]
                                    except Exception as e:
                                        logger.warning(f"Failed to load parent execution metadata: {e}")

                                # Show expected directory structure after staging
                                input_context['expected_input_structure'] = (
                                    "input/\n"
                                    "└── previous_nodes/\n"
                                    "    └── node_1/\n"
                                    "        ├── outputs/\n"
                                )
                                for f in parent_files:
                                    input_context['expected_input_structure'] += f"        │   └── {f}\n"
                                input_context['expected_input_structure'] += (
                                    "        └── inputs/\n"
                                    "            └── (parent's input files if any)"
                                )

                        # Add parent data structure if available
                        parent_data_summary = self._get_parent_data_summary(parent_node, output_dir)
                        if parent_data_summary:
                            input_context['parent_data_structure'] = parent_data_summary

                        # Add original input directory tree for child nodes
                        # This helps child nodes understand the full input directory structure
                        if input_path and input_path.exists():
                            input_dir = input_path.parent
                            input_context['original_input_directory_tree'] = self._get_directory_tree(
                                input_dir,
                                max_depth=self.directory_tree_max_depth
                            )
                            input_context['original_input_path'] = str(input_dir)
                    
                    # Log function creator input if enabled
                    if self.log_llm_to_stdout:
                        logger.info("\n" + "="*80)
                        logger.info("FUNCTION CREATOR LLM INPUT:")
                        logger.info(f"Specification: {json.dumps(spec, indent=2)}")
                        logger.info(f"Input context: {json.dumps(input_context, indent=2)}")
                        logger.info("="*80 + "\n")
                    
                    # Create function block from specification with context
                    creation_result = self.function_creator.create_from_specification(spec, input_context)
                    
                    # Log function creator output if enabled
                    if self.log_llm_to_stdout and creation_result:
                        logger.info("\n" + "="*80)
                        logger.info("FUNCTION CREATOR LLM OUTPUT:")
                        logger.info(f"Name: {creation_result.name}")
                        logger.info(f"Description: {creation_result.description}")
                        logger.info(f"Language: {creation_result.type}")
                        logger.info("Code:")
                        logger.info(creation_result.code)
                        logger.info("="*80 + "\n")
                    
                    if creation_result:
                        if verbose:
                            logger.info(f"  Creating function block: {spec['name']}")
                        
                        # If we detected this is a rework, set the metadata on the function block
                        if is_rework and source_node:
                            # Use the attempt count from orchestrator if provided, otherwise calculate
                            if 'rework_attempts' in action:
                                rework_count = action['rework_attempts']
                            else:
                                rework_count = source_node.rework_attempts + 1
                            
                            # Store metadata on the function block object temporarily
                            # This will be read by TreeManager when creating the node
                            creation_result._rework_attempts = rework_count
                            creation_result._rework_of_node_id = source_node.id  # Track which node this is reworking
                            logger.info(f"Setting rework metadata on function block: attempt #{rework_count} of task '{source_node.function_block.name}' (reworking node {source_node.id[:8]})")
                        
                        # Add node to tree
                        if is_root:
                            node = self.tree_manager.add_root_node(creation_result)
                        else:
                            nodes = self.tree_manager.add_child_nodes(parent_node.id, [creation_result])
                            node = nodes[0] if nodes else None
                        
                        if node:
                            # If we detected this is a rework, log the metadata
                            if is_rework and source_node:
                                # The metadata was already set by tree_manager from the function block
                                logger.info(f"Node {node.function_block.name} is rework attempt #{node.rework_attempts} of task '{source_node.function_block.name}'")
                                
                                # Update node_info.json with rework metadata
                                node_dir = Path(self.current_output_dir) / tree.id / "nodes" / f"node_{node.id}"
                                if node_dir.exists():
                                    node_info_file = node_dir / "node_info.json"
                                    if node_info_file.exists():
                                        with open(node_info_file, 'r') as f:
                                            node_info = json.load(f)
                                        node_info['rework_attempts'] = rework_count
                                        with open(node_info_file, 'w') as f:
                                            json.dump(node_info, f, indent=2)
                                        logger.info(f"Updated node_info.json with rework metadata")
                                logger.info(f"Rework of node {source_node.id[:8]} (direct reference from orchestrator)")
                                
                                # Clear the needs_rework flag on the source node since we're addressing it
                                source_node.needs_rework = False
                                logger.info(f"Cleared needs_rework flag on source node {source_node.id[:8]}")
                                
                                # Propagate failure context from the source node
                                logger.info(f"Propagating failure context from node {source_node.id[:8]} to node {node.id[:8]}")
                                self._propagate_failure_context(tree, source_node.id, node, output_dir / tree.id)
                            
                            # Save LLM interaction details using function creator's enhanced logging
                            # Create node directory path for logging
                            tree_dir = output_dir / tree.id
                            node_dir = tree_dir / "nodes" / f"node_{node.id}"
                            
                            # Save the cached LLM interaction with correct node information
                            self.function_creator.save_cached_llm_interaction(
                                node_id=node.id,
                                node_dir=node_dir,
                                iteration=iteration
                            )
                            
                            # Save Code Checker reports if available
                            if hasattr(self.function_creator, 'code_checker') and self.function_creator.code_checker:
                                self.function_creator.code_checker.save_reports_to_directory(node_dir)
                            
                            self._log_function_creation_to_node(
                                node=node,
                                tree=tree,
                                output_dir=output_dir,
                                block=creation_result,
                                iteration=iteration,
                                block_index=0
                            )
                            
                            if verbose:
                                logger.info(f"Added node: {node.function_block.name}")
                            
                            # Execute the node immediately
                            success = self._execute_single_node(node, tree, input_path, output_dir, verbose)
                            
                            if success:
                                consecutive_no_attach = 0  # Reset counter on successful node creation
                            else:
                                logger.warning(f"Node {node.function_block.name} failed")
                    else:
                        logger.error(f"Failed to create function block: {spec['name']}")
        
        if iteration >= max_iterations:
            logger.warning(f"Reached maximum iterations limit: {max_iterations}")
    
    def _get_tree_state_for_orchestrator(self, tree: AnalysisTree) -> Dict[str, Any]:
        """Get tree state in format expected by orchestrator."""
        nodes_info = []
        
        # Get tree directory for failure context gathering
        tree_dir = Path(self.current_output_dir) / tree.id if hasattr(self, 'current_output_dir') else None
        
        for node_id, node in tree.nodes.items():
            node_info = {
                "id": node_id,
                "name": node.function_block.name,
                "state": node.state.value if hasattr(node.state, 'value') else node.state,
                "description": node.function_block.description,
                "parent_id": node.parent_id,
                "children": node.children,
                "debug_attempts": node.debug_attempts,
                "rework_attempts": getattr(node, 'rework_attempts', 0),  # Include for ALL nodes
                "has_successful_rework": getattr(node, 'has_successful_rework', False),  # Track if rework succeeded
                "rework_of_node_id": getattr(node, 'rework_of_node_id', None)  # Track what this is a rework of
            }
            
            # Include rework limit flag - single source of truth
            node_info["rework_limit_reached"] = getattr(node, 'rework_limit_reached', False)
            
            # Add message when limit is reached
            if node_info["rework_limit_reached"]:
                node_info["rework_limit_message"] = f"Already attempted {node.rework_attempts} times (limit: {MAX_REWORK_ATTEMPTS})"
            
            # Add error information for failed nodes
            if node.state == NodeState.FAILED and hasattr(node, 'error_message'):
                node_info["error"] = getattr(node, 'error_message', 'Unknown error')
            elif node.state == NodeState.FAILED and node.execution_result:
                node_info["error"] = node.execution_result.get('error', 'Unknown error')
            
            # Add comprehensive failure context for failed nodes
            if node.state == NodeState.FAILED and tree_dir:
                failure_context = self._gather_node_failure_context(node, tree_dir)
                if failure_context:
                    node_info["failure_context"] = failure_context
                    logger.debug(f"Added failure context to node {node_id} for orchestrator")
            
            # Add job review information - now separate from execution status
            if node.job_review_status:
                node_info["job_review_status"] = node.job_review_status
                node_info["needs_rework"] = node.needs_rework
                
                if node.job_review_summary:
                    node_info["job_review_summary"] = node.job_review_summary
                
                # For backward compatibility, also include job_review dict
                if node.job_review_result:
                    passed = node.job_review_status == JobReviewStatus.PASSED
                    node_info["job_review"] = {
                        "passed": passed,
                        "summary": node.job_review_summary or "",
                        "needs_rework": node.needs_rework,
                        "rework_attempts": node.rework_attempts
                    }
                    
                    # Add critical concerns if available
                    if isinstance(node.job_review_result, dict) and 'concerns' in node.job_review_result:
                        critical_concerns = [
                            {
                                "type": concern.get('type', 'Unknown'),
                                "description": concern.get('description', '')
                            }
                            for concern in node.job_review_result.get('concerns', [])
                            if concern.get('severity') == "critical"
                        ]
                        if critical_concerns:
                            node_info["job_review"]["critical_concerns"] = critical_concerns
            
            # Add output file information for completed nodes
            if node.state == NodeState.COMPLETED and node.output_data_id:
                output_dir = Path(node.output_data_id)
                if output_dir.exists():
                    output_files = [f.name for f in output_dir.iterdir() if f.is_file()]
                    node_info["output_files"] = output_files
                
                # Try to load execution metadata for more detailed information
                node_base_dir = output_dir.parent  # Go up from outputs to node dir
                metadata_file = node_base_dir / "execution_metadata.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file) as f:
                            exec_metadata = json.load(f)
                        # Add runtime directory structure information
                        node_info["runtime_structure"] = {
                            "output_files_detail": exec_metadata.get("output_files", []),
                            "figure_files": exec_metadata.get("figure_files", []),
                            "accessible_nodes": exec_metadata.get("accessible_nodes", {}),
                            "input_structure": exec_metadata.get("input_info", {})
                        }
                    except Exception as e:
                        logger.warning(f"Failed to load execution metadata for node {node_id}: {e}")
            
            # Add job review information if available
            if hasattr(self, 'orchestrator') and hasattr(self.orchestrator, 'node_results'):
                node_result = self.orchestrator.node_results.get(node_id, {})
                if 'job_review' in node_result:
                    job_review = node_result['job_review']
                    # Validate contract - 'passed' key must exist (from JobReviewResult.to_dict())
                    if 'passed' not in job_review:
                        logger.error(f"Node {node_id} has job_review in orchestrator results but missing 'passed' key. This indicates a bug in job review creation. Skipping.")
                    else:
                        node_info["job_review"] = {
                            "passed": job_review['passed'],  # No default - must exist per contract
                            "needs_rework": node_result.get('needs_rework', False),
                            "summary": job_review.get('summary', ''),
                            "concerns": job_review.get('concerns', []),
                            "critical_concerns": [c for c in job_review.get('concerns', []) if c.get('severity') == 'critical']
                        }
                
            nodes_info.append(node_info)
        
        return {
            "total_nodes": tree.total_nodes,
            "completed_nodes": tree.completed_nodes,
            "failed_nodes": tree.failed_nodes,
            "nodes": nodes_info,
            "constraints": {
                "max_nodes": tree.max_nodes,
                "max_children_per_node": tree.max_children_per_node
            },
            "planning_metadata": {
                # Use actual node states since tree.completed_nodes has a bug
                "has_successful_nodes": any(node.state == NodeState.COMPLETED for node in tree.nodes.values()),
                "all_nodes_failed": all(node.state == NodeState.FAILED for node in tree.nodes.values()) and tree.total_nodes > 0,
                "can_attach_new_nodes": any(node.state == NodeState.COMPLETED for node in tree.nodes.values()) or tree.total_nodes == 0
            }
        }
    
    def _collect_job_review_statistics(self, tree: AnalysisTree) -> Dict[str, Any]:
        """Collect statistics about job review results across all nodes.
        
        Args:
            tree: The analysis tree to collect statistics from
            
        Returns:
            Dictionary containing job review statistics
        """
        stats = {
            'passed': 0,
            'failed': 0,
            'not_reviewed': 0,
            'skipped': 0,
            'needs_rework': 0,
            'total_rework_attempts': 0,
            'executed_and_passed': 0,
            'executed_and_failed_review': 0,
            'execution_failed': 0
        }
        
        for node in tree.nodes.values():
            # Count job review statuses
            if node.job_review_status:
                status_value = node.job_review_status.value if hasattr(node.job_review_status, 'value') else str(node.job_review_status)
                
                if status_value == "passed":
                    stats['passed'] += 1
                elif status_value == "failed":
                    stats['failed'] += 1
                elif status_value == "not_reviewed":
                    stats['not_reviewed'] += 1
                elif status_value == "skipped":
                    stats['skipped'] += 1
            else:
                # If no job review status, count as not reviewed
                stats['not_reviewed'] += 1
            
            # Count needs_rework nodes
            if hasattr(node, 'needs_rework') and node.needs_rework:
                stats['needs_rework'] += 1
            
            # Sum total rework attempts
            if hasattr(node, 'rework_attempts'):
                stats['total_rework_attempts'] += node.rework_attempts
            
            # Track execution vs review combinations
            node_state = node.state.value if hasattr(node.state, 'value') else str(node.state)
            
            if node_state == "completed":
                if node.job_review_status:
                    status_value = node.job_review_status.value if hasattr(node.job_review_status, 'value') else str(node.job_review_status)
                    if status_value == "passed":
                        stats['executed_and_passed'] += 1
                    elif status_value == "failed":
                        stats['executed_and_failed_review'] += 1
            elif node_state == "failed":
                stats['execution_failed'] += 1
        
        return stats
    
    def _execute_single_node(
        self,
        node: AnalysisNode,
        tree: AnalysisTree,
        input_path: Path,
        output_dir: Path,
        verbose: bool
    ) -> bool:
        """Execute a single node and return success status.
        
        Args:
            node: Node to execute
            tree: Analysis tree
            input_path: Input data path for root, or parent output for children
            output_dir: Base output directory
            verbose: Whether to log details
            
        Returns:
            True if node executed successfully, False otherwise
        """
        try:
            # Determine input for this node
            if node.parent_id:
                parent = tree.nodes.get(node.parent_id)
                if parent and parent.output_data_id:
                    node_input = Path(parent.output_data_id)
                else:
                    logger.error(f"Parent node {node.parent_id} has no output")
                    return False
            else:
                node_input = input_path
            
            # Execute the node
            if verbose:
                logger.info(f"Executing node: {node.function_block.name}")
            
            state, output_path, execution_result = self.node_executor.execute_node(
                node=node,
                tree=tree,
                input_path=node_input,
                output_base_dir=output_dir,
                max_debug_attempts=tree.max_debug_trials
            )
            
            # Update tree state
            self.tree_manager.update_node_state(node.id, state, output_data_id=output_path)
            
            # Log tree statistics after node execution
            logger.info(f"After executing {node.function_block.name}:")
            logger.info(f"  Node state: {state.value if hasattr(state, 'value') else state}")
            logger.info(f"  Tree statistics: total={tree.total_nodes}, completed={tree.completed_nodes}, failed={tree.failed_nodes}")
            
            # Handle success
            if state == NodeState.COMPLETED:
                if verbose:
                    logger.info(f"  ✓ Node completed successfully: {node.function_block.name}")
                
                # IMPORTANT: If this is a rework node that succeeded, mark the original node
                # This prevents creating duplicate reworks
                if hasattr(node, 'rework_of_node_id') and node.rework_of_node_id:
                    original_node_id = node.rework_of_node_id
                    if original_node_id in tree.nodes:
                        original_node = tree.nodes[original_node_id]
                        # Mark that this node has been successfully reworked
                        original_node.has_successful_rework = True
                        logger.info(f"Marked original node {original_node_id[:8]} as having successful rework")
                
                # Apply job review if enabled and execution result is available
                if self.job_reviewer and execution_result:
                    self._apply_job_review(node, tree, execution_result, output_path)
                
                return True
            
            # Handle failure
            if state == NodeState.FAILED:
                logger.error(f"  ✗ Node failed: {node.function_block.name}")
                # Bug fixing happens inside InteractiveNodeExecutor
                # No external fixing attempts needed
                logger.info(f"Node failed but interactive debugging already attempted fixes")
                return False
            
            # Pending or other states
            return False
            
        except Exception as e:
            logger.error(f"Error executing node {node.function_block.name}: {e}")
            self.tree_manager.update_node_state(node.id, NodeState.FAILED, error=str(e))
            return False
    
    def _get_tree_state(self, tree: AnalysisTree) -> Dict[str, Any]:
        """Get current state of the analysis tree."""
        return {
            "total_nodes": tree.total_nodes,
            "completed_nodes": tree.completed_nodes,
            "failed_nodes": tree.failed_nodes,
            "nodes": [
                {
                    "id": node.id,
                    "name": node.function_block.name,
                    "state": node.state.value,
                    "level": node.level,
                    "parent_id": node.parent_id,
                    "children": node.children
                }
                for node in tree.nodes.values()
            ]
        }
    
    def _process_recommendations(
        self,
        recommendations: Dict[str, Any],
        tree: AnalysisTree,
        orchestrator_dir: Path,
        output_dir: Path = None,
        parent_node_id: str = None
    ) -> List[Union[NewFunctionBlock, ExistingFunctionBlock]]:
        """Process orchestrator recommendations to create/select function blocks."""
        function_blocks = []
        
        # Get recommended actions
        actions = recommendations.get("next_actions", [])
        
        # Get parent node's data structure if available
        parent_context = None
        if parent_node_id and output_dir:
            parent_node = tree.nodes.get(parent_node_id)
            if parent_node and parent_node.output_data_id:
                # Try to read parent's data structure
                parent_output_dir = Path(parent_node.output_data_id).parent
                data_structure_file = parent_output_dir / "_data_structure.json"
                if data_structure_file.exists():
                    try:
                        with open(data_structure_file, 'r') as f:
                            parent_context = json.load(f)
                    except Exception as e:
                        logger.debug(f"Could not read parent data structure: {e}")
        
        for action in actions:
            if action["type"] == "create_new":
                # Use function creator to generate new block
                if self.function_creator:
                    # Add parent context to specification
                    if parent_context:
                        action["specification"]["parent_output_structure"] = parent_context
                    
                    # Add user request for better context
                    if hasattr(tree, 'user_request'):
                        action["specification"]["user_request"] = tree.user_request
                    
                    block = self.function_creator.create_function_block(
                        action["specification"]
                    )
                    if block:
                        function_blocks.append(block)
            
            elif action["type"] == "use_existing":
                # For now, we don't have existing blocks - log warning
                logger.warning(f"Existing block requested but not implemented: {action.get('name', 'unknown')}")
        
        return function_blocks
    
    def _get_parent_data_summary(self, parent_node: AnalysisNode, output_dir: Path) -> Dict[str, Any]:
        """Get data summary from parent node's output."""
        if not parent_node.output_data_id:
            return {}
        
        try:
            # Try to read data structure file
            parent_output_dir = Path(parent_node.output_data_id).parent
            data_structure_file = parent_output_dir / "_data_structure.json"
            
            if data_structure_file.exists():
                with open(data_structure_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"Could not read parent data structure: {e}")
        
        return {}
    
    def _get_directory_tree(self, directory: Path, max_depth: int = 3, current_depth: int = 0) -> str:
        """Get a tree representation of directory structure."""
        if not directory.exists() or current_depth >= max_depth:
            return ""
        
        lines = []
        prefix = "  " * current_depth
        
        try:
            for item in sorted(directory.iterdir()):
                if item.name.startswith('.'):
                    continue
                    
                if item.is_file():
                    size = item.stat().st_size
                    size_str = self._format_file_size(size)
                    lines.append(f"{prefix}├── {item.name} ({size_str})")
                elif item.is_dir() and current_depth < max_depth - 1:
                    lines.append(f"{prefix}├── {item.name}/")
                    subtree = self._get_directory_tree(item, max_depth, current_depth + 1)
                    if subtree:
                        lines.append(subtree)
        except PermissionError:
            lines.append(f"{prefix}├── [Permission Denied]")
            
        return "\n".join(lines)
    
    def _format_file_size(self, size: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f}{unit}"
            size /= 1024.0
        return f"{size:.1f}TB"
    
    def _get_parent_output_description(self, parent_node: AnalysisNode) -> Optional[str]:
        """Get output description from parent node."""
        if not parent_node:
            return None
            
        # First check if it's stored in the function block
        if hasattr(parent_node.function_block, 'output_description'):
            return parent_node.function_block.output_description
            
        # Then check node metadata
        if hasattr(parent_node, 'metadata') and parent_node.metadata:
            return parent_node.metadata.get('output_description')
            
        # Finally check node_info.json file
        try:
            if not parent_node.output_data_id:
                logger.debug(f"Parent node {parent_node.id} has no output_data_id")
                return None
                
            tree_dir = Path(parent_node.output_data_id).parent.parent.parent
            node_info_file = tree_dir / "nodes" / f"node_{parent_node.id}" / "node_info.json"
            
            if not node_info_file.exists():
                logger.debug(f"No node_info.json for parent {parent_node.id}")
                return None
                
            with open(node_info_file, 'r') as f:
                node_info = json.load(f)
                return node_info.get('output_description')
                
        except json.JSONDecodeError as e:
            logger.warning(f"Malformed node_info.json for parent {parent_node.id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error reading parent output description: {e}")
            
        return None
    
    def _collect_bug_fix_history(self, node_dir: Path) -> List[Dict[str, Any]]:
        """Collect history of previous bug fix attempts for this node.
        
        Args:
            node_dir: Path to the node directory
            
        Returns:
            List of previous attempt information
        """
        history = []
        bug_fixes_dir = node_dir / "agent_tasks" / "bug_fixer" / "bug_fixes"
        
        if not bug_fixes_dir.exists():
            return history
            
        try:
            # Get all fix attempt files sorted by timestamp
            fix_files = sorted(bug_fixes_dir.glob("fix_attempt_*.json"))
            
            for fix_file in fix_files:
                with open(fix_file, 'r') as f:
                    attempt_data = json.load(f)
                    
                # Extract relevant information for history context
                history_entry = {
                    "attempt_number": attempt_data.get("attempt_number", 0),
                    "timestamp": attempt_data.get("timestamp", ""),
                    "error_info": attempt_data.get("error_info", {}),
                    "llm_analysis": attempt_data.get("llm_output", {}).get("analysis", {}),
                    "changes_made": attempt_data.get("llm_output", {}).get("changes_made", []),
                    "requirements_changes": attempt_data.get("llm_output", {}).get("requirements_changes", []),
                    "success": attempt_data.get("success", False),
                    "error": attempt_data.get("error"),
                    "fixed_code_snippet": self._extract_code_snippet(
                        attempt_data.get("fixed_code", ""),
                        attempt_data.get("llm_output", {}).get("analysis", {})
                    )
                }
                history.append(history_entry)
                
        except Exception as e:
            logger.warning(f"Error collecting bug fix history: {e}")
            
        return history
    
    def _extract_code_snippet(self, fixed_code: str, analysis: Dict[str, Any]) -> str:
        """Extract the most relevant part of the fix for context.
        
        Args:
            fixed_code: The full fixed code
            analysis: The LLM's analysis of the fix
            
        Returns:
            A snippet showing the key changes
        """
        # For now, just return the analysis summary
        # In future, could do more sophisticated extraction
        if analysis:
            return f"Root cause: {analysis.get('root_cause', 'Unknown')}, Strategy: {analysis.get('fix_strategy', 'Unknown')}"
        return "No analysis available"
    
    def _save_function_block_to_dir(self, block: Any, function_block_dir: Path):
        """Save function block code, config, and requirements to directory."""
        
        # Save code.py
        if hasattr(block, 'code'):
            code_file = function_block_dir / "code.py"
            with open(code_file, 'w') as f:
                f.write(block.code)
        
        # Save requirements.txt
        if hasattr(block, 'requirements'):
            req_file = function_block_dir / "requirements.txt"
            with open(req_file, 'w') as f:
                f.write(block.requirements)
        
        # Save config.json
        config_data = {
            "name": block.name,
            "type": block.type.value if hasattr(block.type, 'value') else str(block.type),
            "description": block.description,
            "parameters": block.parameters if hasattr(block, 'parameters') else {},
            "static_config": block.static_config.model_dump() if hasattr(block, 'static_config') and hasattr(block.static_config, 'model_dump') else {}
        }
        
        config_file = function_block_dir / "config.json"
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2, default=str)
    
    def _log_function_creation_to_node(
        self,
        node: AnalysisNode,
        tree: AnalysisTree,
        output_dir: Path,
        block: Any,
        iteration: int,
        block_index: int
    ):
        """Log function creation details to the node's agent_tasks folder and save function_block."""
        try:
            # Create node directory structure
            tree_dir = output_dir / tree.id
            nodes_dir = tree_dir / "nodes"
            node_dir = nodes_dir / f"node_{node.id}"
            
            # Create all required subdirectories
            agent_tasks_dir = node_dir / "agent_tasks" / "function_creator"
            agent_tasks_dir.mkdir(parents=True, exist_ok=True)
            
            function_block_dir = node_dir / "function_block"
            function_block_dir.mkdir(parents=True, exist_ok=True)
            
            # Create other required directories
            jobs_dir = node_dir / "jobs"
            jobs_dir.mkdir(parents=True, exist_ok=True)
            
            outputs_dir = node_dir / "outputs"
            outputs_dir.mkdir(parents=True, exist_ok=True)
            
            # Save function block code, config, and requirements
            self._save_function_block_to_dir(block, function_block_dir)
            
            # Create initial node_info.json
            from datetime import datetime
            node_info = {
                "id": node.id,
                "name": node.function_block.name,
                "type": node.function_block.type.value if hasattr(node.function_block.type, 'value') else str(node.function_block.type),
                "parent_id": node.parent_id,
                "children_ids": node.children if hasattr(node, 'children') else [],
                "state": node.state.value if hasattr(node.state, 'value') else str(node.state),
                "job_review_status": getattr(node, 'job_review_status', None),
                "needs_rework": getattr(node, 'needs_rework', False),
                "job_review_summary": getattr(node, 'job_review_summary', None),
                "created_at": datetime.now().isoformat(),
                "last_execution": node.updated_at.isoformat() if hasattr(node, 'updated_at') and node.updated_at else None,
                "execution_count": 1,
                "level": node.level,
                "debug_attempts": node.debug_attempts,
                "rework_attempts": getattr(node, 'rework_attempts', 0),
                "rework_limit_reached": getattr(node, 'rework_limit_reached', False),
                "rework_of_node_id": getattr(node, 'rework_of_node_id', None),
                "output_description": getattr(block, 'output_description', None)
            }
            node_info_file = node_dir / "node_info.json"
            with open(node_info_file, 'w') as f:
                json.dump(node_info, f, indent=2)
            
            # Create log entry
            timestamp = datetime.now()
            log_data = {
                "task_id": f"create_{iteration:02d}_{block_index:02d}",
                "task_type": "function_creation",
                "agent": "function_creator",
                "timestamp": timestamp.isoformat(),
                "node_id": node.id,
                "orchestrator_iteration": iteration,  # This is the planning iteration, not a version
                "function_block_version": 1,  # Function creator always creates version 1
                "function_block": {
                    "name": block.name,
                    "type": block.type.value if hasattr(block.type, 'value') else str(block.type),
                    "description": block.description,
                    "parameters": block.parameters if hasattr(block, 'parameters') else {}
                },
                "metadata": {
                    "tree_id": tree.id,
                    "user_request": tree.user_request[:200] if hasattr(tree, 'user_request') else ""
                }
            }
            
            # Save log file
            log_file = agent_tasks_dir / f"creation_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
            with open(log_file, 'w') as f:
                json.dump(log_data, f, indent=2, default=str)
            
            # Save code version - function creator always creates version 1
            if hasattr(block, 'code'):
                code_dir = agent_tasks_dir / "code_versions"
                code_dir.mkdir(exist_ok=True)
                # Function creator ALWAYS creates version 1, subsequent versions are from bug fixer
                code_file = code_dir / f"v1_{block_index:02d}_{timestamp.strftime('%Y%m%d_%H%M%S')}.py"
                with open(code_file, 'w') as f:
                    f.write(block.code)
            
            logger.debug(f"Logged function creation to {log_file}")
            
        except Exception as e:
            logger.warning(f"Failed to log function creation: {e}")
    
    def _create_analysis_summary_md(self, tree: AnalysisTree, output_path: Path, results: Dict[str, Any]) -> None:
        """Create a markdown summary of the analysis including all nodes and their states."""
        try:
            lines = []
            lines.append("# Analysis Summary\n")
            lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            lines.append(f"**Tree ID:** {tree.id}\n")
            lines.append(f"**User Request:** {tree.user_request}\n")
            
            # Overall statistics
            lines.append("\n## Statistics\n")
            lines.append(f"- **Total Nodes:** {tree.total_nodes}\n")
            lines.append(f"- **Completed:** {tree.completed_nodes} ✅\n")
            lines.append(f"- **Failed:** {tree.failed_nodes} ❌\n")
            lines.append(f"- **Pending:** {tree.total_nodes - tree.completed_nodes - tree.failed_nodes} ⏳\n")
            
            # Node details
            lines.append("\n## Node Details\n")
            
            # Group nodes by state
            completed_nodes = []
            failed_nodes = []
            pending_nodes = []
            
            for node_id, node in tree.nodes.items():
                node_info = {
                    'id': node_id,
                    'name': node.function_block.name,
                    'level': node.level,
                    'parent_id': node.parent_id
                }
                
                if node.state == NodeState.COMPLETED:
                    completed_nodes.append(node_info)
                elif node.state == NodeState.FAILED:
                    # Add error info
                    if hasattr(node, 'error_message'):
                        node_info['error'] = node.error_message
                    elif node.execution_result and 'error' in node.execution_result:
                        node_info['error'] = node.execution_result['error']
                    failed_nodes.append(node_info)
                else:
                    pending_nodes.append(node_info)
            
            # Show completed nodes
            if completed_nodes:
                lines.append("\n### ✅ Completed Nodes\n")
                for node in sorted(completed_nodes, key=lambda x: x['level']):
                    indent = "  " * node['level']
                    lines.append(f"{indent}- **{node['name']}** (node_{node['id'][:8]}...)\n")
            
            # Show failed nodes with errors
            if failed_nodes:
                lines.append("\n### ❌ Failed Nodes\n")
                for node in sorted(failed_nodes, key=lambda x: x['level']):
                    indent = "  " * node['level']
                    lines.append(f"{indent}- **{node['name']}** (node_{node['id'][:8]}...)\n")
                    if 'error' in node:
                        lines.append(f"{indent}  - Error: `{node['error'][:200]}{'...' if len(node.get('error', '')) > 200 else ''}`\n")
            
            # Show pending nodes
            if pending_nodes:
                lines.append("\n### ⏳ Pending Nodes\n")
                for node in sorted(pending_nodes, key=lambda x: x['level']):
                    indent = "  " * node['level']
                    lines.append(f"{indent}- **{node['name']}** (node_{node['id'][:8]}...)\n")
            
            # Add output information
            if results:
                lines.append("\n## Outputs\n")
                output_count = sum(1 for r in results.values() if r.get('success'))
                lines.append(f"- **Successful outputs:** {output_count}\n")
                
                if output_count > 0:
                    lines.append("\n### Output Files\n")
                    for node_id, result in results.items():
                        if result.get('success') and result.get('output_path'):
                            node_name = tree.nodes[node_id].function_block.name if node_id in tree.nodes else "Unknown"
                            lines.append(f"- {node_name}: `{result['output_path']}`\n")
            
            # Write file
            with open(output_path, 'w') as f:
                f.writelines(lines)
                
            logger.debug(f"Created analysis summary at {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to create analysis summary: {e}")
    
    def _find_parent_for_block(
        self,
        tree: AnalysisTree,
        block: Union[NewFunctionBlock, ExistingFunctionBlock],
        recommendations: Dict[str, Any]
    ) -> Optional[str]:
        """Find appropriate parent node for a new block."""
        # Check if recommendations specify a parent
        parent_hint = recommendations.get("parent_node_id")
        if parent_hint and parent_hint in tree.nodes:
            return parent_hint
        
        # Otherwise, find a leaf node (node with no children)
        for node_id, node in tree.nodes.items():
            if len(node.children) == 0 and node.state == NodeState.COMPLETED:
                return node_id
        
        # If no completed leaf nodes, return any leaf node
        for node_id, node in tree.nodes.items():
            if len(node.children) == 0:
                return node_id
        
        return None
    
    def _execute_pending_nodes(
        self,
        tree: AnalysisTree,
        input_path: Path,
        output_dir: Path,
        verbose: bool
    ):
        """Execute nodes that are in pending state."""
        for node_id, node in tree.nodes.items():
            if node.state == NodeState.PENDING:
                # Determine input for this node
                if node.parent_id:
                    parent = tree.nodes.get(node.parent_id)
                    if parent and parent.output_data_id:
                        node_input = Path(parent.output_data_id)
                    else:
                        continue  # Parent not ready
                else:
                    node_input = input_path
                
                # Execute node
                if verbose:
                    logger.info(f"Executing node: {node.function_block.name}")
                
                state, output_path, execution_result = self.node_executor.execute_node(
                    node=node,
                    tree=tree,
                    input_path=node_input,
                    output_base_dir=output_dir,
                    max_debug_attempts=tree.max_debug_trials
                )
                
                # Update tree state
                self.tree_manager.update_node_state(node_id, state, output_data_id=output_path)
                
                # Apply job review for completed nodes
                if state == NodeState.COMPLETED and self.job_reviewer and execution_result:
                    logger.info(f"Reviewing completed function block for node {node_id}")
                    self._apply_job_review(node, tree, execution_result, output_path)

                # Bug fixing happens inside InteractiveNodeExecutor
                # No external fixing attempts needed
                if state == NodeState.FAILED:
                    logger.info(f"Node {node.function_block.name} failed but interactive debugging already attempted fixes")
    
    def _attempt_fix(
        self,
        node: AnalysisNode,
        tree: AnalysisTree,
        input_path: Path,
        output_dir: Path,
        verbose: bool
    ):
        """Attempt to fix a failed node using bug fixer agent.

        Note: This method is deprecated and should not be called.
        Bug fixing now happens inside InteractiveNodeExecutor during node execution.
        Kept for backward compatibility only.
        """
        # This method should not be called - interactive debugging is always enabled
        from analysis_tree_management.interactive_node_executor import InteractiveNodeExecutor
        if isinstance(self.node_executor, InteractiveNodeExecutor):
            logger.warning("_attempt_fix called but interactive debugging is always enabled. "
                         "Bug fixing should happen in InteractiveNodeExecutor.")
            return
        
        # Determine node directory for logging
        tree_dir = output_dir / tree.id
        nodes_dir = tree_dir / "nodes"
        node_dir = nodes_dir / f"node_{node.id}"
        
        for attempt in range(tree.max_debug_trials):
            if verbose:
                logger.info(f"Attempting fix for {node.function_block.name} (attempt {attempt + 1})")
            
            # Try to read actual error logs from the last job
            stdout_content = ""
            stderr_content = ""
            
            # Find the most recent job directory
            jobs_dir = node_dir / "jobs"
            if jobs_dir.exists():
                job_dirs = sorted([d for d in jobs_dir.iterdir() if d.is_dir()], 
                                key=lambda x: x.name, reverse=True)
                if job_dirs:
                    latest_job = job_dirs[0]
                    # Try to read stdout/stderr from the job logs
                    logs_dir = latest_job / "logs"
                    if logs_dir.exists():
                        stdout_file = logs_dir / "stdout.txt"
                        stderr_file = logs_dir / "stderr.txt"
                        
                        if stdout_file.exists():
                            with open(stdout_file, 'r') as f:
                                stdout_content = f.read()
                                # If stdout is too long, get the tail with traceback
                                if len(stdout_content) > 10000:
                                    lines = stdout_content.split('\n')
                                    # Try to find where the error starts
                                    error_start = -1
                                    for i in range(len(lines) - 1, -1, -1):
                                        if 'Traceback (most recent call last):' in lines[i]:
                                            error_start = i
                                            break
                                    
                                    if error_start >= 0:
                                        # Include from traceback to end
                                        stdout_content = '\n'.join(lines[error_start:])
                                    else:
                                        # Just get last 200 lines if no traceback found
                                        stdout_content = '\n'.join(lines[-200:])
                                        stdout_content = f"[... stdout truncated, showing last 200 lines ...]\n{stdout_content}"
                                        
                        if stderr_file.exists():
                            with open(stderr_file, 'r') as f:
                                stderr_content = f.read()
                                # If stderr is too long, get the tail
                                if len(stderr_content) > 5000:
                                    lines = stderr_content.split('\n')
                                    stderr_content = '\n'.join(lines[-100:])
                                    stderr_content = f"[... stderr truncated, showing last 100 lines ...]\n{stderr_content}"
            
            # Get parent node's data structure if available
            parent_data_structure = None
            if node.parent_id:
                parent_node = tree.nodes.get(node.parent_id)
                if parent_node and parent_node.output_data_id:
                    # Try to read parent's data structure
                    parent_output_dir = Path(parent_node.output_data_id).parent
                    data_structure_file = parent_output_dir / "_data_structure.json"
                    if data_structure_file.exists():
                        try:
                            with open(data_structure_file, 'r') as f:
                                parent_data_structure = json.load(f)
                        except Exception as e:
                            logger.debug(f"Could not read parent data structure: {e}")
            
            # Collect previous bug fix attempts history
            previous_attempts = self._collect_bug_fix_history(node_dir)
            
            # Get error details with actual logs
            error_info = {
                "node_id": node.id,
                "error": node.error,
                "function_block": node.function_block,
                "node_dir": node_dir,  # Add node_dir for logging
                "input_data_path": str(input_path),  # Add input data path for Claude workspace
                "error_message": str(node.error) if node.error else "Unknown error",
                "stdout": stdout_content,
                "stderr": stderr_content,
                "parent_data_structure": parent_data_structure,  # Add parent context
                "previous_attempts": previous_attempts  # Add history
            }
            
            # Use bug fixer to generate fix
            if self.bug_fixer_type in ["unified", "claude_code_sdk"]:
                # SDK bug fixer is async and has different interface
                import asyncio
                
                # Only import claude_code_sdk_bug_fixer if actually using it
                if self.bug_fixer_type == "claude_code_sdk":
                    from .claude_code_sdk_bug_fixer import ClaudeCodeSDKBugFixer
                
                # Both unified and SDK bug fixers use async interface
                if hasattr(self.bug_fixer, 'fix_bug'):
                    # Get the workspace directory (where function_block.py is)
                    function_block_dir = node_dir / "function_block"
                    
                    # Prepare error message
                    error_message = f"{node.error}\n\nSTDOUT:\n{stdout_content}\n\nSTDERR:\n{stderr_content}"
                    
                    # Run fix_bug method (async for SDK, sync for unified)
                    if asyncio.iscoroutinefunction(self.bug_fixer.fix_bug):
                        # Async method (SDK)
                        fix_result = asyncio.run(self.bug_fixer.fix_bug(
                            node_name=node.function_block.name,
                            error_message=error_message,
                            working_directory=function_block_dir,
                            attempt_number=attempt + 1,
                            node_description=node.function_block.description
                        ))
                    else:
                        # Sync method (unified)
                        fix_result = self.bug_fixer.fix_bug(
                            node_name=node.function_block.name,
                            error_message=error_message,
                            working_directory=function_block_dir,
                            attempt_number=attempt + 1,
                            node_description=node.function_block.description
                        )
                    
                    # Log SDK session
                    sdk_log_dir = node_dir / "agent_tasks" / "claude_code_sdk" / f"attempt_{attempt + 1}"
                    sdk_log_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Save debug history if available
                    if hasattr(self.bug_fixer, 'save_debug_history'):
                        asyncio.run(self.bug_fixer.save_debug_history(
                            sdk_log_dir / "debug_history.json"
                        ))
                    
                    # Log session info
                    if verbose:
                        if hasattr(self.bug_fixer, 'get_statistics'):
                            # Unified bug fixer
                            stats = self.bug_fixer.get_statistics()
                            logger.info(f"Unified bug fixer ({self.bug_fixer.model_name}): "
                                      f"{fix_result.get('turn_count', 0)} turns, "
                                      f"cost: ${fix_result.get('cost', 0):.4f}")
                        elif hasattr(self.bug_fixer, 'get_stats'):
                            # SDK bug fixer
                            stats = self.bug_fixer.get_stats()
                            logger.info(f"Claude Code SDK: {fix_result.get('message_count', 0)} messages, "
                                      f"cost: ${fix_result.get('total_cost', 0):.4f}")
                else:
                    fix_result = None
            else:
                # Standard bug fixers (OpenAI and Claude LLM)
                fix_result = self.bug_fixer.fix_error(error_info)
                
                # Log Claude-specific information if available
                if fix_result and 'claude_report' in fix_result:
                    claude_report = fix_result['claude_report']
                    # Save Claude report to node directory
                    claude_log_dir = node_dir / "claude_debugging"
                    claude_log_dir.mkdir(exist_ok=True)
                    claude_log_file = claude_log_dir / f"attempt_{attempt + 1}_report.json"
                    with open(claude_log_file, 'w') as f:
                        json.dump(claude_report, f, indent=2)
                    if verbose:
                        logger.info(f"Claude debugging: {claude_report.get('iterations', 0)} turns, "
                                  f"cost: ${claude_report.get('total_cost', 0):.4f}")
            
            if fix_result and fix_result.get('success'):
                if self.bug_fixer_type in ["unified", "claude_code_sdk"]:
                    # SDK modifies files directly, just re-read the updated code
                    # Try both possible filenames
                    code_path = node_dir / "function_block" / "code.py"
                    function_block_path = node_dir / "function_block" / "function_block.py"
                    
                    if code_path.exists():
                        with open(code_path, 'r') as f:
                            node.function_block.code = f.read()
                        if verbose:
                            logger.info(f"Loaded fixed code from {code_path}")
                    elif function_block_path.exists():
                        with open(function_block_path, 'r') as f:
                            node.function_block.code = f.read()
                        if verbose:
                            logger.info(f"Loaded fixed code from {function_block_path}")
                    else:
                        logger.warning(f"Fixed code file not found in {node_dir / 'function_block'}")
                    
                    # Also check for updated requirements
                    requirements_path = node_dir / "function_block" / "requirements.txt"
                    if requirements_path.exists():
                        with open(requirements_path, 'r') as f:
                            node.function_block.requirements = f.read()
                elif fix_result.get('fixed_code'):
                    # Standard bug fixers return code directly
                    node.function_block.code = fix_result['fixed_code']
                    if fix_result.get('fixed_requirements'):
                        node.function_block.requirements = fix_result['fixed_requirements']
                
                # Retry execution with fixed code
                if verbose:
                    logger.info(f"Retrying execution of {node.function_block.name} with fixed code")
                
                state, output_path, execution_result = self.node_executor.execute_node(
                    node=node,
                    tree=tree,
                    input_path=input_path,
                    output_base_dir=output_dir,
                    max_debug_attempts=tree.max_debug_trials
                )
                
                self.tree_manager.update_node_state(node.id, state, output_data_id=output_path)
                
                if state == NodeState.COMPLETED:
                    if verbose:
                        logger.info(f"Successfully fixed {node.function_block.name}")
                    
                    # Apply job review to the fixed node
                    if self.job_reviewer and execution_result:
                        logger.info(f"Reviewing fixed function block for node {node.id}")
                        self._apply_job_review(node, tree, execution_result, output_path)
                    
                    break
    
    def _execute_tree(
        self,
        tree: AnalysisTree,
        input_path: Path,
        output_dir: Path,
        verbose: bool
    ) -> Dict[str, Any]:
        """Execute all nodes in the analysis tree."""
        results = {}
        
        # Execute nodes level by level
        max_level = max((node.level for node in tree.nodes.values()), default=0)
        
        for level in range(max_level + 1):
            level_nodes = [
                (node_id, node) 
                for node_id, node in tree.nodes.items() 
                if node.level == level
            ]
            
            for node_id, node in level_nodes:
                if node.state != NodeState.PENDING:
                    continue
                
                # Determine input
                if node.parent_id:
                    parent = tree.nodes.get(node.parent_id)
                    if parent and parent.output_data_id:
                        node_input = Path(parent.output_data_id)
                    else:
                        continue
                else:
                    node_input = input_path
                
                # Execute
                if verbose:
                    logger.info(f"Executing: {node.function_block.name}")
                
                state, output_path, execution_result = self.node_executor.execute_node(
                    node=node,
                    tree=tree,
                    input_path=node_input,
                    output_base_dir=output_dir,
                    max_debug_attempts=tree.max_debug_trials
                )
                
                self.tree_manager.update_node_state(node_id, state, output_data_id=output_path)
                
                results[node_id] = {
                    "name": node.function_block.name,
                    "state": state.value,
                    "output": output_path,
                    "error": node.error if state == NodeState.FAILED else None
                }
                
                if state == NodeState.FAILED:
                    logger.error(f"  ✗ Failed: {node.function_block.name}")
                elif verbose:
                    logger.info(f"  ✓ Completed: {node.function_block.name}")
                    
                    # Apply job review for completed nodes
                    if self.job_reviewer and execution_result:
                        logger.info(f"Reviewing completed function block for node {node_id}")
                        self._apply_job_review(node, tree, execution_result, output_path)
        
        return results
    
    def _apply_job_review(
        self,
        node: AnalysisNode,
        tree: AnalysisTree,
        execution_result: Any,
        output_path: Optional[str]
    ) -> None:
        """Apply job review to a completed node.
        
        Args:
            node: The completed node
            tree: The analysis tree
            execution_result: The execution result from the node executor
            output_path: The output path of the node
        """
        try:
            # Skip job review for system-generated root node
            if node.function_block.name == ROOT_NODE_NAME and not node.parent_id:
                logger.info("Skipping job review for system-generated root node")
                node.job_review_status = JobReviewStatus.SKIPPED
                node.job_review_summary = "System-generated root node - review skipped"
                return
            
            # Get output files from execution result
            output_files = execution_result.figures if hasattr(execution_result, 'figures') else []
            
            # Get parent output description if available
            parent_output_description = None
            if node.parent_id and node.parent_id in tree.nodes:
                parent_node = tree.nodes[node.parent_id]
                if hasattr(parent_node.function_block, 'output_description'):
                    parent_output_description = parent_node.function_block.output_description
            
            review_result = self.job_reviewer.review_function_block(
                node=node,
                function_block=node.function_block,
                execution_result=execution_result,
                user_request=tree.user_request,
                output_files=output_files,
                parent_output_description=parent_output_description
            )
            
            # Save review results to node directory
            if output_path:
                from pathlib import Path
                node_dir = Path(output_path).parent  # Go up from outputs to node dir
                self.job_reviewer.save_reports_to_directory(node_dir)
            
            # Store review results in node - separate from execution status
            node.job_review_result = review_result.to_dict() if hasattr(review_result, 'to_dict') else review_result
            node.job_review_summary = review_result.summary
            
            # Log review outcome
            if review_result.passed:
                logger.info(f"Job review passed for node {node.id}")
                node.job_review_status = JobReviewStatus.PASSED
                node.needs_rework = False
            else:
                logger.warning(f"Job review identified concerns for node {node.id}: {review_result.summary}")
                node.job_review_status = JobReviewStatus.FAILED
                
                # Check if rework should be triggered
                if self.job_reviewer.should_trigger_rework(review_result):
                    logger.warning(f"Job reviewer recommends rework for node {node.id}")
                    
                    # Check if we've hit the rework limit for this task
                    if node.rework_attempts >= MAX_REWORK_ATTEMPTS:
                        logger.warning(
                            f"Node {node.id} ({node.function_block.name}) has reached "
                            f"rework limit ({MAX_REWORK_ATTEMPTS} attempts). Not setting needs_rework."
                        )
                        node.needs_rework = False
                        node.rework_limit_reached = True
                        # Add system note to review summary
                        if node.job_review_summary:
                            node.job_review_summary += f"\n[System: Rework limit reached after {node.rework_attempts} attempts]"
                        else:
                            node.job_review_summary = f"[System: Rework limit reached after {node.rework_attempts} attempts]"
                    else:
                        node.needs_rework = True
                        node.rework_limit_reached = False
                        logger.info(f"Node {node.id} needs rework (attempt #{node.rework_attempts + 1} will be created)")
                    
                    # Create enhanced error message that includes review concerns
                    review_error_msg = f"Job review failed: {review_result.summary}\n\nCritical concerns:\n"
                    for concern in review_result.concerns:
                        if concern.severity == "critical":
                            review_error_msg += f"- {concern.description}\n"
                    
                    # Store review error separately - don't overwrite execution error
                    if not node.error:  # Only set error if there wasn't an execution error
                        node.error = review_error_msg
                    else:
                        # Append review concerns to existing error
                        node.error += f"\n\n{review_error_msg}"
                    
                    logger.info(f"Node {node.id} needs rework due to job review concerns")
                else:
                    # Review failed but not critical enough for rework
                    node.needs_rework = False
                    logger.info(f"Node {node.id} has review concerns but rework not required")
                    
        except Exception as e:
            logger.error(f"Error during job review for node {node.id}: {e}")
            # Don't fail the node execution due to review errors

    def _gather_node_failure_context(self, node: AnalysisNode, tree_dir: Path) -> Optional[Dict[str, Any]]:
        """Gather comprehensive failure context for a failed node.
        
        Args:
            node: The failed node
            tree_dir: The tree directory
            
        Returns:
            Dictionary containing failure context or None if node didn't fail
        """
        if node.state != NodeState.FAILED:
            return None
        
        logger.info(f"Gathering failure context for node {node.id} ({node.function_block.name})")
        
        context = {
            "_metadata": {
                "version": "1.0",
                "created_at": datetime.now().isoformat(),
                "source_node_id": node.id,
                "source_node_name": node.function_block.name,
                "propagated_by": "orchestrator"
            }
        }
        
        node_dir = tree_dir / "nodes" / f"node_{node.id}"
        
        # 1. Gather execution failure info
        if node.error or hasattr(node, 'error_message'):
            context["execution_failure"] = self._extract_execution_failure(node, node_dir)
            logger.debug(f"Extracted execution failure: {context['execution_failure'].get('error_type', 'Unknown')}")
        
        # 2. Gather job review failure (if exists)
        job_review_dir = node_dir / "agent_tasks" / "job_reviewer"
        if job_review_dir.exists():
            job_reviews = list(job_review_dir.glob("review_*.json"))
            if job_reviews:
                latest_review = sorted(job_reviews)[-1]
                logger.debug(f"Reading job review from {latest_review}")
                try:
                    with open(latest_review) as f:
                        review_data = json.load(f)
                        result = review_data.get("result", {})
                        if not result.get("passed", True):
                            context["job_review_failure"] = {
                                "passed": result.get("passed", False),
                                "concerns": result.get("concerns", []),
                                "summary": result.get("summary", ""),
                                "needs_rework": result.get("recommendations", {}).get("needs_rework", False),
                                "ml_best_practices_score": result.get("ml_best_practices", {}).get("score", 0)
                            }
                            logger.debug("Extracted job review failure")
                except Exception as e:
                    logger.warning(f"Failed to read job review: {e}")
        
        # 3. Gather function block implementation details
        # Use 'type' attribute which exists, not 'language'
        language = getattr(node.function_block, 'type', 'python')
        if hasattr(language, 'value'):
            language = language.value
        
        # Get code with truncation tracking
        code = node.function_block.code
        code_truncated = False
        truncation_info = {}
        
        # Don't truncate in JSON storage - only track if it would be truncated in prompts
        if len(code) > self.failure_context_config.max_code_length_prompt:
            truncation_info["code_full_length"] = len(code)
            truncation_info["code_prompt_truncated"] = True
            truncation_info["code_prompt_max"] = self.failure_context_config.max_code_length_prompt
        
        context["function_block_implementation"] = {
            "name": node.function_block.name,
            "language": language,
            "code": code,  # Store full code in JSON
            "requirements": node.function_block.requirements,
            "parameters": node.function_block.parameters,
            "version": node.debug_attempts + 1,
            "debug_attempts": node.debug_attempts
        }
        
        # Add truncation info if any truncation would occur
        if truncation_info:
            context["function_block_implementation"]["_truncation_info"] = truncation_info
        
        # 4. Gather bug fixer attempts summary
        bug_fixer_dir = node_dir / "agent_tasks" / "bug_fixer"
        if bug_fixer_dir.exists():
            context["bug_fixer_attempts"] = self._summarize_bug_fixer_attempts(bug_fixer_dir)
            logger.debug(f"Summarized {context['bug_fixer_attempts'].get('total_attempts', 0)} bug fixer attempts")
        
        return context
    
    def _extract_execution_failure(self, node: AnalysisNode, node_dir: Path) -> Dict[str, Any]:
        """Extract execution failure details from node.
        
        Args:
            node: The failed node
            node_dir: The node directory
            
        Returns:
            Dictionary containing execution failure details
        """
        failure_info = {
            "error_type": "UnknownError",
            "error_message": str(node.error) if node.error else "Unknown error",
            "exit_code": -1,
            "stdout_tail": "",
            "stderr_tail": ""
        }
        
        # Extract error type and message
        error_msg = str(node.error) if node.error else getattr(node, 'error_message', "Unknown error")
        failure_info["error_message"] = error_msg
        
        # Try to extract error type from message
        import re
        error_patterns = [
            (r'(ModuleNotFoundError|ImportError):\s*No module named', 'ModuleNotFoundError'),
            (r'(AttributeError):\s*', 'AttributeError'),
            (r'(KeyError):\s*', 'KeyError'),
            (r'(ValueError):\s*', 'ValueError'),
            (r'(TypeError):\s*', 'TypeError'),
            (r'(NameError):\s*', 'NameError'),
            (r'(FileNotFoundError):\s*', 'FileNotFoundError'),
            (r'ERROR:.*No matching distribution found for', 'PackageInstallationError'),
            (r'([A-Z]\w*Error):', lambda m: m.group(1))
        ]
        
        for pattern, error_type in error_patterns:
            match = re.search(pattern, error_msg)
            if match:
                if callable(error_type):
                    failure_info["error_type"] = error_type(match)
                else:
                    failure_info["error_type"] = error_type
                break
        
        # Try to read execution logs
        jobs_dir = node_dir / "jobs"
        if jobs_dir.exists():
            job_dirs = sorted([d for d in jobs_dir.iterdir() if d.is_dir()], 
                            key=lambda x: x.name, reverse=True)
            if job_dirs:
                latest_job = job_dirs[0]
                
                # Read stdout
                stdout_file = latest_job / "output" / "stdout.log"
                if stdout_file.exists():
                    try:
                        with open(stdout_file, 'r') as f:
                            stdout_content = f.read()
                            lines = stdout_content.split('\n')
                            failure_info["stdout_tail"] = '\n'.join(lines[-200:]) if len(lines) > 200 else stdout_content
                    except Exception as e:
                        logger.debug(f"Failed to read stdout: {e}")
                
                # Read stderr
                stderr_file = latest_job / "output" / "stderr.log"
                if stderr_file.exists():
                    try:
                        with open(stderr_file, 'r') as f:
                            stderr_content = f.read()
                            lines = stderr_content.split('\n')
                            failure_info["stderr_tail"] = '\n'.join(lines[-100:]) if len(lines) > 100 else stderr_content
                    except Exception as e:
                        logger.debug(f"Failed to read stderr: {e}")
                
                # Try to extract exit code
                error_log = latest_job / "output" / "error.log"
                if error_log.exists():
                    try:
                        with open(error_log, 'r') as f:
                            error_content = f.read()
                            # Look for exit code in error log
                            exit_match = re.search(r'exit code[:\s]+(\d+)', error_content, re.IGNORECASE)
                            if exit_match:
                                failure_info["exit_code"] = int(exit_match.group(1))
                    except Exception as e:
                        logger.debug(f"Failed to extract exit code: {e}")
        
        return failure_info
    
    def _summarize_bug_fixer_attempts(self, bug_fixer_dir: Path) -> Dict[str, Any]:
        """Summarize bug fixer attempts from the bug fixer directory.
        
        Args:
            bug_fixer_dir: Path to bug_fixer agent tasks directory
            
        Returns:
            Dictionary containing bug fixer attempts summary
        """
        summary = {
            "total_attempts": 0,
            "actions_summary": [],
            "learned_issues": []
        }
        
        # Count attempt directories
        attempt_dirs = [d for d in bug_fixer_dir.iterdir() if d.is_dir() and d.name.startswith("attempt_")]
        summary["total_attempts"] = len(attempt_dirs)
        
        # Analyze each attempt
        action_counts = {}
        issues_found = set()
        
        for attempt_dir in sorted(attempt_dirs):
            # Look for turn files
            turn_files = sorted(attempt_dir.glob("turn_*.json"))
            for turn_file in turn_files:
                try:
                    with open(turn_file) as f:
                        turn_data = json.load(f)
                        
                        # Count actions
                        action = turn_data.get("action_taken", {})
                        action_type = action.get("type", "unknown")
                        if action_type != "unknown":
                            action_counts[action_type] = action_counts.get(action_type, 0) + 1
                        
                        # Extract learned issues from error states
                        error_state = turn_data.get("error_state", {})
                        current_error = error_state.get("current_error", "")
                        
                        # Identify specific issues
                        if "No matching distribution found for" in current_error:
                            match = re.search(r'No matching distribution found for (\w+)', current_error)
                            if match:
                                issues_found.add(f"{match.group(1)} package does not exist on PyPI")
                        
                        if "No module named" in current_error:
                            match = re.search(r"No module named '?([^'\"]+)'?", current_error)
                            if match:
                                issues_found.add(f"Missing module: {match.group(1)}")
                        
                        if "requires" in current_error and ("PCA" in current_error or "neighbors" in current_error):
                            issues_found.add("Missing required preprocessing steps")
                        
                except Exception as e:
                    logger.debug(f"Failed to read turn file {turn_file}: {e}")
        
        # Format action summary
        for action_type, count in sorted(action_counts.items(), key=lambda x: x[1], reverse=True):
            summary["actions_summary"].append(f"{action_type}: {count} times")
        
        summary["learned_issues"] = list(issues_found)
        
        return summary
    
    def _propagate_failure_context(self, tree: AnalysisTree, failed_node_id: str, target_node: AnalysisNode, tree_dir: Path) -> None:
        """Propagate failure context from a failed node to a new node.
        
        Args:
            tree: The analysis tree
            failed_node_id: ID of the failed node to get context from
            target_node: The new node to propagate context to
            tree_dir: Directory containing the tree
        """
        try:
            # Get the failed node
            if failed_node_id not in tree.nodes:
                logger.warning(f"Failed node {failed_node_id} not found in tree")
                return
                
            failed_node = tree.nodes[failed_node_id]
            
            # Gather failure context for the failed node
            failure_context = self._gather_node_failure_context(failed_node, tree_dir)
            if not failure_context:
                logger.warning(f"No failure context found for node {failed_node_id}")
                return
            
            # Update metadata for propagation
            failure_context["_metadata"]["propagated_by"] = "orchestrator"
            failure_context["_metadata"]["propagated_to_node_id"] = target_node.id
            failure_context["_metadata"]["propagated_at"] = datetime.now().isoformat()
            
            # Store the failure context in the target node for later use
            # This will be written to job input directory when the node executes
            target_node.propagated_failure_context = failure_context
            
            logger.info(f"Successfully attached failure context from node {failed_node_id} to node {target_node.id}")
            
        except Exception as e:
            logger.error(f"Error propagating failure context: {e}")
            # Don't fail the node creation if context propagation fails
    
    def _update_all_tree_errors(self, tree_dir: Path, failed_nodes: List[Dict[str, Any]]) -> None:
        """Update the complete tree error history.
        
        Args:
            tree_dir: The tree directory
            failed_nodes: List of failure context dictionaries
        """
        all_errors_file = tree_dir / "all_tree_errors.json"
        
        # Load existing errors
        if all_errors_file.exists():
            try:
                with open(all_errors_file) as f:
                    all_errors = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load existing tree errors: {e}")
                all_errors = {"nodes": {}, "last_updated": None}
        else:
            all_errors = {"nodes": {}, "last_updated": None}
        
        # Update with new failures
        for node_context in failed_nodes:
            if node_context and "_metadata" in node_context:
                node_id = node_context["_metadata"]["source_node_id"]
                all_errors["nodes"][node_id] = node_context
                logger.debug(f"Added failure context for node {node_id} to all_tree_errors.json")
        
        all_errors["last_updated"] = datetime.now().isoformat()
        all_errors["total_failed_nodes"] = len(all_errors["nodes"])
        
        # Save updated errors
        try:
            with open(all_errors_file, 'w') as f:
                json.dump(all_errors, f, indent=2)
            logger.info(f"Updated all_tree_errors.json with {len(failed_nodes)} failed nodes")
        except Exception as e:
            logger.error(f"Failed to save all_tree_errors.json: {e}")