"""Orchestrator agent that coordinates the overall analysis workflow with parallel execution."""

from typing import Dict, Any, List, Optional, Set
from pathlib import Path
from datetime import datetime
import uuid
import json
import logging

from agents.base_agent import BaseAgent
from agents.function_creator_agent import FunctionCreatorAgent
from agents.failure_context_config import get_failure_context_config
from models import (
    AnalysisTree, AnalysisNode, NodeState, GenerationMode,
    NewFunctionBlock
)
from analysis_tree_management import AnalysisTreeManager
from job_executors.job_pool import JobPool, JobResult, JobStatus, JobPriority
from constants import ROOT_NODE_NAME, MAX_REWORK_ATTEMPTS, DEFAULT_MAX_DEBUG_TRIALS
from models import JobReviewStatus


class OrchestratorAgent(BaseAgent):
    """Agent that orchestrates the entire analysis workflow with parallel execution."""
    
    def __init__(
        self, 
        llm_service=None,
        tree_manager: Optional[AnalysisTreeManager] = None,
        function_creator: Optional[FunctionCreatorAgent] = None,
        bug_fixer: Optional[Any] = None,  # Can be any bug fixer implementation
        job_reviewer: Optional[Any] = None,  # Job reviewer agent for validating completed nodes
        max_parallel_jobs: int = 3,
        llm_seed: Optional[int] = None
    ):
        super().__init__("orchestrator")
        self.llm_service = llm_service
        self.tree_manager = tree_manager
        self.function_creator = function_creator
        self.bug_fixer = bug_fixer
        self.job_reviewer = job_reviewer
        self.max_parallel_jobs = max_parallel_jobs
        self.llm_seed = llm_seed
        
        # Job pool for parallel execution
        self.job_pool: Optional[JobPool] = None
        
        # State tracking
        self.completed_nodes: Set[str] = set()
        self.failed_nodes: Set[str] = set()
        self.node_results: Dict[str, Dict[str, Any]] = {}
        self.expansion_decisions: Dict[str, Dict[str, Any]] = {}
        self._last_llm_interaction: Optional[Dict[str, Any]] = None  # Cache for LLM interactions
        
    def process(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Orchestrate the analysis workflow with parallel execution.
        
        Required context keys:
            - tree: AnalysisTree
            - user_request: str
            - max_iterations: int
            - node_executor: NodeExecutor (optional)
            - output_dir: Path (optional)
            
        Returns:
            Dict with:
                - satisfied: bool
                - iterations: int
                - final_state: str
                - completed_nodes: List[str]
                - failed_nodes: List[str]
        """
        self.validate_context(context, ['tree', 'user_request', 'max_iterations'])
        
        tree = context['tree']
        user_request = context['user_request']
        max_iterations = context['max_iterations']
        node_executor = context.get('node_executor')
        output_dir = context.get('output_dir', Path('output'))
        
        # Store user request for job reviewer access
        self.current_user_request = user_request
        
        # Initialize job pool
        self.job_pool = JobPool(
            max_parallel_jobs=self.max_parallel_jobs,
            executor_type="thread",
            enable_callbacks=True
        )
        
        # Reset state
        self.completed_nodes.clear()
        self.failed_nodes.clear()
        self.node_results.clear()
        self.expansion_decisions.clear()
        
        satisfied = False
        iteration = 0
        
        try:
            while not satisfied and iteration < max_iterations:
                iteration += 1
                
                # Check if we need to generate new nodes
                if self._needs_expansion(tree):
                    satisfied = self._expand_tree(tree, user_request, context)
                
                # Submit pending nodes for parallel execution
                pending_nodes = self._get_pending_nodes(tree)
                if pending_nodes and node_executor:
                    self._submit_nodes_for_execution(
                        pending_nodes, tree, node_executor, output_dir
                    )
                
                # Wait for some nodes to complete before continuing
                if self.job_pool.job_queue.qsize() > 0 or len(self.job_pool.running_jobs) > 0:
                    self._wait_for_node_completion(timeout=5.0)
                
                # Check if we're done
                if satisfied or not self.tree_manager.can_continue_expansion():
                    break
            
            # Wait for all remaining jobs to complete
            if node_executor:
                self.logger.info("Waiting for all jobs to complete...")
                all_results = self.job_pool.wait_for_all(timeout=300)
                self.logger.info(f"All jobs completed: {len(all_results)} total")
                
        finally:
            # Cleanup
            if self.job_pool:
                self.job_pool.shutdown(wait=True)
                
        return {
            'satisfied': satisfied,
            'iterations': iteration,
            'final_state': self._get_tree_state(tree),
            'completed_nodes': list(self.completed_nodes),
            'failed_nodes': list(self.failed_nodes)
        }
    
    def _submit_nodes_for_execution(
        self,
        nodes: List[AnalysisNode],
        tree: AnalysisTree,
        node_executor,
        output_dir: Path
    ):
        """Submit nodes for parallel execution."""
        for node in nodes:
            if node.id in self.node_results:
                continue  # Already submitted
            
            # Determine dependencies
            dependencies = set()
            if node.parent_id and node.parent_id not in self.completed_nodes:
                dependencies.add(f"node_{node.parent_id}")  # Job ID format
            
            # Submit job
            job_id = self.job_pool.submit_job(
                node_id=node.id,
                tree_id=tree.id,
                execute_fn=self._execute_node_wrapper,
                args=(node, tree, node_executor, output_dir),
                priority=JobPriority.NORMAL,
                callback=lambda result, n=node: self._handle_node_completion(n, result),
                dependencies=dependencies,
                metadata={
                    "node_name": node.function_block.name,
                    "node_level": node.level
                }
            )
            
            # Track submission
            self.node_results[node.id] = {
                "job_id": job_id,
                "status": NodeState.PENDING
            }
            
            self.logger.info(f"Submitted node {node.id} for execution (job_id={job_id})")
    
    def _execute_node_wrapper(
        self,
        node: AnalysisNode,
        tree: AnalysisTree,
        node_executor,
        output_dir: Path
    ) -> Dict[str, Any]:
        """Wrapper for node execution to handle errors."""
        try:
            # Get input path from parent if available
            input_path = tree.input_data_path
            if node.parent_id and node.parent_id in self.node_results:
                parent_result = self.node_results[node.parent_id]
                if parent_result.get('output_path'):
                    input_path = parent_result['output_path']
            
            # Execute node
            state, output_path, execution_result = node_executor.execute_node(
                node=node,
                tree=tree,
                input_path=input_path,
                output_base_dir=output_dir
            )
            
            result_dict = {
                "node_id": node.id,
                "state": state,
                "output_path": str(output_path) if output_path else None
            }
            
            # Add execution result if available
            if execution_result:
                result_dict["execution_result"] = execution_result
                # Also add output files for job reviewer
                result_dict["output_files"] = execution_result.figures if execution_result.figures else []
            
            return result_dict
            
        except Exception as e:
            self.logger.error(f"Error executing node {node.id}: {e}")
            return {
                "node_id": node.id,
                "state": NodeState.FAILED,
                "error": str(e)
            }
    
    def _handle_node_completion(self, node: AnalysisNode, job_result: JobResult):
        """Handle node completion with reactive expansion."""
        self.logger.info(f"Node {node.id} completed with status {job_result.status}")
        
        if job_result.status == JobStatus.COMPLETED:
            result = job_result.result
            self.node_results[node.id].update(result)
            
            if result['state'] == NodeState.COMPLETED:
                # Apply job review if enabled
                if self.job_reviewer and 'execution_result' in result:
                    # Skip job review for system-generated root node
                    if node.function_block.name == ROOT_NODE_NAME and not node.parent_id:
                        self.logger.info("Skipping job review for system-generated root node")
                        node.job_review_status = JobReviewStatus.SKIPPED
                        node.job_review_summary = "System-generated root node - review skipped"
                    else:
                        self.logger.info(f"Reviewing completed function block for node {node.id}")
                        
                        try:
                            review_result = self.job_reviewer.review_function_block(
                                node=node,
                                function_block=node.function_block,
                                execution_result=result.get('execution_result'),
                                user_request=getattr(self, 'current_user_request', 'Unknown request'),
                                output_files=result.get('output_files', [])
                            )
                            
                            # Store review result in node
                            node.job_review_result = review_result.to_dict() if hasattr(review_result, 'to_dict') else review_result
                            node.job_review_summary = review_result.summary
                            
                            # Also store in node_results for backward compatibility
                            self.node_results[node.id]['job_review'] = review_result.to_dict()
                            
                            # Save Job Reviewer reports to node directory
                            if result.get('output_path'):
                                from pathlib import Path
                                node_dir = Path(result['output_path']).parent  # Go up one level from output to node dir
                                self.job_reviewer.save_reports_to_directory(node_dir)
                            
                            if review_result.passed:
                                self.logger.info(f"Node {node.id} passed job review")
                                node.job_review_status = JobReviewStatus.PASSED
                                node.needs_rework = False
                            else:
                                self.logger.warning(f"Job reviewer identified concerns for node {node.id}: {review_result.summary}")
                                node.job_review_status = JobReviewStatus.FAILED
                                
                                if self.job_reviewer.should_trigger_rework(review_result):
                                    self.logger.warning(f"Job reviewer recommends rework for node {node.id}")
                                    node.needs_rework = True
                                    
                                    # Get rework specification
                                    original_spec = {
                                        'name': node.function_block.name,
                                        'description': node.function_block.description,
                                        'type': node.function_block.type.value if hasattr(node.function_block.type, 'value') else node.function_block.type
                                    }
                                    rework_spec = self.job_reviewer.get_rework_specification(review_result, original_spec)
                                    
                                    # Store for potential rework by function creator
                                    self.node_results[node.id]['rework_specification'] = rework_spec
                                    self.node_results[node.id]['needs_rework'] = True
                                    
                                    self.logger.info(f"Node {node.id} needs rework based on job review")
                                else:
                                    # Review failed but not critical enough for rework
                                    node.needs_rework = False
                                    self.logger.info(f"Node {node.id} has review concerns but rework not required")
                                
                        except Exception as e:
                            self.logger.error(f"Job review failed for node {node.id}: {e}")
                            # Continue with execution even if review fails
                
                self.completed_nodes.add(node.id)
                
                # Make reactive expansion decision
                self._make_expansion_decision(node, result)
                
            elif result['state'] == NodeState.FAILED:
                self.failed_nodes.add(node.id)
                # Try to fix if possible
                if hasattr(self, 'handle_failed_node'):
                    self.handle_failed_node(
                        node,
                        result.get('error', 'Unknown error'),
                        '', ''
                    )
        else:
            self.failed_nodes.add(node.id)
            self.node_results[node.id]['state'] = NodeState.FAILED
    
    def _make_expansion_decision(self, node: AnalysisNode, result: Dict[str, Any]):
        """Make decision about expanding from completed node."""
        # Check if node should be expanded
        # Let the tree's max_nodes parameter control expansion limits
        # No hardcoded depth limits here
        
        # Simple heuristic: expand if node completed successfully
        # In future, use LLM to make intelligent decisions
        decision = {
            "should_expand": True,
            "reason": "Node completed successfully",
            "timestamp": datetime.now().isoformat()
        }
        
        self.expansion_decisions[node.id] = decision
    
    def plan_next_steps(self, task: dict) -> dict:
        """Plan next steps for analysis workflow.
        
        Args:
            task: Dictionary with user_request, tree_state, iteration, etc.
            
        Returns:
            Dictionary with satisfied flag and next_actions list
        """
        user_request = task.get("user_request", "")
        tree_state = task.get("tree_state", {})
        iteration = task.get("iteration", 1)
        output_dir = task.get("output_dir")  # Optional, for saving logs
        
        # SIMPLE REWORK LOGIC - No tree traversal, no chains, no complex mappings
        # Just check each node directly for its rework status
        rework_actions = []
        
        # Simple check for each node
        for node_info in tree_state.get('nodes', []):
            node_id = node_info['id']
            is_leaf = not node_info.get('children')
            is_failed = node_info.get('state') == 'failed'
            needs_job_review_rework = node_info.get('needs_rework', False)
            
            # CRITICAL FIX: Check if the node is already at rework limit
            # Check both field names for compatibility (rework_limit_reached is the model field)
            # Validate the flag exists and compute if missing
            if 'at_rework_limit' not in node_info and 'rework_limit_reached' not in node_info:
                # Safety check: compute based on rework_attempts if flag is missing
                self.logger.warning(f"Missing rework limit flag for node {node_id}, computing from rework_attempts")
                at_limit = node_info.get('rework_attempts', 0) >= MAX_REWORK_ATTEMPTS
            else:
                # Prefer model field name, fall back to legacy name
                at_limit = node_info.get('rework_limit_reached', node_info.get('at_rework_limit', False))
            
            if at_limit:
                self.logger.info(f"Skipping rework for {node_id} - at rework limit (flag set by system)")
                continue
            
            # Find the original node if this is a rework
            original_node_id = node_info.get('rework_of_node_id') or node_id
            
            # Count total rework attempts for this original task
            # Also check if this failed node itself already has reworks
            total_rework_attempts = 0
            existing_rework_ids = set()
            for n in tree_state.get('nodes', []):
                # Check reworks of the original
                if n.get('rework_of_node_id') == original_node_id:
                    total_rework_attempts = max(total_rework_attempts, n.get('rework_attempts', 0))
                    existing_rework_ids.add(n['id'])
                # Also check if this specific failed node has reworks
                if n.get('rework_of_node_id') == node_id:
                    # This node already has a rework, skip it
                    total_rework_attempts = MAX_REWORK_ATTEMPTS  # Force skip
            
            # Skip if already at rework limit
            if total_rework_attempts >= MAX_REWORK_ATTEMPTS:
                self.logger.info(f"Skipping rework for {node_id} - already at limit or has pending rework")
                continue
            
            # Skip if this node has a successful rework already
            # Check the has_successful_rework flag (set by MainAgent when rework succeeds)
            if node_info.get('has_successful_rework', False):
                self.logger.info(f"Node {node_id} already has successful rework - skipping")
                continue
                
            # Skip if there's already a rework in progress
            # Check if any node has rework_of_node_id pointing to this node
            has_rework_in_progress = False
            for other_node in tree_state.get('nodes', []):
                if other_node.get('rework_of_node_id') == node_id:
                    # Found a rework of this node
                    rework_state = other_node.get('state')
                    if rework_state in ['pending', 'running', 'completed']:
                        # Has active or successful rework
                        has_rework_in_progress = True
                        if rework_state == 'completed':
                            self.logger.info(f"Node {node_id} has successful rework {other_node['id']} - skipping")
                        else:
                            self.logger.info(f"Node {node_id} has rework in progress {other_node['id']} - skipping")
                        break
            
            if has_rework_in_progress:
                continue
                
            # Check if this node needs rework
            if needs_job_review_rework or (is_leaf and is_failed):
                # This node needs rework - create ONE action for it
                node_name = node_info.get('name', 'Unknown')
                
                if needs_job_review_rework:
                    self.logger.info(f"Node {node_id} ({node_name}) failed job review - creating rework action (attempt #{total_rework_attempts + 1})")
                else:
                    self.logger.info(f"Node {node_id} ({node_name}) failed execution - creating rework action (attempt #{total_rework_attempts + 1})")
                
                # Get rework specification if available
                rework_spec = None
                if node_id in self.node_results:
                    rework_spec = self.node_results[node_id].get('rework_specification')
                
                # Create rework action with direct node ID reference
                rework_action = {
                    "type": "create_new",
                    "name": f"{node_name}_rework",  # Simple naming
                    "rework_of_node_id": original_node_id,  # Reference to the original failed node
                    "rework_attempts": total_rework_attempts + 1,  # Track total attempts
                    "specification": {
                        "name": node_name,  # Keep original task name
                        "description": rework_spec.get('description', node_info.get('description', '')) if rework_spec else node_info.get('description', ''),
                        "task": rework_spec.get('task', f"Rework of {node_name} addressing {'quality issues' if needs_job_review_rework else 'execution failures'}") if rework_spec else f"Rework of {node_name} addressing {'quality issues' if needs_job_review_rework else 'execution failures'}"
                    }
                }
                
                # Add failure details to help with the rework
                if needs_job_review_rework and node_info.get('job_review'):
                    # Add review concerns for job review failures
                    review = node_info['job_review']
                    if review.get('critical_concerns'):
                        concerns_text = "\n\nCritical issues to address:\n"
                        for concern in review['critical_concerns']:
                            concerns_text += f"- {concern['type']}: {concern['description']}\n"
                        rework_action['specification']['task'] += concerns_text
                elif is_failed and node_info.get('error'):
                    # Add error details for execution failures
                    error_text = f"\n\nPrevious execution error:\n{node_info['error'][:500]}"
                    rework_action['specification']['task'] += error_text
                
                rework_actions.append(rework_action)
        
        if rework_actions:
            # Return rework actions immediately without consulting LLM
            self.logger.info(f"Returning {len(rework_actions)} automatic rework actions")
            result = {
                "satisfied": False,
                "reasoning": "Automatic rework required for nodes that failed execution or quality review",
                "next_actions": rework_actions
            }
            
            # Save this decision for logging
            self._last_llm_interaction = {
                'timestamp': datetime.now().isoformat(),
                'iteration': iteration,
                'type': 'automatic_rework',
                'actions': rework_actions,
                'reasoning': 'System-generated rework for failed quality reviews',
                'model': getattr(self.llm_service, 'model', 'automatic-rework'),
                'messages': [],  # No LLM messages for automatic rework
                'response': {'satisfied': False, 'next_actions': rework_actions}
            }
            
            if output_dir:
                self.save_llm_interaction(output_dir, iteration)
            
            return result
        
        # No rework needed - proceed with normal LLM planning
        # Use LLM to parse user request and extract function blocks
        if not hasattr(self, 'llm_service') or not self.llm_service:
            # If no LLM service and no reworks needed, return empty result
            return {
                "satisfied": False,
                "reasoning": "No automatic reworks needed and no LLM service available",
                "next_actions": []
            }
            
        result = self._plan_with_llm(user_request, tree_state, iteration)
        
        # Save LLM interaction logs if output directory provided
        if output_dir and self._last_llm_interaction:
            self.save_llm_interaction(output_dir, iteration)
            
        return result
    
    def _plan_with_llm(self, user_request: str, tree_state: Dict[str, Any], iteration: int) -> Dict[str, Any]:
        """Use LLM to create or update the analysis plan.
        
        Args:
            user_request: Original user request
            tree_state: Current state of the analysis tree
            iteration: Current iteration number
            
        Returns:
            Dictionary with satisfied flag and next_actions list
        """
        try:
            # Build prompt for LLM
            prompt = self._build_planning_prompt(user_request, tree_state, iteration)
            
            # Define JSON schema for structured output
            schema = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                        "satisfied": {
                            "type": "boolean",
                            "description": "Whether the user request has been fully satisfied"
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Explanation of the planning decision"
                        },
                        "next_actions": {
                            "type": "array",
                            "description": "List of next function blocks to create",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "type": {"type": "string", "enum": ["create_new"]},
                                    "name": {"type": "string", "description": "Function block name (snake_case)"},
                                    "specification": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "name": {"type": "string", "description": "Same as parent name"},
                                            "description": {"type": "string"},
                                            "task": {"type": "string", "description": "Detailed task description"}
                                        },
                                        "required": ["name", "description", "task"]
                                    }
                                },
                                "required": ["type", "name", "specification"]
                            }
                        }
                },
                "required": ["satisfied", "reasoning", "next_actions"]
            }
            
            # Call LLM with structured output
            messages = [
                {"role": "system", "content": self.planning_system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            result = self.llm_service.chat_completion_json(
                messages=messages,
                json_schema=schema,
                temperature=0.3,
                max_tokens=2000,
                seed=self.llm_seed
            )
            
            # Save LLM interaction for debugging
            self._last_llm_interaction = {
                'timestamp': datetime.now().isoformat(),
                'iteration': iteration,
                'messages': messages,
                'response': result,
                'model': getattr(self.llm_service, 'model', 'unknown')
            }
            
            # Validate required fields in response
            if 'satisfied' not in result:
                self.logger.error(f"LLM response missing 'satisfied' field. Response keys: {list(result.keys())}")
                # Return a fallback response
                result = {
                    "satisfied": False,
                    "reasoning": f"LLM returned malformed response: {result.get('error', 'Missing required fields')}",
                    "next_actions": []
                }
            
            if 'next_actions' not in result:
                self.logger.error(f"LLM response missing 'next_actions' field. Response keys: {list(result.keys())}")
                result['next_actions'] = []
            
            # Log the plan for debugging
            self.logger.info(f"LLM Planning Result: satisfied={result['satisfied']}, actions={len(result['next_actions'])}")
            if result['next_actions']:
                for action in result['next_actions']:
                    if isinstance(action, dict) and 'name' in action and 'specification' in action:
                        self.logger.info(f"  - {action['name']}: {action['specification'].get('description', 'N/A')}")
                    else:
                        self.logger.warning(f"  - Malformed action: {action}")
            
            # The orchestrator should explicitly set rework_of_node_id when creating rework actions
            # We don't do any name matching or guessing here
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error in LLM planning: {e}")
            raise
    
    def _build_planning_prompt(self, user_request: str, tree_state: Dict[str, Any], iteration: int) -> str:
        """Build prompt for the LLM planner."""
        parts = []
        
        parts.append("## User Request")
        parts.append(user_request)
        parts.append("")
        
        parts.append("## Current Analysis Tree State")
        parts.append(f"- Total nodes: {tree_state.get('total_nodes', 0)}")
        parts.append(f"- Completed nodes: {tree_state.get('completed_nodes', 0)}")
        parts.append(f"- Failed nodes: {tree_state.get('failed_nodes', 0)}")
        parts.append(f"- Current iteration: {iteration}")
        
        # Add constraints if available
        if tree_state.get('constraints'):
            constraints = tree_state['constraints']
            parts.append(f"- Max nodes allowed: {constraints.get('max_nodes', 'Unknown')}")
            parts.append(f"- Max children per node: {constraints.get('max_children_per_node', 'Unknown')}")
        parts.append("")
        
        # Add blocked tasks section for FAILED leaf nodes at rework limit
        # Only show blocked tasks that:
        # 1. Are leaf nodes (no children - could potentially be retried)
        # 2. Are in FAILED state (not completed successfully)
        # 3. Have reached rework limit
        blocked_leaf_tasks = []
        for node_info in tree_state.get('nodes', []):
            is_leaf = not node_info.get('children')
            is_failed = node_info.get('state') == 'failed'
            # Use both field names for compatibility
            at_limit = node_info.get('rework_limit_reached', node_info.get('at_rework_limit', False))
            
            if is_leaf and is_failed and at_limit:
                blocked_leaf_tasks.append({
                    'name': node_info['name'],
                    'attempts': node_info.get('rework_attempts', 0)
                })
        
        if blocked_leaf_tasks:
            parts.append("## ⚠️ BLOCKED TASKS - DO NOT RETRY")
            parts.append(f"The following failed leaf nodes have reached the rework limit and MUST NOT be retried:")
            for task_info in blocked_leaf_tasks:
                parts.append(f"- {task_info['name']} (already tried {task_info['attempts']} times)")
            parts.append("")
            parts.append("CRITICAL: These nodes are at the system-enforced rework limit.")
            parts.append("You MUST NOT create nodes with the same name or functionality.")
            parts.append("Instead, you MUST choose one of these alternatives:")
            parts.append("1. Try a simpler/different method (e.g., if complex_analysis failed, try basic_statistics)")
            parts.append("2. Break down into smaller subtasks (e.g., split analyze_and_visualize into separate steps)")
            parts.append("3. Use alternative libraries/approaches (e.g., if matplotlib fails, try plotly)")
            parts.append("4. Skip if non-critical and continue with other analyses")
            parts.append("")
        
        # Add existing nodes info if available
        if tree_state.get('nodes'):
            parts.append("## Existing Nodes")
            parts.append("NOTE: When creating rework nodes, use descriptive names like 'CellTypist Annotation Rework' or 'Proper Implementation'")
            for node_info in tree_state['nodes']:
                state_info = f"{node_info['state']}"
                # Add debug attempts for failed nodes
                if node_info['state'] == 'failed' and node_info.get('debug_attempts', 0) > 0:
                    state_info += f" (after {node_info.get('debug_attempts', 0)} debug attempts)"
                
                # Add rework information for ALL nodes
                if node_info.get('rework_attempts', 0) > 0:
                    state_info += f" [rework attempt #{node_info['rework_attempts']}]"
                
                # Mark nodes at rework limit prominently (check both field names)
                if node_info.get('rework_limit_reached', node_info.get('at_rework_limit', False)):
                    state_info += " ⚠️ AT REWORK LIMIT - DO NOT RETRY"
                
                node_desc = f"- {node_info['name']} (Node ID: {node_info['id']}): {state_info} - {node_info.get('description', 'No description')}"
                
                # Add failure details for failed nodes
                if node_info['state'] == 'failed' and node_info.get('failure_context'):
                    failure_context = node_info['failure_context']
                    node_desc += "\n  **Failure Details:**"
                    
                    # Add execution failure info
                    if 'execution_failure' in failure_context:
                        exec_fail = failure_context['execution_failure']
                        config = get_failure_context_config()
                        error_msg = exec_fail.get('error_message', 'Unknown error')
                        truncated_error, was_truncated = config.truncate_error(error_msg, for_prompt=True)
                        node_desc += f"\n  - Execution Error: {exec_fail.get('error_type', 'Unknown')}: {truncated_error}"
                        if exec_fail.get('exit_code', -1) != -1:
                            node_desc += f" (exit code: {exec_fail['exit_code']})"
                    
                    # Add job review failure info
                    if 'job_review_failure' in failure_context:
                        review = failure_context['job_review_failure']
                        node_desc += f"\n  - Job Review: FAILED - {review['summary'][:100]}..."
                        if review.get('concerns'):
                            node_desc += "\n    Concerns:"
                            for concern in review['concerns'][:2]:  # Show top 2 concerns
                                node_desc += f"\n    • {concern['type']}: {concern['description'][:80]}..."
                    
                    # Add bug fixer summary
                    if 'bug_fixer_attempts' in failure_context:
                        bf = failure_context['bug_fixer_attempts']
                        node_desc += f"\n  - Debug Attempts: {bf['total_attempts']} attempts made"
                        if bf.get('learned_issues'):
                            node_desc += "\n    Key issues discovered:"
                            for issue in bf['learned_issues'][:2]:  # Show top 2 issues
                                node_desc += f"\n    • {issue}"
                    
                    # Add implementation details
                    if 'function_block_implementation' in failure_context:
                        impl = failure_context['function_block_implementation']
                        if impl.get('requirements'):
                            problematic_reqs = [r for r in impl['requirements'] 
                                              if any(x in r.lower() for x in ['dtflow', 'json', 'os', 'sys'])]
                            if problematic_reqs:
                                node_desc += f"\n  - Problematic requirements: {', '.join(problematic_reqs)}"
                
                # Add output files for completed nodes
                if node_info['state'] == 'completed' and 'output_files' in node_info:
                    node_desc += f"\n  Output files: {', '.join(node_info['output_files'])}"
                    
                    # Add runtime structure information if available
                    if 'runtime_structure' in node_info:
                        runtime = node_info['runtime_structure']
                        # Show detailed output files
                        if runtime.get('output_files_detail'):
                            node_desc += "\n  Detailed outputs:"
                            for f in runtime['output_files_detail'][:5]:  # Show first 5
                                node_desc += f"\n    - {f['name']} ({f['type']}, {f['size']} bytes)"
                            if len(runtime['output_files_detail']) > 5:
                                node_desc += f"\n    ... and {len(runtime['output_files_detail'])-5} more files"
                        
                        # Show accessible nodes information
                        if runtime.get('accessible_nodes', {}).get('count', 0) > 0:
                            node_desc += f"\n  Can access {runtime['accessible_nodes']['count']} previous nodes"
                            nodes_map = runtime['accessible_nodes'].get('nodes', {})
                            if nodes_map:
                                node_desc += " with files:"
                                for idx, node_data in list(nodes_map.items())[:3]:  # Show first 3
                                    available_files = node_data.get('available_files', [])
                                    if available_files:
                                        node_desc += f"\n    - Node {idx}: {', '.join(available_files[:3])}"
                                        if len(available_files) > 3:
                                            node_desc += f" ... and {len(available_files)-3} more"
                
                # Add job review information if available
                if 'job_review' in node_info:
                    review = node_info['job_review']
                    if not review['passed']:
                        node_desc += f"\n  ⚠️ JOB REVIEW FAILED: {review['summary']}"
                        if review.get('critical_concerns'):
                            node_desc += f"\n  Critical issues: {len(review['critical_concerns'])} concerns"
                            for concern in review['critical_concerns'][:2]:  # Show first 2 critical concerns
                                node_desc += f"\n    - {concern['type']}: {concern['description'][:80]}..."
                        if review.get('needs_rework'):
                            node_desc += f"\n  NEEDS REWORK: Function block has quality issues that should be addressed"
                
                parts.append(node_desc)
            parts.append("")
            
            # Show all failed nodes with their debug status
            failed_nodes = [n for n in tree_state.get('nodes', []) if n['state'] == NodeState.FAILED]
            if failed_nodes:
                parts.append("## Failed Nodes")
                max_debug_trials = tree_state.get('constraints', {}).get('max_debug_trials', DEFAULT_MAX_DEBUG_TRIALS)
                for node_info in failed_nodes:
                    debug_attempts = node_info.get('debug_attempts', 0)
                    if debug_attempts >= max_debug_trials:
                        status = "(no more debug attempts available)"
                    else:
                        remaining = max_debug_trials - debug_attempts
                        status = f"({remaining} debug attempts remaining)"
                    parts.append(f"- {node_info['name']} {status}: {node_info.get('description', 'No description')}")
                    if node_info.get('error'):
                        error_summary = self._summarize_error(node_info.get('error', 'Unknown error'))
                        parts.append(f"  Error: {error_summary}")
                    # Show what was attempted
                    parent_name = 'root'
                    if node_info.get('parent_id'):
                        parent_node = next((n for n in tree_state['nodes'] if n['id'] == node_info['parent_id']), None)
                        if parent_node:
                            parent_name = parent_node['name']
                    parts.append(f"  Was attempting to process output from: {parent_name}")
                parts.append("")
                parts.append("IMPORTANT: When nodes fail:")
                parts.append("- For nodes with remaining debug attempts, the system will try to fix them")
                parts.append("- For nodes with exhausted debug attempts, skip analyses that depend on their output")
                parts.append("- Continue with independent analyses that can proceed without failed nodes")
                parts.append("- If the failed step was one of multiple requested methods, continue with the others")
                parts.append("- Consider the overall goal - if core objectives can be met without the failed steps, proceed")
                parts.append("")
            
            # Add section for nodes with failed job reviews
            failed_review_nodes = [n for n in tree_state.get('nodes', []) 
                                 if n.get('job_review') and not n['job_review']['passed']]
            if failed_review_nodes:
                parts.append("## Nodes with Failed Quality Reviews")
                parts.append("These nodes executed successfully but have quality issues:")
                for node_info in failed_review_nodes:
                    review = node_info['job_review']
                    rework_attempts = review.get('rework_attempts', 0)
                    parts.append(f"- {node_info['name']}: {review['summary']}")
                    if rework_attempts > 0:
                        parts.append(f"  ⚠️ This task has been reworked {rework_attempts} time(s)")
                    if review.get('critical_concerns'):
                        for concern in review['critical_concerns']:
                            parts.append(f"  - {concern['type'].upper()}: {concern['description']}")
                parts.append("")
                parts.append("IMPORTANT: When job reviews fail:")
                parts.append("- Consider whether to redo the same analysis with better implementation")
                parts.append("- If the node was attempting method X and it's implemented poorly, try implementing X properly")
                parts.append("- If the user requested specific methods, ensure they are implemented correctly, not with placeholders")
                parts.append("- You may choose to continue with dependent analyses if the output is usable despite quality issues")
                parts.append("- Or you may choose to redo the node with explicit instructions to avoid the identified issues")
                parts.append(f"- ⚠️ REWORK LIMIT: If a task has been reworked {MAX_REWORK_ATTEMPTS}+ times, suggest alternative approaches instead of retrying")
                parts.append("")
            
            # Add dedicated section for nodes that have hit the rework limit
            # Check both field names for compatibility
            rework_limit_nodes = []
            for n in tree_state.get('nodes', []):
                # Check if node is explicitly marked at rework limit (both field names)
                if n.get('rework_limit_reached', n.get('at_rework_limit', False)):
                    rework_limit_nodes.append(n)
                # Also check job review rework attempts (backward compatibility)
                elif (n.get('job_review') and not n['job_review']['passed'] 
                      and n['job_review'].get('rework_attempts', 0) >= MAX_REWORK_ATTEMPTS):
                    rework_limit_nodes.append(n)
                    
            if rework_limit_nodes:
                parts.append("## ⚠️ REWORK LIMIT REACHED - ALTERNATIVES REQUIRED")
                parts.append(f"The following nodes have been reworked {MAX_REWORK_ATTEMPTS} times and CANNOT be reworked again:")
                parts.append("The system will BLOCK any attempts to recreate these nodes.")
                parts.append("")
                for node_info in rework_limit_nodes:
                    parts.append(f"### Node: {node_info['name']} (ID: {node_info['id'][:8]}...)")
                    if node_info.get('job_review'):
                        review = node_info['job_review']
                        parts.append(f"  Failed because: {review['summary']}")
                        if review.get('critical_concerns'):
                            parts.append(f"  Issues:")
                            for concern in review['critical_concerns'][:2]:  # Show top 2 concerns
                                parts.append(f"    - {concern['type']}: {concern['description'][:60]}...")
                    elif node_info.get('error'):
                        parts.append(f"  Failed with error: {node_info['error'][:100]}...")
                    parts.append("")
                    
                parts.append("## REQUIRED: Choose Alternative Approaches")
                parts.append("")
                parts.append("Since these nodes cannot be retried, you MUST select from these alternatives:")
                parts.append("")
                parts.append("### Option 1: Task Decomposition")
                parts.append("Break the complex task into simpler subtasks that are more likely to succeed.")
                parts.append("- Example: 'analyze_and_visualize' → 'analyze_data' + 'create_visualizations'")
                parts.append("- Example: 'complex_pipeline' → 'data_prep' + 'simple_analysis' + 'basic_output'")
                parts.append("")
                parts.append("### Option 2: Alternative Methods")
                parts.append("Use a different algorithm, library, or approach entirely.")
                parts.append("- Example: If trajectory analysis with method A failed → try simpler method B")
                parts.append("- Example: If advanced clustering failed → try basic k-means clustering")
                parts.append("- Example: If visualization with matplotlib failed → try plotly or just save data")
                parts.append("")
                parts.append("### Option 3: Simplified Version")
                parts.append("Implement a simpler version that achieves the core objective.")
                parts.append("- Example: Instead of 10 complex plots → generate 2-3 essential plots")
                parts.append("- Example: Instead of full analysis → compute basic statistics only")
                parts.append("")
                parts.append("### Option 4: Skip and Continue")
                parts.append("If the failed step is not critical, continue with other independent analyses.")
                parts.append("- Only choose this if the user's core request can be satisfied without this step")
                parts.append("")
                parts.append("### Option 5: Document Manual Steps")
                parts.append("Create a summary node that documents what needs manual intervention.")
                parts.append("- Use this as a last resort when automation isn't feasible")
                parts.append("")
                parts.append("⚠️ IMPORTANT: The system will REJECT any attempt to create nodes with the same")
                parts.append("functionality as the blocked nodes. You MUST choose an alternative approach.")
                parts.append("")
        
        # Add planning metadata if available
        if tree_state.get('planning_metadata'):
            metadata = tree_state['planning_metadata']
            parts.append("## Planning Context")
            if metadata.get('all_nodes_failed'):
                parts.append("⚠️ ALL nodes have failed and cannot be retried.")
                parts.append("- You cannot create new nodes that depend on failed nodes")
                parts.append("- If no independent tasks can be performed, mark request as satisfied with explanation")
            if not metadata.get('can_attach_new_nodes'):
                parts.append("⚠️ No successful nodes available to attach new nodes to")
                parts.append("- Cannot proceed with dependent tasks")
                parts.append("- Mark request as satisfied if core objectives cannot be met")
            parts.append("")
        
        parts.append("## Task")
        parts.append("Based on the user request and current tree state, determine:")
        parts.append("1. Whether the user request has been satisfied")
        parts.append("2. What function blocks need to be created next (if any)")
        parts.append("")
        parts.append("## Important Planning Rules:")
        parts.append("1. If all existing nodes have failed after debug attempts, and we cannot create new nodes:")
        parts.append("   - Mark the request as satisfied=True")
        parts.append("   - Explain in reasoning that we cannot proceed due to failures")
        parts.append("2. Only suggest new nodes if there are successful parent nodes to attach to, or if creating a root node")
        parts.append("3. If a critical early step fails but the request involves multiple independent tasks:")
        parts.append("   - Consider if some tasks can still be attempted")
        parts.append("   - For benchmarks/comparisons, try to complete what's possible")
        parts.append("   - Only mark satisfied=True if no meaningful progress can be made")
        parts.append("4. Create meaningful function block names based on the analysis steps")
        parts.append("5. If a node has failed job review due to placeholder/cheating/poor implementation:")
        parts.append("   - Consider creating a replacement node with the same functionality but proper implementation")
        parts.append("   - Include explicit instructions in the task description to avoid the issues identified")
        parts.append("   - Example: If 'process_data' failed review for being a placeholder, create 'process_data_implementation' with explicit implementation requirements")
        parts.append("6. Quality over quantity - ensure requested methods are implemented properly, not as placeholders")
        parts.append("")
        
        return "\n".join(parts)
    
    def _summarize_error(self, error_message: str) -> str:
        """Summarize error message to key information."""
        if "ModuleNotFoundError" in error_message:
            # Extract module name
            if "No module named" in error_message:
                module = error_message.split("No module named")[1].strip().strip("'\"")
                return f"Missing module: {module}"
        elif "FileNotFoundError" in error_message:
            return "Input file not found"
        elif "KeyError" in error_message:
            # Extract key name if possible
            if "'" in error_message:
                key = error_message.split("'")[1]
                return f"Missing key: {key}"
        elif len(error_message) > 100:
            # Truncate long errors
            return error_message[:100] + "..."
        return error_message
    
    @property
    def planning_system_prompt(self) -> str:
        """Get the system prompt for planning with dynamic values."""
        return f"""You are an AI assistant that helps plan single-cell RNA-seq analysis workflows.

Your task is to analyze the user's request and current analysis state to determine:
1. Whether the analysis request has been satisfied
2. What function blocks should be created next
3. How to adapt the plan when certain steps fail

IMPORTANT GUIDELINES:
- Only suggest new function blocks if there are successful leaf nodes to attach them to
- Create descriptive function block names based on the task being performed
- Names should clearly indicate what the function does (e.g., "normalize_data", "run_clustering", "compute_pseudotime")
- Pay attention to the output files from completed nodes - child nodes will need to read these files
- ⚠️ IMPORTANT: Output files can have ANY names (not just '_node_anndata.h5ad')
- When creating function specifications, tell child nodes what files are available
- Child nodes should adapt to actual filenames, not assume conventions

JOB REVIEW FAILURES:
- Nodes have separate execution status (state: completed/failed) and review status (job_review_status: passed/failed)
- A node can be state=completed but job_review_status=failed if it executed successfully but has quality issues
- When a node has needs_rework=true, it means critical quality issues require reimplementation
- You should create a replacement node with the SAME task but enhanced requirements that address the review concerns
- Include the critical concerns from the job review in the new task specification to prevent the same issues
- REWORK LIMIT: Check rework_attempts counter - if a task has been reworked {MAX_REWORK_ATTEMPTS}+ times:
  * DO NOT suggest creating the same node again - the system will block it
  * Instead, suggest alternative approaches as outlined in the prompt
  * For example: if visualization keeps failing to save figures, try a different plotting library
  * Or: if a complex method keeps failing, try a simpler alternative that achieves similar goals
  * Consider task decomposition: break complex tasks into simpler, more manageable subtasks
  * Document what manual intervention may be needed if automated approaches aren't working
- Function blocks can access files from previous nodes using the 'previous_nodes' interface:
  * previous_nodes.list() - shows all accessible ancestor nodes
  * previous_nodes.get_file_path(node_index, 'outputs/file.csv') - returns path to output files (1-based indexing)
  * previous_nodes.get_file_path(node_index, 'inputs/file.h5ad') - returns path to input files (1-based indexing)
  * You must read the files yourself after getting the path (e.g., pd.read_csv(path), sc.read_h5ad(path))
  * This allows accessing data/results from earlier steps without passing through every intermediate node
- Create one function block at a time for each distinct analysis step
- Mark satisfied=true only when ALL requested analyses are complete
- NEVER mark satisfied=true if only the root node (load_input_data) exists, unless loading data was the only request
- Each function block should have a clear, specific task
- Function names should be in snake_case

JOB REVIEW AWARENESS:
- Completed nodes may have job review results indicating quality issues
- Job reviews check for: placeholder code, cheating (fake results), incorrect implementations
- If a node failed job review but the user requested that specific functionality:
  * Create a new node to implement it properly (e.g., if "analyze_data" is a placeholder, create "analyze_data_implementation")
  * Include explicit requirements in the task description to avoid the identified issues
  * Example task: "Implement the data analysis properly. Previous attempt was flagged as placeholder. Must include actual algorithm implementation with real computations, not mock results."
- You can choose to continue with downstream analyses if the output is still usable
- Or redo the analysis with proper implementation if it's critical to the user's request

REWORK NODE CREATION:
- When creating a node to rework/retry a failed task (either execution failure or job review failure):
  * Use descriptive names that indicate it's a rework (e.g., "CellTypist Annotation Proper Implementation")
  * Include the failure reasons in the task description
  * Include words like "rework", "retry", "proper implementation", or "alternative" in the name
  * This enables proper rework tracking and enforcement of rework limits
- Example for rework after job review failure:
  {{
    "type": "create_new",
    "name": "celltypist_annotation_proper",
    "specification": {{
      "name": "CellTypist Annotation Proper Implementation",
      "description": "Implement CellTypist annotation correctly. Previous attempt failed with AttributeError on conf_score.",
      "task": "Use correct CellTypist API to access confidence scores..."
    }}
  }}
- **IMPORTANT**: Use clear rework indicators in the name (e.g., "Rework", "Proper Implementation", "Retry")
- The system will automatically detect reworks based on task names and descriptions
- Rework limits will be enforced to prevent infinite retries

MULTI-METHOD REQUESTS:
- When user requests multiple methods (e.g., "Run method A, method B, method C"), you MUST plan to create ALL of them
- Count numbered items in the request and ensure each gets a corresponding node
- Independent methods that read from the same parent should be created as siblings, but CREATE THEM ONE AT A TIME
- DO NOT mark satisfied=true until ALL explicitly requested methods have been attempted
- If the user lists N tasks, you need at least N nodes (some tasks may require multiple nodes)
- Track completion by counting: "User requested X methods, we've created nodes for Y, still need Z more"
- Return only ONE next_action per response to ensure proper tree structure

BRANCHING CONSTRAINTS:
- Check tree_state.constraints.max_children_per_node for the actual branch limit
- When planning multiple independent methods:
  * If user wants ALL methods in EACH branch with different parameters → create multiple branches
  * If user wants methods as alternatives → they can be siblings up to the branch limit
  * After branch limit is reached, remaining methods continue deeper in the tree
- Due to current implementation, return only ONE next_action per response
- The system processes actions sequentially

FAILURE CONTEXT:
- When nodes fail, they include comprehensive failure context with:
  * Execution errors and debug attempts
  * Job review failures and concerns
  * Bug fixer insights and attempted fixes
  * Function block implementation details
- When creating a rework node:
  * Include the specific failure reasons in the task description
  * Mention what went wrong and what to avoid
  * The system will automatically detect it's a rework and propagate context
- This helps the function creator and bug fixer avoid repeating the same mistakes

HANDLING FAILURES:
- When a node fails after multiple debug attempts, consider it permanently failed
- Failed steps should be noted in your reasoning but should NOT block progress on other requested analyses
- If a failed step is critical for downstream steps, suggest alternatives (e.g., if scFates fails, you can still run other trajectory methods)
- If a failed step is optional/independent, continue with the remaining requested analyses
- When reporting satisfied=true/false, ensure ALL requested tasks have been attempted, not just until first failure

SATISFACTION CRITERIA:
- CRITICAL: The data loading root node (load_input_data) does NOT count as satisfying analysis requests!
  * This node only loads/passes through data - it performs NO analysis
  * If only the root node exists, the actual analysis has NOT started yet
  * You must create analysis nodes that implement the requested tasks
- Count the number of main tasks in the user request
- Verify each task has at least one corresponding node (completed OR failed)
  * EXCLUDE the root node (load_input_data) from this count
  * Only nodes that perform actual analysis/computation count
- Failed attempts COUNT as attempted - don't keep trying alternatives unless requested
- For multi-method requests, ensure ALL requested methods have been attempted
- Only mark satisfied=true when:
  * All numbered items have corresponding nodes (any state) - excluding root
  * All named methods have been attempted (success or failure)
  * DO NOT require success - attempted is sufficient
  * The root node alone is NEVER sufficient unless user only asked to "load data"
  * If preprocessing fails and blocks downstream tasks, explain and mark satisfied
- Examples:
  * "Run DPT" + only root node = NOT satisfied (no DPT node created)
  * "Run DPT" + DPT node fails = task attempted, satisfied
  * "Load and analyze data" + only root = NOT satisfied (analysis not done)
  * "Load data" + only root = satisfied (that's all that was requested)
  * "Run any pseudotime method" + DPT fails = try alternatives
  * "Tasks 1,2,3" + all have nodes = satisfied (even if some failed)

CRITICAL: If there are no completed leaf nodes (nodes with state='completed' and no children), you MUST return next_actions=[] because there's nowhere to attach new nodes.
EXCEPTION: If there are ZERO nodes in the tree (total_nodes=0), you should create the first/root node.

Examples of good function block naming:
- User: "normalize the data" → name: "normalize_data"
- User: "perform DPT analysis" → name: "dpt_pseudotime_analysis"
- User: "cluster cells using Leiden" → name: "leiden_clustering"

Example of handling failures:
- If scFates pseudotime fails but user requested multiple methods, continue with other methods (Palantir, CellRank, etc.)
- If a specific visualization fails, try alternative visualization approaches
- If a dependency is missing (like skmisc), suggest using alternative parameters that don't require it
- User: "compare different methods" → name: "compare_analysis_methods"
"""
    
    def _wait_for_node_completion(self, timeout: float = 5.0):
        """Wait for at least one node to complete."""
        import time
        start_time = time.time()
        initial_completed = len(self.completed_nodes)
        
        while time.time() - start_time < timeout:
            if len(self.completed_nodes) > initial_completed:
                break
            time.sleep(0.1)
    
    def _needs_expansion(self, tree: AnalysisTree) -> bool:
        """Check if the tree needs new nodes."""
        # Tree needs expansion if:
        # 1. No root node yet
        # 2. All leaf nodes are completed and have no children
        
        if not tree.root_node_id:
            return True
            
        leaf_nodes = self._get_leaf_nodes(tree)
        return all(
            node.state == NodeState.COMPLETED and not node.children
            for node in leaf_nodes
        )
    
    def _expand_tree(
        self, 
        tree: AnalysisTree, 
        user_request: str,
        context: Dict[str, Any]
    ) -> bool:
        """Expand the tree with new nodes.
        
        Returns:
            bool: Whether the user request is satisfied
        """
        satisfied = False
        
        if not tree.root_node_id:
            # Create root node
            satisfied = self._create_root_node(tree, user_request, context)
        else:
            # Expand leaf nodes
            leaf_nodes = self._get_completed_leaf_nodes(tree)
            max_children = context.get('max_children', 3)
            
            # Expand each completed leaf node
            for leaf_node in leaf_nodes[:max_children]:
                node_satisfied = self._expand_node(
                    tree, leaf_node, user_request, context
                )
                if node_satisfied:
                    satisfied = True
                    break
                    
        return satisfied
    
    def _create_root_node(
        self, 
        tree: AnalysisTree,
        user_request: str,
        context: Dict[str, Any]
    ) -> bool:
        """Create the root node of the tree."""
        # Get data info (without reading the file)
        data_path = context.get('input_data_path')
        data_summary = {}
        if data_path:
            data_path = Path(data_path)
            if data_path.exists():
                data_summary = {
                    "file_path": str(data_path),
                    "file_name": data_path.name,
                    "file_size": data_path.stat().st_size,
                    "exists": True
                }
            else:
                data_summary = {"file_path": str(data_path), "exists": False}
        
        # Select or create root function block
        result = self.function_creator.process_selection_or_creation({
            'user_request': user_request,
            'tree': tree,
            'current_node': None,
            'parent_chain': [],
            'generation_mode': tree.generation_mode,
            'max_children': 1,  # Root should be single
            'data_path': data_path,
            'data_summary': data_summary
        })
        
        if result['function_blocks']:
            self.tree_manager.add_root_node(result['function_blocks'][0])
            
        return result['satisfied']
    
    def _expand_node(
        self,
        tree: AnalysisTree,
        node: AnalysisNode,
        user_request: str,
        context: Dict[str, Any]
    ) -> bool:
        """Expand a single node with children."""
        # Get parent chain
        parent_chain = self.tree_manager.get_parent_chain(node.id)
        
        # Get latest data path
        data_path = self.tree_manager.get_latest_data_path(node.id)
        
        # Select or create child function blocks
        result = self.function_creator.process_selection_or_creation({
            'user_request': user_request,
            'tree': tree,
            'current_node': node,
            'parent_chain': parent_chain,
            'generation_mode': tree.generation_mode,
            'max_children': context.get('max_children', 3),
            'data_path': data_path
        })
        
        if result['function_blocks']:
            self.tree_manager.add_child_nodes(node.id, result['function_blocks'])
            
        return result['satisfied']
    
    def handle_failed_node(
        self,
        node: AnalysisNode,
        error_message: str,
        stdout: str,
        stderr: str,
        max_debug_attempts: int = 3
    ) -> bool:
        """Handle a failed node by attempting to fix it.
        
        Returns:
            bool: Whether the fix was successful
        """
        if node.debug_attempts >= max_debug_attempts:
            return False
            
        if not isinstance(node.function_block, NewFunctionBlock):
            return False
            
        # Try to fix the code
        result = self.bug_fixer.process({
            'function_block': node.function_block,
            'error_message': error_message,
            'stdout': stdout,
            'stderr': stderr,
            'previous_attempts': []  # TODO: Track previous attempts
        })
        
        if result['success'] and result['fixed_code']:
            # Update the function block
            node.function_block.code = result['fixed_code']
            if result['fixed_requirements']:
                node.function_block.requirements = result['fixed_requirements']
            
            # Increment debug attempts
            self.tree_manager.increment_debug_attempts(node.id)
            
            # Mark as pending to retry
            self.tree_manager.update_node_execution(node.id, NodeState.PENDING)
            
            return True
            
        return False
    
    def _get_leaf_nodes(self, tree: AnalysisTree) -> List[AnalysisNode]:
        """Get all leaf nodes in the tree."""
        return [
            node for node in tree.nodes.values()
            if not node.children
        ]
    
    def _get_completed_leaf_nodes(self, tree: AnalysisTree) -> List[AnalysisNode]:
        """Get completed leaf nodes that can be expanded."""
        return [
            node for node in tree.nodes.values()
            if node.state == NodeState.COMPLETED and not node.children
        ]
    
    def _get_pending_nodes(self, tree: AnalysisTree) -> List[AnalysisNode]:
        """Get nodes that are pending execution."""
        return [
            node for node in tree.nodes.values()
            if node.state == NodeState.PENDING
        ]
    
    def _mark_nodes_for_execution(self, nodes: List[AnalysisNode]) -> None:
        """Mark nodes as ready for execution."""
        # In the current implementation, pending nodes are already
        # ready for execution. This method is here for future
        # enhancements where we might need additional logic.
        pass
    
    def _get_tree_state(self, tree: AnalysisTree) -> str:
        """Get a summary of the tree state."""
        total = len(tree.nodes)
        completed = sum(1 for n in tree.nodes.values() if n.state == NodeState.COMPLETED)
        failed = sum(1 for n in tree.nodes.values() if n.state == NodeState.FAILED)
        pending = sum(1 for n in tree.nodes.values() if n.state == NodeState.PENDING)
        
        return f"Total: {total}, Completed: {completed}, Failed: {failed}, Pending: {pending}"
    
    def save_llm_interaction(self, output_dir: Path, iteration: int) -> None:
        """Save LLM interaction logs to orchestrator tasks directory.
        
        Args:
            output_dir: Base output directory (usually contains main_TIMESTAMP_TREEID)
            iteration: Current orchestrator iteration
        """
        if not self._last_llm_interaction:
            return
            
        try:
            # Create orchestrator_tasks directory
            orchestrator_dir = output_dir / "orchestrator_tasks"
            orchestrator_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now()
            
            # Save JSON file with raw data
            json_file = orchestrator_dir / f"iteration_{iteration:02d}_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
            with open(json_file, 'w') as f:
                json.dump(self._last_llm_interaction, f, indent=2, default=str)
            
            # Save markdown file with formatted content
            md_file = orchestrator_dir / f"iteration_{iteration:02d}_{timestamp.strftime('%Y%m%d_%H%M%S')}.md"
            with open(md_file, 'w') as f:
                f.write("# Orchestrator LLM Interaction\n\n")
                f.write(f"**Timestamp:** {self._last_llm_interaction.get('timestamp', 'unknown')}\n")
                f.write(f"**Iteration:** {iteration}\n")
                f.write(f"**Model:** {self._last_llm_interaction.get('model', 'unknown')}\n")
                f.write(f"**Type:** {self._last_llm_interaction.get('type', 'llm_planning')}\n\n")
                
                # Write messages (if any)
                messages = self._last_llm_interaction.get('messages', [])
                if messages:
                    f.write("## Messages\n\n")
                    for i, msg in enumerate(messages):
                        f.write(f"### Message {i+1} ({msg.get('role', 'unknown')})\n\n")
                        f.write("```\n")
                        f.write(msg.get('content', ''))
                        f.write("\n```\n\n")
                else:
                    f.write("## Messages\n\n*No LLM messages (automatic system action)*\n\n")
                
                # Write response
                f.write("## Response\n\n")
                response = self._last_llm_interaction.get('response', {})
                f.write(f"**Satisfied:** {response.get('satisfied', False)}\n\n")
                f.write(f"**Reasoning:** {response.get('reasoning', self._last_llm_interaction.get('reasoning', 'N/A'))}\n\n")
                
                # Write actions (handling both formats)
                actions = response.get('next_actions', self._last_llm_interaction.get('actions', []))
                if actions:
                    f.write("### Next Actions\n\n")
                    for action in actions:
                        f.write(f"#### {action.get('name', 'Unnamed Action')}\n")
                        f.write(f"- **Type:** {action.get('type', 'unknown')}\n")
                        
                        # Handle both normal actions and rework actions
                        if 'specification' in action:
                            f.write(f"- **Description:** {action['specification'].get('description', 'N/A')}\n")
                            f.write(f"- **Task:** {action['specification'].get('task', 'N/A')}\n\n")
                        else:
                            # For rework actions that might have different structure
                            f.write(f"- **Description:** {action.get('description', 'N/A')}\n")
                            f.write(f"- **Task:** {action.get('task', 'N/A')}\n\n")
                
            self.logger.info(f"Saved orchestrator LLM interaction to {orchestrator_dir}")
            
        except Exception as e:
            self.logger.error(f"Error saving orchestrator LLM interaction: {e}")