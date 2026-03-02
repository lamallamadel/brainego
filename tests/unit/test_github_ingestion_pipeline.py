from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_module(module_name: str, relative_path: str):
    spec = spec_from_file_location(module_name, Path(relative_path))
    module = module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_scheduler_has_github_enable_gate():
    source = Path("data_collectors/scheduler.py").read_text(encoding="utf-8")

    assert "def _is_enabled(" in source
    assert "ENABLE_GITHUB_INGESTION" in source
    assert "Skipping disabled job" in source


def test_collect_and_process_skips_github_when_disabled(monkeypatch):
    ingestion_worker = _load_module("ingestion_worker", "data_collectors/ingestion_worker.py")
    monkeypatch.setenv("ENABLE_GITHUB_INGESTION", "false")

    result = ingestion_worker.collect_and_process(
        "github",
        {"repo_name": "owner/repo", "hours_back": 6},
    )

    assert result["status"] == "skipped"
    assert result["source"] == "github"
    assert result["collected"] == 0
    assert result["processed"] == 0


def test_github_collection_forwards_issue_pr_commit_flags():
    source = Path("data_collectors/ingestion_worker.py").read_text(encoding="utf-8")

    assert "include_issues = config.get(\"include_issues\", True)" in source
    assert "include_prs = config.get(\"include_prs\", True)" in source
    assert "include_commits = config.get(\"include_commits\", True)" in source
    assert "include_discussions = config.get(\"include_discussions\", False)" in source
    assert "include_issues=include_issues" in source
    assert "include_prs=include_prs" in source
    assert "include_commits=include_commits" in source
    assert "include_discussions=include_discussions" in source


def test_collection_schedule_uses_github_toggle_variable():
    config = Path("configs/collection-schedule.yaml").read_text(encoding="utf-8")
    assert "enabled: ${ENABLE_GITHUB_INGESTION}" in config


def test_github_repo_source_is_supported_with_incremental_defaults():
    source = Path("data_collectors/ingestion_worker.py").read_text(encoding="utf-8")

    assert "if source == \"github_repo\":" in source
    assert "return _collect_and_process_github_repo(config)" in source
    assert "incremental = _is_truthy(config.get(\"incremental\"), default=True)" in source
    assert "reindex = _is_truthy(config.get(\"reindex\"), default=False)" in source


def test_collection_schedule_includes_github_repo_codebase_sync():
    config = Path("configs/collection-schedule.yaml").read_text(encoding="utf-8")
    assert "name: github_repo_codebase_sync" in config
    assert "source: github_repo" in config
    assert "incremental: true" in config
