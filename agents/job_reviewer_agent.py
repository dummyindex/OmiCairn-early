"""Job Reviewer agent for validating completed function blocks to prevent cheating and ensure quality."""

import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

from llm_service import BaseLLMService
from models import AnalysisNode, BaseFunctionBlock, ExecutionResult
from utils import setup_logger

logger = setup_logger(__name__)


@dataclass
class JobConcern:
    """Represents a concern found during job review."""
    type: str  # "cheating", "placeholder", "ml_violation", "implementation_mismatch", "other"
    severity: str  # "critical", "warning", "info"
    description: str
    evidence: str
    suggested_fix: str


@dataclass
class JobReviewResult:
    """Result of job review process."""
    passed: bool
    concerns: List[JobConcern]
    recommendations: Dict[str, Any]
    ml_best_practices: Dict[str, Optional[bool]]
    summary: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "passed": self.passed,
            "concerns": [
                {
                    "type": concern.type,
                    "severity": concern.severity,
                    "description": concern.description,
                    "evidence": concern.evidence,
                    "suggested_fix": concern.suggested_fix
                }
                for concern in self.concerns
            ],
            "recommendations": self.recommendations,
            "ml_best_practices": self.ml_best_practices,
            "summary": self.summary
        }


class JobReviewerAgent:
    """Agent for reviewing completed function blocks to ensure quality and prevent cheating."""
    
    # JSON schema for LLM output validation
    JOB_REVIEW_SCHEMA = {
        "type": "object",
        "properties": {
            "passed": {
                "type": "boolean",
                "description": "Whether the function block passes review"
            },
            "concerns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["cheating", "placeholder", "ml_violation", "implementation_mismatch", "other"],
                            "description": "Type of concern identified"
                        },
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "warning", "info"],
                            "description": "Severity level of the concern"
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed description of the concern"
                        },
                        "evidence": {
                            "type": "string",
                            "description": "Specific evidence or code snippet showing the issue"
                        },
                        "suggested_fix": {
                            "type": "string",
                            "description": "Suggested approach to fix the issue"
                        }
                    },
                    "required": ["type", "severity", "description", "evidence", "suggested_fix"],
                    "additionalProperties": False
                }
            },
            "recommendations": {
                "type": "object",
                "properties": {
                    "needs_rework": {
                        "type": "boolean",
                        "description": "Whether the function block needs to be reworked"
                    },
                    "specific_changes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific changes required"
                    },
                    "priority_level": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Priority for addressing issues"
                    }
                },
                "required": ["needs_rework", "specific_changes", "priority_level"],
                "additionalProperties": False
            },
            "ml_best_practices": {
                "type": "object",
                "properties": {
                    "applies_to_node": {
                        "type": "boolean",
                        "description": "Whether ML best practices apply to this node (false for non-ML nodes like data loading, preprocessing, visualization)"
                    },
                    "has_train_test_split": {
                        "type": ["boolean", "null"],
                        "description": "Whether appropriate train/test splitting is used (null if not applicable)"
                    },
                    "handles_data_leakage": {
                        "type": ["boolean", "null"],
                        "description": "Whether the implementation prevents data leakage (null if not applicable)"
                    },
                    "appropriate_validation": {
                        "type": ["boolean", "null"],
                        "description": "Whether validation methods are appropriate (null if not applicable)"
                    },
                    "hyperparameter_handling": {
                        "type": ["boolean", "null"],
                        "description": "Whether hyperparameters are handled properly (null if not applicable)"
                    }
                },
                "required": ["applies_to_node", "has_train_test_split", "handles_data_leakage", "appropriate_validation", "hyperparameter_handling"],
                "additionalProperties": False
            },
            "summary": {
                "type": "string",
                "maxLength": 300,
                "description": "Brief summary of the review findings"
            }
        },
        "required": ["passed", "concerns", "recommendations", "ml_best_practices", "summary"],
        "additionalProperties": False
    }
    
    def __init__(self, llm_service: BaseLLMService, llm_seed: Optional[int] = None):
        """Initialize job reviewer agent.
        
        Args:
            llm_service: LLM service for conducting reviews
            llm_seed: Seed for LLM reproducibility (optional)
        """
        self.llm_service = llm_service
        self.llm_seed = llm_seed
        
        # Statistics tracking
        self.total_reviews = 0
        self.failed_reviews = 0
        self.concern_counts = {}
        
        logger.info("Initialized JobReviewerAgent")
    
    def review_function_block(
        self,
        node: AnalysisNode,
        function_block: BaseFunctionBlock,
        execution_result: ExecutionResult,
        user_request: str,
        parent_output_description: Optional[str] = None,
        output_files: Optional[List[str]] = None
    ) -> JobReviewResult:
        """Review a completed function block for quality and correctness.
        
        Args:
            node: The analysis node that was executed
            function_block: The function block that was executed
            execution_result: Result of the execution
            user_request: Original user request for context
            parent_output_description: Description of parent node outputs
            output_files: List of output files produced
            
        Returns:
            JobReviewResult with review findings
        """
        logger.info(f"Reviewing function block: {function_block.name}")
        
        try:
            # Gather execution context
            execution_context = self._gather_execution_context(
                node, execution_result, output_files
            )
            
            # Build review prompt
            prompt = self._build_review_prompt(
                function_block, user_request, parent_output_description, execution_context
            )
            
            # Call LLM with structured output
            messages = [{"role": "user", "content": prompt}]
            
            response = self.llm_service.chat_completion_json(
                messages=messages,
                json_schema=self.JOB_REVIEW_SCHEMA,
                temperature=0.1,  # Low temperature for consistency
                max_tokens=2500,
                seed=self.llm_seed
            )
            
            # Parse response into result object
            result = self._parse_review_response(response)
            
            # Update statistics
            self.total_reviews += 1
            if not result.passed:
                self.failed_reviews += 1
            
            for concern in result.concerns:
                self.concern_counts[concern.type] = self.concern_counts.get(concern.type, 0) + 1
            
            logger.info(f"Review completed: passed={result.passed}, concerns={len(result.concerns)}")
            
            # Save job review report
            self._save_report(node, function_block, result, user_request, prompt)
            
            return result
            
        except Exception as e:
            logger.error(f"Error during job review: {e}")
            raise
    
    def _gather_execution_context(
        self,
        node: AnalysisNode,
        execution_result: ExecutionResult,
        output_files: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Gather context about the execution for review."""
        
        context = {
            "node_id": node.id,
            "execution_success": execution_result.success,
            "execution_time": getattr(execution_result, 'execution_time', 'unknown'),
            "output_files": output_files or [],
            "error_message": getattr(execution_result, 'error', None) if not execution_result.success else None
        }
        
        # Get actual output directory path from node
        actual_output_files = []
        actual_figures = []
        if hasattr(node, 'output_data_id') and node.output_data_id:
            output_dir = Path(node.output_data_id)
            if output_dir.exists():
                # List all actual files in output directory
                for f in output_dir.rglob('*'):
                    if f.is_file():
                        relative_path = f.relative_to(output_dir)
                        actual_output_files.append(str(relative_path))
                        # Check for figure files
                        if f.suffix.lower() in ['.png', '.jpg', '.jpeg', '.pdf', '.svg']:
                            actual_figures.append(str(relative_path))
                
                context["actual_output_files"] = actual_output_files
                context["actual_figures"] = actual_figures
                context["output_directory_size"] = sum(
                    f.stat().st_size for f in output_dir.rglob('*') if f.is_file()
                )
                context["output_file_count"] = len(actual_output_files)
        
        # Try to get output file information from execution result (legacy)
        try:
            if hasattr(execution_result, 'output_path') and execution_result.output_path:
                output_path = Path(str(execution_result.output_path))  # Convert to string first
                if output_path.exists() and output_path != output_dir:
                    context["execution_result_output_path"] = str(output_path)
        except Exception as e:
            logger.debug(f"Could not get output path info: {e}")
        
        # Check for suspicious patterns in execution
        stdout = getattr(execution_result, 'stdout', '')
        if stdout:
            context["has_warnings"] = "warning" in stdout.lower()
            context["execution_output_length"] = len(stdout)
            
            # Look for signs of actual computation vs fake results
            computation_indicators = [
                "processing", "computing", "analyzing", "fitting", "training",
                "loading data", "saving results", "iteration", "epoch"
            ]
            context["shows_computation"] = any(
                indicator in stdout.lower() for indicator in computation_indicators
            )
            
            # Look for suspicious patterns
            suspicious_patterns = [
                "placeholder", "todo", "not implemented", "fake", "mock",
                "example data", "dummy", "test data"
            ]
            context["has_suspicious_patterns"] = any(
                pattern in stdout.lower() for pattern in suspicious_patterns
            )
            
            # Check for output claims in stdout
            output_claims = []
            lines = stdout.split('\n')
            for line in lines:
                line_lower = line.lower()
                if any(phrase in line_lower for phrase in ['saved to', 'saved at', 'wrote', 'written to', 'output:', 'created']):
                    output_claims.append(line.strip())
            context["output_claims_in_stdout"] = output_claims
        
        return context
    
    def _build_review_prompt(
        self,
        function_block: BaseFunctionBlock,
        user_request: str,
        parent_output_description: Optional[str],
        execution_context: Dict[str, Any]
    ) -> str:
        """Build the prompt for reviewing the function block."""
        
        # Truncate code if too long for prompt
        code_display = function_block.code
        if len(code_display) > 3000:
            code_display = code_display[:1500] + "\n\n... [CODE TRUNCATED] ...\n\n" + code_display[-1000:]
        
        prompt = f"""You are an expert code reviewer specializing in scientific data analysis pipelines. Your task is to review a completed function block execution to ensure quality and prevent cheating.

FUNCTION BLOCK DETAILS:
- Name: {function_block.name}
- Description: {function_block.description}
- Type: {function_block.type}

NODE'S SPECIFIC TASK: {function_block.description}

IMPORTANT: Review this node ONLY against its specific task described above, NOT against the entire user request. 
Each node in the analysis tree has a specific responsibility, and this review should verify that THIS node 
completes ITS ASSIGNED TASK correctly.

OVERALL USER REQUEST (for context only): {user_request[:500]}{"..." if len(user_request) > 500 else ""}

PARENT OUTPUT CONTEXT: {parent_output_description or "No parent node (this is root node)"}

FUNCTION CODE:
```{function_block.type}
{code_display}
```

EXECUTION CONTEXT:
{self._safe_json_dumps(execution_context)}

OUTPUT FILES PRODUCED: {execution_context.get('output_files', [])}
ACTUAL OUTPUT FILES IN DIRECTORY: {execution_context.get('actual_output_files', [])}
ACTUAL FIGURES PRODUCED: {execution_context.get('actual_figures', [])}
OUTPUT CLAIMS IN STDOUT: {execution_context.get('output_claims_in_stdout', [])}

CRITICAL OUTPUT VALIDATION:
- If the code claims to save files (e.g., "saved to", "wrote"), check if those files actually exist in ACTUAL OUTPUT FILES
- If the function description mentions creating figures/plots, check if they exist in ACTUAL FIGURES
- Pay special attention to commented-out save operations (e.g., # plt.savefig()) - this is a CRITICAL issue

REVIEW CRITERIA:

1. **CHEATING DETECTION** (CRITICAL):
   - Is the code filling in made-up results instead of actually computing them?
   - Are hardcoded values being used where real analysis should occur?
   - Is the function generating fake data instead of processing real input?
   - Are benchmark results being fabricated rather than calculated?

2. **PLACEHOLDER CODE** (CRITICAL):
   - Are there TODO comments or placeholder implementations?
   - Is there commented-out code that should be active?
   - Are there "example" or "template" comments suggesting incomplete implementation?
   - Is actual functionality replaced with stubs?

3. **OUTPUT VALIDATION** (CRITICAL):
   - Does the code claim to save files that don't actually exist in ACTUAL OUTPUT FILES?
   - Are save operations commented out (e.g., # plt.savefig()) while stdout claims success?
   - If the function description promises specific outputs (figures, files), do they exist?
   - Is there a mismatch between OUTPUT CLAIMS IN STDOUT and ACTUAL OUTPUT FILES?

4. **IMPLEMENTATION MATCHING** (HIGH):
   - Does the implementation actually perform what the function's specific task description claims?
   - Is the analysis method correctly implemented (e.g., if it says "scFates pseudotime analysis", is scFates actually used)?
   - Are the outputs appropriate for this node's specific task?
   - IMPORTANT: Do NOT fail the node for not implementing other methods that are outside this node's scope

5. **MACHINE LEARNING BEST PRACTICES** (ONLY if this node performs ML/statistical modeling):
   - IMPORTANT: Only evaluate these if the node actually performs machine learning, statistical modeling, or predictive analysis
   - For non-ML nodes (data loading, preprocessing, visualization, etc.), set all ML best practices to null/not applicable
   - For ML tasks: Is there proper train/test splitting?
   - Is data leakage prevented (no future information in training)?
   - Are validation methods appropriate for the task?
   - Are hyperparameters handled properly?

6. **GENERAL QUALITY**:
   - Does the code handle errors appropriately?
   - Are the outputs in the expected format?
   - Is the implementation reasonable for the task?

SEVERITY GUIDELINES:
- **CRITICAL**: Code is cheating, using placeholders, or completely wrong implementation FOR THIS SPECIFIC NODE'S TASK
- **WARNING**: Implementation issues that affect correctness but aren't cheating
- **INFO**: Minor improvements or style suggestions

REMEMBER: Judge this node ONLY on whether it correctly implements its specific task ({function_block.description}), 
NOT on whether it implements everything in the overall user request.

Focus on functional correctness and preventing academic dishonesty. Be strict about cheating but fair about implementation choices."""

        return prompt
    
    def _parse_review_response(self, response: Dict[str, Any]) -> JobReviewResult:
        """Parse LLM response into JobReviewResult."""
        
        # Validate required fields
        required_fields = ["passed", "concerns", "recommendations", "ml_best_practices", "summary"]
        for field in required_fields:
            if field not in response:
                raise ValueError(f"LLM response missing required field: {field}")
        
        # Parse concerns
        concerns = []
        for concern_data in response.get("concerns", []):
            concerns.append(
                JobConcern(
                    type=concern_data["type"],
                    severity=concern_data["severity"],
                    description=concern_data["description"],
                    evidence=concern_data["evidence"],
                    suggested_fix=concern_data["suggested_fix"]
                )
            )
        
        return JobReviewResult(
            passed=response["passed"],
            concerns=concerns,
            recommendations=response["recommendations"],
            ml_best_practices=response.get("ml_best_practices", {}),
            summary=response["summary"]
        )
    
    def _safe_json_dumps(self, obj, indent=2):
        """Safely serialize object to JSON, handling non-serializable objects."""
        try:
            return json.dumps(obj, indent=indent)
        except TypeError:
            # Handle non-serializable objects by converting to string
            safe_obj = {}
            for key, value in obj.items() if isinstance(obj, dict) else []:
                try:
                    json.dumps(value)  # Test if value is serializable
                    safe_obj[key] = value
                except TypeError:
                    safe_obj[key] = str(value)  # Convert to string if not serializable
            return json.dumps(safe_obj, indent=indent)
    
    def _calculate_ml_score(self, ml_best_practices: Dict[str, Optional[bool]]) -> float:
        """Calculate ML best practices score, handling None values for non-ML nodes."""
        if not ml_best_practices:
            return 0.0
        
        # Check if this is a non-ML node
        if not ml_best_practices.get("applies_to_node", True):
            return 1.0  # Non-ML nodes get perfect score for ML practices
        
        # For ML nodes, calculate score based on actual practices
        practices = ["has_train_test_split", "handles_data_leakage", 
                    "appropriate_validation", "hyperparameter_handling"]
        
        applicable = []
        for practice in practices:
            value = ml_best_practices.get(practice)
            if value is not None:  # Only count non-null values
                applicable.append(value)
        
        if not applicable:
            return 0.0
        
        return sum(applicable) / len(applicable)
    
    def should_trigger_rework(self, review_result: JobReviewResult) -> bool:
        """Determine if a function block should be reworked based on review.
        
        Args:
            review_result: Result of the job review
            
        Returns:
            True if rework is recommended
        """
        # Always rework if review explicitly recommends it
        if review_result.recommendations.get("needs_rework", False):
            return True
        
        # Check for critical concerns
        critical_concerns = [
            concern for concern in review_result.concerns 
            if concern.severity == "critical"
        ]
        
        # Rework for any critical cheating or placeholder issues
        critical_types = {"cheating", "placeholder", "implementation_mismatch"}
        for concern in critical_concerns:
            if concern.type in critical_types:
                logger.info(f"Triggering rework due to critical {concern.type} concern")
                return True
        
        return False
    
    def get_rework_specification(self, review_result: JobReviewResult, original_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Generate specification for reworking a function block.
        
        Args:
            review_result: Result of the failed review
            original_spec: Original function block specification
            
        Returns:
            Updated specification for rework
        """
        rework_spec = original_spec.copy()
        
        # Add review feedback to the specification
        rework_spec["review_feedback"] = {
            "failed_review": True,
            "concerns": [concern.description for concern in review_result.concerns],
            "specific_requirements": review_result.recommendations.get("specific_changes", []),
            "must_avoid": [
                concern.evidence for concern in review_result.concerns 
                if concern.severity == "critical"
            ]
        }
        
        # Update description to include requirements
        if review_result.recommendations.get("specific_changes"):
            rework_spec["description"] += "\n\nREVIEW REQUIREMENTS:\n"
            for change in review_result.recommendations["specific_changes"]:
                rework_spec["description"] += f"- {change}\n"
        
        # Add anti-cheating requirements
        critical_concerns = [c for c in review_result.concerns if c.severity == "critical"]
        if critical_concerns:
            rework_spec["description"] += "\n\nCRITICAL FIXES REQUIRED:\n"
            for concern in critical_concerns:
                rework_spec["description"] += f"- {concern.suggested_fix}\n"
        
        return rework_spec
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get review statistics.
        
        Returns:
            Dictionary with usage statistics
        """
        success_rate = (
            (self.total_reviews - self.failed_reviews) / self.total_reviews
            if self.total_reviews > 0 else 0.0
        )
        
        return {
            "total_reviews": self.total_reviews,
            "failed_reviews": self.failed_reviews,
            "success_rate": success_rate,
            "concern_counts": self.concern_counts.copy(),
            "most_common_concern": max(self.concern_counts.items(), key=lambda x: x[1])[0] if self.concern_counts else None
        }
    
    def _save_report(self, node: AnalysisNode, function_block: BaseFunctionBlock, result: JobReviewResult, user_request: str, prompt: str):
        """Save job review report for tracking and analysis."""
        # Log clear evidence to stdout
        logger.info("👨‍⚖️ JOB REVIEWER AGENT ACTIVITY - Function block quality review")
        logger.info(f"  Node: {node.id}")
        logger.info(f"  Function: {function_block.name}")
        logger.info(f"  Result: {'✅ PASSED' if result.passed else '❌ FAILED'}")
        logger.info(f"  Concerns found: {len(result.concerns)}")
        if result.concerns:
            critical_concerns = sum(1 for c in result.concerns if c.severity == "critical")
            logger.info(f"  Critical concerns: {critical_concerns}")
            logger.info(f"  Needs rework: {result.recommendations.get('needs_rework', False)}")
        logger.info(f"  Summary: {result.summary[:100]}{'...' if len(result.summary) > 100 else ''}")
        
        # Create a standardized evidence structure
        evidence = {
            "agent": "Job Reviewer",
            "timestamp": datetime.now().isoformat(),
            "activity": "function_block_review",
            "node_id": node.id,
            "function_name": function_block.name,
            "user_request": user_request[:200] + "..." if len(user_request) > 200 else user_request,
            "llm_input_prompt": prompt,  # Store the raw LLM input
            "result": result.to_dict(),
            "summary": {
                "passed": result.passed,
                "concerns_count": len(result.concerns),
                "critical_concerns": sum(1 for c in result.concerns if c.severity == "critical"),
                "needs_rework": result.recommendations.get("needs_rework", False),
                "ml_best_practices_score": self._calculate_ml_score(result.ml_best_practices)
            }
        }
        
        # Store in class for later saving when node directory is available
        if not hasattr(self, '_pending_reports'):
            self._pending_reports = []
        self._pending_reports.append(evidence)
            
        logger.info(f"📊 Job Reviewer report recorded (will be saved to agent_tasks/job_reviewer/)")
    
    def save_reports_to_directory(self, node_dir: Path):
        """Save all pending reports to the specified node directory."""
        if not hasattr(self, '_pending_reports') or not self._pending_reports:
            logger.debug("No pending job reviewer reports to save")
            return
        
        # Create job reviewer reports directory
        evidence_dir = node_dir / "agent_tasks" / "job_reviewer"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        
        for i, evidence in enumerate(self._pending_reports):
                timestamp = evidence["timestamp"].replace(":", "").replace("-", "")[:15]
                
                # Save JSON report
                json_file = evidence_dir / f"review_{timestamp}_{i:02d}.json"
                with open(json_file, 'w') as f:
                    json.dump(evidence, f, indent=2)
                
                # Save human-readable report
                md_file = evidence_dir / f"review_{timestamp}_{i:02d}.md"
                with open(md_file, 'w') as f:
                    f.write(f"# Job Reviewer Report\n\n")
                    f.write(f"**Timestamp:** {evidence['timestamp']}\n")
                    f.write(f"**Node ID:** {evidence['node_id']}\n")
                    f.write(f"**Function:** {evidence['function_name']}\n")
                    f.write(f"**Result:** {'✅ PASSED' if evidence['summary']['passed'] else '❌ FAILED'}\n\n")
                    
                    f.write(f"**User Request:** {evidence['user_request']}\n\n")
                    
                    if evidence['result']['concerns']:
                        f.write("## Concerns Found\n\n")
                        for concern in evidence['result']['concerns']:
                            f.write(f"- **{concern['severity'].upper()}** ({concern['type']}): {concern['description']}\n")
                            f.write(f"  - *Evidence:* {concern['evidence']}\n")
                            f.write(f"  - *Suggested Fix:* {concern['suggested_fix']}\n\n")
                    
                    if evidence['result']['recommendations']:
                        f.write("## Recommendations\n\n")
                        for key, value in evidence['result']['recommendations'].items():
                            if isinstance(value, list):
                                f.write(f"**{key.replace('_', ' ').title()}:**\n")
                                for item in value:
                                    f.write(f"- {item}\n")
                            else:
                                f.write(f"**{key.replace('_', ' ').title()}:** {value}\n")
                        f.write("\n")
                    
                    if evidence['result']['ml_best_practices']:
                        f.write("## ML Best Practices Assessment\n\n")
                        for practice, passed in evidence['result']['ml_best_practices'].items():
                            status = "✅" if passed else "❌"
                            f.write(f"- {status} {practice.replace('_', ' ').title()}\n")
                    
                    f.write(f"\n## Summary\n\n{evidence['result']['summary']}\n")
                    
                    # Add raw LLM input for reference
                    if 'llm_input_prompt' in evidence:
                        f.write(f"\n## Raw LLM Input\n\n")
                        f.write("```\n")
                        f.write(evidence['llm_input_prompt'])
                        f.write("\n```\n")
        
        logger.info(f"💾 Saved {len(self._pending_reports)} Job Reviewer report files to {evidence_dir}")
        self._pending_reports = []  # Clear pending reports