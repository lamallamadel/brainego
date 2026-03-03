"""Static wiring checks for S3-2 retrieval recipes integration."""

from pathlib import Path


SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_rag_query_applies_retrieval_recipe_before_search() -> None:
    assert "retrieval_recipes_store.get_active_recipes" in SOURCE
    assert "apply_retrieval_recipe(" in SOURCE
    assert '"rewritten_query"' in SOURCE
    assert '"recipe_applied"' in SOURCE
