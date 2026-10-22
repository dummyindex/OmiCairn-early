"""System-wide constants for the omicairn agent."""

# Node names
ROOT_NODE_NAME = "load_input_data"  # System-generated root node that passes through input data

# Agent names
ORCHESTRATOR_AGENT = "orchestrator"
MAIN_AGENT = "main_agent"
FUNCTION_CREATOR_AGENT = "function_creator"
BUG_FIXER_AGENT = "bug_fixer"
JOB_REVIEWER_AGENT = "job_reviewer"
ACTION_DIGESTER_AGENT = "action_digester"
CODE_CHECKER_AGENT = "code_checker"


# Directory names
AGENT_TASKS_DIR = "agent_tasks"
FUNCTION_BLOCK_DIR = "function_block"
JOBS_DIR = "jobs"
OUTPUTS_DIR = "outputs"
FIGURES_DIR = "figures"
NODES_DIR = "nodes"

# File names
ANALYSIS_TREE_FILE = "analysis_tree.json"
NODE_INFO_FILE = "node_info.json"
EXECUTION_SUMMARY_FILE = "execution_summary.json"
CONFIG_FILE = "config.json"
CODE_FILE = "code.py"
REQUIREMENTS_FILE = "requirements.txt"

# Execution limits
DEFAULT_MAX_NODES = 20
DEFAULT_MAX_CHILDREN_PER_NODE = 3
DEFAULT_MAX_DEBUG_TRIALS = 3
DEFAULT_MAX_ITERATIONS = 15  # Maximum planning iterations (how many times orchestrator can be asked for new plan, NOT node execution iterations)
DEFAULT_DOCKER_EXECUTION_TIMEOUT = 1800  # 30 minutes default Docker execution timeout

# Rework limits
MAX_REWORK_ATTEMPTS = 2  # Maximum times to rework a node after job review failures

# Bug fixer limits
DEFAULT_BUG_FIXER_MAX_TURNS = 5  # Default maximum debug turns for bug fixer

# Bug fixer timeout settings
DEBUG_SESSION_TIMEOUT = None  # Overall debug session timeout (None = no timeout)
CONTAINER_OPERATION_TIMEOUT = 30  # Timeout for container start/stop/remove operations (seconds)
LLM_CALL_TIMEOUT = 300  # Timeout for LLM API calls (5 minutes)

# Per-action timeout limits for bug fixer (in seconds)
ACTION_TIMEOUT_READ_FILE = 60
ACTION_TIMEOUT_WRITE_FILE = 60
ACTION_TIMEOUT_LIST_DIRECTORY = 60
ACTION_TIMEOUT_CHECK_FILE_EXISTS = 60
ACTION_TIMEOUT_HEAD_FILE = 60
ACTION_TIMEOUT_TAIL_FILE = 60
ACTION_TIMEOUT_GREP_FILE = 60
ACTION_TIMEOUT_CREATE_DIRECTORY = 60
ACTION_TIMEOUT_INSTALL_PACKAGE = 300  # 5 minutes for package installation
ACTION_TIMEOUT_EXECUTE_COMMAND = 600  # 10 minutes for general commands
ACTION_TIMEOUT_UPDATE_FUNCTION_BLOCK = 1800  # 30 minutes for re-execution
ACTION_TIMEOUT_WEB_RESEARCH = 120  # 2 minutes (web agent has internal 90s timeout)
ACTION_TIMEOUT_DEFAULT = 600  # Default timeout for unknown actions

# Log file patterns
STDOUT_LOG = "stdout.log"
STDERR_LOG = "stderr.log"
COMBINED_LOG = "combined.log"

# LLM Models - OpenAI
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
GPT_4O_MINI = "gpt-4o-mini"
GPT_4O = "gpt-4o"
GPT_4O_2024_08_06 = "gpt-4o-2024-08-06"
GPT_4O_2024_11_20 = "gpt-4o-2024-11-20"
GPT_4 = "gpt-4"
GPT_4_TURBO = "gpt-4-turbo"

# LLM Models - Claude
DEFAULT_CLAUDE_MODEL = "claude-3-haiku-20240307"
CLAUDE_3_HAIKU = "claude-3-haiku-20240307"
CLAUDE_3_SONNET = "claude-3-sonnet-20240229"
CLAUDE_3_OPUS = "claude-3-opus-20240229"
CLAUDE_3_5_HAIKU = "claude-3-5-haiku-20241022"
CLAUDE_3_5_SONNET = "claude-3-5-sonnet-20241022"
CLAUDE_SONNET_4_5 = "claude-sonnet-4-5-20250929"

# Environment Variables
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_CLAUDE_API_KEY = "CLAUDE_API_KEY"
ENV_OPENAI_MODEL = "OPENAI_MODEL"
ENV_CLAUDE_MODEL = "CLAUDE_MODEL"
ENV_CLAUDE_MAX_TURNS = "CLAUDE_MAX_TURNS"
ENV_CLAUDE_MAX_COST = "CLAUDE_MAX_COST"
ENV_CLAUDE_MAX_TOKENS = "CLAUDE_MAX_TOKENS"

# Display/Truncation Limits
LOG_PREVIEW_LINES = 30  # Lines to show in log previews
STDOUT_PREVIEW_LINES = 50  # Lines to show from stdout
ERROR_PREVIEW_CHARS = 500  # Characters to show in error previews
CONTAINER_ID_LENGTH = 12  # Standard Docker short ID length

# Bug fixer exploration limits
MAX_DISPLAY_ITEMS = 15  # Maximum number of columns/items to display when exploring data structures
DISPLAY_TRUNCATE_MESSAGE = True  # Whether to show "... and X more" message when truncating

# Job review status constants
JOB_REVIEW_PASSED = "passed"
JOB_REVIEW_FAILED = "failed"
JOB_REVIEW_NOT_REVIEWED = "not_reviewed"
JOB_REVIEW_SKIPPED = "skipped"


# Helper functions for timeout configuration
def get_action_timeout(action_type: str, default: int = None) -> int:
    """
    Get timeout for a specific action type.
    
    Args:
        action_type: The type of action (e.g., 'read_file', 'execute_command')
        default: Default timeout if action type not found (uses ACTION_TIMEOUT_DEFAULT if None)
        
    Returns:
        Timeout in seconds
    """
    if default is None:
        default = ACTION_TIMEOUT_DEFAULT
        
    action_timeouts = {
        'read_file': ACTION_TIMEOUT_READ_FILE,
        'write_file': ACTION_TIMEOUT_WRITE_FILE,
        'list_directory': ACTION_TIMEOUT_LIST_DIRECTORY,
        'check_file_exists': ACTION_TIMEOUT_CHECK_FILE_EXISTS,
        'head_file': ACTION_TIMEOUT_HEAD_FILE,
        'tail_file': ACTION_TIMEOUT_TAIL_FILE,
        'grep_file': ACTION_TIMEOUT_GREP_FILE,
        'create_directory': ACTION_TIMEOUT_CREATE_DIRECTORY,
        'install_package': ACTION_TIMEOUT_INSTALL_PACKAGE,
        'execute_command': ACTION_TIMEOUT_EXECUTE_COMMAND,
        'update_function_block': ACTION_TIMEOUT_UPDATE_FUNCTION_BLOCK,
        'web_research': ACTION_TIMEOUT_WEB_RESEARCH,
    }
    return action_timeouts.get(action_type, default)


def get_debug_session_timeout():
    """
    Get the overall debug session timeout.
    
    Returns:
        Timeout in seconds or None for no timeout
    """
    return DEBUG_SESSION_TIMEOUT