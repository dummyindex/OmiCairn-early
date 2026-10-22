"""Test report saving functionality for code checker, job reviewer, and action digester agents."""

import os
import tempfile
import shutil
from pathlib import Path
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from agents.code_checker_agent import CodeCheckerAgent, CodeCheckResult, CodeIssue
from agents.job_reviewer_agent import JobReviewerAgent, JobReviewResult, JobConcern
from agents.unified_bug_fixer.action_digester import ActionDigester, ActionDigest
from models import AnalysisNode, NewFunctionBlock, FunctionBlockType, ExecutionResult


class TestCodeCheckerReportSaving:
    """Test code checker agent report saving functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.llm_service = Mock()
        self.code_checker = CodeCheckerAgent(self.llm_service)
        
    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
    def test_code_checker_saves_reports(self):
        """Test that code checker saves reports when save_reports_to_directory is called."""
        # Mock LLM response
        self.llm_service.chat_completion_json.return_value = {
            "valid": False,
            "issues": [
                {
                    "category": "import",
                    "severity": "error",
                    "line_number": 5,
                    "description": "Missing import for 'os' module",
                    "fix": "Add 'import os' at the beginning of the function"
                }
            ],
            "improvements": ["Consider using pathlib instead of os.path"],
            "must_fix": True,
            "suggested_code": "def run(path_dict, params):\n    import os\n    # rest of code"
        }
        
        # Perform code check
        result = self.code_checker.check_code(
            code="def run(path_dict, params):\n    path = os.path.join('test')",
            language="python",
            requirements=["numpy"],
            function_description="Test function block"
        )
        
        # Verify result
        assert not result.valid
        assert len(result.issues) == 1
        assert result.must_fix
        
        # Save reports to directory
        self.code_checker.save_reports_to_directory(self.test_dir)
        
        # Check report files were created
        evidence_dir = self.test_dir / "agent_tasks" / "code_checker"
        assert evidence_dir.exists()
        
        # Check for JSON and MD files
        json_files = list(evidence_dir.glob("validation_*.json"))
        md_files = list(evidence_dir.glob("validation_*.md"))
        
        assert len(json_files) == 1
        assert len(md_files) == 1
        
        # Verify JSON content
        with open(json_files[0], 'r') as f:
            evidence = json.load(f)
        
        assert evidence["agent"] == "Code Checker"
        assert evidence["activity"] == "code_validation"
        assert evidence["function_description"] == "Test function block"
        assert evidence["language"] == "python"
        assert not evidence["summary"]["passed"]
        assert evidence["summary"]["issues_count"] == 1
        assert evidence["summary"]["must_fix"]
        
        # Verify MD content
        with open(md_files[0], 'r') as f:
            md_content = f.read()
        
        assert "Code Checker Validation Report" in md_content
        assert "❌ FAILED" in md_content
        assert "Missing import for 'os' module" in md_content
        assert "Add 'import os'" in md_content
        
    def test_code_checker_multiple_report_entries(self):
        """Test that code checker accumulates multiple report entries."""
        # Mock multiple checks
        self.llm_service.chat_completion_json.return_value = {
            "valid": True,
            "issues": [],
            "must_fix": False
        }
        
        # Perform multiple code checks
        for i in range(3):
            self.code_checker.check_code(
                code=f"def run(path_dict, params): pass  # Check {i}",
                language="python",
                requirements=[],
                function_description=f"Function {i}"
            )
        
        # Save reports
        self.code_checker.save_reports_to_directory(self.test_dir)
        
        # Check all report files were created
        evidence_dir = self.test_dir / "agent_tasks" / "code_checker"
        json_files = list(evidence_dir.glob("validation_*.json"))
        
        assert len(json_files) == 3
        
        # Verify each has unique content
        functions_found = set()
        for json_file in json_files:
            with open(json_file, 'r') as f:
                evidence = json.load(f)
            functions_found.add(evidence["function_description"])
        
        assert len(functions_found) == 3
        assert all(f"Function {i}" in functions_found for i in range(3))


class TestJobReviewerReportSaving:
    """Test job reviewer agent report saving functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.llm_service = Mock()
        self.job_reviewer = JobReviewerAgent(self.llm_service)
        
    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
    def test_job_reviewer_saves_reports(self):
        """Test that job reviewer saves reports when save_reports_to_directory is called."""
        # Create test objects
        node = AnalysisNode(
            id="test_node",
            name="Test Node",
            description="Test node description"
        )
        
        function_block = NewFunctionBlock(
            id="test_fb",
            name="Test Function",
            type=FunctionBlockType.PYTHON,
            description="Test function block",
            code="def run(path_dict, params):\n    return {'fake': 'results'}",
            requirements=[]
        )
        
        execution_result = ExecutionResult(
            success=True,
            stdout="Processing complete",
            stderr="",
            output_path=str(self.test_dir / "output")
        )
        
        # Mock LLM response
        self.llm_service.chat_completion_json.return_value = {
            "passed": False,
            "concerns": [
                {
                    "type": "cheating",
                    "severity": "critical",
                    "description": "Function returns hardcoded fake results",
                    "evidence": "return {'fake': 'results'}",
                    "suggested_fix": "Implement actual data processing logic"
                }
            ],
            "recommendations": {
                "needs_rework": True,
                "specific_changes": ["Remove hardcoded results", "Add real computation"],
                "priority_level": "high"
            },
            "ml_best_practices": {
                "has_train_test_split": False,
                "handles_data_leakage": False
            },
            "summary": "Function appears to return fake results without processing"
        }
        
        # Perform review
        result = self.job_reviewer.review_function_block(
            node=node,
            function_block=function_block,
            execution_result=execution_result,
            user_request="Process the data properly",
            output_files=["output.h5ad"]
        )
        
        # Verify result
        assert not result.passed
        assert len(result.concerns) == 1
        assert result.concerns[0].type == "cheating"
        assert result.recommendations["needs_rework"]
        
        # Save reports to directory
        self.job_reviewer.save_reports_to_directory(self.test_dir)
        
        # Check report files were created
        evidence_dir = self.test_dir / "agent_tasks" / "job_reviewer"
        assert evidence_dir.exists()
        
        # Check for JSON and MD files
        json_files = list(evidence_dir.glob("review_*.json"))
        md_files = list(evidence_dir.glob("review_*.md"))
        
        assert len(json_files) == 1
        assert len(md_files) == 1
        
        # Verify JSON content
        with open(json_files[0], 'r') as f:
            evidence = json.load(f)
        
        assert evidence["agent"] == "Job Reviewer"
        assert evidence["activity"] == "function_block_review"
        assert evidence["node_id"] == "test_node"
        assert evidence["function_name"] == "Test Function"
        assert not evidence["summary"]["passed"]
        assert evidence["summary"]["critical_concerns"] == 1
        assert evidence["summary"]["needs_rework"]
        
        # Verify MD content
        with open(md_files[0], 'r') as f:
            md_content = f.read()
        
        assert "Job Reviewer Report" in md_content
        assert "❌ FAILED" in md_content
        assert "CRITICAL (cheating)" in md_content
        assert "hardcoded fake results" in md_content
        
    def test_job_reviewer_ml_best_practices(self):
        """Test job reviewer ML best practices assessment."""
        # Mock response with ML best practices
        self.llm_service.chat_completion_json.return_value = {
            "passed": True,
            "concerns": [],
            "recommendations": {"needs_rework": False},
            "ml_best_practices": {
                "has_train_test_split": True,
                "handles_data_leakage": True,
                "appropriate_validation": True,
                "hyperparameter_handling": False
            },
            "summary": "ML implementation follows most best practices"
        }
        
        # Create minimal test objects
        node = Mock(id="ml_node")
        function_block = Mock(name="ML Function", type=FunctionBlockType.PYTHON, code="", description="")
        execution_result = Mock(success=True)
        
        # Perform review
        result = self.job_reviewer.review_function_block(
            node=node,
            function_block=function_block,
            execution_result=execution_result,
            user_request="Train ML model"
        )
        
        # Save and check reports
        self.job_reviewer.save_reports_to_directory(self.test_dir)
        
        md_files = list((self.test_dir / "agent_tasks" / "job_reviewer").glob("*.md"))
        assert len(md_files) == 1
        
        with open(md_files[0], 'r') as f:
            md_content = f.read()
        
        assert "ML Best Practices Assessment" in md_content
        assert "✅ Has Train Test Split" in md_content
        assert "✅ Handles Data Leakage" in md_content
        assert "❌ Hyperparameter Handling" in md_content


