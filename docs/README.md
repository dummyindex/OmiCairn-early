# OmiCairn Agent Local Documentation

This directory documents the OmiCairn Agent Local system, a hierarchical multi-agent architecture for automated
single-cell RNA-seq analysis using LLM-guided function blocks with Docker container isolation.

> **Early-stage research version.** These documents were written during development of an early research
> prototype. Some describe intended designs or historical states and may not match the code exactly. Performance
> figures in development notes are informal observations, not benchmarked results.

## core/ - System architecture
- [AGENT_ARCHITECTURE.md](core/AGENT_ARCHITECTURE.md) - Agents and how they communicate
- [BUG_FIXER_ARCHITECTURE.md](core/BUG_FIXER_ARCHITECTURE.md) - Bug fixer container architecture
- [SYSTEM_IMPLEMENTATION.md](core/SYSTEM_IMPLEMENTATION.md) - Execution model and implementation details
- [COMPLETE_SYSTEM_WORKFLOW.md](core/COMPLETE_SYSTEM_WORKFLOW.md) - End-to-end workflow
- [ANALYSIS_TREE_STRUCTURE.md](core/ANALYSIS_TREE_STRUCTURE.md) - Tree specification and output layout
- [DATA_LOADING_ROOT_ARCHITECTURE.md](core/DATA_LOADING_ROOT_ARCHITECTURE.md) - Data-loading root node
- [EXECUTOR_ARCHITECTURE.md](core/EXECUTOR_ARCHITECTURE.md) - Docker executors
- [FUNCTION_CREATOR_ARCHITECTURE.md](core/FUNCTION_CREATOR_ARCHITECTURE.md) - Function creator agent
- [FUNCTION_BLOCK_VALIDATION.md](core/FUNCTION_BLOCK_VALIDATION.md) - Function block validation
- [BUILTIN_FUNCTION_BLOCKS.md](core/BUILTIN_FUNCTION_BLOCKS.md) - Built-in function blocks
- [R_PYTHON_INTEROPERABILITY.md](core/R_PYTHON_INTEROPERABILITY.md) - R/Python interoperability
- [WEB_AGENT_ARCHITECTURE.md](core/WEB_AGENT_ARCHITECTURE.md) - Web research agent

## guides/ - Implementation guides
- [AGENT_IMPLEMENTATION_GUIDE.md](guides/AGENT_IMPLEMENTATION_GUIDE.md)
- [FRAMEWORK_IMPLEMENTATION.md](guides/FRAMEWORK_IMPLEMENTATION.md)
- [PARALLEL_EXECUTION.md](guides/PARALLEL_EXECUTION.md) and [PARALLEL_EXECUTION_DESIGN.md](guides/PARALLEL_EXECUTION_DESIGN.md)
- [OPENAI_SETUP.md](guides/OPENAI_SETUP.md)
- [CLAUDE_BUG_FIXER_IMPLEMENTATION.md](guides/CLAUDE_BUG_FIXER_IMPLEMENTATION.md)
- [in_container_debugging_guide.md](guides/in_container_debugging_guide.md)
- [output_management_guide.md](guides/output_management_guide.md)

## debugging/ - Bug fixing
- [BUG_FIXER_GUIDE.md](debugging/BUG_FIXER_GUIDE.md)
- [HOW_BUG_FIXER_FIXES_CODE.md](debugging/HOW_BUG_FIXER_FIXES_CODE.md)
- [unified_bug_fixer_guide.md](debugging/unified_bug_fixer_guide.md)
- [unified_bug_fixer_implementation.md](debugging/unified_bug_fixer_implementation.md)
- [claude_code_sdk_guide.md](debugging/claude_code_sdk_guide.md)
- [bug_fixer_switching_guide.md](debugging/bug_fixer_switching_guide.md)
- [import_issues_guide.md](debugging/import_issues_guide.md)
- [web_agent_bug_fixer_integration.md](debugging/web_agent_bug_fixer_integration.md)
- [web_agent/](debugging/web_agent/) - Web agent notes (including historical design plans)
- [bug_fixer_orchestrator_improvements_plan.md](debugging/bug_fixer_orchestrator_improvements_plan.md) - Historical design note

## Other topics
- [FUNCTION_BLOCK_FRAMEWORK.md](FUNCTION_BLOCK_FRAMEWORK.md) - Function block I/O framework
- [PREVIOUS_NODES_FILE_ACCESS.md](PREVIOUS_NODES_FILE_ACCESS.md), [previous_nodes_interface.md](previous_nodes_interface.md),
  [previous_nodes_hierarchical_structure.md](previous_nodes_hierarchical_structure.md), [previous_nodes_usage_example.py](previous_nodes_usage_example.py)
- [job_reviewer_agent.md](job_reviewer_agent.md), [job_review_rework_system.md](job_review_rework_system.md), [rework_limits_guide.md](rework_limits_guide.md)
- [state_system_guide.md](state_system_guide.md)
- [domain_knowledge_implementation_plan.md](domain_knowledge_implementation_plan.md)
- [architecture/](architecture/) - Code versioning for function blocks and the bug fixer
- [testing/](testing/) - Benchmark prompts, deprecation notice and testing notes
- [../tests/README.md](../tests/README.md) - Tests
