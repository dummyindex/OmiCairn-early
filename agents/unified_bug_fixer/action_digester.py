"""Action Digester for compressing long action results while preserving critical debugging information."""

import json
import re
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from llm_service import BaseLLMService
from utils import setup_logger

logger = setup_logger(__name__)


@dataclass
class ActionDigest:
    """Represents a digested action result."""
    summary: str
    key_findings: List[str]
    preserved_evidence: Dict[str, Any]
    actionable_insights: List[str]
    requires_followup: bool
    original_length: int
    compression_ratio: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "summary": self.summary,
            "key_findings": self.key_findings,
            "preserved_evidence": self.preserved_evidence,
            "actionable_insights": self.actionable_insights,
            "requires_followup": self.requires_followup,
            "original_length": self.original_length,
            "compression_ratio": self.compression_ratio
        }


class ActionDigester:
    """Digests long action results while preserving critical debugging information."""
    
    # JSON schema for LLM output validation
    ACTION_DIGEST_SCHEMA = {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "maxLength": 500,
                "description": "Concise summary of action result"
            },
            "key_findings": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 5,
                "description": "Most important discoveries from this action"
            },
            "preserved_evidence": {
                "type": "object",
                "properties": {
                    "error_messages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Critical error messages that must be preserved"
                    },
                    "stack_traces": {
                        "type": "array", 
                        "items": {"type": "string"},
                        "description": "Important stack trace segments"
                    },
                    "critical_values": {
                        "type": "array",
                        "description": "Important variable values, file sizes, etc.",
                        "items": {"type": "string"},
                        "maxItems": 10
                    },
                    "file_states": {
                        "type": "array",
                        "description": "Critical information about file existence, permissions, etc.",
                        "items": {"type": "string"},
                        "maxItems": 10
                    }
                },
                "required": ["error_messages", "stack_traces", "critical_values", "file_states"],
                "additionalProperties": False
            },
            "actionable_insights": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 3,
                "description": "Specific next steps or debugging directions"
            },
            "requires_followup": {
                "type": "boolean",
                "description": "Whether this action requires immediate follow-up"
            }
        },
        "required": ["summary", "key_findings", "preserved_evidence", "actionable_insights", "requires_followup"],
        "additionalProperties": False
    }
    
    def __init__(
        self, 
        llm_service: BaseLLMService, 
        llm_seed: Optional[int] = None,
        length_threshold: int = 5000,
        skip_actions: Optional[Set[str]] = None
    ):
        """Initialize action digester.
        
        Args:
            llm_service: LLM service for digesting action results
            llm_seed: Seed for LLM reproducibility (optional)
            length_threshold: Character threshold for triggering digestion
            skip_actions: Set of action types to never digest
        """
        self.llm_service = llm_service
        self.llm_seed = llm_seed
        self.length_threshold = length_threshold
        # Set default skip actions if none provided
        if skip_actions is None:
            self.skip_actions = {
                "update_function_block",  # Always preserve full execution results
                "execute_command"  # Often need full command output for debugging
            }
        else:
            self.skip_actions = skip_actions
        
        # Statistics tracking
        self.total_digests = 0
        self.total_compression = 0.0
        
        logger.info(f"Initialized ActionDigester with threshold={length_threshold}, skip_actions={self.skip_actions}")
    
    def should_digest(self, action_type: str, result: str) -> bool:
        """Determine if action result needs digestion.
        
        Args:
            action_type: Type of action performed
            result: Raw result string
            
        Returns:
            True if digestion is recommended
        """
        # Skip certain action types
        if action_type in self.skip_actions:
            logger.debug(f"Skipping digestion for action type: {action_type}")
            return False
        
        # Check length threshold
        if len(result) <= self.length_threshold:
            logger.debug(f"Result length {len(result)} below threshold {self.length_threshold}")
            return False
        
        # Skip if result is mostly empty lines or whitespace
        non_empty_lines = [line for line in result.split('\n') if line.strip()]
        if len(non_empty_lines) < 10:  # Very short content, even if long due to whitespace
            logger.debug("Result has too few non-empty lines for digestion")
            return False
        
        logger.debug(f"Action {action_type} with {len(result)} characters needs digestion")
        return True
    
    def digest_action_result(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        raw_result: str,
        error_context: str,
        debugging_goal: str
    ) -> ActionDigest:
        """Digest long action results while preserving key evidence.
        
        Args:
            action_type: Type of action performed
            action_params: Parameters used for the action
            raw_result: Full result string
            error_context: Context about the error being debugged
            debugging_goal: What we're trying to accomplish
            
        Returns:
            ActionDigest with compressed information
        """
        # Log clear evidence to stdout
        logger.info("🗜️  ACTION DIGESTER AGENT ACTIVITY - Large result compression")
        logger.info(f"  Action type: {action_type}")
        logger.info(f"  Original size: {len(raw_result):,} characters")
        logger.info(f"  Compression triggered: Exceeded {self.length_threshold:,} char threshold")
        
        try:
            # Build digestion prompt
            prompt = self._build_digest_prompt(
                action_type, action_params, raw_result, error_context, debugging_goal
            )
            
            # Call LLM with structured output
            messages = [{"role": "user", "content": prompt}]
            
            response = self.llm_service.chat_completion_json(
                messages=messages,
                json_schema=self.ACTION_DIGEST_SCHEMA,
                temperature=0.1,  # Low temperature for consistency
                max_tokens=1500,  # Reasonable limit for digest
                seed=self.llm_seed
            )
            
            # Validate required fields
            required_fields = ["summary", "key_findings", "preserved_evidence", "actionable_insights", "requires_followup"]
            for field in required_fields:
                if field not in response:
                    raise ValueError(f"LLM response missing required field: {field}")
            
            # Calculate compression ratio
            digest_length = len(json.dumps(response))
            compression_ratio = digest_length / len(raw_result) if len(raw_result) > 0 else 0.0
            
            # Create digest object
            digest = ActionDigest(
                summary=response["summary"],
                key_findings=response["key_findings"],
                preserved_evidence=response["preserved_evidence"],
                actionable_insights=response["actionable_insights"],
                requires_followup=response["requires_followup"],
                original_length=len(raw_result),
                compression_ratio=compression_ratio
            )
            
            # Validate the digest preserves critical information
            if not self._validate_digest(digest, raw_result, error_context):
                raise ValueError("Digest validation failed - critical information not preserved")
            
            # Update statistics
            self.total_digests += 1
            self.total_compression += compression_ratio
            
            logger.info(f"  Compressed to: {digest_length:,} characters (ratio: {compression_ratio:.2f})")
            logger.info(f"  Key findings: {len(response['key_findings'])} items")
            logger.info(f"  Requires followup: {response['requires_followup']}")
            logger.info("📁 Action digest files saved to agent_tasks/action_digests/")
            
            # Save digest report
            self._save_report(action_type, raw_result, digest)
            
            return digest
            
        except Exception as e:
            logger.error(f"Error digesting action result: {e}")
            raise
    
    def _build_digest_prompt(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        raw_result: str,
        error_context: str,
        debugging_goal: str
    ) -> str:
        """Build the prompt for digesting action results."""
        
        # Truncate very long results for prompt efficiency
        result_sample = raw_result
        if len(raw_result) > 10000:
            # Take first and last parts for context
            result_sample = (
                raw_result[:4000] + 
                "\n\n... [CONTENT TRUNCATED FOR DIGESTION] ...\n\n" + 
                raw_result[-2000:]
            )
        
        prompt = f"""You are an expert debugging assistant. Your task is to digest a long action result while preserving all critical information needed for debugging.

DEBUGGING CONTEXT:
- Goal: {debugging_goal}
- Error Context: {error_context}
- Action: {action_type}
- Action Parameters: {json.dumps(action_params, indent=2)}

ORIGINAL RESULT ({len(raw_result)} characters):
```
{result_sample}
```

DIGESTION REQUIREMENTS:

1. **SUMMARY** (max 500 chars): Concise overview of what this action discovered

2. **KEY FINDINGS** (max 5 items): Most important discoveries that help with debugging

3. **PRESERVED EVIDENCE**: Extract and preserve these critical elements:
   - **error_messages**: Any error messages, exceptions, or failure indicators (array of strings)
   - **stack_traces**: Important traceback information showing where errors occur (array of strings)
   - **critical_values**: Important variable values, file sizes, line numbers, etc. (array of strings, e.g. ["line_number: 3", "file_size: 1024"])
   - **file_states**: File existence, permissions, directory contents that matter (array of strings, e.g. ["file.txt exists", "directory is writable"])

4. **ACTIONABLE INSIGHTS** (max 3 items): Specific next steps or debugging directions based on this result

5. **REQUIRES_FOLLOWUP**: Does this result indicate immediate action is needed?

CRITICAL PRESERVATION RULES:
- If there are ANY error messages, they MUST be preserved exactly
- Stack traces showing error locations must be kept
- File paths, line numbers, and variable values that could help debugging
- Any output that directly relates to the current error being debugged
- Preserve exact error text, not paraphrases

Focus on debugging utility - what information from this result will help fix the current error?"""

        return prompt
    
    def _validate_digest(self, digest: ActionDigest, raw_result: str, error_context: str) -> bool:
        """Validate that digest preserves critical information.
        
        Args:
            digest: The generated digest
            raw_result: Original result
            error_context: Error context for validation
            
        Returns:
            True if digest is valid
        """
        try:
            # Check if error messages are preserved when present in original
            error_indicators = ["error", "exception", "failed", "traceback", "errno"]
            raw_lower = raw_result.lower()
            
            has_errors = any(indicator in raw_lower for indicator in error_indicators)
            
            if has_errors:
                # Ensure error messages are preserved
                error_messages = digest.preserved_evidence.get("error_messages", [])
                if not error_messages:
                    logger.warning("Original has errors but no error messages preserved")
                    return False
            
            # Check that summary is not empty
            if not digest.summary or len(digest.summary.strip()) < 10:
                logger.warning("Summary is too short or empty")
                return False
            
            # Check that key findings exist for long results
            if digest.original_length > 10000 and len(digest.key_findings) == 0:
                logger.warning("Large result but no key findings identified")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating digest: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get digestion statistics.
        
        Returns:
            Dictionary with usage statistics
        """
        avg_compression = (
            self.total_compression / self.total_digests 
            if self.total_digests > 0 else 0.0
        )
        
        return {
            "total_digests": self.total_digests,
            "average_compression_ratio": avg_compression,
            "length_threshold": self.length_threshold,
            "skip_actions": list(self.skip_actions)
        }
    
    def _save_report(self, action_type: str, original_result: str, digest: ActionDigest):
        """Save action digest report for tracking and analysis."""
        from pathlib import Path
        import json
        
        # Log clear evidence to stdout
        logger.info("🗜️ ACTION DIGESTER ACTIVITY - Long result compressed")
        logger.info(f"  Action type: {action_type}")
        logger.info(f"  Original length: {digest.original_length:,} chars")
        logger.info(f"  Compression ratio: {digest.compression_ratio:.1%}")
        logger.info(f"  Key findings: {len(digest.key_findings)}")
        logger.info(f"  Requires follow-up: {digest.requires_followup}")
        
        # Create a standardized evidence structure
        evidence = {
            "agent": "Action Digester",
            "timestamp": datetime.now().isoformat(),
            "activity": "action_result_compression",
            "action_type": action_type,
            "original_length": digest.original_length,
            "compression_ratio": digest.compression_ratio,
            "digest": digest.to_dict(),
            "summary": {
                "compressed": True,
                "key_findings_count": len(digest.key_findings),
                "requires_followup": digest.requires_followup,
                "preserved_evidence_keys": list(digest.preserved_evidence.keys())
            }
        }
        
        # Store in class for later saving when node directory is available
        if not hasattr(self, '_pending_reports'):
            self._pending_reports = []
        self._pending_reports.append(evidence)
        
        logger.info(f"📊 Action Digester report recorded (will be saved to agent_tasks/action_digests/)")
            
    
    def save_reports_to_directory(self, save_dir: Path):
        """Save all pending reports to the specified directory.
        
        Args:
            save_dir: Directory where reports should be saved (can be node_dir or bug_fixer_attempt_dir)
        """
        if not hasattr(self, '_pending_reports') or not self._pending_reports:
            logger.debug("No pending action digester reports to save")
            return
        
        # Create action digests directory
        # If save_dir already contains agent_tasks (like bug_fixer_attempt_dir), don't duplicate
        if "agent_tasks" in str(save_dir):
            evidence_dir = save_dir / "action_digests"
        else:
            evidence_dir = save_dir / "agent_tasks" / "action_digests"
        
        evidence_dir.mkdir(parents=True, exist_ok=True)
        
        for i, evidence in enumerate(self._pending_reports):
            timestamp = evidence["timestamp"].replace(":", "").replace("-", "")[:15]
            
            # Save JSON report
            json_file = evidence_dir / f"digest_{timestamp}_{i:02d}.json"
            with open(json_file, 'w') as f:
                json.dump(evidence, f, indent=2)
            
            # Save human-readable report
            md_file = evidence_dir / f"digest_{timestamp}_{i:02d}.md"
            with open(md_file, 'w') as f:
                f.write(f"# Action Digester Report\n\n")
                f.write(f"**Timestamp:** {evidence['timestamp']}\n")
                f.write(f"**Action Type:** {evidence['action_type']}\n")
                f.write(f"**Original Length:** {evidence['original_length']:,} characters\n")
                f.write(f"**Compression Ratio:** {evidence['compression_ratio']:.1%}\n\n")
                
                digest = evidence['digest']
                f.write(f"## Summary\n\n{digest['summary']}\n\n")
                
                if digest['key_findings']:
                    f.write("## Key Findings\n\n")
                    for finding in digest['key_findings']:
                        f.write(f"- {finding}\n")
                    f.write("\n")
                
                if digest.get('actionable_insights'):
                    f.write("## Actionable Insights\n\n")
                    for insight in digest['actionable_insights']:
                        f.write(f"- {insight}\n")
                    f.write("\n")
                
                if digest['preserved_evidence']:
                    f.write("## Preserved Evidence\n\n")
                    for key, value in digest['preserved_evidence'].items():
                        f.write(f"### {key.replace('_', ' ').title()}\n")
                        if isinstance(value, list):
                            for item in value[:3]:  # Limit to first 3
                                f.write(f"- {item}\n")
                        elif isinstance(value, dict):
                            f.write("```json\n")
                            f.write(json.dumps(value, indent=2)[:500])
                            if len(json.dumps(value)) > 500:
                                f.write("\n... (truncated)")
                            f.write("\n```\n")
                        else:
                            f.write(f"{value}\n")
                        f.write("\n")
                
                f.write(f"**Requires Follow-up:** {'Yes' if digest['requires_followup'] else 'No'}\n")
        
        logger.info(f"💾 Saved {len(self._pending_reports)} Action Digester report files to {evidence_dir}")
        self._pending_reports = []  # Clear pending reports