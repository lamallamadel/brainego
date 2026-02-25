# Data Collection Pipeline

Automated data collection pipeline with scheduled jobs, webhooks, deduplication, and real-time ingestion.

## Features

- **Scheduled Collection**: Cron-based periodic data collection
  - GitHub: Every 6 hours (issues, PRs, commits)
  - Notion: Every 4 hours (pages, databases)
  - Slack: Every 2 hours (messages, threads)
  
- **Real-time Webhooks**: Instant ingestion from external events
  - GitHub webhooks (issues, PRs, comments, pushes)
  - Notion webhooks (page/database updates)
  - Generic webhook endpoint for custom integrations

- **Smart Deduplication**:
  - Hash-based exact duplicate detection
  - Cosine similarity near-duplicate detection (threshold: 0.95)
  - Efficient TF-IDF vectorization

- **Redis Queue Buffering**:
  - Asynchronous processing with RQ (Redis Queue)
  - Multiple worker support
  - Job status tracking and retries

- **Format Normalization**:
  - Unified document format across all sources
  - Metadata standardization
  - Automatic field mapping

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Data Collection Service                  │
│                         (Port 8002)                          │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  Scheduler   │    │   Webhooks   │    │  REST API    │  │
│  │  (Cron Jobs) │    │  (Real-time) │    │  (Triggers)  │  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘  │
│         │                   │                   │           │
│         └───────────────────┼───────────────────┘           │
│                             │                               │
└─────────────────────────────┼───────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   Redis Queue     │
                    │   (Buffering)     │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Ingestion Workers│
                    │   (4 workers)     │
                    └─────────┬─────────┘
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
    ┌────▼─────┐    ┌────────▼────────┐    ┌─────▼─────┐
    │Collector │    │   Normalizer    │    │Deduplicator│
    └────┬─────┘    └────────┬────────┘    └─────┬─────┘
         │                   │                    │
         └───────────────────┼────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   RAG Service   │
                    │   (Qdrant)      │
                    └─────────────────┘
```

## Components

### 1. Data Collectors

**GitHub Collector** (`data_collectors/github_collector.py`)
- Collects issues, pull requests, commits, discussions
- Supports repository-specific and user activity collection
- Configurable time window and content types

**Notion Collector** (`data_collectors/notion_collector.py`)
- Collects pages and database items
- Extracts text content from blocks
- Formats properties and metadata

**Slack Collector** (`data_collectors/slack_collector.py`)
- Collects messages and threads
- Multi-channel support
- User activity tracking

### 2. Format Normalizer

**FormatNormalizer** (`data_collectors/format_normalizer.py`)
- Converts all sources to unified format
- Standard fields: title, url, author, timestamps
- Preserves original metadata

### 3. Deduplicator

**Deduplicator** (`data_collectors/deduplicator.py`)
- Hash-based exact duplicate detection (SHA-256)
- Cosine similarity for near-duplicates
- Configurable similarity threshold (default: 0.95)
- TF-IDF vectorization with scikit-learn

### 4. Ingestion Queue

**IngestionQueue** (`data_collectors/ingestion_queue.py`)
- Redis Queue (RQ) integration
- Job enqueuing and status tracking
- Priority support
- Failure handling and retries

### 5. Worker Service

**Worker Service** (`worker_service.py`)
- Background job processing
- Configurable worker count
- Graceful shutdown handling
- Error logging and recovery

### 6. Scheduler

**CollectionScheduler** (`data_collectors/scheduler.py`)
- Cron-based job scheduling
- YAML configuration support
- Manual trigger capability
- Job status monitoring

### 7. Webhook Endpoints

**Webhook API** (`data_collectors/webhook_endpoints.py`)
- GitHub webhook handler (signature verification)
- Notion webhook handler (signature verification)
- Generic webhook endpoint
- Real-time event processing

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```bash
# GitHub Configuration
GITHUB_TOKEN=your_github_token
GITHUB_DEFAULT_REPO=owner/repo
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# Notion Configuration
NOTION_API_KEY=your_notion_api_key
NOTION_WEBHOOK_SECRET=your_webhook_secret

# Slack Configuration
SLACK_BOT_TOKEN=your_slack_bot_token
SLACK_CHANNELS=C12345678,C87654321

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Qdrant Configuration
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

### 3. Configure Collection Schedule

Edit `configs/collection-schedule.yaml`:

