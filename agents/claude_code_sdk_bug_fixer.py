"""Claude Code SDK Bug Fixer implementation."""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from claude_code_sdk import query, ClaudeCodeOptions, Message
import anyio

from utils import setup_logger

logger = setup_logger(__name__)


class MinimalPromptBuilder:
    """Build minimal prompts for Claude Code SDK."""
    
    @staticmethod
    def build_prompt(node_name: str, error_message: str) -> str:
        """Build a minimal prompt with function block framework rules."""
        return f"""
I need help fixing an error in a function block.

Function Block: {node_name}
Error: {error_message}

The workspace contains:
- function_block.py: The main code to fix
- requirements.txt: Python dependencies

CRITICAL Function Block Framework Rules:

1. The function MUST have this signature:
   def run(path_dict, params):
       # path_dict contains:
       #   - input_dir: Input directory path
       #   - output_dir: Output directory path
       # params is a dictionary of parameters

2. For single-cell RNA-seq data (AnnData):
   - Input: Find and read actual h5ad files from path_dict["input_dir"]
   - Output: Save with descriptive names to path_dict["output_dir"]
   - Create output directories: os.makedirs(path_dict["output_dir"], exist_ok=True)
   - Figures go in: os.path.join(path_dict["output_dir"], "figures")
   - NOTE: '_node_anndata.h5ad' is just an optional convention - use any clear filename

3. Standard imports for single-cell analysis:
   import scanpy as sc
   import pandas as pd
   import numpy as np
   import matplotlib.pyplot as plt
   import os

4. NO return value - all outputs are written to files

5. Example structure:
   def run(path_dict, params):
       # Find actual input files
       from pathlib import Path
       input_dir = Path(path_dict["input_dir"])
       h5ad_files = list(input_dir.glob('*.h5ad'))
       
       if h5ad_files:
           # Load first h5ad file found
           adata = sc.read_h5ad(h5ad_files[0])
       else:
           raise FileNotFoundError(f"No h5ad files found in {{input_dir}}")
       
       # Save with descriptive name
       output_file = os.path.join(path_dict["output_dir"], "processed_data.h5ad")
       
       # Process using params
       # params is already a dict, use params.get('key', default)
       
       # Save output
       adata.write(output_file)

Please explore the workspace, understand the error, and fix it following these rules.
"""


class SDKResultParser:
    """Parse results from Claude Code SDK messages."""
    
    @staticmethod
    def parse_session_result(messages: List[Message]) -> Dict[str, Any]:
        """Extract success status and any modifications made.

        NOTE: 'success' here is a keyword HEURISTIC over the transcript (it can also
        match phrases such as "could not be fixed"). Real success must be decided by
        re-executing the function block; do not report success rates from this flag.
        """
        # Check for successful completion indicators
        success_indicators = [
            "fixed", "resolved", "corrected", "successfully", 
            "error has been addressed", "should now work"
        ]
        
        # Convert messages to string for analysis
        message_text = " ".join(str(m) for m in messages).lower()
        
        # Check if any success indicator is present
        success = any(indicator in message_text for indicator in success_indicators)
        
        # Find files that were modified
        files_modified = []
        for msg in messages:
            msg_str = str(msg)
            if any(action in msg_str for action in ["Edit", "Write", "edited", "modified", "fixed"]):
                files_modified.append(msg_str)
        
        return {
            "success": success,
            "messages": messages,
            "files_modified": files_modified,
            "message_count": len(messages)
        }


