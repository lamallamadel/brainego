#!/usr/bin/env python3
"""
Format Normalization Service
Normalizes data from different sources into a unified format.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class FormatNormalizer:
    """Normalizes documents from various sources into a unified format."""
    
    def __init__(self):
        """Initialize the format normalizer."""
        logger.info("Initialized FormatNormalizer")
    
    def normalize_document(
        self,
        document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Normalize a document to unified format.
        
        Args:
            document: Raw document from collector
            
        Returns:
            Normalized document with standard fields
        """
        source = document.get("metadata", {}).get("source", "unknown")
        
        if source == "github":
            return self._normalize_github(document)
        elif source == "notion":
            return self._normalize_notion(document)
        elif source == "slack":
            return self._normalize_slack(document)
        else:
            return self._normalize_generic(document)
    
    def normalize_batch(
        self,
        documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Normalize a batch of documents.
        
        Args:
            documents: List of raw documents
            
        Returns:
            List of normalized documents
        """
        normalized = []
        
        for doc in documents:
            try:
                normalized_doc = self.normalize_document(doc)
                normalized.append(normalized_doc)
            except Exception as e:
                logger.error(f"Error normalizing document: {e}")
                normalized.append(self._normalize_generic(doc))
        
        return normalized
    
    def _normalize_github(
        self,
        document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Normalize GitHub document."""
        metadata = document.get("metadata", {})
        doc_type = metadata.get("type", "unknown")
        
        normalized = {
            "text": document.get("text", ""),
            "metadata": {
                "source": "github",
                "source_type": doc_type,
                "title": self._extract_github_title(document, doc_type),
                "url": self._extract_github_url(metadata, doc_type),
                "author": metadata.get("author", "unknown"),
                "created_at": metadata.get("created_at", datetime.utcnow().isoformat()),
                "updated_at": metadata.get("updated_at", datetime.utcnow().isoformat()),
                "collected_at": metadata.get("collected_at", datetime.utcnow().isoformat()),
                "repository": metadata.get("repository", ""),
                "labels": metadata.get("labels", []),
                "original_metadata": metadata
            }
        }
        
        return normalized
    
    def _normalize_notion(
        self,
        document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Normalize Notion document."""
        metadata = document.get("metadata", {})
        
        normalized = {
            "text": document.get("text", ""),
            "metadata": {
                "source": "notion",
                "source_type": metadata.get("type", "page"),
                "title": metadata.get("title", "Untitled"),
                "url": metadata.get("page_url", ""),
                "author": "notion_user",
                "created_at": metadata.get("created_time", datetime.utcnow().isoformat()),
                "updated_at": metadata.get("last_edited_time", datetime.utcnow().isoformat()),
                "collected_at": metadata.get("collected_at", datetime.utcnow().isoformat()),
                "page_id": metadata.get("page_id", ""),
                "database_id": metadata.get("database_id", ""),
                "original_metadata": metadata
            }
        }
        
        return normalized
    
    def _normalize_slack(
        self,
        document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Normalize Slack document."""
        metadata = document.get("metadata", {})
        text = document.get("text", "")
        
        title = text[:50] + "..." if len(text) > 50 else text
        
        normalized = {
            "text": text,
            "metadata": {
                "source": "slack",
                "source_type": metadata.get("type", "message"),
                "title": title,
                "url": f"slack://channel?team=&id={metadata.get('channel_id', '')}",
                "author": metadata.get("user_id", "unknown"),
                "created_at": metadata.get("created_at", datetime.utcnow().isoformat()),
                "updated_at": metadata.get("created_at", datetime.utcnow().isoformat()),
                "collected_at": metadata.get("collected_at", datetime.utcnow().isoformat()),
                "channel_id": metadata.get("channel_id", ""),
                "channel_name": metadata.get("channel_name", ""),
                "thread_ts": metadata.get("thread_ts", ""),
                "has_thread": metadata.get("has_thread", False),
                "original_metadata": metadata
            }
        }
        
        return normalized
    
    def _normalize_generic(
        self,
        document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Normalize generic document."""
        metadata = document.get("metadata", {})
        text = document.get("text", "")
        
        normalized = {
            "text": text,
            "metadata": {
                "source": metadata.get("source", "unknown"),
                "source_type": metadata.get("type", "unknown"),
                "title": metadata.get("title", text[:50] + "..." if len(text) > 50 else text),
                "url": metadata.get("url", ""),
                "author": metadata.get("author", "unknown"),
                "created_at": metadata.get("created_at", datetime.utcnow().isoformat()),
                "updated_at": metadata.get("updated_at", datetime.utcnow().isoformat()),
                "collected_at": metadata.get("collected_at", datetime.utcnow().isoformat()),
                "original_metadata": metadata
            }
        }
        
        return normalized
    
    def _extract_github_title(
        self,
        document: Dict[str, Any],
        doc_type: str
    ) -> str:
        """Extract title from GitHub document."""
        text = document.get("text", "")
        lines = text.split("\n")
        
        if lines and lines[0].startswith("# "):
            return lines[0][2:].strip()
        
        metadata = document.get("metadata", {})
        
        if doc_type == "issue":
            return f"Issue #{metadata.get('issue_number', 'unknown')}"
        elif doc_type == "pull_request":
            return f"PR #{metadata.get('pr_number', 'unknown')}"
        elif doc_type == "commit":
            sha = metadata.get("commit_sha", "unknown")[:7]
            return f"Commit {sha}"
        
        return "GitHub Document"
    
    def _extract_github_url(
        self,
        metadata: Dict[str, Any],
        doc_type: str
    ) -> str:
        """Extract URL from GitHub metadata."""
        if doc_type == "issue":
            return metadata.get("issue_url", "")
        elif doc_type == "pull_request":
            return metadata.get("pr_url", "")
        elif doc_type == "commit":
            return metadata.get("commit_url", "")
        
        return ""