```yaml
schedules:
  - name: github_collection
    source: github
    interval: 6h
    config:
      repo_name: ${GITHUB_DEFAULT_REPO}
      hours_back: 6
      
  - name: notion_collection
    source: notion
    interval: 4h
    config:
      hours_back: 4
      
  - name: slack_collection
    source: slack
    interval: 2h
    config:
      channel_ids: ${SLACK_CHANNELS}
      hours_back: 2
```

### 4. Start Services with Docker Compose

```bash
# Start all services
docker compose up -d data-collection ingestion-worker

# View logs
docker compose logs -f data-collection
docker compose logs -f ingestion-worker
```

### 5. Start Services Manually (Development)

**Terminal 1 - Data Collection Service:**
```bash
python data_collection_service.py
```

**Terminal 2 - Worker Service:**
```bash
python worker_service.py
```

## API Reference

### Health Check
```bash
GET http://localhost:8002/health
```

Response:
```json
{
  "status": "healthy",
  "service": "data-collection",
  "scheduler_running": true
}
```

### Get Service Stats
```bash
GET http://localhost:8002/stats
```

Response:
```json
{
  "queue_stats": {
    "queued_jobs": 5,
    "started_jobs": 2,
    "finished_jobs": 100,
    "failed_jobs": 1
  },
  "scheduled_jobs": [...],
  "scheduler_running": true
}
```

### Trigger Collection
```bash
POST http://localhost:8002/trigger/{source}
Content-Type: application/json

{
  "repo_name": "owner/repo",
  "hours_back": 24
}
```

Response:
```json
{
  "status": "triggered",
  "source": "github",
  "job_id": "12345678-1234-1234-1234-123456789abc"
}
```

### Check Job Status
```bash
GET http://localhost:8002/jobs/{job_id}
```

Response:
```json
{
  "job_id": "12345678-1234-1234-1234-123456789abc",
  "status": "finished",
  "created_at": "2024-01-01T00:00:00",
  "started_at": "2024-01-01T00:00:01",
  "ended_at": "2024-01-01T00:01:00",
  "result": {
    "status": "success",
    "collected": 50,
    "processed": 45,
    "duplicates_removed": 5
  }
}
```

### GitHub Webhook
```bash
POST http://localhost:8002/webhooks/github
X-Hub-Signature-256: sha256=...
X-GitHub-Event: issues
Content-Type: application/json

{
  "action": "opened",
  "issue": {...},
  "repository": {...}
}
```

### Notion Webhook
```bash
POST http://localhost:8002/webhooks/notion
Notion-Signature: ...
Content-Type: application/json

{
  "type": "page",
  "page": {...}
}
```

### Generic Webhook
```bash
POST http://localhost:8002/webhooks/generic
Content-Type: application/json

{
  "event": "custom_event",
  "data": {
    "title": "Custom Data",
    "content": "..."
  }
}
```

## Configuration

### Collection Schedule

Edit `configs/collection-schedule.yaml` to customize:

```yaml
schedules:
  - name: my_collection
    source: github
    interval: 12h  # Can be: Xh (hours), Xm (minutes), Xd (days)
    enabled: true
    config:
      repo_name: owner/repo
      hours_back: 12
      include_issues: true
      include_prs: true
      include_commits: false
```

### Deduplication Settings

In `configs/collection-schedule.yaml`:

```yaml
deduplication:
  enabled: true
  hash_based: true
  similarity_based: true
  similarity_threshold: 0.95  # 0.0 to 1.0
```

### Worker Settings

```yaml
workers:
  num_workers: 4
  worker_class: default
  log_level: info
```

## Testing

### Run Tests
```bash
python test_data_collection.py
```

### Run Examples
```bash
python examples/data_collection_examples.py
```

### Manual Testing

**Test GitHub Collection:**
```python
from data_collectors.github_collector import GitHubCollector

collector = GitHubCollector()
docs = collector.collect_repository_data("octocat/Hello-World", hours_back=24)
print(f"Collected {len(docs)} documents")
```

**Test Deduplication:**
```python
from data_collectors.deduplicator import Deduplicator

dedup = Deduplicator(similarity_threshold=0.95)
unique_docs, stats = dedup.deduplicate_batch(documents)
print(f"Removed {stats['duplicates']} duplicates")
```

