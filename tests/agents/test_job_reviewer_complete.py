"""Consolidated tests for Job Reviewer Agent.

This file consolidates all job reviewer related tests into a single comprehensive test suite.
"""

import sys
from pathlib import Path
# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
import json
import tempfile
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from agents.job_reviewer_agent import JobReviewerAgent, JobReviewResult, JobConcern
from models import (
    AnalysisNode, BaseFunctionBlock, NewFunctionBlock, FunctionBlockType, 
    ExecutionResult, Arg, StaticConfig, JobReviewStatus
)
from llm_service import BaseLLMService


class MockLLMService:
    """Mock LLM service for testing."""
    
    def __init__(self, response=None):
        self.response = response or {
            "passed": True,
            "concerns": [],
            "recommendations": {
                "needs_rework": False,
                "specific_changes": [],
                "priority_level": "low"
            },
            "ml_best_practices": {
                "applies_to_node": False,
                "has_train_test_split": None,
                "handles_data_leakage": None,
                "appropriate_validation": None,
                "hyperparameter_handling": None
            },
            "summary": "Function block passes review"
        }
        self.calls = []
    
    def chat_completion_json(self, messages, json_schema, temperature=0.1, max_tokens=2500, seed=None):
        self.calls.append({
            'messages': messages,
            'json_schema': json_schema,
            'temperature': temperature,
            'max_tokens': max_tokens,
            'seed': seed
        })
        return self.response


