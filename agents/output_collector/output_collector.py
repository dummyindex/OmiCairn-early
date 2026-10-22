"""Output Collector Agent that collects scattered outputs after function execution."""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Union
from datetime import datetime

from utils import setup_logger
from job_executors.container_actions import (
    BaseContainerActionHandler, 
    ALLOWED_ACTIONS_OUTPUT_COLLECTOR
)
from agents.unified_bug_fixer.action_input_validator import ActionInputValidator

logger = setup_logger(__name__)


class OutputCollectorAgent:
    """Agent that collects outputs from various locations in container after execution."""
    
    def __init__(self, 
                 llm_service,
                 container,
                 working_dir: str = "/workspace",
                 max_turns: int = 5,
                 enable_domain_knowledge: bool = True,
                 prompt_injector=None,
                 domain_knowledge_domains: List[str] = None):
        """Initialize output collector agent.
        
        Args:
            llm_service: LLM service for intelligent collection decisions
            container: Docker container instance
            working_dir: Working directory in container
            max_turns: Maximum collection turns
            enable_domain_knowledge: Whether to use domain knowledge
            prompt_injector: Domain knowledge prompt injector
            domain_knowledge_domains: List of domain knowledge areas to use
        """
        self.llm_service = llm_service
        self.container = container
        self.working_dir = working_dir
        self.max_turns = max_turns
        self.enable_domain_knowledge = enable_domain_knowledge
        self.prompt_injector = prompt_injector
        self.domain_knowledge_domains = domain_knowledge_domains or ['single_cell_genomics']
        
        # Create action handler
        self.action_handler = BaseContainerActionHandler(
            container=container,
            working_dir=working_dir,
            allowed_actions=ALLOWED_ACTIONS_OUTPUT_COLLECTOR
        )
        
    def collect_outputs(self, 
                       job_dir: Path, 
                       output_dir: Path,
                       node_name: str,
                       function_type: str = "python") -> Dict[str, Any]:
        """Main collection logic using multi-turn LLM-guided approach.
        
        Args:
            job_dir: Job directory on host
            output_dir: Expected output directory in container
            node_name: Name of the node being processed
            function_type: Type of function (python/R)
            
        Returns:
            Collection result with summary and logs
        """
        # Initialize collection state
        collected_files = []
        actions_taken = []
        turn_logs = []
        
        # Container paths
        container_output_dir = str(output_dir).replace(str(job_dir), "/workspace")
        
        logger.info(f"Starting output collection for node: {node_name}")
        logger.info(f"Container output directory: {container_output_dir}")
        
        # Create agent tasks directory for logging
        agent_tasks_dir = job_dir / "agent_tasks" / "output_collector"
        agent_tasks_dir.mkdir(parents=True, exist_ok=True)
        
        # Run collection turns
        for turn in range(self.max_turns):
            logger.info(f"Output collection turn {turn + 1}/{self.max_turns}")
            
            # Get current state
            current_state = self._get_current_state(
                container_output_dir, 
                collected_files,
                actions_taken
            )
            
            # Build prompt for this turn
            prompt = self._build_collection_prompt(
                node_name=node_name,
                function_type=function_type,
                output_dir=container_output_dir,
                current_state=current_state,
                turn_number=turn + 1,
                max_turns=self.max_turns
            )
            
            # Get LLM response
            response = self._get_llm_response(prompt)
            
            # Parse actions from response
            actions = self._parse_actions(response)
            
            # Execute actions
            turn_results = []
            for action in actions:
                result = self.action_handler.execute_action(action)
                turn_results.append({
                    'action': action,
                    'result': result
                })
                actions_taken.append(action)
                
                # Track collected files
                if action['type'] == 'copy_file' and result.get('success'):
                    collected_files.append({
                        'source': action['source'],
                        'destination': action['destination'],
                        'turn': turn + 1
                    })
            
            # Log turn
            turn_log = {
                'turn': turn + 1,
                'timestamp': datetime.now().isoformat(),
                'prompt': prompt,
                'response': response,
                'actions': actions,
                'results': turn_results
            }
            turn_logs.append(turn_log)
            
            # Save turn log
            turn_log_file = agent_tasks_dir / f"turn_{turn + 1:02d}.json"
            with open(turn_log_file, 'w') as f:
                json.dump(turn_log, f, indent=2)
            
            # Check if collection is complete
            if self._is_collection_complete(actions, turn_results):
                logger.info("Output collection complete")
                break
        
        # Generate summary
        summary = self._generate_summary(
            collected_files=collected_files,
            actions_taken=actions_taken,
            turn_logs=turn_logs
        )
        
        # Save summary
        summary_file = agent_tasks_dir / "collection_summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Save human-readable report
        report = self._generate_report(summary)
        report_file = agent_tasks_dir / "collection_report.md"
        with open(report_file, 'w') as f:
            f.write(report)
        
        logger.info(f"Output collection completed. Collected {len(collected_files)} files")
        
        return summary
    
    def _get_current_state(self, output_dir: str, collected_files: List, actions_taken: List) -> Dict[str, Any]:
        """Get current state of output directory and working directory."""
        state = {
            'output_directory': {},
            'working_directory': {},
            'collected_files': collected_files,
            'actions_taken_count': len(actions_taken)
        }
        
        # Check output directory
        result = self.action_handler.execute_action({
            'type': 'tree_directory',
            'path': output_dir,
            'max_depth': 2
        })
        if result.get('success'):
            state['output_directory']['tree'] = result.get('tree', '')
        
        # Check working directory for common output locations
        for subdir in ['figures', 'plots', 'results', '.']:
            result = self.action_handler.execute_action({
                'type': 'list_directory',
                'path': subdir
            })
            if result.get('success'):
                state['working_directory'][subdir] = result.get('entries', [])
        
        return state
    
    def _build_collection_prompt(self, 
                                node_name: str,
                                function_type: str,
                                output_dir: str,
                                current_state: Dict[str, Any],
                                turn_number: int,
                                max_turns: int) -> str:
        """Build prompt for output collection."""
        prompt_parts = []
        
        # System instructions
        prompt_parts.append("""You are an Output Collector Agent responsible for finding and collecting outputs that may have been saved to unexpected locations during function execution.

Your task is to:
1. Identify files that were likely created by the function but saved outside the expected output directory
2. Copy these files to the proper output directory structure
3. Preserve directory organization when copying

Key locations to check:
- Working directory (/workspace)
- ./figures or ./plots directories (common for plotting libraries)
- Current directory where the function was executed
- Any subdirectories mentioned in the function's stdout/stderr

Important guidelines:
- ALWAYS use copy_file action (not move_file) to preserve originals
- Create necessary subdirectories in the output directory
- Focus on files created recently (during this execution)
- Common output file types: .png, .jpg, .pdf, .svg (plots), .csv, .tsv (data), .h5ad (AnnData)
- Preserve directory structure (e.g., figures/plot.png -> output_dir/figures/plot.png)
""")
        
        # Add domain knowledge if enabled
        if self.enable_domain_knowledge and self.prompt_injector:
            # Get domain knowledge and inject it
            domain_knowledge = []
            for domain in self.domain_knowledge_domains:
                knowledge = self.prompt_injector.knowledge_service.get_knowledge_by_domain(domain)
                if knowledge:
                    domain_knowledge.append(knowledge)
            
            if domain_knowledge:
                combined_knowledge = "\n\n".join(domain_knowledge)
                prompt_parts.append("\nDomain Knowledge:")
                prompt_parts.append(combined_knowledge)
        
        # Add specific scanpy note
        if function_type == "python":
            prompt_parts.append("""
Note about scanpy: The scanpy library often saves figures to './figures/' relative to the current working directory, not the specified output directory. Check for any .png files in /workspace/figures/ or similar locations.""")
        
        # Current context
        prompt_parts.append(f"\nContext:")
        prompt_parts.append(f"- Node name: {node_name}")
        prompt_parts.append(f"- Function type: {function_type}")
        prompt_parts.append(f"- Expected output directory: {output_dir}")
        prompt_parts.append(f"- Turn: {turn_number}/{max_turns}")
        prompt_parts.append(f"- Files already collected: {len(current_state['collected_files'])}")
        
        # Current state
        prompt_parts.append("\nCurrent State:")
        prompt_parts.append(f"Output directory structure:\n{current_state['output_directory'].get('tree', 'Empty')}")
        
        if current_state['working_directory']:
            prompt_parts.append("\nWorking directory contents:")
            for subdir, entries in current_state['working_directory'].items():
                if entries:
                    prompt_parts.append(f"\n{subdir}:")
                    for entry in entries[:10]:  # Limit to first 10
                        if entry['type'] == 'file':
                            prompt_parts.append(f"  - {entry['name']} ({entry.get('size', 0)} bytes)")
        
        # Previous collections
        if current_state['collected_files']:
            prompt_parts.append("\nFiles already collected:")
            for file in current_state['collected_files'][-5:]:  # Last 5
                prompt_parts.append(f"  - {file['source']} -> {file['destination']}")
        
        # Action request with formatted documentation
        prompt_parts.append(f"""
Based on the above information, identify any output files that should be collected and copy them to the appropriate location in the output directory.

If no additional files need to be collected, return an empty list of actions.

{ActionInputValidator.format_actions_for_prompt(ALLOWED_ACTIONS_OUTPUT_COLLECTOR)}

Return a JSON array of actions. Example format:
[
    {{"type": "create_directory", "path": "{output_dir}/figures"}},
    {{"type": "find_files", "pattern": "*.png", "path": "/workspace/figures"}},
    {{"type": "copy_file", "source": "/workspace/plot.png", "destination": "{output_dir}/figures/plot.png"}}
]

Actions to take:""")
        
        return "\n".join(prompt_parts)
    
    def _get_llm_response(self, prompt: str) -> Union[str, Dict[str, Any], List[Dict[str, Any]]]:
        """Get response from LLM."""
        try:
            # Add any system messages if needed
            messages = [
                {"role": "system", "content": "You are an expert output collector agent. Always respond with valid JSON arrays of actions."},
                {"role": "user", "content": prompt}
            ]
            
            response = self.llm_service.chat_completion(
                messages=messages,
                temperature=0.3,  # Lower temperature for more deterministic responses
                response_format={"type": "json_object"}
            )
            
            return response
            
        except Exception as e:
            # Log with structured context
            logger.error(f"Error getting LLM response: {e}", extra={
                'error_category': 'llm_communication',
                'operation': 'chat_completion',
                'agent_type': 'output_collector',
                'context': {
                    'message_count': len(messages),
                    'temperature': 0.3,
                    'error_type': type(e).__name__
                },
                'recovery_hint': 'Check LLM service configuration and API availability'
            }, exc_info=True)
            
            # Return empty actions to allow graceful degradation
            # The caller can check for empty actions and handle appropriately
            return {"actions": [], "error": True, "error_message": str(e)}
    
    def _parse_actions(self, response: Union[str, Dict[str, Any], List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Parse and validate actions from LLM response."""
        try:
            raw_actions = []
            
            # Check if response is already a list
            if isinstance(response, list):
                raw_actions = response
            
            # Check if response is already a dictionary (from json_object format)
            elif isinstance(response, dict):
                # Handle OpenAI response format with 'content' key
                if 'content' in response and isinstance(response['content'], str):
                    try:
                        # Parse the content string as JSON
                        content_data = json.loads(response['content'])
                        if isinstance(content_data, dict) and 'actions' in content_data:
                            return content_data['actions']
                        elif isinstance(content_data, list):
                            return content_data
                    except json.JSONDecodeError as e:
                        logger.debug(f"Failed to parse content as JSON: {e}", extra={
                            'error_category': 'json_parsing',
                            'operation': '_parse_actions'
                        })
                        # Fall through to other checks
                
                # Direct actions key
                if 'actions' in response:
                    raw_actions = response['actions']
                else:
                    logger.warning(f"Dictionary response missing 'actions' key: {response}")
                    return []
            
            # Try to parse as JSON string
            else:
                data = json.loads(response)
                
                # Handle parsed data
                if isinstance(data, list):
                    raw_actions = data
                elif isinstance(data, dict) and 'actions' in data:
                    raw_actions = data['actions']
                else:
                    logger.warning(f"Unexpected parsed format: {type(data)}")
                    return []
            
            # Validate and clean each action using ActionInputValidator
            validated_actions = []
            for i, action in enumerate(raw_actions):
                validation_result = ActionInputValidator.validate_action(action)
                
                if validation_result['valid']:
                    validated_actions.append(validation_result['action'])
                    if validation_result['warnings']:
                        for warning in validation_result['warnings']:
                            logger.warning(f"Action {i}: {warning}")
                else:
                    logger.error(f"Invalid action {i}: {validation_result['errors']}")
                    logger.error(f"Skipping action: {action}")
            
            return validated_actions
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response: {response}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing actions: {e}")
            return []
    
    def _is_collection_complete(self, actions: List[Dict], results: List[Dict]) -> bool:
        """Check if collection is complete based on last turn."""
        # If no actions were suggested, collection is complete
        if not actions:
            return True
        
        # If all actions failed, might be complete
        all_failed = all(not r['result'].get('success', False) for r in results)
        if all_failed and len(results) > 0:
            return True
        
        return False
    
    def _generate_summary(self, 
                         collected_files: List[Dict],
                         actions_taken: List[Dict],
                         turn_logs: List[Dict]) -> Dict[str, Any]:
        """Generate collection summary."""
        # Count action types
        action_counts = {}
        for action in actions_taken:
            action_type = action.get('type', 'unknown')
            action_counts[action_type] = action_counts.get(action_type, 0) + 1
        
        # Categorize collected files
        file_categories = {
            'figures': [],
            'data': [],
            'other': []
        }
        
        for file in collected_files:
            source = file['source']
            if any(ext in source.lower() for ext in ['.png', '.jpg', '.pdf', '.svg']):
                file_categories['figures'].append(file)
            elif any(ext in source.lower() for ext in ['.csv', '.tsv', '.h5ad', '.h5']):
                file_categories['data'].append(file)
            else:
                file_categories['other'].append(file)
        
        summary = {
            'success': True,
            'total_files_collected': len(collected_files),
            'total_actions_taken': len(actions_taken),
            'turns_used': len(turn_logs),
            'action_counts': action_counts,
            'file_categories': {
                'figures': len(file_categories['figures']),
                'data': len(file_categories['data']),
                'other': len(file_categories['other'])
            },
            'collected_files': collected_files,
            'timestamp': datetime.now().isoformat()
        }
        
        return summary
    
    def _generate_report(self, summary: Dict[str, Any]) -> str:
        """Generate human-readable report."""
        report_lines = []
        
        report_lines.append("# Output Collection Report")
        report_lines.append(f"\n**Timestamp**: {summary['timestamp']}")
        report_lines.append(f"**Status**: {'Success' if summary['success'] else 'Failed'}")
        report_lines.append(f"**Total Files Collected**: {summary['total_files_collected']}")
        report_lines.append(f"**Total Actions Taken**: {summary['total_actions_taken']}")
        report_lines.append(f"**Turns Used**: {summary['turns_used']}")
        
        report_lines.append("\n## File Categories")
        for category, count in summary['file_categories'].items():
            report_lines.append(f"- {category.capitalize()}: {count} files")
        
        report_lines.append("\n## Actions Summary")
        for action_type, count in summary['action_counts'].items():
            report_lines.append(f"- {action_type}: {count} times")
        
        if summary['collected_files']:
            report_lines.append("\n## Collected Files")
            for file in summary['collected_files']:
                report_lines.append(f"- `{file['source']}` → `{file['destination']}` (Turn {file['turn']})")
        
        return "\n".join(report_lines)