#!/usr/bin/env python3
"""
Ingestion Worker
Background worker that processes documents from the ingestion queue.
"""

import os
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


def _normalize_channel_ids(raw_channel_ids: Any) -> List[str]:
    """Normalize channel IDs from list or comma-separated string."""
    if isinstance(raw_channel_ids, str):
        return [channel.strip() for channel in raw_channel_ids.split(",") if channel.strip()]

    if isinstance(raw_channel_ids, list):
        normalized: List[str] = []
        for channel in raw_channel_ids:
            if channel is None:
                continue
            value = str(channel).strip()
            if value:
                normalized.append(value)
        return normalized

    return []


def process_document(document: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single document through the ingestion pipeline.
    
    This function is executed by RQ workers.
    
    Args:
        document: Document to process
        
    Returns:
        Processing result
    """
    from data_collectors.format_normalizer import FormatNormalizer
    from data_collectors.deduplicator import Deduplicator
    from rag_service import RAGIngestionService
    
    try:
        logger.info(f"Processing document from {document.get('metadata', {}).get('source', 'unknown')}")
        
        normalizer = FormatNormalizer()
        normalized_doc = normalizer.normalize_document(document)
        
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
        
        rag_service = RAGIngestionService(
            qdrant_host=qdrant_host,
            qdrant_port=qdrant_port,
            collection_name="documents"
        )
        
        result = rag_service.ingest_document(
            text=normalized_doc["text"],
            metadata=normalized_doc["metadata"]
        )
        
        logger.info(f"Successfully processed document: {result['document_id']}")
        
        return {
            "status": "success",
            "document_id": result["document_id"],
            "chunks_created": result["chunks_created"],
            "processed_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error processing document: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "processed_at": datetime.utcnow().isoformat()
        }


def collect_and_process(
    source: str,
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Collect data from source and process through pipeline.
    
    This function is executed by RQ workers.
    
    Args:
        source: Data source (github, notion, slack)
        config: Collection configuration
        
    Returns:
        Collection and processing result
    """
    from data_collectors.github_collector import GitHubCollector
    from data_collectors.notion_collector import NotionCollector
    from data_collectors.slack_collector import SlackCollector
    from data_collectors.mcp_streaming_collector import MCPStreamingCollector
    from data_collectors.format_normalizer import FormatNormalizer
    from data_collectors.deduplicator import Deduplicator
    from rag_service import RAGIngestionService
    
    try:
        logger.info(f"Starting collection from {source} with config: {config}")
        
        documents = []
        
        if source == "github":
            collector = GitHubCollector()
            repo_name = config.get("repo_name")
            hours_back = config.get("hours_back", 6)
            
            if repo_name:
                documents = collector.collect_repository_data(
                    repo_name=repo_name,
                    hours_back=hours_back
                )
            else:
                documents = collector.collect_user_activity(hours_back=hours_back)
        
        elif source == "notion":
            collector = NotionCollector()
            hours_back = config.get("hours_back", 4)
            
            database_id = config.get("database_id")
            if database_id:
                documents = collector.collect_database_items(
                    database_id=database_id,
                    hours_back=hours_back
                )
            else:
                documents = collector.collect_recent_pages(hours_back=hours_back)
        
        elif source == "slack":
            collector = SlackCollector()
            channel_ids = _normalize_channel_ids(config.get("channel_ids", []))
            hours_back = config.get("hours_back", 2)

            if channel_ids:
                documents = collector.collect_multiple_channels(
                    channel_ids=channel_ids,
                    hours_back=hours_back
                )
            else:
                logger.warning("No Slack channels specified")

        elif source == "mcp-slack":
            collector = MCPStreamingCollector(config_path=config.get("mcp_config_path"))
            channel_ids = _normalize_channel_ids(config.get("channel_ids", []))
            hours_back = config.get("hours_back", 2)
            query = config.get("query", "decision OR todo OR action item OR urgent")
            count = config.get("count", 50)

            import asyncio

            documents = asyncio.run(
                collector.collect_slack_signals_via_mcp(
                    query=query,
                    hours_back=hours_back,
                    count=count,
                    channel_ids=channel_ids,
                )
            )

        else:
            raise ValueError(f"Unknown source: {source}")
        
        logger.info(f"Collected {len(documents)} documents from {source}")
        
        if not documents:
            return {
                "status": "success",
                "source": source,
                "collected": 0,
                "processed": 0,
                "message": "No new documents found"
            }
        
        normalizer = FormatNormalizer()
        normalized_docs = normalizer.normalize_batch(documents)
        
        deduplicator = Deduplicator(similarity_threshold=0.95)
        unique_docs, dedup_stats = deduplicator.deduplicate_batch(normalized_docs)
        
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
        
        rag_service = RAGIngestionService(
            qdrant_host=qdrant_host,
            qdrant_port=qdrant_port,
            collection_name="documents"
        )
        
        batch_result = rag_service.ingest_documents_batch(unique_docs)
        
        result = {
            "status": "success",
            "source": source,
            "collected": len(documents),
            "duplicates_removed": dedup_stats["duplicates"],
            "processed": len(unique_docs),
            "total_chunks": batch_result["total_chunks"],
            "deduplication_stats": dedup_stats,
            "completed_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"Collection complete: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error in collect_and_process: {e}", exc_info=True)
        return {
            "status": "error",
            "source": source,
            "error": str(e),
            "completed_at": datetime.utcnow().isoformat()
        }
