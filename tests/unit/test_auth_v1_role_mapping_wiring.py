# Needs: python-package:pytest>=9.0.2

"""Static wiring checks for AFR-87 auth v1 + role mapping."""

from pathlib import Path


API_SERVER_SOURCE = Path("api_server.py").read_text(encoding="utf-8")


def test_auth_v1_middleware_exists_and_enforces_protected_paths() -> None:
    assert "async def enforce_auth_v1(request: Request, call_next):" in API_SERVER_SOURCE
    assert "_is_auth_v1_enabled()" in API_SERVER_SOURCE
    assert "_is_auth_enforced_path(path)" in API_SERVER_SOURCE
    assert "_authenticate_request_v1(request)" in API_SERVER_SOURCE
    assert "AUTH_REQUIRED_EXACT_PATHS = WORKSPACE_REQUIRED_EXACT_PATHS | {\"/audit\"}" in API_SERVER_SOURCE
    assert "status_code=exc.status_code" in API_SERVER_SOURCE
    assert "\"type\": \"authentication_error\"" in API_SERVER_SOURCE


def test_auth_identity_and_role_are_attached_to_request_state() -> None:
    assert "request.state.auth_user_id = identity.get(\"user_id\")" in API_SERVER_SOURCE
    assert "request.state.auth_role = role" in API_SERVER_SOURCE
    assert "request.state.auth_method = identity.get(\"auth_method\")" in API_SERVER_SOURCE
    assert "AUTH_USER_CONTEXT.set(identity.get(\"user_id\"))" in API_SERVER_SOURCE
    assert "AUTH_ROLE_CONTEXT.set(role)" in API_SERVER_SOURCE


def test_audit_logs_include_role_and_authenticated_user() -> None:
    assert "auth_user_id = get_authenticated_user_id(raw_request)" in API_SERVER_SOURCE
    assert "auth_user_id = get_authenticated_user_id(request)" in API_SERVER_SOURCE
    assert "role=auth_role," in API_SERVER_SOURCE
    assert "\"role\": auth_role" in API_SERVER_SOURCE
    assert "\"auth_method\": auth_method" in API_SERVER_SOURCE


def test_metering_tracks_user_id_in_metrics_store() -> None:
    assert "self.user_metering: Dict[str, Dict[str, int]] = {}" in API_SERVER_SOURCE
    assert "\"metering\": user_metering" in API_SERVER_SOURCE
    assert "user_id=effective_user_id" in API_SERVER_SOURCE
    assert "user_id=metering_user_id" in API_SERVER_SOURCE
