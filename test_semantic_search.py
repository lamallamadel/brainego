#!/usr/bin/env python3
"""Unit tests for semantic search support over Qdrant collections."""

import sys
import types


# Minimal stubs so rag_service imports without heavyweight dependencies.
httpx_stub = types.ModuleType("httpx")
httpx_stub.get = lambda *args, **kwargs: None
httpx_stub.post = lambda *args, **kwargs: None
sys.modules.setdefault("httpx", httpx_stub)

sentence_transformers_stub = types.ModuleType("sentence_transformers")
sentence_transformers_stub.SentenceTransformer = object
sys.modules.setdefault("sentence_transformers", sentence_transformers_stub)

qdrant_client_stub = types.ModuleType("qdrant_client")
qdrant_client_stub.QdrantClient = object
sys.modules.setdefault("qdrant_client", qdrant_client_stub)

models_stub = types.ModuleType("qdrant_client.models")


class Filter:
    def __init__(self, must):
        self.must = must


class FieldCondition:
    def __init__(self, key, match):
        self.key = key
        self.match = match


class MatchValue:
    def __init__(self, value):
        self.value = value


class MatchAny:
    def __init__(self, any):
        self.any = any


class _Simple:
    def __init__(self, *args, **kwargs):
        pass


models_stub.Distance = _Simple
models_stub.VectorParams = _Simple
models_stub.PointStruct = _Simple
models_stub.Filter = Filter
models_stub.FieldCondition = FieldCondition
models_stub.MatchValue = MatchValue
models_stub.MatchAny = MatchAny
sys.modules.setdefault("qdrant_client.models", models_stub)

from rag_service import QdrantStorage, RAGIngestionService


class DummyClient:
    def __init__(self):
        self.last_kwargs = None

    def search(self, **kwargs):
        self.last_kwargs = kwargs

        class Result:
            def __init__(self):
                self.id = "p1"
                self.score = 0.91
                self.payload = {
                    "text": "hello world",
                    "metadata": {"project": "alpha", "source": "github"},
                    "ingested_at": "2026-01-01T00:00:00",
                }

        return [Result()]


def test_qdrant_storage_search_with_any_filter_and_collection_override():
    storage = QdrantStorage.__new__(QdrantStorage)
    storage.client = DummyClient()
    storage.collection_name = "default-docs"

    results = storage.search(
        query_vector=[0.1, 0.2],
        limit=3,
        filter_conditions={"project": "alpha", "source": {"any": ["github", "notion"]}},
        collection_name="project-docs",
    )

    assert len(results) == 1
    assert results[0]["id"] == "p1"

    kwargs = storage.client.last_kwargs
    assert kwargs["collection_name"] == "project-docs"
    assert kwargs["limit"] == 3
    assert kwargs["query_filter"] is not None
    assert len(kwargs["query_filter"].must) == 2


def test_semantic_search_delegates_to_search_documents_with_top_k():
    service = RAGIngestionService.__new__(RAGIngestionService)
    captured = {}

    def fake_search_documents(query, limit, filters=None, collection_name=None):
        captured["query"] = query
        captured["limit"] = limit
        captured["filters"] = filters
        captured["collection_name"] = collection_name
        return [{"id": "x"}]

    service.search_documents = fake_search_documents

    results = service.semantic_search(
        query="Find architecture docs",
        top_k=4,
        filters={"project": "alpha"},
        collection_name="project-docs",
    )

    assert results == [{"id": "x"}]
    assert captured == {
        "query": "Find architecture docs",
        "limit": 4,
        "filters": {"project": "alpha"},
        "collection_name": "project-docs",
    }
