# Needs: python-package:pytest>=9.0.2

from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "internal_mcp_client.py"


def test_internal_client_supports_confirmation_parameters() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert "confirm: Optional[bool] = None" in content
    assert "confirmation_id: Optional[str] = None" in content


def test_internal_client_forwards_confirmation_fields_in_payload() -> None:
    content = SOURCE.read_text(encoding="utf-8")
    assert 'payload["confirm"] = bool(confirm)' in content
    assert 'payload["confirmation_id"] = confirmation_id' in content