class TestJobReviewerAgent:
    """Core tests for JobReviewerAgent."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.llm_service = MockLLMService()
        self.agent = JobReviewerAgent(self.llm_service, llm_seed=42)
        
        # Create test function block
        static_config = StaticConfig(
            args=[],
            description="Test function",
            tag="test"
        )
        
        self.function_block = NewFunctionBlock(
            id="test_fb",
            name="Test Function",
            description="Test function block",
            type=FunctionBlockType.PYTHON,
            code="def run(path_dict, params):\n    pass",
            requirements="numpy\\npandas",
            parameters={},
            static_config=static_config
        )
        
        # Create test node
        self.node = AnalysisNode(
            id="test_node",
            analysis_id="test_tree",
            function_block=self.function_block
        )
        
        # Create test execution result
        self.execution_result = ExecutionResult(
            success=True,
            stdout="Test output",
            stderr="",
            figures=[],
            output_data_path="/test/output"
        )
    
    def test_initialization(self):
        """Test agent initialization."""
        assert self.agent.llm_service == self.llm_service
        assert self.agent.llm_seed == 42
        assert self.agent.total_reviews == 0
        assert self.agent.failed_reviews == 0
        assert len(self.agent.concern_counts) == 0
    
    def test_successful_review(self):
        """Test review of a valid function block."""
        result = self.agent.review_function_block(
            self.node,
            self.function_block,
            self.execution_result,
            "Test user request"
        )
        
        assert result.passed
        assert len(result.concerns) == 0
        assert not result.recommendations["needs_rework"]
        assert self.agent.total_reviews == 1
        assert self.agent.failed_reviews == 0
    
    def test_failed_review_with_concerns(self):
        """Test review that fails with concerns."""
        self.llm_service.response = {
            "passed": False,
            "concerns": [
                {
                    "type": "placeholder",
                    "severity": "critical",
                    "description": "Function contains placeholder code",
                    "evidence": "pass statement with no implementation",
                    "suggested_fix": "Implement actual functionality"
                }
            ],
            "recommendations": {
                "needs_rework": True,
                "specific_changes": ["Replace placeholder with actual implementation"],
                "priority_level": "high"
            },
            "ml_best_practices": {
                "applies_to_node": False,
                "has_train_test_split": None,
                "handles_data_leakage": None,
                "appropriate_validation": None,
                "hyperparameter_handling": None
            },
            "summary": "Function block contains placeholder code"
        }
        
        result = self.agent.review_function_block(
            self.node,
            self.function_block,
            self.execution_result,
            "Test user request"
        )
        
        assert not result.passed
        assert len(result.concerns) == 1
        assert result.concerns[0].type == "placeholder"
        assert result.concerns[0].severity == "critical"
        assert result.recommendations["needs_rework"]
        assert self.agent.total_reviews == 1
        assert self.agent.failed_reviews == 1
        assert self.agent.concern_counts["placeholder"] == 1
    
    def test_should_trigger_rework(self):
        """Test rework trigger logic."""
        # Case 1: No rework needed
        result = JobReviewResult(
            passed=True,
            concerns=[],
            recommendations={"needs_rework": False},
            ml_best_practices={},
            summary="All good"
        )
        assert not self.agent.should_trigger_rework(result)
        
        # Case 2: Explicit rework recommendation
        result.recommendations["needs_rework"] = True
        assert self.agent.should_trigger_rework(result)
        
        # Case 3: Critical cheating concern
        result = JobReviewResult(
            passed=False,
            concerns=[
                JobConcern(
                    type="cheating",
                    severity="critical",
                    description="Fake results",
                    evidence="Random values",
                    suggested_fix="Compute real values"
                )
            ],
            recommendations={"needs_rework": False},
            ml_best_practices={},
            summary="Cheating detected"
        )
        assert self.agent.should_trigger_rework(result)
        
        # Case 4: Non-critical concern
        result.concerns[0].severity = "warning"
        assert not self.agent.should_trigger_rework(result)
    
    def test_get_rework_specification(self):
        """Test rework specification generation."""
        review_result = JobReviewResult(
            passed=False,
            concerns=[
                JobConcern(
                    type="placeholder",
                    severity="critical",
                    description="Contains TODO comments",
                    evidence="# TODO: implement this",
                    suggested_fix="Implement the actual logic"
                )
            ],
            recommendations={
                "needs_rework": True,
                "specific_changes": ["Remove TODO and implement logic"],
                "priority_level": "high"
            },
            ml_best_practices={},
            summary="Needs implementation"
        )
        
        original_spec = {
            "name": "Test Function",
            "description": "Original description"
        }
        
        rework_spec = self.agent.get_rework_specification(review_result, original_spec)
        
        assert "review_feedback" in rework_spec
        assert rework_spec["review_feedback"]["failed_review"]
        assert len(rework_spec["review_feedback"]["concerns"]) == 1
        assert "REVIEW REQUIREMENTS:" in rework_spec["description"]
        assert "CRITICAL FIXES REQUIRED:" in rework_spec["description"]
    
    def test_execution_context_gathering(self):
        """Test gathering execution context for review."""
        # Create mock node with output directory
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "outputs"
            output_dir.mkdir()
            
            # Create some output files
            (output_dir / "result.h5ad").write_text("mock data")
            (output_dir / "figures").mkdir()
            (output_dir / "figures" / "plot.png").write_text("mock image")
            
            self.node.output_data_id = str(output_dir)
            
            context = self.agent._gather_execution_context(
                self.node,
                self.execution_result,
                ["result.h5ad"]
            )
            
            assert context["execution_success"]
            assert "result.h5ad" in context["actual_output_files"]
            assert "figures/plot.png" in context["actual_figures"]
            assert context["output_file_count"] == 2
    
    def test_output_validation_detection(self):
        """Test detection of output validation issues."""
        # Mock execution result with output claims but no actual files
        self.execution_result.stdout = "Saved plot to output.png\nWrote results to data.csv"
        
        # Test with no actual output files
        self.llm_service.response = {
            "passed": False,
            "concerns": [
                {
                    "type": "cheating",
                    "severity": "critical",
                    "description": "Code claims to save files but no outputs exist",
                    "evidence": "stdout claims 'Saved plot' but no files in output",
                    "suggested_fix": "Actually save the files that are claimed"
                }
            ],
            "recommendations": {
                "needs_rework": True,
                "specific_changes": ["Ensure files are actually saved"],
                "priority_level": "high"
            },
            "ml_best_practices": {
                "applies_to_node": False,
                "has_train_test_split": None,
                "handles_data_leakage": None,
                "appropriate_validation": None,
                "hyperparameter_handling": None
            },
            "summary": "Output validation failed"
        }
        
        result = self.agent.review_function_block(
            self.node,
            self.function_block,
            self.execution_result,
            "Generate plots"
        )
        
        assert not result.passed
        assert any(c.type == "cheating" for c in result.concerns)
    
    def test_node_specific_review(self):
        """Test that review is specific to node's task, not overall request."""
        # Function block for a specific clustering task
        self.function_block.description = "Perform Leiden clustering on the data"
        
        # User request mentions multiple analyses
        user_request = "Perform clustering, trajectory analysis, and cell type annotation"
        
        # Review should pass even though other analyses aren't done
        result = self.agent.review_function_block(
            self.node,
            self.function_block,
            self.execution_result,
            user_request
        )
        
        # Check that the prompt focused on the specific task
        assert len(self.llm_service.calls) == 1
        prompt = self.llm_service.calls[0]['messages'][0]['content']
        assert "Perform Leiden clustering" in prompt
        assert "NODE'S SPECIFIC TASK" in prompt
    
    def test_ml_best_practices_scoring(self):
        """Test ML best practices scoring logic."""
        # Non-ML node should get perfect score
        practices = {
            "applies_to_node": False,
            "has_train_test_split": None,
            "handles_data_leakage": None,
            "appropriate_validation": None,
            "hyperparameter_handling": None
        }
        score = self.agent._calculate_ml_score(practices)
        assert score == 1.0
        
        # ML node with all good practices
        practices = {
            "applies_to_node": True,
            "has_train_test_split": True,
            "handles_data_leakage": True,
            "appropriate_validation": True,
            "hyperparameter_handling": True
        }
        score = self.agent._calculate_ml_score(practices)
        assert score == 1.0
        
        # ML node with some bad practices
        practices = {
            "applies_to_node": True,
            "has_train_test_split": True,
            "handles_data_leakage": False,
            "appropriate_validation": True,
            "hyperparameter_handling": False
        }
        score = self.agent._calculate_ml_score(practices)
        assert score == 0.5
    
    def test_statistics_tracking(self):
        """Test that statistics are properly tracked."""
        # Run multiple reviews
        for i in range(3):
            if i < 2:
                # First two pass
                self.llm_service.response["passed"] = True
                self.llm_service.response["concerns"] = []
            else:
                # Last one fails
                self.llm_service.response["passed"] = False
                self.llm_service.response["concerns"] = [
                    {
                        "type": "placeholder",
                        "severity": "critical",
                        "description": "Test",
                        "evidence": "Test",
                        "suggested_fix": "Test"
                    }
                ]
            
            self.agent.review_function_block(
                self.node,
                self.function_block,
                self.execution_result,
                "Test"
            )
        
        stats = self.agent.get_statistics()
        assert stats["total_reviews"] == 3
        assert stats["failed_reviews"] == 1
        assert stats["success_rate"] == 2/3
        assert stats["concern_counts"]["placeholder"] == 1
        assert stats["most_common_concern"] == "placeholder"


