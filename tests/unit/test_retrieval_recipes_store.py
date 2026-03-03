"""Unit tests for retrieval recipes store and application."""

import importlib.util
import tempfile
from pathlib import Path

MODULE_PATH = Path("retrieval_recipes_store.py")
SPEC = importlib.util.spec_from_file_location("retrieval_recipes_store", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_recipes_store_versioning_and_rollback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = MODULE.RetrievalRecipesStore(path=Path(tmp) / "recipes.json")
        v1 = store.create_version(workspace_id="ws", recipes=[{"match_keyword": "policy", "top_k": 7}])
        v2 = store.create_version(workspace_id="ws", recipes=[{"match_keyword": "policy", "top_k": 3}])
        assert v2 > v1
        assert store.get_active_recipes("ws")[0]["top_k"] == 3
        store.rollback(v1)
        assert store.get_active_recipes("ws")[0]["top_k"] == 7


def test_apply_recipe_rewrites_query_and_top_k() -> None:
    plan = MODULE.apply_retrieval_recipe(
        "internal policy retention",
        [{"match_keyword": "policy", "rewrite_prefix": "enterprise", "top_k": 8}],
        5,
    )
    assert plan["recipe_applied"] is True
    assert plan["query"].startswith("enterprise")
    assert plan["top_k"] == 8
