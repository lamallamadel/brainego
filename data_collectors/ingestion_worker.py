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
    try:
        logger.info(f"Starting collection from {source} with config: {config}")
        
        documents = []
        
        if source == "github":
            github_enabled = str(
                os.getenv("ENABLE_GITHUB_INGESTION", "true")
            ).strip().lower() in {"1", "true", "yes", "on"}

            if not github_enabled:
                logger.info("GitHub ingestion is disabled by ENABLE_GITHUB_INGESTION")
                return {
                    "status": "skipped",
                    "source": source,
                    "collected": 0,
                    "processed": 0,
                    "message": "GitHub ingestion is disabled"
                }

            from data_collectors.github_collector import GitHubCollector

            collector = GitHubCollector()
            repo_name = config.get("repo_name")
            hours_back = config.get("hours_back", 6)
            include_issues = config.get("include_issues", True)
            include_prs = config.get("include_prs", True)
            include_commits = config.get("include_commits", True)
            include_discussions = config.get("include_discussions", False)

            if repo_name:
                documents = collector.collect_repository_data(
                    repo_name=repo_name,
                    hours_back=hours_back,
                    include_issues=include_issues,
                    include_prs=include_prs,
                    include_commits=include_commits,
                    include_discussions=include_discussions,
                )
            else:
                documents = collector.collect_user_activity(hours_back=hours_back)
        
        elif source == "notion":
            from data_collectors.notion_collector import NotionCollector

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

        elif source == "notion_mcp":
            from data_collectors.notion_mcp_ingestion import NotionMCPIngestionJob
            from mcp_client import MCPClientService
            import yaml

            mcp_config_path = os.getenv("MCP_SERVERS_CONFIG", "configs/mcp-servers.yaml")
            notion_space = config.get("notion_space", "Docs brainego")
            project = config.get("project", "brainego")
            query = config.get("query", "")
            database_ids = config.get("database_ids", [])

            with open(mcp_config_path, "r", encoding="utf-8") as stream:
                mcp_config = yaml.safe_load(stream)

            mcp_service = MCPClientService(mcp_config.get("servers", {}))
            awaitable_initialize = getattr(mcp_service, "initialize")
            if callable(awaitable_initialize):
                import asyncio
                asyncio.run(awaitable_initialize())

            rag_service = RAGIngestionService(
                qdrant_host=os.getenv("QDRANT_HOST", "localhost"),
                qdrant_port=int(os.getenv("QDRANT_PORT", "6333")),
                collection_name="documents"
            )
            job = NotionMCPIngestionJob(mcp_service, rag_service)
            import asyncio
            job_result = asyncio.run(
                job.run(
                    notion_space=notion_space,
                    project=project,
                    query=query,
                    database_ids=database_ids,
                )
            )
            return job_result
        
        elif source == "slack":
            from data_collectors.slack_collector import SlackCollector

            collector = SlackCollector()
            channel_ids = config.get("channel_ids", [])
            hours_back = config.get("hours_back", 2)
            
            if channel_ids:
                documents = collector.collect_multiple_channels(
                    channel_ids=channel_ids,
                    hours_back=hours_back
                )
            else:
                logger.warning("No Slack channels specified")
        
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

        from data_collectors.format_normalizer import FormatNormalizer
        from data_collectors.deduplicator import Deduplicator
        from rag_service import RAGIngestionService

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