class TestJobReviewerCodeSync:
    """Tests for job reviewer code synchronization after bug fixes."""
    
    def test_function_block_code_visibility(self):
        """Test that job reviewer sees the correct function block code."""
        llm_service = MockLLMService()
        agent = JobReviewerAgent(llm_service)
        
        # Create function block with specific code
        static_config = StaticConfig(
            args=[],
            description="Test",
            tag="test"
        )
        
        test_code = "def run(path_dict, params):\n    print('Updated code')"
        function_block = NewFunctionBlock(
            id="test",
            name="Test",
            description="Test",
            type=FunctionBlockType.PYTHON,
            code=test_code,
            requirements="",
            parameters={},
            static_config=static_config
        )
        
        node = AnalysisNode(
            id="test_node",
            analysis_id="test_tree",
            function_block=function_block
        )
        
        execution_result = ExecutionResult(success=True)
        
        # Review the function block
        agent.review_function_block(
            node,
            function_block,
            execution_result,
            "Test"
        )
        
        # Verify the code was passed to LLM
        assert len(llm_service.calls) == 1
        prompt = llm_service.calls[0]['messages'][0]['content']
        assert test_code in prompt


class TestJobReviewerReworkIntegration:
    """Tests for job reviewer and rework system integration."""
    
    def test_rework_trigger_on_placeholder(self):
        """Test that placeholder code triggers rework."""
        llm_service = MockLLMService()
        agent = JobReviewerAgent(llm_service)
        
        # Set up response to fail on placeholder
        llm_service.response = {
            "passed": False,
            "concerns": [
                {
                    "type": "placeholder",
                    "severity": "critical",
                    "description": "Contains TODO placeholder",
                    "evidence": "# TODO: implement",
                    "suggested_fix": "Implement actual logic"
                }
            ],
            "recommendations": {
                "needs_rework": True,
                "specific_changes": ["Replace TODO with implementation"],
                "priority_level": "high"
            },
            "ml_best_practices": {
                "applies_to_node": False,
                "has_train_test_split": None,
                "handles_data_leakage": None,
                "appropriate_validation": None,
                "hyperparameter_handling": None
            },
            "summary": "Placeholder code detected"
        }
        
        static_config = StaticConfig(
            args=[],
            description="Test",
            tag="test"
        )
        
        # Function block with placeholder
        function_block = NewFunctionBlock(
            id="test",
            name="Test",
            description="Test analysis",
            type=FunctionBlockType.PYTHON,
            code="def run(path_dict, params):\n    # TODO: implement\n    pass",
            requirements="",
            parameters={},
            static_config=static_config
        )
        
        node = AnalysisNode(
            id="test_node",
            analysis_id="test_tree",
            function_block=function_block
        )
        
        result = agent.review_function_block(
            node,
            function_block,
            ExecutionResult(success=True),
            "Perform analysis"
        )
        
        assert not result.passed
        assert agent.should_trigger_rework(result)
        assert result.recommendations["needs_rework"]
    
    def test_rework_specification_includes_feedback(self):
        """Test that rework spec includes review feedback."""
        agent = JobReviewerAgent(MockLLMService())
        
        review_result = JobReviewResult(
            passed=False,
            concerns=[
                JobConcern(
                    type="implementation_mismatch",
                    severity="critical",
                    description="Uses wrong clustering method",
                    evidence="Uses KMeans instead of Leiden",
                    suggested_fix="Use scanpy Leiden clustering"
                )
            ],
            recommendations={
                "needs_rework": True,
                "specific_changes": ["Replace KMeans with sc.tl.leiden"],
                "priority_level": "high"
            },
            ml_best_practices={},
            summary="Wrong method used"
        )
        
        original_spec = {
            "name": "Leiden Clustering",
            "description": "Perform Leiden clustering"
        }
        
        rework_spec = agent.get_rework_specification(review_result, original_spec)
        
        assert "review_feedback" in rework_spec
        assert "Uses wrong clustering method" in rework_spec["review_feedback"]["concerns"][0]
        assert "Use scanpy Leiden clustering" in rework_spec["description"]


