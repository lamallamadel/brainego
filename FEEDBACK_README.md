# Feedback Collection System

Comprehensive feedback collection system with thumbs-up/down ratings, feedback taxonomy categories, optional expected answers, PostgreSQL storage, per-model accuracy tracking, and automated fine-tuning dataset export.

## Features

### 1. Feedback Collection (POST /v1/feedback)
- **Thumbs-up/down ratings**: Simple +1/-1 rating system
- **Feedback taxonomy**: `hallucination`, `wrong_tool`, `missing_citation`, `policy_denial`
- **Expected answer capture**: Optional corrected answer for negative feedback
- **Full context tracking**: Query, response, model, memory usage, tools called
- **Rich metadata**: User ID, session ID, intent, project, custom metadata
- **PostgreSQL storage**: Reliable, queryable storage with ACID guarantees

### 2. Accuracy Tracking (GET /v1/feedback/accuracy)
- **Per-model metrics**: Accuracy calculated for each model
- **Intent-based breakdown**: Separate metrics for code/reasoning/general intents
- **Project-level tracking**: Track accuracy across different projects
- **Auto-refresh**: PostgreSQL materialized view auto-updates on new feedback
- **Percentage calculation**: `(positive_feedback / total_feedback) * 100`

### 3. Fine-tuning Dataset Export (POST /v1/feedback/export/finetuning)
- **Weekly exports**: Default 7-day rolling window
- **Weighted samples**: 
  - Positive feedback (👍): **2.0x weight**
  - Negative feedback (👎): **0.5x weight**
- **JSONL format**: Compatible with common fine-tuning frameworks
- **Metadata preservation**: Intent, project, model, timestamp included

### 4. Statistics & Analytics (GET /v1/feedback/stats)
- **Time-based filtering**: Last 7/30/90 days
- **Model/intent/project filters**: Drill down into specific segments
- **Aggregated metrics**: Total feedback, positive %, unique users/sessions
- **Memory tracking**: Average memory usage across requests

## Database Schema

### Feedback Table
```sql
CREATE TABLE feedback (
    id SERIAL PRIMARY KEY,
    feedback_id VARCHAR(255) UNIQUE NOT NULL,
    query TEXT NOT NULL,
    response TEXT NOT NULL,
    model VARCHAR(255) NOT NULL,
    memory_used INTEGER DEFAULT 0,
    tools_called TEXT[] DEFAULT ARRAY[]::TEXT[],
    rating INTEGER NOT NULL CHECK (rating IN (-1, 1)),
    reason TEXT,
    category VARCHAR(64),
    expected_answer TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR(255),
    session_id VARCHAR(255),
    intent VARCHAR(100),
    project VARCHAR(255),
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### Accuracy Materialized View
```sql
CREATE MATERIALIZED VIEW model_accuracy_by_intent AS
SELECT 
    model,
    intent,
    project,
    COUNT(*) as total_feedback,
    COUNT(*) FILTER (WHERE rating = 1) as positive_feedback,
    COUNT(*) FILTER (WHERE rating = -1) as negative_feedback,
    ROUND(COUNT(*) FILTER (WHERE rating = 1)::NUMERIC / 
          NULLIF(COUNT(*), 0) * 100, 2) as accuracy_percentage,
    MAX(timestamp) as last_updated
FROM feedback
WHERE intent IS NOT NULL
GROUP BY model, intent, project;
```

## API Endpoints

### Submit Feedback
```bash
POST /v1/feedback
Content-Type: application/json

{
  "query": "Write a Python function to reverse a string",
  "response": "def reverse_string(s):\n    return s[::-1]",
  "model": "qwen-2.5-coder-7b",
  "rating": 1,
  "category": "hallucination",
  "reason": "The model fabricated a production metric",
  "expected_answer": "I don't have access to that production metric in this context.",
  "memory_used": 1024000,
  "tools_called": ["code_generator", "syntax_validator"],
  "user_id": "user-123",
  "session_id": "session-abc",
  "intent": "code",
  "project": "my-project",
  "metadata": {"complexity": "simple"}
}
```

**Response:**
```json
{
  "status": "success",
  "feedback_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "id": 42,
  "timestamp": "2025-01-15T10:30:00.123456Z",
  "rating": 1,
  "model": "qwen-2.5-coder-7b"
}
```

### Get Feedback by ID
```bash
GET /v1/feedback/{feedback_id}
```

### Update Feedback
```bash
PUT /v1/feedback/{feedback_id}
Content-Type: application/json

