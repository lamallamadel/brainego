"""Static contract checks for feedback API payload and persistence fields."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")
FEEDBACK_SERVICE_SOURCE = Path("feedback_service.py").read_text(encoding="utf-8")
POSTGRES_INIT_SOURCE = Path("init-scripts/postgres/init.sql").read_text(encoding="utf-8")


def test_feedback_request_accepts_optional_reason_field():
    """POST /v1/feedback request model should expose optional textual reason."""
    assert "class FeedbackRequest(BaseModel):" in API_SERVER_SOURCE
    assert "reason: Optional[str] = Field(None, description=\"Optional textual reason for the feedback\")" in API_SERVER_SOURCE
    assert "reason=request.reason" in API_SERVER_SOURCE


def test_feedback_service_persists_reason_in_insert_and_select():
    """FeedbackService should write/read the reason column from PostgreSQL."""
    assert "reason: Optional[str] = None" in FEEDBACK_SERVICE_SOURCE
    assert "tools_called, rating, reason, user_id, session_id" in FEEDBACK_SERVICE_SOURCE
    assert "tools_called, rating, reason, timestamp, user_id, session_id" in FEEDBACK_SERVICE_SOURCE


def test_feedback_table_schema_includes_reason_column():
    """PostgreSQL feedback schema should contain a nullable reason column."""
    assert "reason TEXT" in POSTGRES_INIT_SOURCE
    assert "RETURNS TABLE (" in POSTGRES_INIT_SOURCE
    assert "    reason TEXT," in POSTGRES_INIT_SOURCE
