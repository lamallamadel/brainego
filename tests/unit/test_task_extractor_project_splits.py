"""Unit tests for per-project support/query task extraction behavior."""

import sys
import types
from pathlib import Path

# Make repository root importable.
sys.path.append(str(Path(__file__).resolve().parents[2]))

# Keep tests offline/lightweight when psycopg2 is unavailable.
psycopg2_stub = types.ModuleType("psycopg2")
psycopg2_stub.connect = lambda **kwargs: None
sys.modules.setdefault("psycopg2", psycopg2_stub)

import importlib.util

_TASK_EXTRACTOR_PATH = Path(__file__).resolve().parents[2] / "learning_engine" / "task_extractor.py"
spec = importlib.util.spec_from_file_location("task_extractor_module", _TASK_EXTRACTOR_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
TaskExtractor = module.TaskExtractor


def _build_extractor() -> TaskExtractor:
    return TaskExtractor(
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="db",
        postgres_user="user",
        postgres_password="pass",
    )


def test_build_project_task_splits_creates_support_and_query_sets() -> None:
    extractor = _build_extractor()
    project_tasks = {
        "alpha": [{"input": f"q{i}", "output": f"a{i}"} for i in range(10)],
    }

    splits = extractor.build_project_task_splits(project_tasks, support_ratio=0.6)

    alpha = splits["alpha"]
    assert alpha["task_id"] == "project_alpha"
    assert alpha["support_size"] == 6
    assert alpha["query_size"] == 4
    assert len(alpha["interactions"]) == 10


def test_build_project_task_splits_enforces_minimum_query_samples() -> None:
    extractor = _build_extractor()
    project_tasks = {
        "beta": [{"input": f"q{i}", "output": f"a{i}"} for i in range(3)],
    }

    splits = extractor.build_project_task_splits(
        project_tasks,
        support_ratio=0.95,
        min_support_samples=1,
        min_query_samples=1,
    )

    beta = splits["beta"]
    assert beta["support_size"] == 2
    assert beta["query_size"] == 1


def test_build_project_task_splits_skips_projects_without_enough_samples() -> None:
    extractor = _build_extractor()
    project_tasks = {
        "tiny": [{"input": "q0", "output": "a0"}],
    }

    splits = extractor.build_project_task_splits(
        project_tasks,
        min_support_samples=1,
        min_query_samples=1,
    )

    assert "tiny" not in splits
