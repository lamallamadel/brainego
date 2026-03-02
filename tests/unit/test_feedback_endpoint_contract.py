import re
from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_feedback_request_includes_reason_category_and_expected_answer_fields() -> None:
    api_server = _read("api_server.py")

    assert "reason: Optional[str]" in api_server
    assert "category: Optional[str]" in api_server
    assert "expected_answer: Optional[str]" in api_server
    assert "Optional reason for thumbs-up/down feedback" in api_server
    assert "hallucination" in api_server
    assert "wrong_tool" in api_server
    assert "missing_citation" in api_server
    assert "policy_denial" in api_server


def test_feedback_endpoint_passes_taxonomy_fields_to_service() -> None:
    api_server = _read("api_server.py")

    feedback_call_pattern = re.compile(
        (
            r"service\.add_feedback\("
            r".*?rating=request\.rating,"
            r"\s*reason=request\.reason,"
            r"\s*category=request\.category,"
            r"\s*expected_answer=request\.expected_answer,"
        ),
        re.DOTALL,
    )
    assert feedback_call_pattern.search(api_server)


def test_feedback_update_endpoint_passes_taxonomy_fields_to_service() -> None:
    api_server = _read("api_server.py")

    update_call_pattern = re.compile(
        (
            r"service\.update_feedback\("
            r".*?rating=request\.rating,"
            r"\s*reason=request\.reason,"
            r"\s*category=request\.category,"
            r"\s*expected_answer=request\.expected_answer,"
        ),
        re.DOTALL,
    )
    assert update_call_pattern.search(api_server)


def test_feedback_service_persists_reason_category_and_expected_answer_columns() -> None:
    service = _read("feedback_service.py")

    assert "reason: Optional[str] = None" in service
    assert "category: Optional[str] = None" in service
    assert "expected_answer: Optional[str] = None" in service
    assert "intent, project, metadata, reason, category, expected_answer" in service
    assert "normalized_reason" in service
    assert "normalized_category" in service
    assert "normalized_expected_answer" in service
    assert "metadata, reason, category, expected_answer" in service


def test_postgres_schema_and_export_include_feedback_taxonomy() -> None:
    init_sql = _read("init-scripts/postgres/init.sql")

    assert "reason TEXT" in init_sql
    assert "category VARCHAR(64)" in init_sql
    assert "expected_answer TEXT" in init_sql
    assert "RETURNS TABLE (" in init_sql
    assert "reason TEXT," in init_sql
    assert "category VARCHAR," in init_sql
    assert "expected_answer TEXT," in init_sql
    assert "f.reason" in init_sql
    assert "f.category" in init_sql
    assert "f.expected_answer" in init_sql


def test_finetuning_export_request_exposes_minio_options() -> None:
    api_server = _read("api_server.py")

    assert "upload_to_minio: bool" in api_server
    assert "minio_bucket: Optional[str]" in api_server
    assert "minio_prefix: Optional[str]" in api_server


def test_finetuning_export_endpoint_forwards_minio_options() -> None:
    api_server = _read("api_server.py")

    call_pattern = re.compile(
        r"service\.export_finetuning_dataset\(.*?upload_to_minio=request\.upload_to_minio,"
        r".*?minio_bucket=request\.minio_bucket,"
        r".*?minio_prefix=request\.minio_prefix,",
        re.DOTALL,
    )
    assert call_pattern.search(api_server)