class TestActionDigesterReportSaving:
    """Test action digester report saving functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.llm_service = Mock()
        self.action_digester = ActionDigester(self.llm_service, length_threshold=100)
        
    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
    def test_action_digester_saves_reports(self):
        """Test that action digester saves reports when save_reports_to_directory is called."""
        # Create long result to digest
        long_result = "Error: " + "x" * 500 + "\nTraceback: " + "y" * 500
        
        # Mock LLM response
        self.llm_service.chat_completion_json.return_value = {
            "summary": "Error occurred with long output",
            "key_findings": ["Error detected", "Traceback present"],
            "preserved_evidence": {
                "error_messages": ["Error: xxxxx..."],
                "stack_traces": ["Traceback: yyyyy..."]
            },
            "actionable_insights": ["Check error details", "Review stack trace"],
            "requires_followup": True
        }
        
        # Perform digestion
        digest = self.action_digester.digest_action_result(
            action_type="execute_command",
            raw_result=long_result,
            error_context={"command": "test_command"}
        )
        
        # Verify digest
        assert digest.summary == "Error occurred with long output"
        assert len(digest.key_findings) == 2
        assert digest.requires_followup
        assert digest.compression_ratio > 0
        
        # Save reports to directory
        self.action_digester.save_reports_to_directory(self.test_dir)
        
        # Check report files were created
        evidence_dir = self.test_dir / "agent_tasks" / "action_digests"
        assert evidence_dir.exists()
        
        # Check for JSON and MD files
        json_files = list(evidence_dir.glob("digest_*.json"))
        md_files = list(evidence_dir.glob("digest_*.md"))
        
        assert len(json_files) == 1
        assert len(md_files) == 1
        
        # Verify JSON content
        with open(json_files[0], 'r') as f:
            evidence = json.load(f)
        
        assert evidence["agent"] == "Action Digester"
        assert evidence["activity"] == "action_result_compression"
        assert evidence["action_type"] == "execute_command"
        assert evidence["original_length"] == len(long_result)
        assert evidence["summary"]["requires_followup"]
        
        # Verify MD content
        with open(md_files[0], 'r') as f:
            md_content = f.read()
        
        assert "Action Digester Report" in md_content
        assert "execute_command" in md_content
        assert "Key Findings" in md_content
        assert "Actionable Insights" in md_content
        assert "Requires Follow-up: Yes" in md_content
        
    def test_action_digester_skip_short_results(self):
        """Test that action digester skips short results."""
        # Create short result
        short_result = "Success"
        
        # This should return None (skip digestion)
        digest = self.action_digester.digest_action_result(
            action_type="read_file",
            raw_result=short_result
        )
        
        assert digest is None
        
        # Save reports - should have nothing to save
        self.action_digester.save_reports_to_directory(self.test_dir)
        
        # Check no files created
        evidence_dir = self.test_dir / "agent_tasks" / "action_digests"
        assert not evidence_dir.exists()
        
    def test_action_digester_fallback_on_error(self):
        """Test action digester fallback when LLM fails."""
        # Make LLM fail
        self.llm_service.chat_completion_json.side_effect = Exception("LLM error")
        
        # Create result to digest
        error_result = "Error: File not found\nTraceback: at line 42"
        
        # Should use fallback digest
        digest = self.action_digester.digest_action_result(
            action_type="read_file",
            raw_result=error_result
        )
        
        # Verify fallback digest
        assert "Action result with" in digest.summary
        assert "errors detected" in digest.summary
        assert len(digest.key_findings) > 0
        assert digest.requires_followup
        
        # Save reports
        self.action_digester.save_reports_to_directory(self.test_dir)
        
        # Check reports were saved even with fallback
        json_files = list((self.test_dir / "agent_tasks" / "action_digests").glob("*.json"))
        assert len(json_files) == 1


class TestIntegrationWithInteractiveExecutor:
    """Test integration of report saving with interactive executor."""
    
    def setup_method(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.container_mock = Mock()
        self.node_dir = self.test_dir / "node_123"
        self.node_dir.mkdir(parents=True)
        
    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
    @patch('job_executors.interactive_executor.CodeCheckerAgent')
    @patch('job_executors.interactive_executor.OpenAIService')
    def test_code_checker_integration_in_update_function_block(self, mock_openai, mock_code_checker_class):
        """Test that code checker reports are saved in update_function_block."""
        from job_executors.interactive_executor import ContainerActionHandler
        
        # Set up mocks
        mock_llm_service = Mock()
        mock_openai.return_value = mock_llm_service
        
        mock_code_checker = Mock()
        mock_code_checker_class.return_value = mock_code_checker
        
        # Mock code check result
        mock_result = Mock()
        mock_result.valid = True
        mock_result.must_fix = False
        mock_result.issues = []
        mock_code_checker.check_code.return_value = mock_result
        
        # Set environment variable
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            # Create handler with node_dir
            handler = ContainerActionHandler(
                container=self.container_mock,
                working_dir="/workspace",
                node_dir=self.node_dir
            )
            
            # Mock container responses
            self.container_mock.exec_run.return_value = Mock(
                exit_code=0,
                output=(b"", b"")
            )
            
            # Call update_function_block
            result = handler._update_function_block(
                code="def run(path_dict, params): pass",
                requirements=[],
                language="python",
                confidence=0.9
            )
            
            # Verify code checker was called
            mock_code_checker.check_code.assert_called_once()
            
            # Verify save_reports_to_directory was called
            mock_code_checker.save_reports_to_directory.assert_called_once_with(self.node_dir)
            
    def test_all_agents_directory_structure(self):
        """Test that all agents create consistent directory structure."""
        # Create instances
        llm_service = Mock()
        code_checker = CodeCheckerAgent(llm_service)
        job_reviewer = JobReviewerAgent(llm_service)
        action_digester = ActionDigester(llm_service)
        
        # Mock some reports for each
        code_checker._pending_reports = [{"test": "code_checker"}]
        job_reviewer._pending_reports = [{"test": "job_reviewer"}]
        action_digester._pending_reports = [{"test": "action_digester"}]
        
        # Save reports for all
        for agent in [code_checker, job_reviewer, action_digester]:
            agent.save_reports_to_directory(self.test_dir)
        
        # Check directory structure
        agent_tasks_dir = self.test_dir / "agent_tasks"
        assert agent_tasks_dir.exists()
        
        # Check each agent has its subdirectory
        assert (agent_tasks_dir / "code_checker").exists()
        assert (agent_tasks_dir / "job_reviewer").exists()
        assert (agent_tasks_dir / "action_digests").exists()
        
        # Verify no cross-contamination
        code_checker_files = list((agent_tasks_dir / "code_checker").glob("*"))
        job_reviewer_files = list((agent_tasks_dir / "job_reviewer").glob("*"))
        action_digester_files = list((agent_tasks_dir / "action_digests").glob("*"))
        
        assert all("validation" in f.name for f in code_checker_files)
        assert all("review" in f.name for f in job_reviewer_files)
        assert all("digest" in f.name for f in action_digester_files)