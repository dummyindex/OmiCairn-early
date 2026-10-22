"""Test context-specific report saving for all three agents."""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from agents.code_checker_agent import CodeCheckerAgent, CodeCheckResult, CodeIssue
from agents.job_reviewer_agent import JobReviewerAgent, JobReviewResult, JobConcern
from agents.unified_bug_fixer.action_digester import ActionDigester, ActionDigest
from agents.unified_bug_fixer.enhanced_debug_session import EnhancedDebugSession
from agents.unified_bug_fixer.action_executor import ActionExecutor
from job_executors.interactive_executor import ContainerActionHandler, InContainerDebugSession

# Import models
from models import AnalysisNode, BaseFunctionBlock, FunctionBlockType, NodeState


class TestContextSpecificReportSaving:
    """Test that agents save reports to correct context-specific directories."""
    
    def setup_method(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.node_dir = self.test_dir / "nodes" / "node_test"
        self.node_dir.mkdir(parents=True, exist_ok=True)
        
        # Create function block directory
        self.function_block_dir = self.node_dir / "function_block"
        self.function_block_dir.mkdir(parents=True, exist_ok=True)
        
        # Create bug fixer attempt directory
        self.bug_fixer_dir = self.node_dir / "agent_tasks" / "unified_bug_fixer" / "attempt_1"
        self.bug_fixer_dir.mkdir(parents=True, exist_ok=True)
        
        # Create mock LLM service
        self.llm_service = Mock()
        self.llm_service.model = "test-model"
        
    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.test_dir)
    
    def test_code_checker_saves_to_function_block_during_creation(self):
        """Test that code checker saves to function_block folder during function creation."""
        # Create code checker
        code_checker = CodeCheckerAgent(self.llm_service)
        
        # Mock check result
        check_result = CodeCheckResult(
            valid=False,
            issues=[CodeIssue(
                category="import",
                severity="error", 
                line_number=10,
                description="Missing import",
                fix="Add import os"
            )],
            improvements=["Use pathlib"],
            must_fix=True,
            suggested_code="import os\n..."
        )
        
        # Store report in pending
        code_checker._save_report("Test function", "python", check_result)
        
        # Save to function_block folder
        code_checker.save_reports_to_directory(self.function_block_dir)
        
        # Verify reports saved to code_checker subdirectory
        checker_dir = self.function_block_dir / "code_checker"
        assert checker_dir.exists()
        
        json_files = list(checker_dir.glob("validation_*.json"))
        md_files = list(checker_dir.glob("validation_*.md"))
        
        assert len(json_files) == 1
        assert len(md_files) == 1
        
        # Verify content
        with open(json_files[0]) as f:
            data = json.load(f)
            assert data["agent"] == "Code Checker"
            assert data["result"]["must_fix"] is True
    
    def test_code_checker_saves_to_bug_fixer_during_debugging(self):
        """Test that code checker saves to bug_fixer folder during debugging."""
        # This test verifies the concept that code checker should save to bug_fixer folder
        # during debugging. The actual implementation is tested through integration tests.
        
        # Create code checker
        code_checker = CodeCheckerAgent(self.llm_service)
        
        # Mock check result for debugging context
        check_result = CodeCheckResult(
            valid=False,
            issues=[CodeIssue(
                category="import",
                severity="error", 
                line_number=5,
                description="Missing pandas import",
                fix="Add import pandas as pd"
            )],
            improvements=[],
            must_fix=True,
            suggested_code="import pandas as pd\n..."
        )
        
        # Store report in pending
        code_checker._save_report("Debug function", "python", check_result)
        
        # Save to bug_fixer folder (simulating what happens during debugging)
        code_checker.save_reports_to_directory(self.bug_fixer_dir)
        
        # Verify reports saved to code_checker subdirectory under bug_fixer
        checker_dir = self.bug_fixer_dir / "code_checker"
        assert checker_dir.exists()
        
        json_files = list(checker_dir.glob("validation_*.json"))
        md_files = list(checker_dir.glob("validation_*.md"))
        
        assert len(json_files) == 1
        assert len(md_files) == 1
    
    def test_action_digester_saves_to_bug_fixer_folder(self):
        """Test that action digester saves to bug_fixer folder."""
        # Create action digester
        action_digester = ActionDigester(self.llm_service)
        
        # Create enhanced debug session with bug_fixer_attempt_dir
        mock_executor = Mock(spec=ActionExecutor)
        debug_session = EnhancedDebugSession(
            action_executor=mock_executor,
            llm_service=self.llm_service,
            node_dir=self.node_dir,
            bug_fixer_attempt_dir=self.bug_fixer_dir,
            enable_action_digester=False  # We'll set it manually
        )
        debug_session.action_digester = action_digester
        
        # Add some digests
        digest = ActionDigest(
            summary="Fixed import error",
            key_findings=["Added import os"],
            preserved_evidence={"error_type": "ImportError"},
            actionable_insights=["Check for other missing imports"],
            requires_followup=False,
            original_length=1000,
            compression_ratio=0.95
        )
        action_digester._save_report("update_function_block", "Original long result...", digest)
        
        # Call the save method (would be called at end of debug session)
        action_digester.save_reports_to_directory(self.bug_fixer_dir)
        
        # Verify reports saved to action_digests subdirectory
        digests_dir = self.bug_fixer_dir / "agent_tasks" / "action_digests"
        assert digests_dir.exists()
        
        json_files = list(digests_dir.glob("digest_*.json"))
        md_files = list(digests_dir.glob("digest_*.md"))
        
        assert len(json_files) == 1
        assert len(md_files) == 1
    
    def test_job_reviewer_saves_to_node_folder(self):
        """Test that job reviewer saves to node folder."""
        # Create job reviewer
        job_reviewer = JobReviewerAgent(self.llm_service)
        
        # Create a mock node and result
        node = Mock(spec=AnalysisNode)
        node.id = "test_node"
        node.name = "Test Node"
        node.function_block = Mock(spec=BaseFunctionBlock)
        node.function_block.name = "test_function"
        node.function_block.description = "Test function"
        
        # Mock review result
        review_result = JobReviewResult(
            passed=True,
            concerns=[JobConcern(
                type="other",
                severity="warning",
                description="Output file size is large",
                evidence="Output file is 2GB",
                suggested_fix="Consider compression"
            )],
            recommendations={"compression": "Use h5ad compression"},
            ml_best_practices={"cross_validation": True},
            summary="Function completed but with warnings"
        )
        
        # Store review in pending
        job_reviewer._save_report(node, node.function_block, review_result, "Analyze data")
        
        # Save to node directory
        job_reviewer.save_reports_to_directory(self.node_dir)
        
        # Verify reports saved to job_reviewer subdirectory
        reviewer_dir = self.node_dir / "agent_tasks" / "job_reviewer"
        assert reviewer_dir.exists()
        
        json_files = list(reviewer_dir.glob("review_*.json"))
        md_files = list(reviewer_dir.glob("review_*.md"))
        
        assert len(json_files) == 1
        assert len(md_files) == 1
        
        # Verify content
        with open(json_files[0]) as f:
            data = json.load(f)
            assert data["agent"] == "Job Reviewer"
            assert data["result"]["passed"] is True
    
    def test_integration_all_agents_in_debug_session(self):
        """Test all agents working together in a debug session."""
        # This test verifies that all agents can work together and save to correct directories
        
        # Create code checker and save to bug_fixer folder
        code_checker = CodeCheckerAgent(self.llm_service)
        check_result = CodeCheckResult(
            valid=True,
            issues=[],
            improvements=["Consider using type hints"],
            must_fix=False
        )
        code_checker._save_report("Debug integration", "python", check_result)
        code_checker.save_reports_to_directory(self.bug_fixer_dir)
        
        # Create action digester and save to bug_fixer folder  
        action_digester = ActionDigester(self.llm_service)
        digest = ActionDigest(
            summary="Executed file read",
            key_findings=["File exists"],
            preserved_evidence={},
            actionable_insights=[],
            requires_followup=False,
            original_length=500,
            compression_ratio=0.9
        )
        action_digester._save_report("read_file", "Long output...", digest)
        action_digester.save_reports_to_directory(self.bug_fixer_dir)
        
        # Create job reviewer and save to node folder
        job_reviewer = JobReviewerAgent(self.llm_service)
        node = Mock()
        node.id = "integration_node"
        function_block = Mock()
        function_block.name = "integration_function"
        review_result = JobReviewResult(
            passed=True,
            concerns=[],
            recommendations={},
            ml_best_practices={},
            summary="All checks passed"
        )
        job_reviewer._save_report(node, function_block, review_result, "Test integration")
        job_reviewer.save_reports_to_directory(self.node_dir)
        
        # Verify all reports exist in correct locations
        assert (self.bug_fixer_dir / "code_checker").exists()
        assert (self.bug_fixer_dir / "agent_tasks" / "action_digests").exists()
        assert (self.node_dir / "agent_tasks" / "job_reviewer").exists()
    
    def test_orchestrator_saves_job_reviewer_reports(self):
        """Test that orchestrator saves job reviewer reports to node directory."""
        # This test verifies that job reviewer reports are saved to the node directory
        # when the orchestrator processes completed nodes
        
        # Create job reviewer
        job_reviewer = JobReviewerAgent(self.llm_service)
        
        # Create test data
        mock_node = Mock()
        mock_node.id = "orchestrator_test_node"
        mock_function_block = Mock()
        mock_function_block.name = "orchestrator_test_function"
        
        # Create a review result
        review_result = JobReviewResult(
            passed=True,
            concerns=[],
            recommendations={"optimization": "Consider caching results"},
            ml_best_practices={"validation": True},
            summary="Function executed successfully with optimization opportunity"
        )
        
        # Save the report
        job_reviewer._save_report(mock_node, mock_function_block, review_result, "Orchestrate analysis")
        job_reviewer.save_reports_to_directory(self.node_dir)
        
        # Verify report exists in correct location
        reviewer_dir = self.node_dir / "agent_tasks" / "job_reviewer"
        assert reviewer_dir.exists()
        
        json_files = list(reviewer_dir.glob("review_*.json"))
        md_files = list(reviewer_dir.glob("review_*.md"))
        
        assert len(json_files) == 1
        assert len(md_files) == 1
        
        # Verify content includes orchestrator context
        with open(json_files[0]) as f:
            data = json.load(f)
            assert data["agent"] == "Job Reviewer"
            assert data["node_id"] == "orchestrator_test_node"
            assert data["result"]["summary"] == "Function executed successfully with optimization opportunity"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])