"""Enhanced debug session with proper error tracking and early termination."""

import json
import re
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from datetime import datetime

from .action_executor import ActionExecutor
from llm_service.base_llm_service import BaseLLMService
from .prompt_templates import (
    SYSTEM_PROMPT,
    create_initial_prompt,
    create_followup_prompt,
    create_completion_check_prompt
)
from .error_tracker import ErrorTracker
from utils import setup_logger

logger = setup_logger(__name__)

# Note: We use text parsing for bug fixer actions because OpenAI's strict JSON mode
# requires ALL properties to be in the required array, which doesn't work for our
# flexible action schema where different actions need different fields.

# Legacy flat schema (kept for reference)
LEGACY_DEBUG_ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": [
                "read_file", "write_file", "execute_command", "install_package",
                "update_function_block", "list_directory", "create_directory",
                "check_file_exists", "tail_file", "head_file", "grep_file"
            ],
            "description": "The type of action to perform"
        },
        # Action-specific parameters (flat structure)
        "path": {"type": "string", "description": "File or directory path (for file operations)"},
        "content": {"type": "string", "description": "Content to write (for write_file)"},
        "command": {"type": "string", "description": "Command to execute (for execute_command)"},
        "package": {"type": "string", "description": "Package to install (for install_package)"},
        "code": {"type": "string", "description": "Python/R code (for update_function_block)"},
        "requirements": {"type": "array", "items": {"type": "string"}, "description": "List of requirements (for update_function_block)"},
        "lines": {"type": "integer", "description": "Number of lines to show (for head_file/tail_file)"},
        "pattern": {"type": "string", "description": "Search pattern (for grep_file)"},
        "max_lines": {"type": "integer", "description": "Maximum lines to read (for read_file, default 1000)"},
        # Metadata
        "explanation": {
            "type": "string",
            "description": "Detailed explanation of why this action is being taken"
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Confidence level in this action (0-1)"
        }
    },
    "required": ["type"],
    "additionalProperties": False
}


