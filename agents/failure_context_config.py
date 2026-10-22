"""Configuration for failure context truncation and logging."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class FailureContextConfig:
    """Configuration for failure context gathering and truncation.
    
    This class controls how failure context information is truncated
    to avoid excessive memory usage and log sizes.
    """
    
    # Code truncation settings
    max_code_length: int = 10000  # Maximum characters for code in JSON (no truncation by default)
    max_code_length_prompt: int = 1000  # Maximum characters for code in prompts
    
    # Error message truncation
    max_error_message_length: int = 5000  # Maximum characters for error messages in JSON
    max_error_message_prompt: int = 500  # Maximum characters for error messages in prompts
    
    # Stdout/stderr truncation
    max_stdout_tail: int = 2000  # Maximum tail characters for stdout in JSON
    max_stderr_tail: int = 2000  # Maximum tail characters for stderr in JSON
    max_stdout_prompt: int = 500  # Maximum tail characters for stdout in prompts
    max_stderr_prompt: int = 500  # Maximum tail characters for stderr in prompts
    
    # Bug fixer action truncation
    max_action_result_length: int = 3000  # Maximum characters per action result in JSON
    max_action_result_prompt: int = 300  # Maximum characters per action result in prompts
    max_bug_fixer_attempts: int = 10  # Maximum number of bug fixer attempts to include
    
    # Job review truncation
    max_concerns_per_review: int = 10  # Maximum concerns to include from job review
    max_concern_description: int = 500  # Maximum characters per concern description
    
    # Learned issues truncation
    max_learned_issues: int = 20  # Maximum number of learned issues to track
    max_issue_length: int = 200  # Maximum characters per learned issue
    
    # File listing truncation
    max_files_to_list: int = 50  # Maximum files to list in any directory
    
    # Prompt assembly truncation (for orchestrator/function creator)
    max_failure_context_prompt: int = 2000  # Maximum total failure context in prompts
    
    # Logging configuration
    log_truncation_info: bool = True  # Whether to log when truncation occurs
    include_truncation_stats: bool = True  # Include truncation statistics in context
    
    def truncate_code(self, code: str, for_prompt: bool = False) -> tuple[str, bool]:
        """Truncate code with appropriate length limit.
        
        Args:
            code: The code to truncate
            for_prompt: Whether this is for prompt (uses shorter limit)
            
        Returns:
            Tuple of (truncated_code, was_truncated)
        """
        max_len = self.max_code_length_prompt if for_prompt else self.max_code_length
        if len(code) > max_len:
            return code[:max_len] + f"\n... ({len(code) - max_len} characters truncated)", True
        return code, False
    
    def truncate_error(self, error: str, for_prompt: bool = False) -> tuple[str, bool]:
        """Truncate error message with appropriate length limit.
        
        Args:
            error: The error message to truncate
            for_prompt: Whether this is for prompt (uses shorter limit)
            
        Returns:
            Tuple of (truncated_error, was_truncated)
        """
        max_len = self.max_error_message_prompt if for_prompt else self.max_error_message_length
        if len(error) > max_len:
            # Try to preserve the most important parts (beginning and end)
            half = max_len // 2
            return (error[:half] + 
                   f"\n... ({len(error) - max_len} characters truncated) ...\n" + 
                   error[-half:]), True
        return error, False
    
    def truncate_stdout_stderr(self, text: str, is_stdout: bool = True, for_prompt: bool = False) -> tuple[str, bool]:
        """Truncate stdout/stderr with appropriate length limit.
        
        Args:
            text: The stdout/stderr text to truncate
            is_stdout: Whether this is stdout (vs stderr)
            for_prompt: Whether this is for prompt (uses shorter limit)
            
        Returns:
            Tuple of (truncated_text, was_truncated)
        """
        if for_prompt:
            max_len = self.max_stdout_prompt if is_stdout else self.max_stderr_prompt
        else:
            max_len = self.max_stdout_tail if is_stdout else self.max_stderr_tail
            
        if len(text) > max_len:
            # Keep the tail (most recent output)
            return f"... ({len(text) - max_len} characters truncated)\n" + text[-max_len:], True
        return text, False
    
    def get_truncation_stats(self) -> dict:
        """Get current truncation configuration as stats.
        
        Returns:
            Dictionary with truncation settings
        """
        return {
            "code_limits": {
                "json": self.max_code_length,
                "prompt": self.max_code_length_prompt
            },
            "error_limits": {
                "json": self.max_error_message_length,
                "prompt": self.max_error_message_prompt
            },
            "output_limits": {
                "stdout_json": self.max_stdout_tail,
                "stderr_json": self.max_stderr_tail,
                "stdout_prompt": self.max_stdout_prompt,
                "stderr_prompt": self.max_stderr_prompt
            },
            "other_limits": {
                "max_bug_fixer_attempts": self.max_bug_fixer_attempts,
                "max_concerns": self.max_concerns_per_review,
                "max_learned_issues": self.max_learned_issues,
                "max_files_listed": self.max_files_to_list
            }
        }


# Default configuration instance
DEFAULT_FAILURE_CONTEXT_CONFIG = FailureContextConfig()


def get_failure_context_config() -> FailureContextConfig:
    """Get the current failure context configuration.
    
    Returns:
        The active FailureContextConfig instance
    """
    return DEFAULT_FAILURE_CONTEXT_CONFIG