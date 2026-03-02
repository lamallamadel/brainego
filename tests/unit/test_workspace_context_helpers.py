# Needs: python-package:pytest>=9.0.2

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from workspace_context import (
    build_rag_retrieval_filters,
    ensure_workspace_filter,
    ensure_workspace_metadata,
    get_valid_workspace_ids,
    resolve_workspace_id,
)


def _make_request(headers: dict[str, str] | None = None, query: dict[str, str] | None = None):
    return SimpleNamespace(headers=headers or {}, query_params=query or {})


def test_resolve_workspace_id_prefers_header_over_query() -> None:
    request = _make_request(
        headers={"x-workspace-id": "team-a"},
        query={"workspace_id": "team-b"},
    )
    assert resolve_workspace_id(request) == "team-a"


def test_resolve_workspace_id_falls_back_to_query_param() -> None:
    request = _make_request(query={"workspace_id": "team-a"})
    assert resolve_workspace_id(request) == "team-a"


def test_get_valid_workspace_ids_reads_env_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSPACE_IDS", "alpha,beta,gamma")
    get_valid_workspace_ids.cache_clear()
    assert get_valid_workspace_ids() == {"alpha", "beta", "gamma"}
    get_valid_workspace_ids.cache_clear()


def test_ensure_workspace_filter_injects_workspace_id() -> None:
    merged = ensure_workspace_filter({"project": "brainego"}, "workspace-123")
    assert merged["project"] == "brainego"
    assert merged["workspace_id"] == "workspace-123"


def test_ensure_workspace_filter_rejects_mismatched_workspace() -> None:
    with pytest.raises(HTTPException) as exc_info:
        ensure_workspace_filter({"workspace_id": "other-workspace"}, "workspace-123")

    assert exc_info.value.status_code == 400
    assert "workspace_id filter does not match" in str(exc_info.value.detail)


def test_build_rag_retrieval_filters_merges_repo_path_lang_and_workspace() -> None:
    merged = build_rag_retrieval_filters(
        filters={"project": "brainego"},
        workspace_id="workspace-123",
        repo="acme/repo",
        path=["src/api.py", "src/rag.py"],
        lang="python",
    )
    assert merged["project"] == "brainego"
    assert merged["repo"] == "acme/repo"
    assert merged["path"] == {"any": ["src/api.py", "src/rag.py"]}
    assert merged["lang"] == "python"
    assert merged["workspace_id"] == "workspace-123"


def test_build_rag_retrieval_filters_detects_conflicting_repo_filter() -> None:
    with pytest.raises(HTTPException) as exc_info:
        build_rag_retrieval_filters(
            filters={"repo": "other/repo"},
            workspace_id="workspace-123",
            repo="acme/repo",
        )

    assert exc_info.value.status_code == 400
    assert "filters.repo conflicts with retrieval repo filter" in str(exc_info.value.detail)


def test_build_rag_retrieval_filters_accepts_equivalent_existing_any_filter() -> None:
    merged = build_rag_retrieval_filters(
        filters={"lang": {"any": ["python", "typescript"]}},
        workspace_id="workspace-123",
        lang=["typescript", "python"],
    )
    assert merged["lang"] == {"any": ["python", "typescript"]}
    assert merged["workspace_id"] == "workspace-123"


def test_ensure_workspace_metadata_rejects_mismatched_workspace() -> None:
    with pytest.raises(HTTPException) as exc_info:
        ensure_workspace_metadata({"workspace_id": "other-workspace"}, "workspace-123")

    assert exc_info.value.status_code == 400
    assert "metadata.workspace_id does not match" in str(exc_info.value.detail)
