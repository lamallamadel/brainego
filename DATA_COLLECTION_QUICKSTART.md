# Data Collection Pipeline - Quick Start Guide

Get your automated data collection pipeline running in minutes.

## Prerequisites

- Docker and Docker Compose installed
- GitHub personal access token
- (Optional) Notion API key
- (Optional) Slack bot token
- Redis and Qdrant running (via docker-compose)

## 5-Minute Setup

### 1. Configure Environment

Copy the example environment file:
```bash
cp .env.datacollection.example .env
```

Edit `.env` and add your credentials:
```bash
# Required
GITHUB_TOKEN=ghp_your_token_here

# Optional (for full functionality)
NOTION_API_KEY=secret_your_notion_key_here
SLACK_BOT_TOKEN=xoxb-your_slack_token_here
SLACK_CHANNELS=C12345678,C87654321
```

### 2. Start Services

Using Make (recommended):
```bash
make datacollection
```

Or using Docker Compose directly:
```bash
docker compose up -d data-collection ingestion-worker
```

### 3. Verify Services

Check health:
```bash
curl http://localhost:8002/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "data-collection",
  "scheduler_running": true
}
```

### 4. View Statistics

```bash
make datacollection-stats
```

Or:
```bash
curl http://localhost:8002/stats | jq
```

## Quick Tests

### Test GitHub Collection

```bash
curl -X POST http://localhost:8002/trigger/github \
  -H "Content-Type: application/json" \
  -d '{
    "repo_name": "octocat/Hello-World",
    "hours_back": 24
  }'
```

Response:
```json
{
  "status": "triggered",
  "source": "github",
  "job_id": "abc123..."
}
```

### Check Job Status

```bash
curl http://localhost:8002/jobs/{job_id}
```

### Test Webhook

Send test GitHub webhook:
```bash
curl -X POST http://localhost:8002/webhooks/github \
  -H "X-GitHub-Event: issues" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "opened",
    "issue": {
      "number": 1,
      "title": "Test Issue",
      "body": "This is a test",
      "state": "open",
      "html_url": "https://github.com/test/repo/issues/1",
      "user": {"login": "testuser"},
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z",
      "labels": []
    },
    "repository": {"full_name": "test/repo"}
  }'
```

## Configuration

### Customize Collection Schedule

Edit `configs/collection-schedule.yaml`:

```yaml
schedules:
  - name: github_collection
    source: github
    interval: 6h  # Change interval
    config:
      repo_name: your-org/your-repo
      hours_back: 6
```

Restart service:
```bash
make datacollection-stop
make datacollection-start
```

### Adjust Deduplication

In `configs/collection-schedule.yaml`:

```yaml
deduplication:
  similarity_threshold: 0.90  # Lower = more aggressive deduplication
```

### Scale Workers

In `docker-compose.yaml`:

```yaml
environment:
  - NUM_WORKERS=8  # Increase for more throughput
```

## Common Use Cases

### 1. Monitor GitHub Repository

Automatically collect issues, PRs, and commits every 6 hours:

**config/collection-schedule.yaml:**
```yaml
schedules:
  - name: repo_monitor
    source: github
    interval: 6h
    config:
      repo_name: facebook/react
      hours_back: 6
      include_issues: true
      include_prs: true
      include_commits: true
```

### 2. Track Notion Workspace

Collect all page updates every 4 hours:

**config/collection-schedule.yaml:**
```yaml
schedules:
  - name: notion_workspace
    source: notion
    interval: 4h
    config:
      hours_back: 4
```

### 3. Archive Slack Conversations

Collect messages from specific channels every 2 hours:

**config/collection-schedule.yaml:**
```yaml
schedules:
  - name: slack_archive
    source: slack
    interval: 2h
    config:
      channel_ids:
        - C12345678
        - C87654321
      hours_back: 2
```

### 4. Real-time GitHub Integration

Set up GitHub webhook to capture events instantly:

1. Go to GitHub repo → Settings → Webhooks
2. Add webhook URL: `https://your-domain.com/webhooks/github`
3. Select events: Issues, Pull requests, Pushes
4. Add secret from `.env` file (`GITHUB_WEBHOOK_SECRET`)

### 5. Custom Data Source

Use generic webhook for custom integrations:

