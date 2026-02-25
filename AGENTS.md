# AGENTS.md

## Setup & Commands

**Initial Setup:**
```bash
# Install Python dependencies
pip install -r requirements.txt

# Download Llama 3.3 8B model
chmod +x download_model.sh
./download_model.sh

# Initialize and start all services
chmod +x init.sh
./init.sh
```

**Build:** 
```bash
# Build Docker images
docker compose build

# Or with Make
make build
```

**Lint:** 
```bash
# Python linting (if needed)
pip install flake8 black
flake8 api_server.py load_test.py test_api.py monitor.py
black --check api_server.py load_test.py test_api.py monitor.py
```

**Tests:** 
```bash
# Basic API tests
python test_api.py

# Load tests
python load_test.py --requests 100 --concurrency 10

# With Make
make test
make load-test
```

**Dev Server:** 
```bash
# Start all services
docker compose up -d

# Or with Make
make start

# Monitor services
docker compose logs -f
```

## Tech Stack & Architecture

### Core Components

**Model Serving:**
- **MAX Serve**: Modular's high-performance inference engine
- **Model**: Llama 3.3 8B Instruct (GGUF Q4_K_M quantization)
- **Batching**: Dynamic batching with max_batch_size=32
- **GPU Acceleration**: NVIDIA CUDA support

**API Layer:**
- **FastAPI**: Modern Python web framework for APIs
- **Uvicorn**: ASGI server for production
- **httpx**: Async HTTP client for MAX Serve communication
- **Pydantic**: Data validation and settings management

**Infrastructure:**
- **Docker Compose**: Container orchestration
- **Qdrant**: Vector database (v1.7+)
- **Redis**: In-memory cache (v7)
- **PostgreSQL**: Relational database (v15)
- **MinIO**: S3-compatible object storage

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Client Layer                        │
│  (HTTP/REST, OpenAI-compatible API)                    │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│              API Server (FastAPI)                       │
│  - /v1/chat/completions (OpenAI-compatible)            │
│  - /health (Health checks)                              │
│  - /metrics (Performance metrics)                       │
│  Port: 8000                                             │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│            MAX Serve (Inference)                        │
│  - Model: Llama 3.3 8B Instruct (Q4_K_M)               │
│  - Batching: max_batch_size=32                         │
│  - GPU Acceleration: CUDA                               │
│  Port: 8080                                             │
└──────────────────┬──────────────────────────────────────┘
                   │
         ┌─────────┴─────────┐
         │                   │
┌────────▼────────┐  ┌──────▼──────────┐
│  Support Stack  │  │  Storage Layer   │
│  - Qdrant       │  │  - PostgreSQL    │
│  - Redis        │  │  - MinIO         │
└─────────────────┘  └──────────────────┘
```

### Data Flow

1. **Client Request** → API Server (`/v1/chat/completions`)
2. **Format Prompt** → Convert messages to Llama 3.3 format
3. **Call MAX Serve** → Send to inference engine
4. **Batching** → MAX Serve batches concurrent requests
5. **GPU Inference** → Model generates response
6. **Parse Response** → Extract and format output
7. **Return to Client** → OpenAI-compatible JSON response

### Performance Features

**Dynamic Batching:**
- Automatically groups up to 32 concurrent requests
- Processes batch in single GPU pass
- Reduces per-request latency under load
- Configurable via `max_batch_size` parameter

**Request Metrics:**
- P50/P95/P99 latency tracking
- Token usage statistics
- Error rate monitoring
- Real-time performance dashboard

**Load Testing:**
- Concurrent request simulation
- Multiple test scenarios (short/medium/long prompts)
- Comprehensive latency analysis
- JSON report generation

## Code Style & Conventions

### Python Code Style

**General Guidelines:**
- Follow PEP 8 style guide
- Use type hints for function signatures
- Docstrings for all public functions/classes
- 4 spaces for indentation
- Maximum line length: 100 characters

**Example:**
```python
async def send_request(
    client: httpx.AsyncClient,
    messages: List[Dict[str, str]],
    max_tokens: int = 100
) -> Dict[str, Any]:
    """
    Send a chat completion request to the API.
    
    Args:
        client: HTTP client instance
        messages: List of chat messages
        max_tokens: Maximum tokens to generate
        
    Returns:
        API response as dictionary
    """
    payload = {
        "model": "llama-3.3-8b-instruct",
        "messages": messages,
        "max_tokens": max_tokens
    }
    response = await client.post(url, json=payload)
    return response.json()
```

### API Conventions

**Endpoint Design:**
- RESTful resource-oriented URLs
- OpenAI-compatible format for chat endpoints
- Consistent error responses
- Health checks at `/health`

**Request/Response Format:**
```python
# Request
{
    "model": "llama-3.3-8b-instruct",
    "messages": [
        {"role": "system", "content": "..."},
        {"role": "user", "content": "..."}
    ],
    "max_tokens": 100,
    "temperature": 0.7
}

