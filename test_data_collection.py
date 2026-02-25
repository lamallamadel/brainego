#!/usr/bin/env python3
"""
Test Data Collection Pipeline
"""

import os
import time
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_github_collector():
    """Test GitHub data collection."""
    logger.info("Testing GitHub collector...")
    
    from data_collectors.github_collector import GitHubCollector
    
    try:
        collector = GitHubCollector()
        
        repo_name = os.getenv("GITHUB_DEFAULT_REPO", "octocat/Hello-World")
        documents = collector.collect_repository_data(
            repo_name=repo_name,
            hours_back=168,
            include_issues=True,
            include_prs=True,
            include_commits=False
        )
        
        logger.info(f"✓ Collected {len(documents)} documents from GitHub")
        
        if documents:
            logger.info(f"  Sample: {documents[0]['metadata']['type']} - {documents[0]['metadata'].get('title', 'N/A')}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ GitHub collector test failed: {e}")
        return False


def test_notion_collector():
    """Test Notion data collection."""
    logger.info("Testing Notion collector...")
    
    from data_collectors.notion_collector import NotionCollector
    
    try:
        collector = NotionCollector()
        
        documents = collector.collect_recent_pages(hours_back=168)
        
        logger.info(f"✓ Collected {len(documents)} documents from Notion")
        
        if documents:
            logger.info(f"  Sample: {documents[0]['metadata']['title']}")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Notion collector test failed: {e}")
        return False


def test_slack_collector():
    """Test Slack data collection."""
    logger.info("Testing Slack collector...")
    
    from data_collectors.slack_collector import SlackCollector
    
    try:
        collector = SlackCollector()
        
        channel_ids = os.getenv("SLACK_CHANNELS", "").split(",")
        
        if not channel_ids or not channel_ids[0]:
            logger.warning("  No Slack channels configured, skipping")
            return True
        
        documents = collector.collect_multiple_channels(
            channel_ids=channel_ids[:1],
            hours_back=24
        )
        
        logger.info(f"✓ Collected {len(documents)} documents from Slack")
        
        if documents:
            logger.info(f"  Sample: {documents[0]['text'][:50]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Slack collector test failed: {e}")
        return False


def test_format_normalizer():
    """Test format normalization."""
    logger.info("Testing format normalizer...")
    
    from data_collectors.format_normalizer import FormatNormalizer
    
    try:
        normalizer = FormatNormalizer()
        
        test_docs = [
            {
                "text": "Test issue",
                "metadata": {
                    "source": "github",
                    "type": "issue",
                    "issue_number": 1,
                    "author": "test_user"
                }
            },
            {
                "text": "Test page",
                "metadata": {
                    "source": "notion",
                    "type": "page",
                    "title": "Test Page",
                    "page_id": "123"
                }
            }
        ]
        
        normalized = normalizer.normalize_batch(test_docs)
        
        assert len(normalized) == 2
        assert normalized[0]["metadata"]["source"] == "github"
        assert normalized[1]["metadata"]["source"] == "notion"
        
        logger.info("✓ Format normalizer test passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ Format normalizer test failed: {e}")
        return False


def test_deduplicator():
    """Test deduplication."""
    logger.info("Testing deduplicator...")
    
    from data_collectors.deduplicator import Deduplicator
    
    try:
        deduplicator = Deduplicator(similarity_threshold=0.95)
        
        test_docs = [
            {"text": "This is a test document about machine learning."},
            {"text": "This is a test document about machine learning."},
            {"text": "This is a test document about machine learning and AI."},
            {"text": "Completely different content about cooking recipes."}
        ]
        
        unique_docs, stats = deduplicator.deduplicate_batch(test_docs)
        
        assert stats["duplicates"] >= 1
        assert len(unique_docs) < len(test_docs)
        
        logger.info(f"✓ Deduplicator test passed - removed {stats['duplicates']} duplicates")
        return True
        
    except Exception as e:
        logger.error(f"✗ Deduplicator test failed: {e}")
        return False


def test_ingestion_queue():
    """Test ingestion queue."""
    logger.info("Testing ingestion queue...")
    
    from data_collectors.ingestion_queue import IngestionQueue
    
    try:
        queue = IngestionQueue(
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379"))
        )
        
        test_docs = [
            {
                "text": "Test document for queue",
                "metadata": {
                    "source": "test",
                    "type": "test_doc"
                }
            }
        ]
        
        job_ids = queue.enqueue_documents(test_docs)
        
        assert len(job_ids) == 1
        
        time.sleep(1)
        
        job_status = queue.get_job_status(job_ids[0])
        logger.info(f"  Job status: {job_status['status']}")
        
        stats = queue.get_queue_stats()
        logger.info(f"  Queue stats: {stats}")
        
        logger.info("✓ Ingestion queue test passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ Ingestion queue test failed: {e}")
        return False


def test_end_to_end_pipeline():
    """Test complete end-to-end pipeline."""
    logger.info("Testing end-to-end pipeline...")
    
    from data_collectors.github_collector import GitHubCollector
    from data_collectors.format_normalizer import FormatNormalizer
    from data_collectors.deduplicator import Deduplicator
    from data_collectors.ingestion_queue import IngestionQueue
    
    try:
        collector = GitHubCollector()
        normalizer = FormatNormalizer()
        deduplicator = Deduplicator(similarity_threshold=0.95)
        queue = IngestionQueue()
        
        repo_name = os.getenv("GITHUB_DEFAULT_REPO", "octocat/Hello-World")
        raw_docs = collector.collect_repository_data(
            repo_name=repo_name,
            hours_back=168,
            include_commits=False
        )
        
        logger.info(f"  Step 1: Collected {len(raw_docs)} raw documents")
        
        normalized_docs = normalizer.normalize_batch(raw_docs)
        logger.info(f"  Step 2: Normalized {len(normalized_docs)} documents")
        
        unique_docs, dedup_stats = deduplicator.deduplicate_batch(normalized_docs)
        logger.info(f"  Step 3: Deduplicated to {len(unique_docs)} unique documents (removed {dedup_stats['duplicates']})")
        
        if unique_docs:
            job_ids = queue.enqueue_documents(unique_docs[:5])
            logger.info(f"  Step 4: Enqueued {len(job_ids)} documents for ingestion")
        
        logger.info("✓ End-to-end pipeline test passed")
        return True
        
    except Exception as e:
        logger.error(f"✗ End-to-end pipeline test failed: {e}")
        return False


def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("Data Collection Pipeline Tests")
    logger.info("=" * 60)
    
    results = {
        "GitHub Collector": test_github_collector(),
        "Format Normalizer": test_format_normalizer(),
        "Deduplicator": test_deduplicator(),
        "Ingestion Queue": test_ingestion_queue(),
        "End-to-End Pipeline": test_end_to_end_pipeline()
    }
    
    optional_tests = {
        "Notion Collector": test_notion_collector(),
        "Slack Collector": test_slack_collector()
    }
    
    logger.info("=" * 60)
    logger.info("Test Results:")
    logger.info("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results.items():
        status = "✓ PASSED" if result else "✗ FAILED"
        logger.info(f"{test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    logger.info("\nOptional Tests:")
    for test_name, result in optional_tests.items():
        status = "✓ PASSED" if result else "⚠ SKIPPED/FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info("=" * 60)
    logger.info(f"Total: {passed} passed, {failed} failed")
    logger.info("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
