"""Static unit tests for chat memory integration in api_server.py.

These tests avoid runtime service dependencies and verify that memory controls,
metadata emission, and auto-store hooks remain wired in the endpoint logic.
"""

from pathlib import Path
import re


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")



def test_memory_options_model_and_top_k_bounds_exist():
    """Memory options should expose top_k with lower/upper validation bounds."""
    assert "class ChatMemoryOptions(BaseModel):" in API_SERVER_SOURCE
    assert "top_k: int = Field(5, ge=1, le=20" in API_SERVER_SOURCE



def test_memory_retrieval_branch_and_system_injection_exist():
    """Memory-enabled branch should retrieve memories and inject a system message."""
    assert "if request.memory and request.memory.enabled:" in API_SERVER_SOURCE
    assert "memory_results = service.search_memory(" in API_SERVER_SOURCE
    assert "messages_for_generation = prepend_context_system_message(" in API_SERVER_SOURCE
    assert "Remembered context:" in API_SERVER_SOURCE



def test_memory_metadata_and_context_response_fields_exist():
    """Response should include memory telemetry fields when memory is active."""
    assert "response_data[\"x-memory-metadata\"] = memory_metadata" in API_SERVER_SOURCE
    assert "response_data[\"memory_context\"] = memory_context_data" in API_SERVER_SOURCE
    assert "metrics.record_memory_telemetry(memory_metadata, memory_context_data)" in API_SERVER_SOURCE


def test_memory_telemetry_aggregates_are_exposed_in_metrics_store():
    """Metrics store should expose memory hit rate/context size/score distributions."""
    assert "self.memory_requests = 0" in API_SERVER_SOURCE
    assert "self.memory_hits = 0" in API_SERVER_SOURCE
    assert "self.memory_context_items_total = 0" in API_SERVER_SOURCE
    assert "self.memory_scores = []" in API_SERVER_SOURCE
    assert '"memory_hit_rate"' in API_SERVER_SOURCE
    assert '"avg_memory_context_size"' in API_SERVER_SOURCE
    assert '"score_distribution"' in API_SERVER_SOURCE



def test_auto_store_guard_exists_and_calls_add_memory():
    """Auto-store should be guarded by flag and persist memory through add_memory."""
    guard_pattern = (
        r"if request\.memory and request\.memory\.enabled and request\.memory\.auto_store:"
    )
    assert re.search(guard_pattern, API_SERVER_SOURCE)
    assert "store_result = memory_service_instance.add_memory(" in API_SERVER_SOURCE



def test_auto_store_marks_memory_metadata():
    """Auto-store branch should annotate metadata with storage status and memory id."""
    assert 'memory_metadata["memory_stored"] = True' in API_SERVER_SOURCE
    assert 'memory_metadata["stored_memory_id"] = store_result.get("memory_id")' in API_SERVER_SOURCE
