# Needs: python-package:pytest>=9.0.2

"""Unit tests for github_repo ingestion worker pipeline."""

from __future__ import annotations

import sys
import types

from data_collectors import ingestion_worker


def test_collect_and_process_github_repo_syncs_and_deletes_stale_documents(monkeypatch) -> None:
    fake_collector_module = types.ModuleType("data_collectors.github_collector")

    class FakeCollector:
        calls = []

        @staticmethod
        def build_repository_document_id(repo_name: str, path: str, workspace_id: str) -> str:
            return f"{workspace_id}:{repo_name}:{path}"

        def collect_repository_codebase(self, **kwargs):
            FakeCollector.calls.append(kwargs)
            return {
                "status": "success",
                "repository": "acme/repo",
                "documents": [
                    {
                        "text": "print('main')\n",
                        "metadata": {
                            "source": "github_repo",
                            "repo": "acme/repo",
                            "path": "src/main.py",
                            "commit": "c2",
                            "lang": "python",
                            "workspace": "workspace-alpha",
                            "workspace_id": "workspace-alpha",
                            "document_id": "doc-main",
                        },
                    }
                ],
                "deleted_paths": ["src/legacy.py"],
                "sync": {
                    "mode": "incremental",
                    "previous_commit": "c1",
                    "current_commit": "c2",
                },
            }

    fake_collector_module.GitHubCollector = FakeCollector

    fake_rag_module = types.ModuleType("rag_service")

    class FakeRAGIngestionService:
        instances = []

        def __init__(self, *args, **kwargs):
            self.deleted = []
            self.ingested = []
            FakeRAGIngestionService.instances.append(self)

        def delete_document(self, document_id: str, workspace_id: str = None):
            self.deleted.append((document_id, workspace_id))

        def ingest_documents_batch(self, documents, workspace_id=None):
            self.ingested.append((documents, workspace_id))
            return {
                "status": "success",
                "documents_processed": len(documents),
                "total_chunks": 3,
            }

    fake_rag_module.RAGIngestionService = FakeRAGIngestionService

    monkeypatch.setitem(sys.modules, "data_collectors.github_collector", fake_collector_module)
    monkeypatch.setitem(sys.modules, "rag_service", fake_rag_module)

    result = ingestion_worker.collect_and_process(
        "github_repo",
        {
            "repo_name": "acme/repo",
            "workspace_id": "workspace-alpha",
        },
    )

    assert result["status"] == "success"
    assert result["source"] == "github_repo"
    assert result["processed"] == 1
    assert result["deleted_paths"] == 1
    assert result["deleted_documents"] == 2
    assert result["sync"]["mode"] == "incremental"

    assert FakeCollector.calls
    assert FakeCollector.calls[0]["incremental"] is True
    assert FakeCollector.calls[0]["reindex"] is False

    rag_instance = FakeRAGIngestionService.instances[0]
    assert ("doc-main", "workspace-alpha") in rag_instance.deleted
    assert ("workspace-alpha:acme/repo:src/legacy.py", "workspace-alpha") in rag_instance.deleted
    assert rag_instance.ingested[0][1] == "workspace-alpha"


def test_collect_and_process_github_repo_requires_repo_name() -> None:
    result = ingestion_worker.collect_and_process(
        "github_repo",
        {"workspace_id": "workspace-alpha"},
    )

    assert result["status"] == "error"
    assert "repo_name is required" in result["error"]