class ClaudeCodeSDKBugFixer:
    """Bug fixer implementation using Claude Code SDK."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        max_turns: int = 5,
        allowed_tools: List[str] = None
    ):
        """Initialize the SDK bug fixer.
        
        Args:
            api_key: Anthropic API key (uses env var if not provided)
            max_turns: Maximum conversation turns
            allowed_tools: List of allowed tools for SDK
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.max_turns = max_turns
        self.allowed_tools = allowed_tools or []
        self.debug_sessions = []
        
        # For tracking costs (estimated)
        self.total_cost = 0.0
        self.total_tokens = 0
        
    async def fix_bug(
        self,
        node_name: str,
        error_message: str,
        working_directory: Path,
        attempt_number: int = 1
    ) -> Dict[str, Any]:
        """Fix a bug using Claude Code SDK with minimal context.
        
        Args:
            node_name: Name of the function block
            error_message: The error message to fix
            working_directory: Path to the workspace
            attempt_number: Current attempt number
            
        Returns:
            Dictionary with success status and details
        """
        logger.info(f"Starting Claude Code SDK bug fix for {node_name} (attempt {attempt_number})")
        
        # Build minimal prompt
        prompt = MinimalPromptBuilder.build_prompt(node_name, error_message)
        
        # Configure SDK options
        options = ClaudeCodeOptions(
            max_turns=self.max_turns,
            cwd=str(working_directory),
            allowed_tools=self.allowed_tools,
            system_prompt="You are a Python debugging assistant. Fix errors in function blocks for single-cell RNA-seq analysis."
        )
        
        # Track session start
        session_start = datetime.now()
        messages = []
        
        try:
            # Execute query and collect messages
            async for message in query(prompt=prompt, options=options):
                messages.append(message)
                logger.debug(f"SDK Message: {message}")
            
            # Parse results
            result = SDKResultParser.parse_session_result(messages)
            
            # Track session
            session_duration = (datetime.now() - session_start).total_seconds()
            self._track_session(node_name, attempt_number, result, session_duration)
            
            # Log result
            if result['success']:
                logger.info(f"Claude Code SDK successfully fixed {node_name}")
            else:
                logger.warning(f"Claude Code SDK could not fix {node_name}")
            
            # Add debugging info
            result.update({
                'node_name': node_name,
                'attempt_number': attempt_number,
                'duration_seconds': session_duration,
                'total_cost': self.total_cost,
                'total_tokens': self.total_tokens
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error during SDK bug fixing: {str(e)}")
            
            # Check for specific errors
            if "claude-code: command not found" in str(e):
                raise RuntimeError(
                    "Claude Code CLI not installed. Please run: npm install -g @anthropic-ai/claude-code"
                )
            
            return {
                'success': False,
                'error': str(e),
                'node_name': node_name,
                'attempt_number': attempt_number,
                'messages': messages
            }
    
    def _track_session(
        self, 
        node_name: str, 
        attempt_number: int,
        result: Dict[str, Any],
        duration: float
    ):
        """Track debugging session for analysis."""
        session = {
            'node_name': node_name,
            'attempt_number': attempt_number,
            'success': result['success'],
            'message_count': result['message_count'],
            'files_modified': len(result.get('files_modified', [])),
            'duration_seconds': duration,
            'timestamp': datetime.now().isoformat()
        }
        
        self.debug_sessions.append(session)
        
        # ROUGH ESTIMATE ONLY (not measured): assumes ~500 tokens per message at a
        # fixed per-token price. total_cost/total_tokens below are estimates.
        estimated_tokens = result['message_count'] * 500
        estimated_cost = (estimated_tokens / 1000) * 0.00025  # Haiku input pricing
        
        self.total_tokens += estimated_tokens
        self.total_cost += estimated_cost
        
        logger.info(
            f"Session complete: {session['message_count']} messages, "
            f"~{estimated_tokens} tokens, ~${estimated_cost:.4f}"
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about debugging sessions."""
        if not self.debug_sessions:
            return {
                'total_sessions': 0,
                'successful_sessions': 0,
                'success_rate': 0.0,
                'total_cost': 0.0,
                'total_tokens': 0
            }
        
        successful = sum(1 for s in self.debug_sessions if s['success'])
        
        return {
            'total_sessions': len(self.debug_sessions),
            'successful_sessions': successful,
            'success_rate': successful / len(self.debug_sessions),
            'total_cost': self.total_cost,
            'total_tokens': self.total_tokens,
            'average_messages_per_session': sum(s['message_count'] for s in self.debug_sessions) / len(self.debug_sessions),
            'average_duration_seconds': sum(s['duration_seconds'] for s in self.debug_sessions) / len(self.debug_sessions),
            'note': "success_rate uses a transcript keyword heuristic; total_cost/total_tokens are rough estimates"
        }
    
    async def save_debug_history(self, output_path: Path):
        """Save debugging history to a file."""
        history = {
            'sessions': self.debug_sessions,
            'stats': self.get_stats(),
            'timestamp': datetime.now().isoformat()
        }
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(history, f, indent=2)
        
        logger.info(f"Saved debug history to {output_path}")


# Wrapper for synchronous usage if needed
def fix_bug_sync(
    bug_fixer: ClaudeCodeSDKBugFixer,
    node_name: str,
    error_message: str,
    working_directory: Path,
    attempt_number: int = 1
) -> Dict[str, Any]:
    """Synchronous wrapper for bug fixing."""
    return anyio.run(
        bug_fixer.fix_bug,
        node_name,
        error_message,
        working_directory,
        attempt_number
    )