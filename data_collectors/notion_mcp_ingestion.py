#!/usr/bin/env python3
"""MCP-based Notion ingestion flow for RAG."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NotionMCPIngestionJob:
    """Ingest Notion pages/databases via MCP and store as RAG documents."""

    def __init__(
        self,
        mcp_client: Any,
        rag_ingestion_service: Any,
        notion_server_id: str = "mcp-notion",
    ):
        self.mcp_client = mcp_client
        self.rag_ingestion_service = rag_ingestion_service
        self.notion_server_id = notion_server_id

    async def run(
        self,
        notion_space: str = "Docs brainego",
        project: str = "brainego",
        query: str = "",
        database_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run Notion MCP ingestion and push documents to RAG."""
        pages = await self._collect_pages(notion_space=notion_space, query=query)
        database_items = await self._collect_database_items(database_ids or [])

        raw_documents = pages + database_items
        documents = [
            self._to_rag_document(item=item, default_project=project, notion_space=notion_space)
            for item in raw_documents
        ]

        batch_result = self.rag_ingestion_service.ingest_documents_batch(documents)
        return {
            "status": "success",
            "source": "notion-mcp",
            "notion_space": notion_space,
            "documents_collected": len(documents),
            "documents": documents,
            "ingestion_result": batch_result,
            "completed_at": datetime.utcnow().isoformat(),
        }

    async def verify_example_query(
        self,
        query: str = "what are brainego invariants?",
        project: str = "brainego",
        min_matches: int = 1,
    ) -> Dict[str, Any]:
        """Verify the example query retrieves Notion knowledge base documents."""
        results = self.rag_ingestion_service.search_documents(
            query=query,
            limit=5,
            filters={"source": "notion", "project": project},
        )
        matched = [
            result
            for result in results
            if "invariant" in (result.get("text") or "").lower()
            or "invariant" in (result.get("metadata", {}).get("title", "").lower())
        ]
        return {
            "query": query,
            "project": project,
            "results_found": len(results),
            "matches_found": len(matched),
            "verified": len(matched) >= min_matches,
            "results": results,
        }

    async def _collect_pages(self, notion_space: str, query: str) -> List[Dict[str, Any]]:
        args = {
            "query": query,
            "filter": {"property": "object", "value": "page"},
        }
        response = await self.mcp_client.call_tool(self.notion_server_id, "notion_search", args)
        payload = self._extract_payload(response)
        return [item for item in payload.get("results", []) if self._belongs_to_space(item, notion_space)]

    async def _collect_database_items(self, database_ids: List[str]) -> List[Dict[str, Any]]:
        if not database_ids:
            return []

        items: List[Dict[str, Any]] = []
        for database_id in database_ids:
            response = await self.mcp_client.call_tool(
                self.notion_server_id,
                "notion_query_database",
                {"database_id": database_id},
            )
            payload = self._extract_payload(response)
            items.extend(payload.get("results", []))
        return items

    def _belongs_to_space(self, item: Dict[str, Any], notion_space: str) -> bool:
        text = json.dumps(item).lower()
        return notion_space.lower() in text

    def _to_rag_document(
        self,
        item: Dict[str, Any],
        default_project: str,
        notion_space: str,
    ) -> Dict[str, Any]:
        title = self._extract_title(item)
        tags = self._extract_tags(item)
        project = self._extract_project(item, default_project)
        body_text = self._extract_plain_text(item)

        text = f"# {title}\n\n{body_text}" if body_text else f"# {title}"
        return {
            "text": text,
            "metadata": {
                "source": "notion",
                "source_type": item.get("object", "page"),
                "title": title,
                "tags": tags,
                "project": project,
                "notion_space": notion_space,
                "page_id": item.get("id", ""),
                "url": item.get("url", ""),
                "updated_at": item.get("last_edited_time", ""),
                "created_at": item.get("created_time", ""),
                "original_metadata": item,
            },
        }

    def _extract_payload(self, response: Dict[str, Any]) -> Dict[str, Any]:
        if "results" in response:
            return response

        for block in response.get("content", []):
            text = block.get("text")
            if not text:
                continue
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

        return {"results": []}

    def _extract_title(self, item: Dict[str, Any]) -> str:
        properties = item.get("properties", {})
        for field in properties.values():
            if field.get("type") == "title":
                parts = field.get("title", [])
                title = "".join(part.get("plain_text", "") for part in parts).strip()
                if title:
                    return title

        if item.get("title"):
            parts = item.get("title")
            if isinstance(parts, list):
                title = "".join(part.get("plain_text", "") for part in parts).strip()
                if title:
                    return title

        return "Untitled"

    def _extract_tags(self, item: Dict[str, Any]) -> List[str]:
        tags: List[str] = []
        for field in item.get("properties", {}).values():
            if field.get("type") == "multi_select":
                tags.extend([entry.get("name", "") for entry in field.get("multi_select", []) if entry.get("name")])
            if field.get("type") == "select" and field.get("select", {}).get("name"):
                tags.append(field["select"]["name"])
        return sorted(set(tags))

    def _extract_project(self, item: Dict[str, Any], default_project: str) -> str:
        for field in item.get("properties", {}).values():
            field_type = field.get("type")
            if field_type == "rich_text":
                text = "".join(part.get("plain_text", "") for part in field.get("rich_text", [])).strip()
                if text and "project" in json.dumps(field).lower():
                    return text
            if field_type == "select":
                name = field.get("select", {}).get("name", "")
                if name and "project" in json.dumps(field).lower():
                    return name
        return default_project

    def _extract_plain_text(self, item: Dict[str, Any]) -> str:
        parts: List[str] = []
        if item.get("properties"):
            for field_name, field in item["properties"].items():
                field_type = field.get("type")
                if field_type == "rich_text":
                    text = "".join(part.get("plain_text", "") for part in field.get("rich_text", [])).strip()
                    if text:
                        parts.append(f"{field_name}: {text}")
                elif field_type == "title":
                    continue
                elif field_type == "multi_select":
                    values = [entry.get("name", "") for entry in field.get("multi_select", []) if entry.get("name")]
                    if values:
                        parts.append(f"{field_name}: {', '.join(values)}")

        return "\n".join(parts).strip()


def run_notion_mcp_ingestion_job(
    mcp_client: Any,
    rag_ingestion_service: Any,
    notion_space: str = "Docs brainego",
    project: str = "brainego",
    query: str = "",
    database_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Synchronous wrapper to execute the Notion MCP ingestion job."""
    job = NotionMCPIngestionJob(mcp_client=mcp_client, rag_ingestion_service=rag_ingestion_service)
    return asyncio.run(
        job.run(
            notion_space=notion_space,
            project=project,
            query=query,
            database_ids=database_ids,
        )
    )
