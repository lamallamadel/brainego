#!/usr/bin/env python3
"""
GitHub Repository RAG Worker
Ingests GitHub repository contents into RAG system with file-walking logic,
chunking, and path+commit metadata for citation support.
"""

import os
import logging
import httpx
from typing import Dict, Any, Optional, List

from data_collectors.github_collector import GitHubCollector

logger = logging.getLogger(__name__)

RAG_INGEST_BATCH_URL = os.getenv(
    "RAG_INGEST_BATCH_URL",
    "http://localhost:8000/v1/rag/ingest/batch"
)
RAG_INGEST_BATCH_TIMEOUT = int(os.getenv("RAG_INGEST_BATCH_TIMEOUT", "300"))


class GitHubRepoRAGWorker:
    """
    Worker that collects GitHub repository contents and ingests them into RAG.
    Uses GitHubCollector file-walking logic for language detection, binary exclusion,
    and size limits.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        rag_api_url: Optional[str] = None,
        timeout: int = RAG_INGEST_BATCH_TIMEOUT,
    ):
        """
        Initialize GitHub RAG worker.
        
        Args:
            access_token: GitHub personal access token
            rag_api_url: RAG batch ingest endpoint URL
            timeout: HTTP timeout in seconds
        """
        self.collector = GitHubCollector(access_token=access_token)
        self.rag_api_url = (rag_api_url or RAG_INGEST_BATCH_URL).rstrip("/")
        self.timeout = timeout

    def ingest_repository(
        self,
        repo: str,
        workspace_id: str,
        branch: Optional[str] = None,
        incremental: bool = True,
        max_file_size_bytes: int = 200_000,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Collect and ingest GitHub repository contents into RAG system.
        
        Args:
            repo: Repository name in format "owner/repo"
            workspace_id: Workspace identifier for partitioning
            branch: Branch name (defaults to repo default branch)
            incremental: Enable incremental syncing
            max_file_size_bytes: Maximum file size to ingest
            include_patterns: Optional glob patterns to include
            exclude_patterns: Optional glob patterns to exclude
            
        Returns:
            Dict with ingestion results and statistics
        """
        if not workspace_id or not str(workspace_id).strip():
            raise ValueError("workspace_id is required")

        logger.info(
            "Starting GitHub RAG ingestion for repo=%s workspace=%s branch=%s",
            repo,
            workspace_id,
            branch or "(default)",
        )

        # Collect repository documents using GitHubCollector
        collection_result = self.collector.collect_repository_codebase(
            repo_name=repo,
            workspace_id=workspace_id,
            branch=branch,
            incremental=incremental,
            max_file_size_bytes=max_file_size_bytes,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
        )

        documents = collection_result.get("documents", [])
        if not documents:
            logger.info("No documents collected from %s", repo)
            return {
                "status": "success",
                "repo": repo,
                "workspace_id": workspace_id,
                "documents_collected": 0,
                "documents_ingested": 0,
                "chunks_created": 0,
                "collection_result": collection_result,
            }

        # POST to RAG batch ingest endpoint
        logger.info(
            "Ingesting %d documents from %s into RAG system",
            len(documents),
            repo,
        )

        ingest_result = self._post_to_rag_batch_ingest(
            documents=documents,
            workspace_id=workspace_id,
        )

        return {
            "status": "success",
            "repo": repo,
            "workspace_id": workspace_id,
            "documents_collected": len(documents),
            "documents_ingested": ingest_result.get("documents_processed", 0),
            "chunks_created": ingest_result.get("total_chunks", 0),
            "collection_result": collection_result,
            "ingest_result": ingest_result,
        }

    def _post_to_rag_batch_ingest(
        self,
        documents: List[Dict[str, Any]],
        workspace_id: str,
    ) -> Dict[str, Any]:
        """
        POST documents to RAG batch ingest endpoint.
        
        Args:
            documents: List of document dicts with text and metadata
            workspace_id: Workspace identifier
            
        Returns:
            RAG batch ingest response
        """
        url = f"{self.rag_api_url}/v1/rag/ingest/batch"
        
        headers = {
            "Content-Type": "application/json",
            "X-Workspace-Id": workspace_id,
        }

        payload = {"documents": documents}

        try:
            response = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "RAG batch ingest failed with status %d: %s",
                exc.response.status_code,
                exc.response.text,
            )
            raise
        except Exception as exc:
            logger.error("RAG batch ingest request failed: %s", exc)
            raise