{
  "rating": -1,
  "intent": "code_review",
  "metadata": {"updated_reason": "incorrect syntax"}
}
```

### Delete Feedback
```bash
DELETE /v1/feedback/{feedback_id}
```

### Get Model Accuracy
```bash
GET /v1/feedback/accuracy
GET /v1/feedback/accuracy?model=qwen-2.5-coder-7b
GET /v1/feedback/accuracy?intent=code
GET /v1/feedback/accuracy?model=llama-3.3-8b-instruct&intent=general&project=my-project
```

**Response:**
```json
[
  {
    "model": "qwen-2.5-coder-7b",
    "intent": "code",
    "project": "my-project",
    "total_feedback": 150,
    "positive_feedback": 135,
    "negative_feedback": 15,
    "accuracy_percentage": 90.0,
    "last_updated": "2025-01-15T10:30:00.123456Z"
  }
]
```

### Get Feedback Statistics
```bash
GET /v1/feedback/stats
GET /v1/feedback/stats?model=deepseek-r1-distill-qwen-7b&days=30
GET /v1/feedback/stats?intent=reasoning&days=7
```

**Response:**
```json
{
  "total_feedback": 500,
  "positive_count": 425,
  "negative_count": 75,
  "positive_percentage": 85.0,
  "avg_memory_used": 1536000,
  "unique_users": 45,
  "unique_sessions": 123,
  "days": 7,
  "filters": {
    "model": null,
    "intent": "reasoning",
    "project": null
  }
}
```

### Export Fine-tuning Dataset
```bash
POST /v1/feedback/export/finetuning
Content-Type: application/json

{
  "output_path": "/app/exports/finetuning_2025_01_15.jsonl",
  "start_date": "2025-01-08T00:00:00Z",
  "end_date": "2025-01-15T23:59:59Z",
  "format": "jsonl"
}
```

**Response:**
```json
{
  "status": "success",
  "output_path": "/app/exports/finetuning_2025_01_15.jsonl",
  "total_samples": 342,
  "positive_samples": 289,
  "negative_samples": 53,
  "total_weight": 604.5,
  "filtered_out_samples": 21,
  "start_date": "2025-01-08T00:00:00Z",
  "end_date": "2025-01-15T23:59:59Z"
}
```

**Output Format (JSONL):**
```json
{"instruction": "Respond to the user input accurately and helpfully.", "input": "...", "output": "...", "weight": 2.0, "metadata": {"model": "qwen-2.5-coder-7b", "rating": 1, "timestamp": "2025-01-15T10:30:00Z", "intent": "code", "project": "my-project", "category": null, "reason": null, "expected_answer": null}}
{"instruction": "Respond to the user input accurately and helpfully.", "input": "...", "output": "...", "weight": 0.5, "metadata": {"model": "llama-3.3-8b-instruct", "rating": -1, "timestamp": "2025-01-15T11:30:00Z", "intent": "general", "project": "my-project", "category": "missing_citation", "reason": "No source cited", "expected_answer": "Add the source and quote it."}}
```

## Weighting Strategy

The fine-tuning dataset applies weights to emphasize learning from good examples:

| Rating | Meaning | Weight | Effect |
|--------|---------|--------|--------|
| +1 | 👍 Thumbs Up | 2.0x | **Doubled importance** - learn strongly from good responses |
| -1 | 👎 Thumbs Down | 0.5x | **Half importance** - learn weakly from bad responses (for contrast) |

**Rationale:**
- **Positive feedback (2.0x)**: These are confirmed good responses. We want the model to learn strongly from them and replicate similar patterns.
- **Negative feedback (0.5x)**: These help the model learn what NOT to do, but we don't want to over-emphasize bad examples. Reduced weight prevents the model from learning incorrect patterns.

## Usage Examples

### Python Client
```python
import httpx

# Submit feedback
response = httpx.post(
    "http://localhost:8000/v1/feedback",
    json={
        "query": "Explain neural networks",
        "response": "Neural networks are...",
        "model": "llama-3.3-8b-instruct",
        "rating": 1,
        "intent": "general"
    }
)
feedback = response.json()
print(f"Feedback ID: {feedback['feedback_id']}")

# Get accuracy by model
response = httpx.get(
    "http://localhost:8000/v1/feedback/accuracy",
    params={"model": "llama-3.3-8b-instruct"}
)
metrics = response.json()
for m in metrics:
    print(f"{m['intent']}: {m['accuracy_percentage']:.2f}%")
```

### cURL
```bash
# Submit feedback
curl -X POST http://localhost:8000/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Debug this code",
    "response": "Here is the fixed version...",
    "model": "qwen-2.5-coder-7b",
    "rating": 1,
    "intent": "code"
  }'

# Get statistics
curl "http://localhost:8000/v1/feedback/stats?days=30"

# Export dataset
curl -X POST http://localhost:8000/v1/feedback/export/finetuning \
  -H "Content-Type: application/json" \
  -d '{
    "output_path": "/tmp/dataset.jsonl",
    "format": "jsonl"
  }'
```

## Automated Workflows

### Weekly Fine-tuning Dataset Export
Create a cron job or scheduled task:

```bash
#!/bin/bash
# export_weekly_dataset.sh

OUTPUT_DIR="/app/exports"
DATE=$(date +%Y_%m_%d)
OUTPUT_FILE="${OUTPUT_DIR}/finetuning_${DATE}.jsonl"

curl -X POST http://localhost:8000/v1/feedback/export/finetuning \
  -H "Content-Type: application/json" \
  -d "{
    \"output_path\": \"${OUTPUT_FILE}\",
    \"format\": \"jsonl\"
  }"

