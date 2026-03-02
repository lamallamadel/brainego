# Needs: python-package:pytest>=9.0.2

"""Static tests for workspace context enforcement in lightweight_api_service.py."""

from pathlib import Path


LIGHTWEIGHT_SOURCE = Path("lightweight_api_service.py").read_text(encoding="utf-8")


def test_lightweight_service_has_workspace_middleware() -> None:
    assert "async def enforce_workspace_context(request: Request, call_next):" in LIGHTWEIGHT_SOURCE
    assert "workspace_id = resolve_workspace_id(request)" in LIGHTWEIGHT_SOURCE
    assert '"code": "workspace_id_missing"' in LIGHTWEIGHT_SOURCE
    assert '"code": "workspace_id_unknown"' in LIGHTWEIGHT_SOURCE
    assert "request.state.workspace_id = workspace_id" in LIGHTWEIGHT_SOURCE


def test_lightweight_service_forwards_workspace_header_downstream() -> None:
    assert "workspace_id = getattr(request.state, \"workspace_id\", None)" in LIGHTWEIGHT_SOURCE
    assert "forwarded_headers[WORKSPACE_ID_RESPONSE_HEADER] = workspace_id" in LIGHTWEIGHT_SOURCE
