"""Unit tests for Qdrant filter construction in RAG storage."""

import sys
import types
from pathlib import Path

import pytest

# Make repository root importable.
sys.path.append(str(Path(__file__).resolve().parents[2]))

# Stub optional heavy dependencies so importing rag_service stays offline/lightweight.
sentence_transformers_stub = types.ModuleType("sentence_transformers")


class _SentenceTransformerStub:
    def __init__(self, *args, **kwargs):
        pass

    def get_sentence_embedding_dimension(self):
        return 768


sentence_transformers_stub.SentenceTransformer = _SentenceTransformerStub
sys.modules.setdefault("sentence_transformers", sentence_transformers_stub)

qdrant_client_stub = types.ModuleType("qdrant_client")
qdrant_models_stub = types.ModuleType("qdrant_client.models")


class Filter:
    def __init__(self, must=None, should=None, must_not=None):
        self.must = must or []
        self.should = should or []
        self.must_not = must_not or []


class FieldCondition:
    def __init__(self, key, match=None):
        self.key = key
        self.match = match


class MatchValue:
    def __init__(self, value):
        self.value = value


class MatchAny:
    def __init__(self, any):
        self.any = any


class Distance:
    COSINE = "cosine"


class VectorParams:
    def __init__(self, size, distance):
        self.size = size
        self.distance = distance


class PointStruct:
    def __init__(self, id, vector, payload):
        self.id = id
        self.vector = vector
        self.payload = payload


class QdrantClient:
    def __init__(self, *args, **kwargs):
        pass


qdrant_models_stub.Filter = Filter
qdrant_models_stub.FieldCondition = FieldCondition
qdrant_models_stub.MatchValue = MatchValue
qdrant_models_stub.MatchAny = MatchAny
qdrant_models_stub.Distance = Distance
qdrant_models_stub.VectorParams = VectorParams
qdrant_models_stub.PointStruct = PointStruct

qdrant_client_stub.QdrantClient = QdrantClient

sys.modules.setdefault("qdrant_client", qdrant_client_stub)
sys.modules.setdefault("qdrant_client.models", qdrant_models_stub)

from rag_service import QdrantStorage


class DummyClient:
    """Simple test double for Qdrant client search call."""

    def __init__(self):
        self.last_kwargs = None

    def search(self, **kwargs):
        self.last_kwargs = kwargs
        return []


def test_search_builds_metadata_filter_keys():
    """Ensure workspace and metadata filters are translated to Qdrant conditions."""
    storage = QdrantStorage.__new__(QdrantStorage)
    storage.client = DummyClient()
    storage.collection_name = "documents"

    storage.search(
        query_vector=[0.1, 0.2, 0.3],
        workspace_id="workspace-acme",
        limit=3,
        filter_conditions={"source": "user_upload", "tenant": "acme"},
    )

    query_filter = storage.client.last_kwargs["query_filter"]
    must_conditions = query_filter.must

    keys = sorted(condition.key for condition in must_conditions)
    values = sorted(condition.match.value for condition in must_conditions)

    assert keys == ["metadata.source", "metadata.tenant", "workspace_id"]
    assert values == ["acme", "user_upload", "workspace-acme"]


def test_search_without_filters_still_applies_workspace_filter():
    """Ensure query_filter always contains workspace isolation condition."""
    storage = QdrantStorage.__new__(QdrantStorage)
    storage.client = DummyClient()
    storage.collection_name = "documents"

    storage.search(
        query_vector=[0.1, 0.2, 0.3],
        workspace_id="workspace-alpha",
        limit=2,
        filter_conditions=None,
    )

    query_filter = storage.client.last_kwargs["query_filter"]
    assert query_filter is not None
    assert len(query_filter.must) == 1
    assert query_filter.must[0].key == "workspace_id"
    assert query_filter.must[0].match.value == "workspace-alpha"


def test_search_rejects_conflicting_workspace_filter():
    """Ensure conflicting workspace IDs cannot bypass isolation."""
    storage = QdrantStorage.__new__(QdrantStorage)
    storage.client = DummyClient()
    storage.collection_name = "documents"

    with pytest.raises(ValueError, match="workspace_id filter must match"):
        storage.search(
            query_vector=[0.1, 0.2, 0.3],
            workspace_id="workspace-alpha",
            limit=2,
            filter_conditions={"workspace_id": "workspace-beta"},
        )


def test_search_builds_repo_path_lang_filters():
    """Ensure repo/path/lang retrieval filters map to metadata payload keys."""
    storage = QdrantStorage.__new__(QdrantStorage)
    storage.client = DummyClient()
    storage.collection_name = "documents"

    storage.search(
        query_vector=[0.1, 0.2, 0.3],
        workspace_id="workspace-alpha",
        limit=4,
        filter_conditions={
            "repo": "acme/repo",
            "path": {"any": ["src/api.py", "src/rag.py"]},
            "lang": "python",
        },
    )

    query_filter = storage.client.last_kwargs["query_filter"]
    condition_by_key = {condition.key: condition for condition in query_filter.must}

    assert condition_by_key["workspace_id"].match.value == "workspace-alpha"
    assert condition_by_key["metadata.repo"].match.value == "acme/repo"
    assert condition_by_key["metadata.path"].match.any == ["src/api.py", "src/rag.py"]
    assert condition_by_key["metadata.lang"].match.value == "python"
