# Feedback System Quick Start Guide

## 🚀 Getting Started in 5 Minutes

### 1. Start Services
```bash
docker compose up -d postgres api-server
```

### 2. Submit Feedback
```bash
curl -X POST http://localhost:8000/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Write a Python hello world",
    "response": "print(\"Hello, World!\")",
    "model": "qwen-2.5-coder-7b",
    "rating": 1,
    "intent": "code"
  }'
```

### 3. Check Accuracy
```bash
curl http://localhost:8000/v1/feedback/accuracy
```

### 4. Export Weekly Dataset
```bash
python export_weekly_finetuning.py /tmp/dataset.jsonl
```

---

## 📊 Common Operations

### Submit Positive Feedback (Thumbs Up)
```python
import httpx

httpx.post("http://localhost:8000/v1/feedback", json={
    "query": "Your query here",
    "response": "Model's response here",
    "model": "llama-3.3-8b-instruct",
    "rating": 1,  # 👍
    "intent": "general"
})
```

### Submit Negative Feedback (Thumbs Down)
```python
httpx.post("http://localhost:8000/v1/feedback", json={
    "query": "Your query here",
    "response": "Model's incorrect response",
    "model": "deepseek-r1-distill-qwen-7b",
    "rating": -1,  # 👎
    "intent": "reasoning"
})
```

### Get Model Accuracy
```bash
# All models
curl http://localhost:8000/v1/feedback/accuracy

# Specific model
curl "http://localhost:8000/v1/feedback/accuracy?model=qwen-2.5-coder-7b"

# By intent
curl "http://localhost:8000/v1/feedback/accuracy?intent=code"
```

### Get Statistics
```bash
# Last 7 days (default)
curl http://localhost:8000/v1/feedback/stats

# Last 30 days
curl "http://localhost:8000/v1/feedback/stats?days=30"

# Specific model
curl "http://localhost:8000/v1/feedback/stats?model=llama-3.3-8b-instruct&days=7"
```

---

## 🎯 Rating Guide

| Rating | Meaning | Weight | Use When |
|--------|---------|--------|----------|
| +1 | 👍 Thumbs Up | 2.0x | Response is correct, helpful, accurate |
| -1 | 👎 Thumbs Down | 0.5x | Response is wrong, unhelpful, inaccurate |

---

## 📁 Files Reference

| File | Purpose |
|------|---------|
| `feedback_service.py` | Core service implementation |
| `api_server.py` | REST API endpoints |
| `test_feedback.py` | Test suite |
| `export_weekly_finetuning.py` | Dataset export script |
| `feedback_dashboard.py` | Real-time monitoring |
| `init-scripts/postgres/init.sql` | Database schema |

---

## 🔧 Environment Variables

```bash
export POSTGRES_HOST=postgres
export POSTGRES_PORT=5432
export POSTGRES_DB=ai_platform
export POSTGRES_USER=ai_user
export POSTGRES_PASSWORD=ai_password
```

---

## 📈 Dashboard

```bash
# Real-time monitoring
python feedback_dashboard.py --interval 5

# Shows:
# - Overall statistics
# - Accuracy by model
# - Accuracy by intent
# - Visual progress bars
```

---

## 🧪 Testing

```bash
# Run full test suite
python test_feedback.py

# Tests all endpoints:
# ✓ Add feedback
# ✓ Get feedback
# ✓ Update feedback
# ✓ Accuracy metrics
# ✓ Statistics
# ✓ Dataset export
# ✓ Delete feedback
```

---

## 📤 Weekly Export

### Manual Export
```bash
python export_weekly_finetuning.py /tmp/dataset.jsonl --days 7
```

### Automated (Cron)
```bash
# Add to crontab (every Sunday at 2 AM)
0 2 * * 0 python /app/export_weekly_finetuning.py /app/exports/weekly_$(date +\%Y\%m\%d).jsonl
```

### Output Format
```json
{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}], "weight": 2.0, "metadata": {...}}
```

---

## 🔍 Useful Queries

### Find Low-Performing Models
```sql
SELECT model, intent, accuracy_percentage, total_feedback
FROM model_accuracy_by_intent
WHERE total_feedback >= 10
ORDER BY accuracy_percentage ASC
LIMIT 5;
```

### Feedback Trends
```sql
SELECT 
    DATE(timestamp) as date,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE rating = 1) as positive,
    ROUND(COUNT(*) FILTER (WHERE rating = 1)::NUMERIC / COUNT(*) * 100, 2) as accuracy
FROM feedback
WHERE timestamp >= NOW() - INTERVAL '30 days'
GROUP BY DATE(timestamp)
ORDER BY date;
```

### Top Users by Feedback
```sql
SELECT 
    user_id,
    COUNT(*) as feedback_count,
    COUNT(*) FILTER (WHERE rating = 1) as thumbs_up,
    COUNT(*) FILTER (WHERE rating = -1) as thumbs_down
FROM feedback
WHERE user_id IS NOT NULL
GROUP BY user_id
ORDER BY feedback_count DESC
LIMIT 10;
```

---

## 🐛 Troubleshooting

### Connection Error
```
Problem: psycopg2.OperationalError: could not connect to server
Solution: Check POSTGRES_HOST and credentials, ensure PostgreSQL is running
```

### No Accuracy Data
```
Problem: GET /v1/feedback/accuracy returns empty array
Solution: Submit some feedback first, then check again
```

### Materialized View Not Refreshing
```sql
-- Manual refresh
REFRESH MATERIALIZED VIEW CONCURRENTLY model_accuracy_by_intent;
```

---

## 📚 More Information

- Full Documentation: `FEEDBACK_README.md`
- Implementation Details: `FEEDBACK_IMPLEMENTATION.md`
- API Server Code: `api_server.py` (lines 1643-1949)
- Service Code: `feedback_service.py`

---

## ✨ Integration Example

```python
from feedback_service import FeedbackService

# Initialize service
feedback = FeedbackService(
    db_host="localhost",
    db_port=5432,
    db_name="ai_platform",
    db_user="ai_user",
    db_password="ai_password"
)

# Add feedback
result = feedback.add_feedback(
    query="Explain recursion",
    response="Recursion is when a function calls itself...",
    model="llama-3.3-8b-instruct",
    rating=1,
    intent="general",
    user_id="user123"
)

print(f"Feedback ID: {result['feedback_id']}")

# Get accuracy
metrics = feedback.get_model_accuracy(model="llama-3.3-8b-instruct")
for m in metrics:
    print(f"{m['intent']}: {m['accuracy_percentage']}%")

# Close connection
feedback.close()
```

---

## 🎓 Best Practices

1. **Always set intent**: Helps with accuracy tracking
2. **Include project**: Enables project-level metrics
3. **Set user_id**: Tracks user engagement
4. **Export weekly**: Regular fine-tuning dataset updates
5. **Monitor accuracy**: Track trends to identify issues
6. **Archive old data**: Keep database performant

---

## 🚨 Important Notes

- ✅ Ratings must be exactly +1 or -1
- ✅ Query and response are required fields
- ✅ Model identifier should match actual model used
- ✅ Intent helps categorize feedback (code/reasoning/general)
- ✅ Accuracy auto-updates via PostgreSQL triggers
- ✅ Export weights: Positive=2.0x, Negative=0.5x

---

**Ready to collect feedback! 🎉**
