"""Unit tests for MCP Notion ingestion flow."""

import asyncio
import sys
from pathlib import Path

# Make repository root importable.
sys.path.append(str(Path(__file__).resolve().parents[2]))


from data_collectors.notion_mcp_ingestion import NotionMCPIngestionJob


class StubMCPClient:
    def __init__(self):
        self.calls = []

    async def call_tool(self, server_id, tool_name, arguments):
        self.calls.append((server_id, tool_name, arguments))
        if tool_name == "notion_search":
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            '{"results": [{"object": "page", "id": "page-1", "url": "https://notion.so/page-1", '
                            '"created_time": "2026-01-01T00:00:00Z", "last_edited_time": "2026-01-02T00:00:00Z", '
                            '"parent": {"type": "workspace", "workspace": true, "space_name": "Docs brainego"}, "properties": {"Name": {"type": "title", "title": [{"plain_text": "Brainego invariants"}]}, '
                            '"Tags": {"type": "multi_select", "multi_select": [{"name": "architecture"}, {"name": "invariants"}]}, '
                            '"Project": {"type": "rich_text", "rich_text": [{"plain_text": "brainego"}]}, '
                            '"Summary": {"type": "rich_text", "rich_text": [{"plain_text": "Invariants define non-negotiable architecture constraints in brainego."}]}}}]}'
                        ),
                    }
                ]
            }
        if tool_name == "notion_query_database":
            return {"results": []}
        raise AssertionError(f"Unexpected tool call: {tool_name}")


class StubRAGService:
    def __init__(self):
        self.ingested = []

    def ingest_documents_batch(self, documents):
        self.ingested = documents
        return {"status": "success", "documents_processed": len(documents), "total_chunks": len(documents)}

    def search_documents(self, query, limit, filters):
        return [
            {
                "text": "Brainego invariants include offline dependency and test environment contracts.",
                "metadata": {"title": "Brainego invariants"},
            }
        ]


def test_run_ingests_docs_brainego_space_with_metadata():
    mcp_client = StubMCPClient()
    rag_service = StubRAGService()
    job = NotionMCPIngestionJob(mcp_client=mcp_client, rag_ingestion_service=rag_service)

    result = asyncio.run(job.run(notion_space="Docs brainego", project="brainego"))

    assert result["status"] == "success"
    assert result["documents_collected"] == 1
    doc = rag_service.ingested[0]
    assert doc["metadata"]["title"] == "Brainego invariants"
    assert doc["metadata"]["tags"] == ["architecture", "invariants"]
    assert doc["metadata"]["project"] == "brainego"
    assert doc["metadata"]["notion_space"] == "Docs brainego"


def test_verify_example_query_for_invariants_returns_verified_true():
    job = NotionMCPIngestionJob(mcp_client=StubMCPClient(), rag_ingestion_service=StubRAGService())

    verification = asyncio.run(job.verify_example_query())

    assert verification["query"] == "what are brainego invariants?"
    assert verification["verified"] is True
    assert verification["matches_found"] >= 1
