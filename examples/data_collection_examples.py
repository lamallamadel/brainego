#!/usr/bin/env python3
"""
Data Collection Pipeline Examples
"""

import os
import time
import requests


def example_trigger_github_collection():
    """Example: Trigger GitHub data collection via API."""
    print("Example: Trigger GitHub Collection")
    
    url = "http://localhost:8002/trigger/github"
    config = {
        "repo_name": "octocat/Hello-World",
        "hours_back": 24,
        "include_issues": True,
        "include_prs": True,
        "include_commits": True
    }
    
    response = requests.post(url, json=config)
    result = response.json()
    
    print(f"Status: {result['status']}")
    print(f"Job ID: {result['job_id']}")
    
    return result['job_id']


def example_trigger_notion_collection():
    """Example: Trigger Notion data collection via API."""
    print("\nExample: Trigger Notion Collection")
    
    url = "http://localhost:8002/trigger/notion"
    config = {
        "hours_back": 24
    }
    
    response = requests.post(url, json=config)
    result = response.json()
    
    print(f"Status: {result['status']}")
    print(f"Job ID: {result['job_id']}")
    
    return result['job_id']


def example_trigger_slack_collection():
    """Example: Trigger Slack data collection via API."""
    print("\nExample: Trigger Slack Collection")
    
    url = "http://localhost:8002/trigger/slack"
    config = {
        "channel_ids": ["C12345678"],
        "hours_back": 6
    }
    
    response = requests.post(url, json=config)
    result = response.json()
    
    print(f"Status: {result['status']}")
    print(f"Job ID: {result['job_id']}")
    
    return result['job_id']


def example_check_job_status(job_id):
    """Example: Check job status."""
    print(f"\nExample: Check Job Status ({job_id})")
    
    url = f"http://localhost:8002/jobs/{job_id}"
    response = requests.get(url)
    result = response.json()
    
    print(f"Job ID: {result['job_id']}")
    print(f"Status: {result['status']}")
    print(f"Created: {result.get('created_at', 'N/A')}")
    print(f"Started: {result.get('started_at', 'N/A')}")
    print(f"Ended: {result.get('ended_at', 'N/A')}")
    
    if result.get('result'):
        print(f"Result: {result['result']}")
    
    return result


def example_get_service_stats():
    """Example: Get service statistics."""
    print("\nExample: Get Service Statistics")
    
    url = "http://localhost:8002/stats"
    response = requests.get(url)
    result = response.json()
    
    print("Queue Stats:")
    queue_stats = result['queue_stats']
    print(f"  Queued: {queue_stats['queued_jobs']}")
    print(f"  Running: {queue_stats['started_jobs']}")
    print(f"  Completed: {queue_stats['finished_jobs']}")
    print(f"  Failed: {queue_stats['failed_jobs']}")
    
    print("\nScheduled Jobs:")
    for job in result['scheduled_jobs']:
        print(f"  {job['job']} - Next run: {job['next_run']}")
    
    return result


def example_github_webhook():
    """Example: Send test GitHub webhook."""
    print("\nExample: GitHub Webhook")
    
    url = "http://localhost:8002/webhooks/github"
    
    payload = {
        "action": "opened",
        "issue": {
            "number": 123,
            "title": "Test Issue",
            "body": "This is a test issue created via webhook",
            "state": "open",
            "html_url": "https://github.com/test/repo/issues/123",
            "user": {"login": "testuser"},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "labels": []
        },
        "repository": {
            "full_name": "test/repo"
        }
    }
    
    headers = {
        "X-GitHub-Event": "issues"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    result = response.json()
    
    print(f"Status: {result['status']}")
    print(f"Event: {result['event']}")
    print(f"Job IDs: {result['job_ids']}")
    
    return result


def example_generic_webhook():
    """Example: Send generic webhook."""
    print("\nExample: Generic Webhook")
    
    url = "http://localhost:8002/webhooks/generic"
    
    payload = {
        "event": "custom_event",
        "data": {
            "title": "Custom Event",
            "content": "This is custom data from an external source",
            "timestamp": "2024-01-01T00:00:00Z"
        }
    }
    
    response = requests.post(url, json=payload)
    result = response.json()
    
    print(f"Status: {result['status']}")
    print(f"Event: {result['event']}")
    print(f"Job IDs: {result['job_ids']}")
    
    return result


def example_programmatic_collection():
    """Example: Programmatic data collection."""
    print("\nExample: Programmatic Collection")
    
    from data_collectors.github_collector import GitHubCollector
    from data_collectors.format_normalizer import FormatNormalizer
    from data_collectors.deduplicator import Deduplicator
    from rag_service import RAGIngestionService
    
    collector = GitHubCollector()
    normalizer = FormatNormalizer()
    deduplicator = Deduplicator(similarity_threshold=0.95)
    
    rag_service = RAGIngestionService(
        qdrant_host="localhost",
        qdrant_port=6333
    )
    
    print("Step 1: Collecting data from GitHub...")
    documents = collector.collect_repository_data(
        repo_name="octocat/Hello-World",
        hours_back=168
    )
    print(f"  Collected {len(documents)} documents")
    
    print("Step 2: Normalizing format...")
    normalized = normalizer.normalize_batch(documents)
    print(f"  Normalized {len(normalized)} documents")
    
    print("Step 3: Deduplicating...")
    unique_docs, stats = deduplicator.deduplicate_batch(normalized)
    print(f"  Removed {stats['duplicates']} duplicates")
    print(f"  Unique documents: {len(unique_docs)}")
    
    print("Step 4: Ingesting into RAG...")
    result = rag_service.ingest_documents_batch(unique_docs)
    print(f"  Processed: {result['documents_processed']}")
    print(f"  Total chunks: {result['total_chunks']}")
    
    return result


def main():
    """Run all examples."""
    print("=" * 60)
    print("Data Collection Pipeline Examples")
    print("=" * 60)
    
    try:
        example_get_service_stats()
        
        github_job_id = example_trigger_github_collection()
        
        print("\nWaiting 5 seconds...")
        time.sleep(5)
        
        example_check_job_status(github_job_id)
        
        example_github_webhook()
        
        example_generic_webhook()
        
    except requests.exceptions.ConnectionError:
        print("\nError: Could not connect to data collection service")
        print("Make sure the service is running on http://localhost:8002")
    except Exception as e:
        print(f"\nError: {e}")
    
    print("\n" + "=" * 60)
    print("Examples completed")
    print("=" * 60)


if __name__ == "__main__":
    main()