**Test Queue:**
```python
from data_collectors.ingestion_queue import IngestionQueue

queue = IngestionQueue()
job_ids = queue.enqueue_documents(documents)
print(f"Enqueued {len(job_ids)} jobs")
```

## Webhook Setup

### GitHub Webhooks

1. Go to repository Settings → Webhooks → Add webhook
2. Set Payload URL: `https://your-domain.com/webhooks/github`
3. Set Content type: `application/json`
4. Set Secret: Your `GITHUB_WEBHOOK_SECRET`
5. Select events: Issues, Pull requests, Pushes, Issue comments
6. Click "Add webhook"

### Notion Webhooks

1. Go to Notion integrations page
2. Create new integration or edit existing
3. Add webhook URL: `https://your-domain.com/webhooks/notion`
4. Set shared secret
5. Subscribe to page and database events

## Monitoring

### Queue Statistics

```bash
curl http://localhost:8002/stats
```

### Worker Logs

```bash
docker compose logs -f ingestion-worker
```

### Job Failures

Check Redis for failed jobs:
```bash
redis-cli
> LRANGE rq:queue:ingestion:failed 0 -1
```

## Troubleshooting

### Issue: No documents collected

**Solution:** Check API tokens and permissions
```bash
# Test GitHub token
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user

# Test Notion token
curl -H "Authorization: Bearer $NOTION_API_KEY" https://api.notion.com/v1/users/me
```

### Issue: Workers not processing jobs

**Solution:** Check Redis connection
```bash
# Test Redis connection
redis-cli ping

# Check worker processes
docker compose ps ingestion-worker
```

### Issue: High duplicate rate

**Solution:** Adjust deduplication threshold
```python
# Lower threshold for stricter deduplication
deduplicator = Deduplicator(similarity_threshold=0.85)
```

### Issue: Webhook signature verification fails

**Solution:** Ensure webhook secret matches
```bash
# Verify environment variable is set
echo $GITHUB_WEBHOOK_SECRET
```

## Performance

### Collection Intervals

- **GitHub**: 6 hours (recommended: 4-12 hours)
- **Notion**: 4 hours (recommended: 2-8 hours)
- **Slack**: 2 hours (recommended: 1-4 hours)

### Worker Scaling

Adjust worker count based on load:
```yaml
workers:
  num_workers: 8  # Increase for higher throughput
```

### Deduplication Performance

- Hash-based: O(n) - very fast
- Similarity-based: O(n²) - slower for large batches
- Recommendation: Process in batches of < 1000 documents

## Integration with RAG Service

The pipeline automatically feeds into the RAG service:

1. **Collection** → Raw documents from sources
2. **Normalization** → Unified format
3. **Deduplication** → Remove duplicates
4. **Chunking** → Split into embeddings-ready chunks (via RAG service)
5. **Embedding** → Generate vectors (Nomic Embed v1.5)
6. **Storage** → Store in Qdrant vector database

Query collected data:
```python
from rag_service import RAGIngestionService

rag = RAGIngestionService()
results = rag.search_documents("machine learning", limit=10)
```

## Best Practices

1. **Token Security**: Never commit tokens to git
2. **Webhook Verification**: Always verify webhook signatures
3. **Error Handling**: Monitor failed jobs and retry
4. **Rate Limits**: Respect API rate limits (especially GitHub)
5. **Deduplication**: Adjust threshold based on your use case
6. **Worker Scaling**: Scale workers based on queue depth
7. **Logging**: Enable debug logging for troubleshooting

## Files Created

- `data_collectors/__init__.py` - Package init
- `data_collectors/github_collector.py` - GitHub data collector
- `data_collectors/notion_collector.py` - Notion data collector
- `data_collectors/slack_collector.py` - Slack data collector
- `data_collectors/format_normalizer.py` - Format normalization
- `data_collectors/deduplicator.py` - Deduplication service
- `data_collectors/ingestion_queue.py` - Redis Queue management
- `data_collectors/ingestion_worker.py` - Worker job processing
- `data_collectors/scheduler.py` - Cron job scheduler
- `data_collectors/webhook_endpoints.py` - Webhook API endpoints
- `data_collection_service.py` - Main service
- `worker_service.py` - Worker process
- `configs/collection-schedule.yaml` - Schedule configuration
- `test_data_collection.py` - Test suite
- `examples/data_collection_examples.py` - Usage examples
- `DATA_COLLECTION_README.md` - This file

## License

Same as parent project.
