# OpenAI Integration Tests

This directory contains tests that require real OpenAI API access.

## Requirements

These tests require:
- Valid `OPENAI_API_KEY` environment variable
- Active internet connection
- OpenAI API credits

## Test Files

- `test_openai_api.py`: Comprehensive OpenAI API integration tests
- `test_openai_quick.py`: Quick verification of OpenAI API connectivity

## Running These Tests

These tests are **excluded by default** from the main test suite to avoid:
- Consuming API credits
- Requiring API keys in CI/CD
- Network dependencies

To run OpenAI integration tests specifically:

```bash
# Run all OpenAI integration tests
pytest tests/openai_integration/

# Run a specific test
pytest tests/openai_integration/test_openai_quick.py

# Run with verbose output
pytest tests/openai_integration/ -v
```

## Excluding from Main Test Suite

When running all tests, you can exclude these:

```bash
# Run all tests except OpenAI integration
pytest tests/ --ignore=tests/openai_integration/
```

## Environment Setup

Create a `.env` file with:
```
OPENAI_API_KEY=your-api-key-here
OPENAI_MODEL=gpt-4o-mini  # Optional, defaults to gpt-4o-mini
```