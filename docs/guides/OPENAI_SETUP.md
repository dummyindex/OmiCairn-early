# OpenAI API Setup and Configuration

## Configuration

### 1. API Key Storage

The OpenAI API key is stored securely in a `.env` file in the project root:

```bash
# .env file
OPENAI_API_KEY=your-api-key-here
OPENAI_MODEL=gpt-4o-mini
```

**Important**: The `.env` file is excluded from version control via `.gitignore` to prevent accidental exposure of the API key.

### 2. Model Selection

The project is configured to use `gpt-4o-mini` by default, which offers:
- Fast response times
- Lower cost compared to GPT-4
- Sufficient capability for function block generation
- Good performance for code generation tasks

### 3. Configuration Locations

The model is configured in multiple places:
- `.env` file: `OPENAI_MODEL=gpt-4o-mini`
- `config.py`: Uses environment variable with fallback
- `models.py`: Default model in AnalysisTree

## Testing

### Quick Test

Run a quick test to verify the API key works:

```bash
python tests/openai_integration/test_openai_quick.py
```

Expected output:
```
API Key: sk-proj-...
Model: gpt-4o-mini
Response: API test successful.
✓ OpenAI API is working correctly!
```

### Comprehensive Test Suite

Run the full test suite to verify all API features:

```bash
python tests/openai_integration/test_openai_api.py
```

This tests:
1. **Basic Completion**: Simple chat completion
2. **JSON Mode**: Structured JSON responses
3. **Code Extraction**: Extracting code blocks from responses
4. **Function Calling**: Using tool/function calling features
5. **Streaming**: Streaming responses for real-time output
6. **Context Length**: Handling long contexts
7. **Error Handling**: Proper error handling for invalid requests
8. **Rate Limiting**: Handling multiple rapid requests
9. **Model Info**: Verifying model availability
10. **Embeddings**: Creating text embeddings
11. **Function Block Generation**: Generating single-cell analysis code

## API Features Used

### 1. Chat Completion
```python
from llm_service.openai_service import OpenAIService

service = OpenAIService()
response = service.chat_completion(
    messages=[{"role": "user", "content": "Hello"}],
    temperature=0.7,
    max_tokens=100
)
```

### 2. JSON Response Format
```python
response = service.chat_completion(
    messages=messages,
    response_format={"type": "json_object"}
)
```

### 3. Code Extraction
```python
response = service.chat_completion(messages)
code = service.extract_code_block(response)
```

### 4. Function Calling
```python
client.chat.completions.create(
    model="gpt-4o-mini",
    messages=messages,
    tools=tools,
    tool_choice="auto"
)
```

### 5. Streaming
```python
stream = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=messages,
    stream=True
)
for chunk in stream:
    print(chunk.choices[0].delta.content)
```

## Cost Optimization

Using `gpt-4o-mini` provides significant cost savings:
- Substantially cheaper than GPT-4
- Faster response times
- Adequate for most function block generation tasks

For production use, consider:
- Implementing caching for repeated queries
- Batching requests when possible
- Using embeddings for similarity search before generation

## Security Best Practices

1. **Never commit API keys**: Always use environment variables
2. **Rotate keys regularly**: Update keys periodically
3. **Monitor usage**: Track API usage for unusual patterns
4. **Use minimal permissions**: Create keys with only necessary permissions
5. **Validate inputs**: Sanitize user inputs before sending to API

## Troubleshooting

### API Key Not Found
```
ERROR: OPENAI_API_KEY not found in environment
```
**Solution**: Ensure `.env` file exists with the API key

### Model Not Available
```
✗ Model gpt-4o-mini not found
```
**Solution**: Check available models or update to a supported model

### Rate Limiting
```
Rate limit exceeded
```
**Solution**: Implement exponential backoff or reduce request frequency

### Invalid Response Format
```
Failed to parse JSON response
```
**Solution**: Ensure proper response_format is set for JSON responses

## Test Coverage Summary

The API test suite exercises the following features (requires a valid `OPENAI_API_KEY`; results depend on your account and the current API):
- Basic Completion
- JSON Mode
- Code Extraction
- Function Calling
- Streaming
- Context Length
- Error Handling
- Rate Limiting
- Model Info
- Embeddings
- Function block generation for single-cell analysis tasks