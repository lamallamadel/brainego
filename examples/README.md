# Examples

This directory contains example scripts demonstrating various use cases of the MAX Serve API.

## Available Examples

### 1. Interactive Chat (`chat_example.py`)

Interactive command-line chat interface with Llama 3.3.

**Features:**
- Persistent conversation history
- Clear command to start new conversation
- History command to view past messages
- Graceful error handling

**Usage:**
```bash
python examples/chat_example.py
```

**Commands:**
- Type your message to chat
- `quit` or `exit` - End the conversation
- `clear` - Start a new conversation
- `history` - View conversation history

### 2. Batch Processing (`batch_processing.py`)

Demonstrates efficient batch processing of multiple prompts using concurrent requests.

**Features:**
- Concurrent request processing
- Latency metrics per request
- Throughput calculation
- Demonstrates batching benefits

**Usage:**
```bash
python examples/batch_processing.py
```

**Output:**
- Processing time for batch
- Throughput (requests/second)
- Individual request latencies
- Average, min, max latency statistics

### 3. Streaming (Future) (`streaming_example.py`)

Template for future streaming implementation.

**Note:** Streaming is not yet implemented in the current API server. This example shows what the implementation would look like.

**Usage:**
```bash
python examples/streaming_example.py
```

## Requirements

Install dependencies before running examples:

```bash
pip install -r requirements.txt
```

## Configuration

All examples use the default API endpoint: `http://localhost:8000`

To use a different endpoint, modify the `API_URL` variable in each script:

```python
API_URL = "http://your-server:8000"
```

## Tips

### Performance Optimization

1. **Batch Processing**: Use concurrent requests to leverage MAX Serve's batching
2. **Connection Pooling**: Reuse HTTP connections for better performance
3. **Timeout Settings**: Adjust timeouts based on expected response times

### Error Handling

All examples include error handling for:
- Connection errors
- Timeout errors
- Invalid responses
- Keyboard interrupts

### Advanced Usage

Customize request parameters:

```python
payload = {
    "model": "llama-3.3-8b-instruct",
    "messages": messages,
    "max_tokens": 500,        # Adjust based on needs
    "temperature": 0.7,       # 0.0 = deterministic, 2.0 = very creative
    "top_p": 0.9,            # Nucleus sampling
}
```

## Troubleshooting

**Connection Refused:**
- Ensure the API server is running: `docker compose ps`
- Check the API endpoint URL

**Slow Responses:**
- Check GPU utilization: `nvidia-smi`
- Review MAX Serve logs: `docker compose logs max-serve`
- Consider reducing `max_tokens` for faster responses

**Out of Memory:**
- Reduce batch size in docker-compose.yaml
- Reduce max_tokens in requests
- Check GPU memory: `nvidia-smi`

## Contributing

Feel free to add more examples! Follow the existing structure:
- Clear docstrings
- Error handling
- Command-line interface
- Usage instructions
