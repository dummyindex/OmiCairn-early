# Makefile for omicairn_agent_local

.PHONY: help clean test test-unit test-integration test-verbose test-list docker-build docker-build-minimal docker-clean install install-dev

help:
	@echo "Available commands:"
	@echo "  make install        - Install Python dependencies"
	@echo "  make clean          - Clean test outputs and cache files"
	@echo "  make test           - Run tests that need no API keys"
	@echo "  make test-unit      - Run unit tests only"
	@echo "  make test-integration - Run integration tests (need Docker/API keys/test data)"
	@echo "  make test-verbose   - Run tests with verbose output"
	@echo "  make test-list      - List collected tests"
	@echo "  make docker-build   - Build Docker images"
	@echo "  make docker-build-minimal - Build minimal Docker images"
	@echo "  make docker-clean   - Remove Docker images"

# Clean test outputs
clean:
	@echo "Cleaning test outputs..."
	@bash tests/clean_test_outputs.sh
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	@echo "Done!"

# Run tests that do not need LLM API access
test:
	@python -m pytest tests -m "not llm_required and not benchmark"

test-unit:
	@python -m pytest tests/unit

test-integration:
	@python -m pytest tests/integration

test-verbose:
	@python -m pytest tests -vv -m "not llm_required and not benchmark"

test-list:
	@python -m pytest tests --collect-only -q

# Docker commands
docker-build:
	@echo "Building Docker images..."
	cd docker && ./build.sh

docker-build-minimal:
	@echo "Building minimal Docker images..."
	cd docker && ./build_minimal.sh

docker-clean:
	@echo "Removing Docker images..."
	docker rmi omicairn-python:local omicairn/python-executor:latest omicairn-r:minimal 2>/dev/null || true
	docker rmi omicairn-python:minimal 2>/dev/null || true

# Development helpers
lint:
	@echo "Running linters..."
	@python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	@python -m flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

format:
	@echo "Formatting code..."
	@python -m black . --line-length 100 --target-version py38

typecheck:
	@echo "Running type checks..."
	@python -m mypy . --ignore-missing-imports

# Installation
install:
	@echo "Installing dependencies..."
	pip install -r requirements.txt

install-dev:
	@echo "Installing development dependencies..."
	pip install -r requirements.txt
	pip install flake8 black mypy pytest pytest-cov

# Documentation
docs:
	@echo "Building documentation..."
	@python -c "print('Documentation building not yet configured')"

# Show project statistics
stats:
	@echo "Project Statistics:"
	@echo "==================="
	@echo "Python files: $$(find . -name '*.py' -not -path './__pycache__/*' | wc -l)"
	@echo "Test files: $$(find tests -name 'test_*.py' | wc -l)"
	@echo "Lines of code: $$(find . -name '*.py' -not -path './__pycache__/*' | xargs wc -l | tail -1)"
	@echo "==================="