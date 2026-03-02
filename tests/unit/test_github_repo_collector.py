# Needs: python-package:pytest>=9.0.2

"""Unit tests for GitHub repository codebase collection and sync state."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Dict, List, Optional, Tuple


if "github" not in sys.modules:
    github_stub = types.ModuleType("github")

    class _Github:  # pragma: no cover - simple import stub
        pass

    class _GithubException(Exception):  # pragma: no cover - simple import stub
        pass

    github_stub.Github = _Github
    github_stub.GithubException = _GithubException
    sys.modules["github"] = github_stub

from data_collectors.github_collector import GitHubCollector


class _FakeTreeEntry:
    def __init__(self, path: str, size: int = 64, entry_type: str = "blob"):
        self.path = path
        self.size = size
        self.type = entry_type


class _FakeContent:
    def __init__(self, text: str, sha: str):
        raw = text.encode("utf-8")
        self.decoded_content = raw
        self.size = len(raw)
        self.sha = sha


class _FakeCompareFile:
    def __init__(
        self,
        filename: str,
        status: str,
        previous_filename: Optional[str] = None,
    ):
        self.filename = filename
        self.status = status
        self.previous_filename = previous_filename


class _FakeRepo:
    def __init__(
        self,
        *,
        full_name: str,
        default_branch: str,
        head_commit: str,
        tree_entries: List[_FakeTreeEntry],
        contents: Dict[str, _FakeContent],
        comparisons: Optional[Dict[Tuple[str, str], List[_FakeCompareFile]]] = None,
    ):
        self.full_name = full_name
        self.default_branch = default_branch
        self._head_commit = head_commit
        self._tree_entries = tree_entries
        self._contents = contents
        self._comparisons = comparisons or {}

    def get_branch(self, branch: str):
        assert branch == self.default_branch
        return types.SimpleNamespace(commit=types.SimpleNamespace(sha=self._head_commit))

    def get_git_tree(self, ref: str, recursive: bool = True):
        assert recursive is True
        assert ref == self._head_commit
        return types.SimpleNamespace(tree=self._tree_entries)

    def get_contents(self, path: str, ref: str):
        assert ref == self._head_commit
        return self._contents[path]

    def compare(self, previous: str, current: str):
        key = (previous, current)
        if key not in self._comparisons:
            raise AssertionError(f"Unexpected comparison requested: {key}")
        return types.SimpleNamespace(files=self._comparisons[key])


def _build_collector(fake_repo: _FakeRepo) -> GitHubCollector:
    collector = GitHubCollector.__new__(GitHubCollector)
    collector.github = types.SimpleNamespace(get_repo=lambda _repo_name: fake_repo)
    return collector


def test_build_repository_document_id_is_stable() -> None:
    doc_id_1 = GitHubCollector.build_repository_document_id(
        repo_name="Acme/Repo",
        path="src/main.py",
        workspace_id="workspace-a",
    )
    doc_id_2 = GitHubCollector.build_repository_document_id(
        repo_name="acme/repo",
        path="src/main.py",
        workspace_id="workspace-a",
    )
    doc_id_3 = GitHubCollector.build_repository_document_id(
        repo_name="acme/repo",
        path="src/other.py",
        workspace_id="workspace-a",
    )

    assert doc_id_1 == doc_id_2
    assert doc_id_1 != doc_id_3


def test_collect_repository_codebase_full_sync_emits_required_metadata(tmp_path: Path) -> None:
    repo = _FakeRepo(
        full_name="acme/repo",
        default_branch="main",
        head_commit="c1",
        tree_entries=[
            _FakeTreeEntry("src/main.py"),
            _FakeTreeEntry("README.md"),
            _FakeTreeEntry("assets/logo.png"),
            _FakeTreeEntry("node_modules/pkg/index.js"),
        ],
        contents={
            "src/main.py": _FakeContent("print('hello')\n", "blob-a"),
            "README.md": _FakeContent("# Repo\n", "blob-b"),
        },
    )
    collector = _build_collector(repo)
    state_path = tmp_path / "github-sync-state.json"

    result = collector.collect_repository_codebase(
        repo_name="acme/repo",
        workspace_id="workspace-alpha",
        state_path=str(state_path),
    )

    assert result["status"] == "success"
    assert result["sync"]["mode"] == "full"
    assert result["sync"]["current_commit"] == "c1"
    assert result["deleted_paths"] == []
    assert sorted(doc["metadata"]["path"] for doc in result["documents"]) == [
        "README.md",
        "src/main.py",
    ]

    for document in result["documents"]:
        metadata = document["metadata"]
        assert metadata["repo"] == "acme/repo"
        assert metadata["path"] in {"README.md", "src/main.py"}
        assert metadata["commit"] == "c1"
        assert metadata["workspace"] == "workspace-alpha"
        assert metadata["workspace_id"] == "workspace-alpha"
        assert metadata["lang"] in {"python", "markdown"}
        assert metadata["document_id"] == GitHubCollector.build_repository_document_id(
            repo_name="acme/repo",
            path=metadata["path"],
            workspace_id="workspace-alpha",
        )

    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["acme/repo:workspace-alpha:main"]["last_commit"] == "c1"
    assert state_payload["acme/repo:workspace-alpha:main"]["indexed_paths"] == [
        "README.md",
        "src/main.py",
    ]


def test_collect_repository_codebase_incremental_sync_uses_default_branch(tmp_path: Path) -> None:
    state_path = tmp_path / "github-sync-state.json"

    repo_v1 = _FakeRepo(
        full_name="acme/repo",
        default_branch="main",
        head_commit="c1",
        tree_entries=[
            _FakeTreeEntry("src/main.py"),
            _FakeTreeEntry("src/unchanged.py"),
            _FakeTreeEntry("README.md"),
        ],
        contents={
            "src/main.py": _FakeContent("print('v1')\n", "blob-main-v1"),
            "src/unchanged.py": _FakeContent("UNCHANGED = True\n", "blob-unchanged"),
            "README.md": _FakeContent("# v1\n", "blob-readme-v1"),
        },
    )
    _build_collector(repo_v1).collect_repository_codebase(
        repo_name="acme/repo",
        workspace_id="workspace-alpha",
        state_path=str(state_path),
        incremental=True,
    )

    repo_v2 = _FakeRepo(
        full_name="acme/repo",
        default_branch="main",
        head_commit="c2",
        tree_entries=[
            _FakeTreeEntry("src/main.py"),
            _FakeTreeEntry("src/unchanged.py"),
            _FakeTreeEntry("src/new_feature.ts"),
        ],
        contents={
            "src/main.py": _FakeContent("print('v2')\n", "blob-main-v2"),
            "src/new_feature.ts": _FakeContent("export const value = 1;\n", "blob-ts"),
        },
        comparisons={
            ("c1", "c2"): [
                _FakeCompareFile(filename="src/main.py", status="modified"),
                _FakeCompareFile(filename="src/new_feature.ts", status="added"),
                _FakeCompareFile(filename="README.md", status="removed"),
            ]
        },
    )

    incremental_result = _build_collector(repo_v2).collect_repository_codebase(
        repo_name="acme/repo",
        workspace_id="workspace-alpha",
        state_path=str(state_path),
        incremental=True,
    )

    assert incremental_result["sync"]["mode"] == "incremental"
    assert incremental_result["sync"]["previous_commit"] == "c1"
    assert incremental_result["sync"]["current_commit"] == "c2"
    assert sorted(doc["metadata"]["path"] for doc in incremental_result["documents"]) == [
        "src/main.py",
        "src/new_feature.ts",
    ]
    assert incremental_result["deleted_paths"] == ["README.md"]

    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["acme/repo:workspace-alpha:main"]["last_commit"] == "c2"
    assert state_payload["acme/repo:workspace-alpha:main"]["indexed_paths"] == [
        "src/main.py",
        "src/new_feature.ts",
        "src/unchanged.py",
    ]


def test_collect_repository_codebase_supports_csv_patterns(tmp_path: Path) -> None:
    repo = _FakeRepo(
        full_name="acme/repo",
        default_branch="main",
        head_commit="c1",
        tree_entries=[
            _FakeTreeEntry("src/main.py"),
            _FakeTreeEntry("src/main.test.py"),
            _FakeTreeEntry("docs/guide.md"),
        ],
        contents={
            "src/main.py": _FakeContent("print('ok')\n", "blob-main"),
            "src/main.test.py": _FakeContent("print('test')\n", "blob-test"),
            "docs/guide.md": _FakeContent("# Guide\n", "blob-doc"),
        },
    )

    result = _build_collector(repo).collect_repository_codebase(
        repo_name="acme/repo",
        workspace_id="workspace-alpha",
        state_path=str(tmp_path / "github-sync-state.json"),
        include_patterns="src/*.py,docs/*.md",
        exclude_patterns="*.test.py",
    )

    assert result["status"] == "success"
    assert sorted(doc["metadata"]["path"] for doc in result["documents"]) == [
        "docs/guide.md",
        "src/main.py",
    ]


def test_incremental_compare_applies_include_patterns(tmp_path: Path) -> None:
    state_path = tmp_path / "github-sync-state.json"

    repo_v1 = _FakeRepo(
        full_name="acme/repo",
        default_branch="main",
        head_commit="c1",
        tree_entries=[
            _FakeTreeEntry("src/main.py"),
            _FakeTreeEntry("docs/guide.md"),
        ],
        contents={
            "src/main.py": _FakeContent("print('v1')\n", "blob-main-v1"),
            "docs/guide.md": _FakeContent("# docs\n", "blob-doc-v1"),
        },
    )
    _build_collector(repo_v1).collect_repository_codebase(
        repo_name="acme/repo",
        workspace_id="workspace-alpha",
        state_path=str(state_path),
        incremental=True,
        include_patterns="src/*.py",
    )

    repo_v2 = _FakeRepo(
        full_name="acme/repo",
        default_branch="main",
        head_commit="c2",
        tree_entries=[
            _FakeTreeEntry("src/main.py"),
            _FakeTreeEntry("src/new.py"),
        ],
        contents={
            "src/main.py": _FakeContent("print('v2')\n", "blob-main-v2"),
            "src/new.py": _FakeContent("print('new')\n", "blob-new-v2"),
        },
        comparisons={
            ("c1", "c2"): [
                _FakeCompareFile(filename="src/new.py", status="added"),
                _FakeCompareFile(filename="docs/guide.md", status="removed"),
            ]
        },
    )

    result = _build_collector(repo_v2).collect_repository_codebase(
        repo_name="acme/repo",
        workspace_id="workspace-alpha",
        state_path=str(state_path),
        incremental=True,
        include_patterns="src/*.py",
    )

    assert sorted(doc["metadata"]["path"] for doc in result["documents"]) == ["src/new.py"]
    assert result["deleted_paths"] == []


def test_decode_content_to_text_rejects_binary_like_payload() -> None:
    binary_like_content = types.SimpleNamespace(
        decoded_content=(b"\x80\x81\x82" * 128),
        size=384,
        sha="blob-binary",
    )

    assert GitHubCollector._decode_content_to_text(binary_like_content) is None
