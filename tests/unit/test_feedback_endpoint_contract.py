import re
from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_feedback_request_includes_optional_reason_field() -> None:
    api_server = _read("api_server.py")

    assert "reason: Optional[str]" in api_server
    assert "Optional reason for thumbs-up/down feedback" in api_server


def test_feedback_endpoint_passes_reason_to_service() -> None:
    api_server = _read("api_server.py")

    feedback_call_pattern = re.compile(
        r"service\.add_feedback\(.*?rating=request\.rating,\s*reason=request\.reason,",
        re.DOTALL,
    )
    assert feedback_call_pattern.search(api_server)


def test_feedback_service_persists_reason_column() -> None:
    service = _read("feedback_service.py")

    assert "reason: Optional[str] = None" in service
    assert "intent, project, metadata, reason" in service
    assert "json.dumps(meta), reason" in service
    assert "metadata, reason, created_at, updated_at" in service


def test_postgres_schema_and_export_include_reason() -> None:
    init_sql = _read("init-scripts/postgres/init.sql")

    assert "reason TEXT" in init_sql
    assert "RETURNS TABLE (" in init_sql
    assert "reason TEXT," in init_sql
    assert "f.reason" in init_sql
