"""Code quality checker agent for validating function block code."""

import json
import re
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

from llm_service import BaseLLMService
from utils import setup_logger

logger = setup_logger(__name__)


@dataclass
class CodeIssue:
    """Represents a code quality issue."""
    category: str  # "import", "syntax", "logic", "best_practice", "security"
    severity: str  # "error", "warning", "info"
    line_number: Optional[int]
    description: str
    fix: str


@dataclass
class CodeCheckResult:
    """Result of code quality check."""
    valid: bool
    issues: List[CodeIssue]
    improvements: List[str]
    must_fix: bool
    suggested_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "valid": self.valid,
            "issues": [
                {
                    "category": issue.category,
                    "severity": issue.severity,
                    "line_number": issue.line_number,
                    "description": issue.description,
                    "fix": issue.fix
                }
                for issue in self.issues
            ],
            "improvements": self.improvements,
            "must_fix": self.must_fix,
            "suggested_code": self.suggested_code
        }


class CodeCheckerAgent:
    """Agent for checking code quality and correctness with language-agnostic rules."""
    
    # JSON schema for LLM output validation
    CODE_CHECK_SCHEMA = {
        "type": "object",
        "properties": {
            "valid": {"type": "boolean"},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string", 
                            "enum": ["import", "syntax", "logic", "best_practice", "security"]
                        },
                        "severity": {
                            "type": "string", 
                            "enum": ["error", "warning", "info"]
                        },
                        "line_number": {"type": ["integer", "null"]},
                        "description": {"type": "string"},
                        "fix": {"type": "string"}
                    },
                    "required": ["category", "severity", "line_number", "description", "fix"],
                    "additionalProperties": False
                }
            },
            "improvements": {
                "type": "array",
                "items": {"type": "string"}
            },
            "must_fix": {"type": "boolean"},
            "suggested_code": {"type": ["string", "null"]}
        },
        "required": ["valid", "issues", "improvements", "must_fix", "suggested_code"],
        "additionalProperties": False
    }
    
    # Domain-specific rules for different languages
    DOMAIN_RULES = {
        "python": {
            "code_completeness": [
                "NEVER use placeholder comments like '# ... (rest of code remains unchanged)'",
                "ALWAYS provide complete, runnable code - no abbreviations or omissions",
                "If suggesting fixes, include the ENTIRE function, not just snippets",
                "Do NOT use ellipsis (...) to abbreviate code sections"
            ],
            "imports": [
                "Every used module must be imported at the function start (common issue: missing 'import os')",
                "Standard libraries like os, json, pathlib should be imported before third-party libraries",
                "Avoid star imports (from module import *) - use specific imports",
                "Import statements should be at the top of the run() function"
            ],
            "error_handling": [
                "File operations should handle FileNotFoundError and PermissionError",
                "API calls should have appropriate try/catch blocks",
                "Always check if files exist before reading them"
            ],
            "data_science": [
                "Always check if data is empty before processing (e.g., adata.n_obs > 0)",
                "Handle missing values appropriately in data analysis",
                "Validate array/matrix shapes before operations",
                "Use scanpy.settings.verbosity to control output",
                "Create output directory with os.makedirs(path_dict['output_dir'], exist_ok=True)"
            ],
            "function_structure": [
                "Function must be named 'run' and accept (path_dict, params) arguments",
                "Must read from path_dict['input_dir'] and write to path_dict['output_dir']",
                "For root nodes: read original data files, for child nodes: read '_node_anndata.h5ad'",
                "Always save main output as '_node_anndata.h5ad' in output directory"
            ]
        },
        "r": {
            "code_completeness": [
                "NEVER use placeholder comments like '# ... (rest of code remains unchanged)'",
                "ALWAYS provide complete, runnable code - no abbreviations or omissions",
                "If suggesting fixes, include the ENTIRE function, not just snippets",
                "Do NOT use ellipsis (...) to abbreviate code sections"
            ],
            "imports": [
                "Use library() for each required package at function start",
                "Check if package is installed before loading with require()",
                "Load packages in logical order (base packages first)"
            ],
            "error_handling": [
                "Use tryCatch for error-prone operations",
                "Check file existence with file.exists() before reading",
                "Handle missing packages gracefully"
            ],
            "data_science": [
                "Always validate data dimensions before processing",
                "Handle missing values (NA) appropriately",
                "Use appropriate file I/O functions (readRDS, saveRDS for Seurat objects)",
                "Check object class before operations (e.g., is(obj, 'Seurat'))"
            ],
            "function_structure": [
                "Function must be named 'run' and accept (path_dict, params) arguments",
                "Must read from path_dict$input_dir and write to path_dict$output_dir",
                "Create output directory with dir.create(path_dict$output_dir, recursive=TRUE, showWarnings=FALSE)",
                "For Seurat objects: save as '_node_seuratObject.rds'"
            ]
        }
    }
    
    def __init__(
        self, 
        llm_service: BaseLLMService, 
        llm_seed: Optional[int] = None,
        enable_domain_knowledge: bool = True,
        domain_knowledge_domains: Optional[List[str]] = None
    ):
        """Initialize code checker agent.
        
        Args:
            llm_service: LLM service for code analysis
            llm_seed: Seed for LLM reproducibility (optional)
            enable_domain_knowledge: Whether to use domain knowledge injection
            domain_knowledge_domains: List of domain knowledge to inject
        """
        self.llm_service = llm_service
        self.llm_seed = llm_seed
        
        # Initialize domain knowledge if enabled
        self.enable_domain_knowledge = enable_domain_knowledge
        self.domain_knowledge_domains = domain_knowledge_domains or ["code_quality_best_practices"]
        
        if self.enable_domain_knowledge:
            try:
                from domain_knowledge import get_knowledge_service, PromptInjector
                self.knowledge_service = get_knowledge_service()
                self.prompt_injector = PromptInjector(self.knowledge_service)
                logger.info(f"Domain knowledge enabled for code checker: {self.domain_knowledge_domains}")
            except ImportError:
                logger.warning("Domain knowledge not available, using basic prompts")
                self.enable_domain_knowledge = False
        
        # Keep DOMAIN_RULES as fallback for now but prefer domain knowledge
        self.domain_rules = self.DOMAIN_RULES if not self.enable_domain_knowledge else {}
        
        logger.info("Initialized CodeCheckerAgent")
    
    def check_code(
        self,
        code: str,
        language: str,
        requirements: List[str],
        function_description: str,
        config: Optional[Dict[str, Any]] = None
    ) -> CodeCheckResult:
        """Check code quality and correctness.
        
        Args:
            code: The code to check
            language: Programming language ("python" or "r")
            requirements: List of package requirements
            function_description: Description of what the function should do
            config: Optional configuration parameters
            
        Returns:
            CodeCheckResult with validation results
        """
        logger.info(f"Checking {language} code quality for function: {function_description[:50]}...")
        
        try:
            # Get language-specific rules
            lang_rules = self.domain_rules.get(language.lower(), {})
            
            # Build prompt with domain knowledge
            prompt = self._build_check_prompt(
                code, language, requirements, function_description, lang_rules, config
            )
            
            # Call LLM with structured output
            messages = [{"role": "user", "content": prompt}]
            
            response = self.llm_service.chat_completion_json(
                messages=messages,
                json_schema=self.CODE_CHECK_SCHEMA,
                temperature=0.1,  # Low temperature for consistency
                max_tokens=2000,
                seed=self.llm_seed
            )
            
            # Convert to CodeCheckResult
            result = self._parse_llm_response(response)
            
            logger.info(f"Code check completed: valid={result.valid}, issues={len(result.issues)}, must_fix={result.must_fix}")
            
            # Save code checking report
            self._save_report(function_description, language, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error in code check: {e}")
            raise
    
    def _build_check_prompt(
        self,
        code: str,
        language: str,
        requirements: List[str],
        function_description: str,
        lang_rules: Dict[str, List[str]],
        config: Optional[Dict[str, Any]]
    ) -> str:
        """Build the prompt for code checking."""
        
        # Build base prompt
        prompt = f"""You are an expert code reviewer specializing in scientific data analysis pipelines.

TASK: Review the following {language.upper()} function block code for quality issues and correctness.

FUNCTION DESCRIPTION: {function_description}

REQUIREMENTS: {', '.join(requirements) if requirements else 'None specified'}

CONFIGURATION: {json.dumps(config, indent=2) if config else 'None'}

CODE TO REVIEW:
```{language}
{code}
```

CRITICAL VALIDATION CRITERIA:
1. **IMPORTS**: All used modules/packages must be properly imported
2. **FUNCTION STRUCTURE**: Must follow the required run(path_dict, params) signature
3. **ERROR HANDLING**: Should handle common error conditions gracefully
4. **DATA VALIDATION**: Check for empty data, proper formats, etc.
5. **OUTPUT REQUIREMENTS**: Must create output directory and save required files
6. **LOGIC CORRECTNESS**: Implementation should match the function description
7. **BEST PRACTICES**: Follow language-specific best practices
8. **SECURITY**: No obvious security vulnerabilities

SEVERITY LEVELS:
- **error**: Code will not run or produces incorrect results
- **warning**: Code runs but has potential issues
- **info**: Minor style or optimization suggestions

For each issue found:
1. Identify the exact problem
2. Explain why it's an issue
3. Provide a specific fix

If must_fix is true, provide corrected code in suggested_code field.
Only set must_fix=true for critical errors that prevent execution.

⚠️ CRITICAL REQUIREMENTS FOR SUGGESTED CODE:
- **NEVER use placeholders** like "# ... (rest of the code remains unchanged) ..."
- **NEVER abbreviate code** with comments like "# existing code here"
- **ALWAYS provide the COMPLETE, RUNNABLE function** in suggested_code
- **INCLUDE ALL imports, logic, and error handling** - no omissions
- The suggested_code must be a drop-in replacement that can be executed immediately
- If you cannot provide complete code, set must_fix=false instead

Focus on functional correctness over style preferences."""
        
        # Inject domain knowledge if enabled
        if self.enable_domain_knowledge and hasattr(self, 'prompt_injector'):
            prompt = self.prompt_injector.inject_domain_knowledge(
                prompt, 
                self.domain_knowledge_domains
            )
        
        return prompt
    
    def _parse_llm_response(self, response: Dict[str, Any]) -> CodeCheckResult:
        """Parse LLM response into CodeCheckResult."""
        
        # Validate required fields
        if "valid" not in response or "issues" not in response or "must_fix" not in response:
            raise ValueError("LLM response missing required fields")
        
        # Parse issues
        issues = []
        for issue_data in response.get("issues", []):
            issues.append(
                CodeIssue(
                    category=issue_data["category"],
                    severity=issue_data["severity"],
                    line_number=issue_data.get("line_number"),
                    description=issue_data["description"],
                    fix=issue_data["fix"]
                )
            )
        
        # Check for placeholder code before creating result
        suggested_code = response.get("suggested_code")
        must_fix = response["must_fix"]
        
        if suggested_code and must_fix:
            # Ensure suggested code is complete
            placeholder_patterns = [
                "# ... (rest of the code remains unchanged)",
                "# ... (rest of the code",
                "# existing code here", 
                "# rest of the code",
                "# ... rest of",
                "...",
            ]
            
            for pattern in placeholder_patterns:
                if pattern in suggested_code:
                    logger.warning(f"Code checker returned incomplete code with placeholder: '{pattern}'")
                    logger.warning("Disabling must_fix due to incomplete suggested code")
                    must_fix = False
                    suggested_code = None
                    break
        
        return CodeCheckResult(
            valid=response["valid"],
            issues=issues,
            improvements=response.get("improvements", []),
            must_fix=must_fix,
            suggested_code=suggested_code
        )
    
    def validate_response(self, response: Dict[str, Any]) -> bool:
        """Validate that LLM response follows expected schema."""
        try:
            # Basic structure validation
            required_fields = ["valid", "issues", "must_fix"]
            for field in required_fields:
                if field not in response:
                    logger.error(f"Missing required field: {field}")
                    return False
            
            # Validate issues structure
            for issue in response.get("issues", []):
                required_issue_fields = ["category", "severity", "description", "fix"]
                for field in required_issue_fields:
                    if field not in issue:
                        logger.error(f"Issue missing required field: {field}")
                        return False
                
                # Validate enums
                if issue["category"] not in ["import", "syntax", "logic", "best_practice", "security"]:
                    logger.error(f"Invalid issue category: {issue['category']}")
                    return False
                
                if issue["severity"] not in ["error", "warning", "info"]:
                    logger.error(f"Invalid issue severity: {issue['severity']}")
                    return False
            
            # If must_fix is true, suggested_code should be provided
            if response["must_fix"] and not response.get("suggested_code"):
                logger.warning("must_fix is true but no suggested_code provided")
            
            # Check for placeholder code
            if response.get("suggested_code"):
                placeholder_patterns = [
                    "# ... (rest of the code remains unchanged)",
                    "# ... (rest of the code",
                    "# existing code here",
                    "# rest of the code",
                    "# ... rest of",
                    "# ... (unchanged)",
                    "# ... unchanged",
                    "...",
                    "# TODO:",
                    "# FIXME:"
                ]
                
                suggested_code = response["suggested_code"]
                for pattern in placeholder_patterns:
                    if pattern in suggested_code:
                        logger.error(f"Suggested code contains placeholder: '{pattern}'")
                        logger.error("Code checker must provide COMPLETE code without placeholders")
                        # Force must_fix to false if placeholders found
                        response["must_fix"] = False
                        response["suggested_code"] = None
                        break
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating response: {e}")
            return False
    
    def _save_report(self, function_description: str, language: str, result: CodeCheckResult):
        """Save code checking report for tracking and analysis."""
        from pathlib import Path
        import json
        from datetime import datetime
        
        # Log clear evidence to stdout
        logger.info("🔍 CODE CHECKER AGENT ACTIVITY - Validation completed")
        logger.info(f"  Function: {function_description[:50]}...")
        logger.info(f"  Language: {language}")
        logger.info(f"  Result: {'✅ PASSED' if result.valid else '❌ FAILED'}")
        logger.info(f"  Issues found: {len(result.issues)}")
        logger.info(f"  Must fix: {result.must_fix}")
        logger.info(f"  Auto-fix available: {'Yes' if result.suggested_code else 'No'}")
        
        # Save detailed report to function creator's agent_tasks folder
        # This will be in the node directory structure
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Create a standardized evidence structure
        evidence = {
            "agent": "Code Checker",
            "timestamp": datetime.now().isoformat(),
            "activity": "code_validation",
            "function_description": function_description,
            "language": language,
            "result": result.to_dict(),
            "summary": {
                "passed": result.valid,
                "issues_count": len(result.issues),
                "must_fix": result.must_fix,
                "auto_fix_available": result.suggested_code is not None
            }
        }
        
        # Store in class for later saving when node directory is available
        if not hasattr(self, '_pending_reports'):
            self._pending_reports = []
        self._pending_reports.append(evidence)
        
        logger.info(f"📊 Code Checker report recorded (will be saved to agent_tasks/code_checker/)")
            
    
    def save_reports_to_directory(self, save_dir: Path):
        """Save all pending reports to the specified directory."""
        if not hasattr(self, '_pending_reports') or not self._pending_reports:
            logger.debug("No pending code checker reports to save")
            return
            
        # Create code checker subdirectory
        # If save_dir already contains agent_tasks (like bug_fixer_attempt_dir), use it directly
        if "agent_tasks" in str(save_dir) and "unified_bug_fixer" in str(save_dir):
            evidence_dir = save_dir / "code_checker"
        else:
            evidence_dir = save_dir / "code_checker"
        
        evidence_dir.mkdir(parents=True, exist_ok=True)
        
        for i, evidence in enumerate(self._pending_reports):
            timestamp = evidence["timestamp"].replace(":", "").replace("-", "")[:15]
            
            # Save JSON report
            json_file = evidence_dir / f"validation_{timestamp}_{i:02d}.json"
            with open(json_file, 'w') as f:
                json.dump(evidence, f, indent=2)
            
            # Save human-readable report
            md_file = evidence_dir / f"validation_{timestamp}_{i:02d}.md"
            with open(md_file, 'w') as f:
                f.write(f"# Code Checker Validation Report\n\n")
                f.write(f"**Timestamp:** {evidence['timestamp']}\n")
                f.write(f"**Function:** {evidence['function_description']}\n")
                f.write(f"**Language:** {evidence['language']}\n")
                f.write(f"**Result:** {'✅ PASSED' if evidence['summary']['passed'] else '❌ FAILED'}\n\n")
                
                if evidence['result']['issues']:
                    f.write("## Issues Found\n\n")
                    for issue in evidence['result']['issues']:
                        f.write(f"- **{issue['severity'].upper()}** ({issue['category']}): {issue['description']}\n")
                        if issue['fix']:
                            f.write(f"  - *Fix:* {issue['fix']}\n")
                
                if evidence['result']['improvements']:
                    f.write("\n## Improvement Suggestions\n\n")
                    for improvement in evidence['result']['improvements']:
                        f.write(f"- {improvement}\n")
                
                if evidence['result']['suggested_code']:
                    f.write("\n## Auto-Fix Code\n\n")
                    f.write("```python\n")
                    f.write(evidence['result']['suggested_code'])
                    f.write("\n```\n")
        
        logger.info(f"💾 Saved {len(self._pending_reports)} Code Checker report files to {evidence_dir}")
        self._pending_reports = []  # Clear pending reports
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get usage statistics for the code checker."""
        # For future implementation - track usage metrics
        return {
            "total_checks": 0,
            "checks_passed": 0,
            "common_issues": {}
        }