class EnhancedDebugSession:
    """Enhanced debugging session with proper error tracking."""
    
    def __init__(
        self, 
        action_executor: ActionExecutor,
        llm_service: BaseLLMService,
        max_turns: int = 5,
        node_dir: Optional[Path] = None,
        attempt_number: Optional[int] = None,
        enable_domain_knowledge: bool = False,
        prompt_injector: Optional[Any] = None,
        domain_knowledge_domains: Optional[List[str]] = None,
        enable_action_digester: bool = True,
        bug_fixer_attempt_dir: Optional[Path] = None
    ):
        self.action_executor = action_executor
        self.llm_service = llm_service
        self.max_turns = max_turns
        self.node_dir = node_dir
        self.attempt_number = attempt_number
        self.bug_fixer_attempt_dir = bug_fixer_attempt_dir
        
        # Domain knowledge settings
        self.enable_domain_knowledge = enable_domain_knowledge
        self.prompt_injector = prompt_injector
        self.domain_knowledge_domains = domain_knowledge_domains or []
        
        # Action digester settings
        self.enable_action_digester = enable_action_digester
        self.action_digester = None
        if self.enable_action_digester:
            try:
                from .action_digester import ActionDigester
                self.action_digester = ActionDigester(llm_service)
                logger.info("Action digester enabled for debug session")
            except Exception as e:
                logger.warning(f"Failed to initialize action digester: {e}")
                self.enable_action_digester = False
        
        # Session state
        self.turn_count = 0
        self.actions_taken = []
        self.files_modified = set()
        self.messages = []
        self.session_start = datetime.now()
        
        # Error tracking
        self.error_tracker = None  # Will be initialized in debug method
        
        # Bug fixer uses text parsing mode for actions due to OpenAI's strict
        # JSON schema requirements that conflict with our flexible action schema
        logger.info("Bug fixer uses text parsing for actions (flexible schema)")
    
    def debug(
        self,
        node_name: str,
        error_message: str,
        stdout: str,
        stderr: str,
        attempt_number: int,
        previous_attempts: Optional[List[Dict]] = None,
        node_description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Run enhanced debugging session with proper error tracking."""
        logger.info(f"Starting enhanced debug session for {node_name} (attempt {attempt_number})")
        
        # Initialize error tracker
        self.error_tracker = ErrorTracker(error_message, self.node_dir)
        
        # Initialize conversation with system prompt
        system_prompt = self._get_enhanced_system_prompt()
        self.messages = [{"role": "system", "content": system_prompt}]
        
        # Get directory tree of workspace/input
        directory_tree = self._get_input_directory_tree()
        
        # Add initial user message with available actions
        available_actions = self.action_executor.get_available_actions() if hasattr(self.action_executor, 'get_available_actions') else None
        initial_prompt = create_initial_prompt(
            node_name, error_message, stdout, stderr, attempt_number, previous_attempts, directory_tree, node_description,
            available_actions=available_actions
        )
        self.messages.append({"role": "user", "content": initial_prompt})
        
        # Keep track of the original message index for updates
        self.original_message_index = len(self.messages) - 1
        
        success = False
        final_explanation = ""
        
        # Store action results from previous turn for conversation updates
        pending_action_update = None
        
        # Main debugging loop
        for turn in range(1, self.max_turns + 1):
            self.turn_count = turn
            self.error_tracker.start_turn(turn)
            
            # Notify action executor about turn change
            if hasattr(self.action_executor, 'increment_turn'):
                self.action_executor.increment_turn()
            
            logger.info(f"\n{'='*60}")
            logger.info(f"DEBUG TURN {turn}/{self.max_turns}")
            logger.info(f"{'='*60}")
            
            # Apply action results from previous turn BEFORE LLM call
            if pending_action_update:
                self._update_conversation_with_action(
                    pending_action_update['turn'],
                    pending_action_update['action'],
                    pending_action_update['action_result'],
                    pending_action_update['explanation']
                )
                pending_action_update = None
            
            is_final_turn = (turn == self.max_turns)
            
            # Add final turn instructions if needed
            if is_final_turn:
                self._update_conversation_for_final_turn()
            
            # Capture the current messages before calling LLM (for logging)
            messages_before_llm = [msg.copy() for msg in self.messages]
            
            # Get action from LLM
            action_response = self._get_llm_action()
            
            if action_response:
                # DO NOT add assistant's raw response to messages - it creates redundancy
                # The action results will be added to the user message via _update_conversation_with_action
                llm_response = action_response.get('llm_response', '')
                if not llm_response:
                    logger.warning(f"Turn {turn}: No llm_response captured in action_response")
                
                # Handle parsing failures specially
                if action_response.get('type') == 'PARSING_FAILED':
                    # This is a parsing failure, not a normal action
                    action = action_response  # The whole response is the "action"
                    explanation = 'Failed to parse JSON from LLM response'
                else:
                    # Normal action processing
                    action = action_response.get('action', action_response)  # Fallback to full response if no 'action' key
                    explanation = action_response.get('explanation', '')
                
                # Check if this is a parsing error action - DO NOT EXECUTE
                if action.get('type') == 'PARSING_FAILED':
                    logger.error(f"JSON parsing failed - will inform LLM in next turn")
                    action_result = {
                        'success': False,
                        'error': f"JSON PARSING ERROR: {action.get('error', 'Unknown parsing error')}",
                        'parsing_failed': True,
                        'raw_response_sample': action.get('raw_response', '')[:500],
                        'help': "Please respond with valid JSON only. No text before or after the JSON object."
                    }
                else:
                    # Execute action
                    logger.info(f"Executing action: {action['type']}")
                    action_result = self.action_executor.execute_action(action)
                    
                    # Apply action digestion if enabled and needed
                    if (self.enable_action_digester and self.action_digester and
                        'result' in action_result and isinstance(action_result['result'], str)):
                        
                        if self.action_digester.should_digest(action['type'], action_result['result']):
                            logger.info(f"Digesting large action result for {action['type']}")
                            
                            # Store original result for file saving
                            original_result = action_result['result']
                            
                            digest = self.action_digester.digest_action_result(
                                action_type=action['type'],
                                action_params=action,
                                raw_result=original_result,
                                error_context=error_message,
                                debugging_goal=f"Fix error in {node_name}"
                            )
                            
                            # Save both raw and digested outputs to files
                            if self.node_dir:
                                self._save_action_digest_files(turn, action, original_result, digest)
                            
                            # Replace the result with digest for conversation
                            action_result['original_result_length'] = len(original_result)
                            action_result['digested'] = True
                            action_result['result'] = f"[DIGESTED RESULT - Original: {digest.original_length} chars, Compressed: {len(str(digest.to_dict()))} chars]\n\n{digest.summary}\n\nKey Findings:\n" + "\n".join(f"- {finding}" for finding in digest.key_findings)
                            
                            if digest.preserved_evidence.get('error_messages'):
                                action_result['result'] += "\n\nError Messages:\n" + "\n".join(digest.preserved_evidence['error_messages'])
                            
                            if digest.actionable_insights:
                                action_result['result'] += "\n\nNext Steps:\n" + "\n".join(f"- {insight}" for insight in digest.actionable_insights)
                
                # Track modifications
                if action['type'] == 'write_file' and action_result['success']:
                    self.files_modified.add(action.get('path', ''))
                
                # Record action in error tracker
                self.error_tracker.record_action(action, action_result)
                
                # Store action results for conversation update in NEXT turn (before next LLM call)
                # This ensures action results are included in subsequent LLM input
                pending_action_update = {
                    'turn': turn,
                    'action': action,
                    'action_result': action_result,
                    'explanation': explanation
                }
                
                # Record action for later
                self.actions_taken.append({
                    'turn': turn,
                    'action': action,
                    'result_summary': action_result.get('success', False),
                    'action_result': action_result,  # Store full result for detailed logging
                    'explanation': explanation,
                    'llm_response': llm_response
                })
                
                # Save turn log
                if self.node_dir:
                    self._save_enhanced_turn_log(turn, action, action_result, explanation, llm_response, messages_before_llm)
                    
                    # Also save raw LLM input/output in a dedicated file for easy access
                    # Use self.messages to capture the updated messages with action results
                    self._save_llm_raw_io(turn, self.messages, llm_response)
                
                # Check if error is resolved
                if not self.error_tracker.should_continue_debugging():
                    success = True
                    final_explanation = f"Error resolved in turn {turn} with {action['type']} action"
                    logger.info(f"✅ ERROR RESOLVED! Stopping debug session early.")
                    break
                
                # Update final explanation for final turn
                if is_final_turn or action_response.get('confidence', 0) > 0.8:
                    final_explanation = explanation
        
        # Apply any remaining pending action update to the conversation
        # This ensures the conversation history is complete for logs and knowledge transfer
        if pending_action_update:
            self._update_conversation_with_action(
                pending_action_update['turn'],
                pending_action_update['action'],
                pending_action_update['action_result'],
                pending_action_update['explanation']
            )
        
        # Save error tracking summary
        if self.node_dir:
            self._save_error_tracking_summary()
        
        # Prepare result
        # Build detailed turn information for knowledge inheritance
        detailed_turns = []
        for turn_data in self.error_tracker.turns:
            turn_summary = {
                'turn': turn_data['turn'],
                'actions': []
            }
            
            for action_data in turn_data.get('actions', []):
                action_summary = {
                    'type': action_data['type'],
                    'success': action_data['success'],
                    'summary': action_data.get('result_summary', '')
                }
                
                # Add specific details based on action type
                if action_data['type'] == 'execute_command':
                    action_summary['command'] = action_data.get('action', {}).get('command', '')
                    if 'action_result' in action_data:
                        action_summary['stdout'] = action_data['action_result'].get('stdout', '')
                        action_summary['stderr'] = action_data['action_result'].get('stderr', '')
                elif action_data['type'] == 'write_and_run':
                    # Add write_and_run specific details
                    if 'action_result' in action_data:
                        action_summary['stdout'] = action_data['action_result'].get('stdout', '')
                        action_summary['stderr'] = action_data['action_result'].get('stderr', '')
                        action_summary['exit_code'] = action_data['action_result'].get('exit_code')
                        action_summary['files_written'] = action_data['action_result'].get('files_written', [])
                    else:
                        # Ensure we always have these fields for write_and_run, even if action_result is missing
                        action_summary['stdout'] = ''
                        action_summary['stderr'] = ''
                        action_summary['exit_code'] = None  # Use None instead of 'unknown' for missing data
                        action_summary['files_written'] = []
                elif action_data['type'] == 'update_function_block':
                    action_summary['resolved_error'] = action_data.get('resolved_error', False)
                    if 're_execution' in action_data.get('result_summary', ''):
                        action_summary['function_executed'] = True
                        action_summary['new_error'] = action_data.get('new_error')
                elif action_data['type'] == 'read_file':
                    action_summary['path'] = action_data.get('action', {}).get('path', '')
                    if 'action_result' in action_data:
                        action_summary['content'] = action_data['action_result'].get('content', action_data['action_result'].get('result', ''))
                elif action_data['type'] == 'write_file':
                    action_summary['path'] = action_data.get('action', {}).get('path', '')
                    
                turn_summary['actions'].append(action_summary)
                
            # Add error state evolution
            turn_summary['error_state'] = {
                'current_error': turn_data['error_state'].get('current_error'),
                'is_resolved': turn_data['error_state'].get('is_resolved', False)
            }
            
            detailed_turns.append(turn_summary)
        
        result = {
            'success': success,
            'turn_count': self.turn_count,
            'turns': self.turn_count,
            'actions': self.actions_taken,
            'files_modified': list(self.files_modified),
            'explanation': final_explanation if success else self._extract_error_summary(),
            'error_tracking': self.error_tracker.get_resolution_summary(),
            'duration_seconds': (datetime.now() - self.session_start).total_seconds(),
            'detailed_turns': detailed_turns  # For knowledge inheritance
        }
        
        # Add usage stats if available
        if hasattr(self.llm_service, 'get_usage_summary'):
            usage = self.llm_service.get_usage_summary()
            result['cost'] = usage.get('total_cost', 0)
            result['tokens'] = {'total': usage.get('total_tokens', 0)}
        
        # Save action digester reports if available
        if self.action_digester and self.node_dir and hasattr(self.action_digester, 'save_reports_to_directory'):
            # Save to bug fixer attempt directory if available, otherwise to node_dir
            save_dir = getattr(self, 'bug_fixer_attempt_dir', None) or self.node_dir
            self.action_digester.save_reports_to_directory(save_dir)
            logger.info(f"Action digester reports saved to {save_dir}/agent_tasks/action_digests/")
        
        # Save timing summary if available
        if hasattr(self.action_executor, 'save_timing_summary'):
            self.action_executor.save_timing_summary()
        
        return result
    
    def _get_enhanced_system_prompt(self) -> str:
        """Get enhanced system prompt with additional constraints."""
        from .prompt_templates import get_available_actions_documentation
        
        # Get the base prompt
        base_prompt = SYSTEM_PROMPT
        
        # Replace the actions placeholder with actual available actions
        if hasattr(self.action_executor, 'get_available_actions'):
            available_actions = self.action_executor.get_available_actions()
            actions_doc = get_available_actions_documentation(available_actions)
            base_prompt = base_prompt.replace('{ACTIONS_DOCUMENTATION}', actions_doc)
        
        # Add constraint about using function block code only
        constraint = """

CRITICAL CONSTRAINT - Function Block Code Only:
- You MUST complete the task using ONLY the function block code
- DO NOT create external scripts or helper files to do the main work
- The function block (run function) must contain ALL logic to complete the user's request
- You may use execute_command to check data structures or gather information
- But the actual task implementation MUST be in the function block itself
- If you need helper functions, define them WITHIN the function block file

CRITICAL CONSTRAINT - Task Preservation:
- You MUST implement the EXACT method specified in the function block name/description
- DO NOT substitute one analysis method for another
- If a method has prerequisites, load them correctly - don't re-implement them
- The goal is to fix errors while preserving the original analytical intent

Example of what NOT to do:
❌ Creating a separate analyze.py script and calling it from the function block
❌ Writing the main logic in a jupyter notebook and just loading results
❌ Replacing the specified method with a different algorithm
❌ Re-running prerequisite analyses instead of loading their results

Example of what TO do:
✅ Implementing all analysis logic directly in the run() function
✅ Defining helper functions within the function block file if needed
✅ Using execute_command only for debugging/exploration, not for the main task
✅ Loading prerequisite results and using them correctly for the specified method
✅ Fixing errors while maintaining the requested analytical approach
"""
        
        # Combine base prompt with constraint
        full_prompt = base_prompt + constraint
        
        # Inject domain knowledge if enabled
        if self.enable_domain_knowledge and self.prompt_injector:
            full_prompt = self.prompt_injector.inject_domain_knowledge(
                full_prompt, self.domain_knowledge_domains
            )
            logger.info(f"Injected domain knowledge for: {self.domain_knowledge_domains}")
        
        return full_prompt
    
    def _update_conversation_with_action(self, turn: int, action: Dict[str, Any], action_result: Dict[str, Any], explanation: str):
        """Update the original user message with action results instead of adding new messages."""
        # Get the original message
        original_message = self.messages[self.original_message_index]['content']
        
        # Check if we need to add the "Actions Performed" section
        if "\n\n## Actions Performed" not in original_message:
            original_message += "\n\n## Actions Performed"
        
        # Format action information
        action_info = f"\n\n### Turn {turn}\n"
        action_info += f"**Action**: {action['type']}\n"
        
        # Add action-specific parameters
        if action['type'] == 'read_file':
            action_info += f"**File**: {action.get('path', 'Unknown')}\n"
        elif action['type'] == 'write_file':
            action_info += f"**File**: {action.get('path', 'Unknown')}\n"
        elif action['type'] == 'execute_command':
            action_info += f"**Command**: `{action.get('command', 'Unknown')}`\n"
        elif action['type'] == 'write_and_run':
            # Show files being written for write_and_run
            files = action.get('files', [])
            if files:
                file_names = [f.get('path', 'unknown') for f in files]
                action_info += f"**Files**: {', '.join(file_names)}\n"
            if action.get('run_script'):
                action_info += f"**Script**: `{action['run_script']}`\n"
        elif action['type'] == 'update_function_block':
            action_info += f"**Language**: {action.get('language', 'python')}\n"
            requirements = action.get('requirements', [])
            if requirements:
                action_info += f"**Requirements**: {', '.join(requirements)}\n"
        
        # Add explanation if provided
        if explanation:
            action_info += f"**Explanation**: {explanation}\n"
        
        # Add result information
        action_info += f"**Result**: {'✅ Success' if action_result.get('success', False) else '❌ Failed'}\n"
        
        # Add relevant result details based on action type
        if action_result.get('success', False):
            if action['type'] == 'read_file' and 'content' in action_result:
                # Show file content for any successful read_file action
                content_lines = action_result['content'].split('\n')[:10]
                # Always include file content regardless of length - even short files are important!
                action_info += "**File Content**"
                if len(action_result['content'].split('\n')) > 10:
                    action_info += " (first 10 lines)"
                action_info += ":\n```\n"
                action_info += '\n'.join(content_lines)
                if len(action_result['content'].split('\n')) > 10:
                    action_info += "\n... (truncated)"
                action_info += "\n```\n"
            elif action['type'] == 'execute_command':
                if action_result.get('stdout'):
                    stdout_lines = action_result['stdout'].strip().split('\n')
                    if len(stdout_lines) <= 10:
                        action_info += f"**Output**:\n```\n{action_result['stdout'].strip()}\n```\n"
                    else:
                        action_info += f"**Output** (truncated):\n```\n"
                        action_info += '\n'.join(stdout_lines[:10])
                        action_info += f"\n... ({len(stdout_lines) - 10} more lines)\n```\n"
            elif action['type'] == 'write_and_run':
                # Show output from write_and_run execution
                if action_result.get('stdout'):
                    stdout = action_result['stdout'].strip()
                    stdout_lines = stdout.split('\n')
                    if len(stdout_lines) <= 20:  # Show more lines for write_and_run
                        action_info += f"**Output**:\n```\n{stdout}\n```\n"
                    else:
                        action_info += f"**Output** (truncated, showing first 20 lines):\n```\n"
                        action_info += '\n'.join(stdout_lines[:20])
                        action_info += f"\n... ({len(stdout_lines) - 20} more lines)\n```\n"
                
                # Show stderr if present
                if action_result.get('stderr'):
                    stderr = action_result['stderr'].strip()
                    if stderr:
                        stderr_lines = stderr.split('\n')
                        if len(stderr_lines) <= 5:
                            action_info += f"**Stderr**:\n```\n{stderr}\n```\n"
                        else:
                            action_info += f"**Stderr** (truncated):\n```\n"
                            action_info += '\n'.join(stderr_lines[:5])
                            action_info += f"\n... ({len(stderr_lines) - 5} more lines)\n```\n"
                
                # Show exit code
                if 'exit_code' in action_result:
                    action_info += f"**Exit Code**: {action_result['exit_code']}\n"
                
                # Show files written
                if action_result.get('files_written'):
                    action_info += f"**Files Created**: {', '.join(action_result['files_written'])}\n"
            elif action['type'] == 'update_function_block':
                # Check for re_execution results (new key) or execution_result (legacy)
                exec_result = action_result.get('re_execution') or action_result.get('execution_result')
                if exec_result:
                    action_info += f"**Execution Result**: Exit code {exec_result.get('exit_code', 'Unknown')}\n"
                    if exec_result.get('function_executed'):
                        action_info += "**Function Executed**: Yes\n"
                    if exec_result.get('success') is not None:
                        action_info += f"**Function Success**: {'Yes' if exec_result.get('success') else 'No'}\n"
                    if exec_result.get('actual_error'):
                        action_info += f"**Actual Error**: {exec_result.get('actual_error')}\n"
                    if exec_result.get('output_files'):
                        action_info += f"**Output Files Created**: {', '.join(exec_result.get('output_files'))}\n"
        else:
            # Show error details
            error_msg = action_result.get('error', 'Unknown error')
            action_info += f"**Error**: {error_msg}\n"
            
            # Add special handling for parsing failures
            if action_result.get('parsing_failed'):
                action_info += "\n⚠️ **JSON PARSING FAILED** ⚠️\n"
                action_info += "Your response was not valid JSON. Remember:\n"
                action_info += "- Start your response with `{` and end with `}`\n"
                action_info += "- NO text before or after the JSON\n"
                action_info += "- NO markdown code blocks (no ```json```)\n"
                action_info += "- NO trailing commas in objects or arrays\n"
                if action_result.get('raw_response_sample'):
                    action_info += f"\nYour response started with:\n```\n{action_result['raw_response_sample']}\n```\n"
                action_info += "\nPlease try again with valid JSON format.\n"
        
        # Update the original message
        self.messages[self.original_message_index]['content'] = original_message + action_info
    
    def _update_conversation_for_final_turn(self):
        """Update the conversation for final turn instructions."""
        # Get the original message
        original_message = self.messages[self.original_message_index]['content']
        
        # Add final turn section
        final_section = f"""

## Final Turn Instructions ({self.turn_count}/{self.max_turns})

You have reached the final turn. You MUST now use the `update_function_block` action to provide your complete solution based on all the debugging you've done.

**Requirements**:
1. Action type MUST be: update_function_block
2. Include complete working code that addresses the original error
3. Include all necessary imports in the code
4. Update requirements list if new packages are needed
5. Consider all the actions performed above and incorporate the fixes
6. NO PLACEHOLDER CODE - Every line must be functional:
   - NO commented-out implementations like "# method() # TODO: fix this"
   - NO fake column names like 'placeholder_key' 
   - NO template-style comments like "# Example: scFates analysis steps would go here"
   - NO phrases like "placeholder for actual analysis code" or "steps would go here"
   - NO template patterns like "# Process data", "# ... your analysis code ..."
   - If a package doesn't exist, use an alternative or raise a clear error
   - The code must be ready to execute, not a template
   - Write ACTUAL implementation code, not suggestions for code

**Current Status**:
- Original Error: {self.error_tracker.initial_error_type if hasattr(self.error_tracker, 'initial_error_type') else 'See above'}
- Files Explored: {', '.join(self.files_modified) if self.files_modified else 'function_block.py'}
- Actions Taken: {self.turn_count - 1} actions performed

Please provide your complete solution now."""
        
        # Update the message
        self.messages[self.original_message_index]['content'] = original_message + final_section
    
    def _add_final_turn_instructions(self):
        """Deprecated method - kept for compatibility."""
        # This method is now replaced by _update_conversation_for_final_turn
        self._update_conversation_for_final_turn()
    
    def _get_llm_action(self) -> Dict[str, Any]:
        """Get action from LLM with response logging.
        
        Uses text parsing for bug fixer actions because OpenAI's strict JSON mode
        requires ALL properties to be in the required array, which doesn't work
        for our flexible action schema where different actions need different fields.
        """
        # Log LLM input
        logger.info("\n" + "="*80)
        logger.info("BUG FIXER LLM INPUT:")
        logger.info(f"Model: {self.llm_service.model}")
        logger.info(f"Turn: {self.turn_count}/{self.max_turns}")
        logger.info(f"Messages count: {len(self.messages)}")
        
        # Log message summary
        for i, msg in enumerate(self.messages):
            role = msg['role']
            content_len = len(msg['content'])
            logger.info(f"Message {i+1} [{role}] ({content_len} chars)")
        
        logger.info("\n--- LAST USER MESSAGE ---")
        # Display full message (no truncation)
        logger.info(self.messages[-1]['content'])
        logger.info("--- END OF MESSAGE ---")
        logger.info("="*80 + "\n")
        
        # Use text mode for bug fixer actions
        # JSON mode doesn't work with our flexible action schema due to OpenAI's
        # requirement that ALL properties must be in the required array
        try:
            response_text = self.llm_service.call_llm(
                messages=self.messages,
                temperature=0.1
            )
            
            # Log LLM output - show more content (5000 chars)
            logger.info("\n" + "="*80)
            logger.info("BUG FIXER LLM OUTPUT:")
            logger.info(response_text[:5000] + "..." if len(response_text) > 5000 else response_text)
            logger.info("="*80 + "\n")
            
            # Parse response
            parsed = self._parse_action_from_text(response_text)
            if parsed:
                parsed['llm_response'] = response_text
                return parsed
            else:
                logger.error("Failed to parse action from LLM response")
                return None
            
        except Exception as e:
            logger.error(f"Error getting LLM response: {e}")
            return None
    
    def _parse_action_from_text(self, text: str) -> Dict[str, Any]:
        """Parse action from text response using the single JSON parser."""
        from agents.unified_bug_fixer.json_parser import JSONParser
        
        # Log the raw response for debugging
        logger.info(f"Parsing LLM response (length: {len(text)})")
        logger.debug(f"Raw LLM response: {text[:5000]}{'...' if len(text) > 5000 else ''}")
        
        # Use the single JSON parser
        parsed_action, error_msg = JSONParser.parse_action(text)
        
        if parsed_action:
            logger.info(f"Successfully parsed action: {parsed_action.get('type')}")
            # Add the raw LLM response for logging
            parsed_action['llm_response'] = text
            return parsed_action
        else:
            # Log the parsing failure
            logger.error("="*80)
            logger.error("JSON PARSING FAILED")
            logger.error(f"Error: {error_msg}")
            logger.error(f"Raw LLM Response (first 1000 chars):")
            logger.error(text[:1000])
            if len(text) > 1000:
                logger.error("... (truncated)")
            logger.error("="*80)
            
            # Return a special action that indicates parsing failed
            # This will be included in the next turn's prompt
            return {
                'type': 'PARSING_FAILED',
                'error': error_msg,
                'raw_response': text[:2000],  # Include first 2000 chars for context
                'llm_response': text
            }
    def _create_enhanced_followup_prompt(self, action_result: Dict, explanation: str) -> str:
        """Create enhanced followup prompt with domain knowledge injection."""
        base_followup = create_followup_prompt(action_result, explanation)
        
        # Add error resolution status
        if self.error_tracker.is_resolved:
            base_followup += "\n\n✅ **SUCCESS**: The error has been resolved! The function block now executes successfully."
        
        # Inject domain knowledge if enabled
        if self.enable_domain_knowledge and self.prompt_injector:
            # Add domain knowledge reminder section
            domain_knowledge_reminder = "\n\n## Domain Knowledge Reminder\n"
            domain_knowledge_reminder += "Relevant domain-specific knowledge has been injected to help guide your debugging:\n"
            domain_knowledge_reminder += "- API changes and migration patterns\n"
            domain_knowledge_reminder += "- Common error fixes and best practices\n"
            domain_knowledge_reminder += "- Package-specific implementation guidance\n"
            
            # Inject domain knowledge into the prompt
            enhanced_prompt = base_followup + domain_knowledge_reminder
            enhanced_prompt = self.prompt_injector.inject_domain_knowledge(
                enhanced_prompt, self.domain_knowledge_domains
            )
            
            logger.info(f"Injected domain knowledge into follow-up prompt for domains: {self.domain_knowledge_domains}")
            return enhanced_prompt
        
        return base_followup
    
    def _save_enhanced_turn_log(self, turn: int, action: Dict, action_result: Dict, explanation: str, llm_response: str, messages_before_llm: List[Dict] = None):
        """Save enhanced turn log with clear sections."""
        if not self.node_dir or not self.attempt_number:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Markdown log
        md_file = self.node_dir / "agent_tasks" / "bug_fixer" / f"attempt_{self.attempt_number}" / f"turn_{turn}_{timestamp}.md"
        md_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(md_file, 'w') as f:
            f.write(f"# Debug Turn {turn} - {timestamp}\n\n")
            f.write(f"**Attempt:** {self.attempt_number}\n")
            f.write(f"**Turn:** {turn}/{self.max_turns}\n")
            f.write(f"**Timestamp:** {datetime.now().isoformat()}\n\n")
            
            # Section 1: Action Taken
            f.write("## 1. Action Taken\n\n")
            f.write(f"**Action Type:** `{action['type']}`\n\n")
            f.write("**Action Parameters:**\n")
            f.write("```json\n")
            f.write(json.dumps(action, indent=2))
            f.write("\n```\n\n")
            
            # Section 2: Action Result
            f.write("## 2. Action Result\n\n")
            f.write(f"**Success:** {action_result.get('success', False)}\n")
            
            if action['type'] == 'update_function_block':
                re_exec = action_result.get('re_execution', {})
                if re_exec:
                    f.write(f"**Re-execution Status:**\n")
                    f.write(f"- Exit Code: {re_exec.get('exit_code')}\n")
                    f.write(f"- Function Executed: {re_exec.get('function_executed', False)}\n")
                    f.write(f"- Function Success: {re_exec.get('success', False)}\n")
                    f.write(f"- Actual Error: {re_exec.get('actual_error', 'None')}\n")
                    f.write(f"- Output Files: {re_exec.get('output_files', [])}\n")
                    f.write(f"- Has Output: {re_exec.get('has_output', False)}\n")
                    
                    # Log stdout/stderr snippets if available
                    if re_exec.get('stdout'):
                        stdout_lines = re_exec['stdout'].strip().split('\n')[:10]
                        f.write(f"- STDOUT Preview:\n")
                        for line in stdout_lines:
                            f.write(f"  {line}\n")
                        if len(re_exec['stdout'].strip().split('\n')) > 10:
                            f.write(f"  ... (truncated)\n")
                    
                    if re_exec.get('stderr'):
                        stderr_lines = re_exec['stderr'].strip().split('\n')[:10]
                        f.write(f"- STDERR Preview:\n")
                        for line in stderr_lines:
                            f.write(f"  {line}\n")
                        if len(re_exec['stderr'].strip().split('\n')) > 10:
                            f.write(f"  ... (truncated)\n")
            
            if action_result.get('error'):
                f.write(f"**Error:** {action_result['error']}\n")
            
            f.write("\n### Full Result\n")
            f.write("```json\n")
            f.write(json.dumps(action_result, indent=2))
            f.write("\n```\n\n")
            
            # Section 3: LLM Response
            f.write("## 3. LLM Response\n\n")
            f.write("### Explanation\n")
            f.write(explanation + "\n\n")
            
            f.write("### Raw LLM Output\n")
            if llm_response:
                f.write("```\n")
                f.write(llm_response)
                f.write("\n```\n\n")
            else:
                f.write("*No raw LLM output captured - this may indicate an issue with response logging*\n\n")
            
            # Section 4: Raw LLM Input for This Turn
            f.write("## 4. Raw LLM Input for This Turn\n\n")
            if messages_before_llm:
                f.write(f"*Messages sent to LLM for turn {turn} ({len(messages_before_llm)} messages total)*\n\n")
                
                # Show complete messages sent to LLM for this specific turn
                f.write("### Complete Messages Array (JSON)\n")
                f.write("```json\n")
                f.write(json.dumps(messages_before_llm, indent=2))
                f.write("\n```\n\n")
                
                # Also show a formatted view for readability
                f.write("### Formatted Message View\n\n")
                for i, msg in enumerate(messages_before_llm):
                    f.write(f"#### Message {i+1} - {msg['role'].upper()}\n")
                    if msg['role'] == 'system':
                        f.write("*System instructions for bug fixing*\n\n")
                        # Show first 500 chars of system message
                        content = msg['content']
                        if len(content) > 500:
                            f.write(f"```\n{content[:500]}...\n\n[Truncated - full content is {len(content)} chars]\n```\n\n")
                        else:
                            f.write(f"```\n{content}\n```\n\n")
                    elif msg['role'] == 'user':
                        f.write("*User message with error details and action history*\n\n")
                        # Show full user message since it contains the important context
                        f.write(f"```\n{msg['content']}\n```\n\n")
                    elif msg['role'] == 'assistant':
                        f.write("*Previous assistant response*\n\n")
                        f.write(f"```\n{msg['content']}\n```\n\n")
            else:
                f.write("*No messages captured for this turn - this may indicate an issue*\n\n")
            
            # Section 5: Error State (was Section 4)
            f.write("## 5. Error State\n\n")
            current_turn_data = self.error_tracker.turns[-1] if self.error_tracker.turns else {}
            error_state = current_turn_data.get('error_state', {})
            f.write(f"**Initial Error Type:** {error_state.get('initial_error_type', 'Unknown')}\n")
            f.write(f"**Current Error:** {error_state.get('current_error', 'Unknown')[:200]}...\n")
            f.write(f"**Is Resolved:** {error_state.get('is_resolved', False)}\n")
            
            if self.error_tracker.is_resolved:
                f.write(f"\n✅ **Error resolved in this turn!**\n")
            
            # Section 6: Full LLM Input (Message History)
            f.write("\n## 6. Full LLM Input (Message History)\n\n")
            f.write(f"*Total messages in conversation: {len(self.messages)}*\n\n")
            
            # Write a more detailed breakdown
            for i, msg in enumerate(self.messages):
                f.write(f"### Message {i+1} - Role: {msg['role']}\n")
                if msg['role'] == 'system':
                    f.write(f"*System prompt ({len(msg['content'])} chars)*\n")
                elif msg['role'] == 'user':
                    f.write(f"*User message ({len(msg['content'])} chars)*\n")
                elif msg['role'] == 'assistant':
                    f.write(f"*Assistant response ({len(msg['content'])} chars)*\n")
                f.write("\n")
            
            f.write("\n### Full Message History (JSON)\n")
            f.write("```json\n")
            f.write(json.dumps(self.messages, indent=2))
            f.write("\n```\n")
        
        # JSON log
        json_file = md_file.with_suffix('.json')
        with open(json_file, 'w') as f:
            json.dump({
                "attempt": self.attempt_number,
                "turn": turn,
                "timestamp": timestamp,
                "action": action,
                "action_result": action_result,
                "explanation": explanation,
                "llm_response": llm_response,
                "error_state": current_turn_data.get('error_state', {}),
                "llm_input_messages": self.messages,
                "llm_input_for_this_turn": messages_before_llm or []
            }, f, indent=2)
    
    def _save_llm_raw_io(self, turn: int, messages_input: List[Dict], raw_output: str):
        """Save raw LLM input/output in a dedicated file for easy access."""
        if not self.node_dir or not self.attempt_number:
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create dedicated LLM I/O file
        llm_io_file = self.node_dir / "agent_tasks" / "bug_fixer" / f"attempt_{self.attempt_number}" / f"llm_io_turn_{turn}_{timestamp}.md"
        llm_io_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(llm_io_file, 'w') as f:
            f.write(f"# Raw LLM Input/Output - Turn {turn}\n\n")
            f.write(f"**Timestamp:** {datetime.now().isoformat()}\n")
            f.write(f"**Attempt:** {self.attempt_number}\n")
            f.write(f"**Turn:** {turn}/{self.max_turns}\n")
            f.write(f"**Model:** {getattr(self.llm_service, 'model', 'Unknown')}\n\n")
            
            f.write("## 1. RAW LLM INPUT\n\n")
            f.write(f"*Exact messages array sent to LLM API ({len(messages_input or [])} messages)*\n\n")
            f.write("```json\n")
            f.write(json.dumps(messages_input or [], indent=2))
            f.write("\n```\n\n")
            
            f.write("## 2. RAW LLM OUTPUT\n\n")
            f.write("*Exact response received from LLM API*\n\n")
            if raw_output:
                f.write("```\n")
                f.write(raw_output)
                f.write("\n```\n")
            else:
                f.write("*No output captured*\n")
                
        # Also save as JSON for programmatic access
        llm_io_json = llm_io_file.with_suffix('.json')
        with open(llm_io_json, 'w') as f:
            json.dump({
                "turn": turn,
                "attempt": self.attempt_number,
                "timestamp": timestamp,
                "model": getattr(self.llm_service, 'model', 'Unknown'),
                "input_messages": messages_input or [],
                "raw_output": raw_output or ""
            }, f, indent=2)
    
    def _save_error_tracking_summary(self):
        """Save comprehensive error tracking summary."""
        if not self.node_dir:
            return
        
        # Save to attempt-specific directory if available
        if hasattr(self, 'bug_fixer_attempt_dir') and self.bug_fixer_attempt_dir:
            summary_file = self.bug_fixer_attempt_dir / "error_tracking_summary.json"
        else:
            summary_file = self.node_dir / "agent_tasks" / "bug_fixer" / "error_tracking_summary.json"
        
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        
        summary = self.error_tracker.get_resolution_summary()
        summary['session_duration_seconds'] = (datetime.now() - self.session_start).total_seconds()
        summary['files_modified'] = list(self.files_modified)
        summary['attempt_number'] = self.attempt_number if hasattr(self, 'attempt_number') else 1
        
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
    
    def _extract_error_summary(self) -> str:
        """Extract error summary when debugging fails."""
        summary = f"Debug session ended after {self.turn_count} turns.\n"
        
        if self.error_tracker:
            tracking_summary = self.error_tracker.get_resolution_summary()
            summary += f"Initial error: {tracking_summary['initial_error_type']}\n"
            summary += f"Error resolved: {tracking_summary['is_resolved']}\n"
            
            if tracking_summary['turns_summary']:
                summary += "\nActions taken:\n"
                for turn in tracking_summary['turns_summary']:
                    for action in turn['actions']:
                        summary += f"- Turn {turn['turn']}: {action['type']} ({'success' if action['success'] else 'failed'})\n"
        
        return summary
    
    def _get_input_directory_tree(self) -> str:
        """Get complete workspace structure for the bug fixer, showing FULL recursive directory tree."""
        workspace_structure = []
        
        # First, show the top-level workspace structure (critical for understanding file locations)
        workspace_structure.append("## WORKSPACE STRUCTURE\n")
        workspace_structure.append("```")
        workspace_structure.append("/workspace/                    # Container working directory")
        workspace_structure.append("├── function_block.py          # Main Python code file (or function_block.R for R)")
        workspace_structure.append("├── requirements.txt           # Package dependencies")
        workspace_structure.append("├── input/                     # Input data directory")
        workspace_structure.append("│   ├── [data files]          # Direct input files from parent node")
        workspace_structure.append("│   ├── previous_nodes/       # Outputs from all ancestor nodes")
        workspace_structure.append("│   │   ├── node_1/          # First ancestor node")
        workspace_structure.append("│   │   │   ├── inputs/      # Its input files")
        workspace_structure.append("│   │   │   └── outputs/     # Its output files")
        workspace_structure.append("│   │   └── node_N/          # Other ancestor nodes...")
        workspace_structure.append("│   └── _node_failure_context.json  # (Optional) Previous failure info")
        workspace_structure.append("└── output/                    # Output directory (create if needed)")
        workspace_structure.append("```\n")
        
        workspace_structure.append("## COMPLETE INPUT DIRECTORY TREE (FULL RECURSIVE)\n")
        workspace_structure.append("*Showing ALL files and subdirectories, no depth limits*\n")
        
        try:
            # Use tree without depth limit to show EVERYTHING
            # Add -a to show hidden files, --dirsfirst for better organization
            # Don't limit the output - we want to see everything!
            result = self.action_executor.execute_action({
                'type': 'execute_command',
                'command': 'tree /workspace/input -a --dirsfirst 2>/dev/null || find /workspace/input -type f -o -type d | sort'
            })
            
            if result.get('success') and result.get('stdout'):
                lines = result['stdout'].strip().split('\n')
                # Only truncate if absolutely massive (>1000 lines)
                # But still show much more than before
                if len(lines) > 1000:
                    # Show first 800 lines and last 150 lines - much more generous
                    truncated = lines[:800] + [
                        "",
                        f"... ({len(lines) - 950} more lines - showing important parts) ...",
                        "",
                        "... Final directory entries ..."
                    ] + lines[-150:]
                    workspace_structure.append('\n'.join(truncated))
                else:
                    # Show everything if under 1000 lines
                    workspace_structure.append(result['stdout'])
            else:
                # Enhanced fallback: Use find with better formatting to build a tree-like structure
                result = self.action_executor.execute_action({
                    'type': 'execute_command',
                    'command': '''find /workspace/input -print | sort | awk '
                        function basename(path) {
                            sub(/.*\\//, "", path)
                            return path
                        }
                        function depth(path) {
                            gsub(/[^\\/]/, "", path)
                            return length(path)
                        }
                        {
                            d = depth($0) - depth("/workspace/input")
                            for (i=0; i<d; i++) printf "  "
                            if (system("test -d \\"" $0 "\\"") == 0)
                                print "├── " basename($0) "/"
                            else
                                print "├── " basename($0)
                        }' '''
                })
                
                if result.get('success') and result.get('stdout'):
                    lines = result['stdout'].strip().split('\n')
                    # Be very generous with fallback too
                    if len(lines) > 1000:
                        truncated = lines[:800] + [
                            f"... ({len(lines) - 950} more entries) ...",
                            "... (showing last 150 entries) ..."
                        ] + lines[-150:]
                        workspace_structure.append('\n'.join(truncated))
                    else:
                        workspace_structure.append(result['stdout'])
                else:
                    # Last resort: Use Python to build a detailed tree recursively
                    result = self.action_executor.execute_action({
                        'type': 'execute_command',
                        'command': '''python -c "
import os
import sys

def print_tree(path, prefix='', is_last=True, max_depth=None, current_depth=0):
    try:
        entries = sorted(os.listdir(path))
    except PermissionError:
        return
    
    dirs = [e for e in entries if os.path.isdir(os.path.join(path, e))]
    files = [e for e in entries if os.path.isfile(os.path.join(path, e))]
    
    # Combine dirs first, then files
    all_entries = dirs + files
    
    for i, entry in enumerate(all_entries):
        is_last_entry = (i == len(all_entries) - 1)
        entry_path = os.path.join(path, entry)
        
        # Print the entry
        connector = '└── ' if is_last_entry else '├── '
        if os.path.isdir(entry_path):
            print(f'{prefix}{connector}{entry}/')
            # Recursively print subdirectory
            extension = '    ' if is_last_entry else '│   '
            print_tree(entry_path, prefix + extension, is_last_entry)
        else:
            try:
                size = os.path.getsize(entry_path)
                print(f'{prefix}{connector}{entry} ({size} bytes)')
            except:
                print(f'{prefix}{connector}{entry}')

print('/workspace/input/')
print_tree('/workspace/input/')
"'''
                    })
                    
                    if result.get('success') and result.get('stdout'):
                        lines = result['stdout'].strip().split('\n')
                        if len(lines) > 1000:
                            truncated = lines[:800] + [
                                f"... ({len(lines) - 950} more lines) ...",
                                "... (showing last 150 lines) ..."
                            ] + lines[-150:]
                            workspace_structure.append('\n'.join(truncated))
                        else:
                            workspace_structure.append(result['stdout'])
                    else:
                        workspace_structure.append("(Unable to generate detailed tree)")
                        
        except Exception as e:
            logger.warning(f"Failed to get directory tree: {e}")
            workspace_structure.append("(Error getting directory tree)")
        
        # Add a section showing file counts by directory
        workspace_structure.append("\n## FILE STATISTICS\n")
        try:
            result = self.action_executor.execute_action({
                'type': 'execute_command',
                'command': '''for dir in $(find /workspace/input -type d | head -20); do 
                    count=$(find "$dir" -maxdepth 1 -type f | wc -l)
                    echo "$dir: $count files"
                done'''
            })
            if result.get('success') and result.get('stdout'):
                workspace_structure.append(result['stdout'])
        except:
            pass
        
        return '\n'.join(workspace_structure)
    
    def _save_action_digest_files(self, turn: int, action: Dict, original_result: str, digest) -> None:
        """Save both raw and digested action outputs to files.
        
        Args:
            turn: Current debug turn number
            action: Action that was executed
            original_result: Raw action output before digestion
            digest: ActionDigest object containing compressed information
        """
        try:
            # Create action digests directory
            digests_dir = self.node_dir / "agent_tasks" / "action_digests"
            digests_dir.mkdir(parents=True, exist_ok=True)
            
            action_type = action.get('type', 'unknown')
            timestamp = datetime.now().strftime('%H%M%S')
            base_filename = f"turn_{turn:02d}_{action_type}_{timestamp}"
            
            # Save raw output
            raw_file = digests_dir / f"{base_filename}_raw.txt"
            with open(raw_file, 'w', encoding='utf-8') as f:
                f.write(f"# Raw Action Output - Turn {turn}\n")
                f.write(f"# Action: {action_type}\n")
                f.write(f"# Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"# Original Length: {len(original_result)} characters\n")
                f.write("# Action Parameters:\n")
                for key, value in action.items():
                    if key != 'type':
                        f.write(f"#   {key}: {str(value)[:100]}{'...' if len(str(value)) > 100 else ''}\n")
                f.write("\n" + "="*80 + "\n\n")
                f.write(original_result)
            
            # Save digested output
            digest_file = digests_dir / f"{base_filename}_digest.json"
            with open(digest_file, 'w', encoding='utf-8') as f:
                digest_data = {
                    "metadata": {
                        "turn": turn,
                        "action_type": action_type,
                        "timestamp": datetime.now().isoformat(),
                        "original_length": digest.original_length,
                        "compression_ratio": digest.compression_ratio
                    },
                    "digest": digest.to_dict(),
                    "action_parameters": action
                }
                json.dump(digest_data, f, indent=2, ensure_ascii=False)
            
            # Save human-readable digest
            readable_file = digests_dir / f"{base_filename}_digest.md"
            with open(readable_file, 'w', encoding='utf-8') as f:
                f.write(f"# Action Digest - Turn {turn}\n\n")
                f.write(f"**Action Type:** {action_type}\n")
                f.write(f"**Timestamp:** {datetime.now().isoformat()}\n")
                f.write(f"**Original Length:** {digest.original_length:,} characters\n")
                f.write(f"**Compression Ratio:** {digest.compression_ratio:.2%}\n\n")
                
                f.write("## Summary\n\n")
                f.write(f"{digest.summary}\n\n")
                
                if digest.key_findings:
                    f.write("## Key Findings\n\n")
                    for finding in digest.key_findings:
                        f.write(f"- {finding}\n")
                    f.write("\n")
                
                if digest.preserved_evidence.get('error_messages'):
                    f.write("## Error Messages\n\n")
                    for error in digest.preserved_evidence['error_messages']:
                        f.write(f"```\n{error}\n```\n\n")
                
                if digest.actionable_insights:
                    f.write("## Actionable Insights\n\n")
                    for insight in digest.actionable_insights:
                        f.write(f"- {insight}\n")
                    f.write("\n")
                
                f.write(f"**Requires Follow-up:** {'Yes' if digest.requires_followup else 'No'}\n")
            
            logger.info(f"Saved action digest files: {base_filename}_{{raw.txt,digest.json,digest.md}}")
            
        except Exception as e:
            logger.error(f"Failed to save action digest files: {e}")

    def _check_if_fixed(self) -> Tuple[bool, str]:
        """Check if the error has been fixed."""
        # This is now handled by the error tracker
        if self.error_tracker and self.error_tracker.is_resolved:
            return True, "Error resolved successfully"
        return False, "Error not yet resolved"