class TestJobReviewerEdgeCases:
    """Test edge cases and error handling."""
    
    def test_malformed_llm_response(self):
        """Test handling of malformed LLM response."""
        llm_service = MockLLMService()
        # Set incomplete response
        llm_service.response = {
            "passed": True
            # Missing required fields
        }
        
        agent = JobReviewerAgent(llm_service)
        
        static_config = StaticConfig(args=[], description="Test", tag="test")
        function_block = NewFunctionBlock(
            id="test",
            name="Test",
            description="Test",
            type=FunctionBlockType.PYTHON,
            code="def run(path_dict, params): pass",
            requirements="",
            parameters={},
            static_config=static_config
        )
        
        node = AnalysisNode(
            id="test",
            analysis_id="test",
            function_block=function_block
        )
        
        with pytest.raises(ValueError, match="missing required field"):
            agent.review_function_block(
                node,
                function_block,
                ExecutionResult(success=True),
                "Test"
            )
    
    def test_empty_concern_list(self):
        """Test handling of empty concerns with failed review."""
        llm_service = MockLLMService()
        llm_service.response = {
            "passed": False,
            "concerns": [],  # Empty but review failed
            "recommendations": {
                "needs_rework": True,
                "specific_changes": [],
                "priority_level": "medium"
            },
            "ml_best_practices": {
                "applies_to_node": False,
                "has_train_test_split": None,
                "handles_data_leakage": None,
                "appropriate_validation": None,
                "hyperparameter_handling": None
            },
            "summary": "General quality issues"
        }
        
        agent = JobReviewerAgent(llm_service)
        static_config = StaticConfig(args=[], description="Test", tag="test")
        
        function_block = NewFunctionBlock(
            id="test",
            name="Test",
            description="Test",
            type=FunctionBlockType.PYTHON,
            code="def run(path_dict, params): pass",
            requirements="",
            parameters={},
            static_config=static_config
        )
        
        node = AnalysisNode(
            id="test",
            analysis_id="test",
            function_block=function_block
        )
        
        result = agent.review_function_block(
            node,
            function_block,
            ExecutionResult(success=True),
            "Test"
        )
        
        assert not result.passed
        assert len(result.concerns) == 0
        assert result.recommendations["needs_rework"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])