```bash
curl -X POST http://localhost:8002/webhooks/generic \
  -H "Content-Type: application/json" \
  -d '{
    "event": "user_signup",
    "data": {
      "user_id": "123",
      "email": "user@example.com",
      "timestamp": "2024-01-01T00:00:00Z"
    }
  }'
```

## Monitoring

### View Logs

```bash
make datacollection-logs
```

Or specific service:
```bash
docker compose logs -f data-collection
docker compose logs -f ingestion-worker
```

### Queue Status

```bash
curl http://localhost:8002/stats | jq '.queue_stats'
```

Output:
```json
{
  "queued_jobs": 5,
  "started_jobs": 2,
  "finished_jobs": 150,
  "failed_jobs": 1
}
```

### Scheduled Jobs

```bash
curl http://localhost:8002/stats | jq '.scheduled_jobs'
```

## Troubleshooting

### Service Won't Start

**Check logs:**
```bash
docker compose logs data-collection
```

**Common issues:**
- Missing Redis: Ensure Redis is running
- Missing environment variables: Check `.env` file
- Port conflict: Change port in `.env`

### No Data Collected

**Check token permissions:**
```bash
# GitHub
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/user

# Notion
curl -H "Authorization: Bearer $NOTION_API_KEY" \
  https://api.notion.com/v1/users/me
```

**Verify configuration:**
```bash
cat configs/collection-schedule.yaml
```

### Workers Not Processing

**Check Redis connection:**
```bash
docker compose ps redis
redis-cli ping
```

**Check worker logs:**
```bash
docker compose logs ingestion-worker
```

**Restart workers:**
```bash
docker compose restart ingestion-worker
```

### High Memory Usage

**Reduce batch size** in `data_collectors/deduplicator.py`:
```python
# Process smaller batches
max_batch_size = 500  # Instead of 1000
```

**Scale down workers:**
```yaml
environment:
  - NUM_WORKERS=2  # Instead of 4
```

## Next Steps

### 1. Test the Pipeline

```bash
python test_data_collection.py
```

### 2. Run Examples

```bash
python examples/data_collection_examples.py
```

### 3. Query Collected Data

```python
from rag_service import RAGIngestionService

rag = RAGIngestionService()
results = rag.search_documents("bug fix", limit=10)

for result in results:
    print(f"Source: {result['metadata']['source']}")
    print(f"Title: {result['metadata']['title']}")
    print(f"Score: {result['score']}")
    print()
```

### 4. Set Up Production Webhooks

Configure real GitHub/Notion webhooks pointing to your server.

### 5. Customize Collection

Modify collectors in `data_collectors/` to add custom logic.

## Production Checklist

- [ ] Set strong webhook secrets
- [ ] Use HTTPS for webhook endpoints
- [ ] Configure rate limiting
- [ ] Set up monitoring alerts
- [ ] Enable backup for Redis
- [ ] Configure log rotation
- [ ] Set resource limits in Docker
- [ ] Test failover scenarios
- [ ] Document custom configurations
- [ ] Set up scheduled health checks

## Performance Tips

1. **Adjust intervals** based on data volume
2. **Scale workers** horizontally for throughput
3. **Tune deduplication threshold** for your use case
4. **Use webhooks** for real-time data (more efficient)
5. **Monitor queue depth** and adjust workers
6. **Enable Redis persistence** for reliability

## Getting Help

- **Documentation**: See `DATA_COLLECTION_README.md`
- **Examples**: Check `examples/data_collection_examples.py`
- **Tests**: Run `test_data_collection.py`
- **Logs**: `make datacollection-logs`

## Summary

You now have a fully automated data collection pipeline that:

✅ Collects data from GitHub, Notion, and Slack  
✅ Runs on customizable schedules (6h, 4h, 2h)  
✅ Accepts real-time webhooks  
✅ Deduplicates content automatically  
✅ Queues jobs with Redis  
✅ Processes asynchronously with workers  
✅ Feeds directly into RAG system  

**Key endpoints:**
- Service: `http://localhost:8002`
- Health: `http://localhost:8002/health`
- Stats: `http://localhost:8002/stats`
- GitHub webhook: `http://localhost:8002/webhooks/github`
- Notion webhook: `http://localhost:8002/webhooks/notion`

**Key commands:**
```bash
make datacollection        # Start everything
make datacollection-stats  # Check status
make datacollection-logs   # View logs
make datacollection-test   # Run tests
```

Happy collecting! 🚀