echo "Dataset exported to ${OUTPUT_FILE}"
```

Schedule with cron (every Sunday at 2 AM):
```cron
0 2 * * 0 /app/scripts/export_weekly_dataset.sh
```

## PostgreSQL Functions

The system includes stored procedures for efficient data processing:

### Get Weekly Dataset
```sql
SELECT * FROM get_weekly_finetuning_dataset(
    NOW() - INTERVAL '7 days',  -- start_date
    NOW()                        -- end_date
);
```

### Manual Accuracy Refresh
```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY model_accuracy_by_intent;
```

## Performance Considerations

### Connection Pooling
- **Min connections**: 2
- **Max connections**: 10
- **Automatically manages** connection lifecycle

### Indexing
All critical columns are indexed for fast queries:
- `feedback.timestamp` - Time-based filtering
- `feedback.model` - Model-specific queries
- `feedback.intent` - Intent-based filtering
- `feedback.rating` - Accuracy calculations
- `feedback.project` - Project-level metrics

### Materialized View
- **Auto-refresh** on INSERT/UPDATE/DELETE via triggers
- **Concurrent refresh** - no table locking
- **Indexed** on (model, intent, project) for fast lookups

## Testing

Run the test suite:
```bash
python test_feedback.py
```

Tests cover:
1. ✓ Adding feedback (thumbs-up/down)
2. ✓ Retrieving feedback by ID
3. ✓ Updating feedback metadata
4. ✓ Getting accuracy metrics with filters
5. ✓ Getting statistics with time ranges
6. ✓ Exporting fine-tuning datasets
7. ✓ Deleting feedback

## Integration with Existing APIs

### Chat Completions Integration
```python
# In your chat completion handler
response_data = await generate_completion(messages)

# Optionally collect feedback
feedback_payload = {
    "query": messages[-1]["content"],
    "response": response_data["choices"][0]["message"]["content"],
    "model": response_data["model"],
    "rating": user_rating,  # From UI
    "intent": response_data.get("x-routing-metadata", {}).get("intent"),
    "memory_used": get_memory_usage(),
    "tools_called": get_tools_used()
}

# Submit feedback asynchronously
await submit_feedback(feedback_payload)
```

## Monitoring & Analytics

### Key Metrics to Track
1. **Overall Accuracy**: `(total_positive / total_feedback) * 100`
2. **Model Comparison**: Which model has highest accuracy per intent
3. **Trend Analysis**: Accuracy over time (daily/weekly/monthly)
4. **Problem Areas**: Low accuracy intents/projects needing improvement
5. **User Engagement**: Feedback submission rate

### Example Queries

**Find lowest performing model/intent combinations:**
```sql
SELECT model, intent, accuracy_percentage, total_feedback
FROM model_accuracy_by_intent
WHERE total_feedback >= 10
ORDER BY accuracy_percentage ASC
LIMIT 5;
```

**Feedback trends over time:**
```sql
SELECT 
    DATE(timestamp) as date,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE rating = 1) as positive
FROM feedback
WHERE timestamp >= NOW() - INTERVAL '30 days'
GROUP BY DATE(timestamp)
ORDER BY date;
```

## Environment Variables

```bash
# PostgreSQL Configuration
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=ai_platform
POSTGRES_USER=ai_user
POSTGRES_PASSWORD=ai_password
```

Add to `docker-compose.yaml` or `.env` file.

## Security Considerations

1. **SQL Injection**: All queries use parameterized statements
2. **Connection Pool**: Prevents connection exhaustion attacks
3. **Input Validation**: Rating restricted to +1/-1, all inputs validated
4. **Authentication**: Add API key/JWT validation in production
5. **Rate Limiting**: Implement per-user rate limits for feedback submission

## Future Enhancements

- [ ] Real-time accuracy dashboard with Grafana
- [ ] A/B testing framework for model variants
- [ ] Automatic fine-tuning trigger at accuracy thresholds
- [ ] Sentiment analysis on negative feedback
- [ ] Feedback clustering for issue identification
- [ ] Multi-turn conversation feedback
- [ ] Comparative feedback (A/B response rating)
- [ ] Export to OpenAI/HuggingFace fine-tuning formats

## Troubleshooting

### Connection Errors
```
psycopg2.OperationalError: could not connect to server
```
**Solution**: Ensure PostgreSQL is running and accessible. Check `POSTGRES_HOST` and credentials.

### Materialized View Not Refreshing
```sql
-- Manual refresh
REFRESH MATERIALIZED VIEW CONCURRENTLY model_accuracy_by_intent;

-- Check trigger exists
SELECT * FROM pg_trigger WHERE tgname = 'trigger_refresh_accuracy';
```

### Missing Feedback
Check table exists and is accessible:
```sql
SELECT COUNT(*) FROM feedback;
```

## Contributing

When adding new features:
1. Update database schema in `init-scripts/postgres/init.sql`
2. Add service methods in `feedback_service.py`
3. Add API endpoints in `api_server.py`
4. Update tests in `test_feedback.py`
5. Document in this README

## License

Part of the AI Platform project.