# Response
{
    "id": "chatcmpl-...",
    "object": "chat.completion",
    "created": 1234567890,
    "model": "llama-3.3-8b-instruct",
    "choices": [{
        "index": 0,
        "message": {
            "role": "assistant",
            "content": "..."
        },
        "finish_reason": "stop"
    }],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30
    }
}
```

### Configuration Management

**Environment Variables:**
- Use `.env` file for local development
- Never commit secrets to git
- Document all environment variables

**YAML Configuration:**
- Use YAML for structured configuration
- Clear comments for all parameters
- Sensible defaults

**Example:**
```yaml
# MAX Serve Configuration
batching:
  max_batch_size: 32        # Max concurrent requests
  max_wait_time_ms: 10      # Batching window
  timeout_ms: 30000         # Request timeout

inference:
  max_tokens: 2048          # Max response length
  temperature: 0.7          # Sampling temperature
  context_length: 8192      # Context window size
```

### Error Handling

**Consistent Error Responses:**
```python
try:
    result = await call_api()
except httpx.HTTPError as e:
    raise HTTPException(
        status_code=503,
        detail=f"Service error: {str(e)}"
    )
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    raise HTTPException(
        status_code=500,
        detail="Internal server error"
    )
```

### Logging

**Structured Logging:**
```python
import logging

logger = logging.getLogger(__name__)

# Info level for normal operations
logger.info(f"Processing request with {len(messages)} messages")

# Warning for recoverable issues
logger.warning(f"High latency detected: {latency}ms")

# Error for failures
logger.error(f"Request failed: {error}", exc_info=True)
```

### Testing

**Test Structure:**
```python
def test_feature():
    """Test description."""
    # Arrange
    input_data = {...}
    
    # Act
    result = function_under_test(input_data)
    
    # Assert
    assert result["status"] == "success"
```

**Load Test Naming:**
```python
# Test scenarios
TEST_MESSAGES_SHORT = [...]   # Quick responses
TEST_MESSAGES_MEDIUM = [...]  # Standard queries
TEST_MESSAGES_LONG = [...]    # Complex conversations
```

### Docker & Infrastructure

**Service Naming:**
- Use lowercase with hyphens: `max-serve`, `api-server`
- Descriptive container names
- Consistent port mappings

**Volume Organization:**
```
./models/          # Model files
./configs/         # Configuration files
./logs/            # Application logs
./init-scripts/    # Initialization scripts
./examples/        # Usage examples
```

### Git Conventions

**Commit Messages:**
```
feat: Add streaming support for chat completions
fix: Resolve timeout issues in load tests
docs: Update deployment guide with GPU requirements
perf: Optimize batching configuration
```

**Branch Naming:**
```
feature/streaming-api
fix/memory-leak
docs/api-documentation
perf/batch-optimization
```

## Development Workflow

1. **Local Development:**
   ```bash
   # Install dependencies
   pip install -r requirements.txt
   
   # Start services
   docker compose up -d
   
   # Run tests
   python test_api.py
   ```

2. **Code Changes:**
   - Edit Python files
   - Restart API server: `docker compose restart api-server`
   - Test changes: `python test_api.py`

3. **Configuration Changes:**
   - Edit `docker-compose.yaml` or `configs/`
   - Restart affected services
   - Verify with health checks

4. **Performance Testing:**
   ```bash
   # Quick test
   python load_test.py --requests 100
   
   # Comprehensive test
   python load_test.py --scenario all --requests 500
   ```

5. **Monitoring:**
   ```bash
   # Real-time dashboard
   python monitor.py
   
   # Service logs
   docker compose logs -f max-serve
   docker compose logs -f api-server
   ```

## File Structure

```
.
├── api_server.py              # OpenAI-compatible API server
├── load_test.py               # Load testing with P50/P95/P99 metrics
├── test_api.py                # Basic API tests
├── monitor.py                 # Real-time performance monitoring
├── download_model.sh          # Model download script
├── init.sh                    # Initialization script
├── Dockerfile.api             # API server container
├── docker-compose.yaml        # Service orchestration
├── requirements.txt           # Python dependencies
├── Makefile                   # Convenient command shortcuts
├── configs/
│   └── max-serve-config.yaml # MAX Serve configuration
├── examples/
│   ├── chat_example.py       # Interactive chat
│   ├── batch_processing.py   # Batch request example
│   └── streaming_example.py  # Streaming template (future)
├── models/                    # Model storage (gitignored)
├── logs/                      # Application logs (gitignored)
└── init-scripts/
    └── postgres/
        └── init.sql          # Database initialization
```

## Key Features

1. **OpenAI-Compatible API**: Drop-in replacement for OpenAI chat API
2. **Dynamic Batching**: Process up to 32 concurrent requests efficiently
3. **Comprehensive Load Testing**: Detailed latency metrics (P50/P95/P99)
4. **Real-time Monitoring**: Performance dashboard with trends
5. **Production-Ready**: Health checks, error handling, logging
6. **Extensible**: Easy to add new endpoints and features

## Performance Targets

- **P50 Latency**: < 500ms (typical workload)
- **P95 Latency**: < 1000ms (typical workload)
- **P99 Latency**: < 1500ms (typical workload)
- **Throughput**: 20-30 requests/second (batch_size=32)
- **Error Rate**: < 0.1% (excluding rate limits)

## Security Considerations

- Change default credentials in production
- Use HTTPS/TLS for external access
- Implement authentication/authorization
- Rate limiting for public APIs
- Input validation and sanitization
- Regular security updates

---

*This file should be updated as the project evolves with new features and best practices.*
