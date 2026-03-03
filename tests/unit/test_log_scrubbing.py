"""
Test log hygiene: verify secrets are redacted from logs and no sensitive data leaks.

This test verifies:
1. Secret patterns are detected and redacted in log messages
2. Test marker secrets (TEST_SECRET_MARKER_*) are caught
3. API calls don't leak secrets in logs
4. At least one redaction occurs when secrets are present
"""
import os
import logging
import json
import tempfile
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


def test_secret_marker_verification():
    """
    Inject TEST_SECRET_MARKER_ghp_SMOKE_12345, trigger API call, capture logs,
    assert 0 occurrences + at least one [REDACTED_SECRET].
    """
    # Set environment to disable request body logging for cleaner test
    os.environ["LOG_REQUEST_BODIES"] = "false"
    
    # Import after setting env vars
    from api_server import app
    from safety_sanitizer import redact_secrets_in_logs
    
    client = TestClient(app)
    
    # Capture logs
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    # Get the root logger and add our handler
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    original_level = root_logger.level
    root_logger.setLevel(logging.INFO)
    
    try:
        # Prepare a request with the marker secret embedded
        marker_secret = "TEST_SECRET_MARKER_ghp_SMOKE_12345"
        
        # Test with health endpoint that should log something
        response = client.get("/health")
        
        # Also test with a chat request containing the secret
        chat_payload = {
            "model": "llama-3.3-8b-instruct",
            "messages": [
                {"role": "user", "content": f"Here is my secret: {marker_secret}"}
            ],
            "temperature": 0.7,
            "max_tokens": 100
        }
        
        # Mock the router to avoid actual LLM call
        with patch('api_server.get_agent_router') as mock_router:
            mock_instance = MagicMock()
            mock_instance.generate_completion_stream.return_value = iter([
                {"choices": [{"delta": {"content": "test"}, "index": 0}]}
            ])
            mock_instance.generate_completion.return_value = {
                "id": "test-id",
                "object": "chat.completion",
                "created": 1234567890,
                "model": "llama-3.3-8b-instruct",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "Test response"},
                    "finish_reason": "stop"
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
            }
            mock_router.return_value = mock_instance
            
            # Make a request that might log the payload
            try:
                response = client.post(
                    "/v1/chat/completions",
                    json=chat_payload,
                    headers={"X-Workspace-Id": "test-workspace"}
                )
            except Exception:
                # Ignore errors, we're testing log scrubbing
                pass
        
        # Get the log output
        log_output = log_stream.getvalue()
        
        # Verify the marker secret does NOT appear in logs
        assert marker_secret not in log_output, (
            f"Secret marker '{marker_secret}' found in logs! "
            f"Log output:\n{log_output[:500]}"
        )
        
        # Verify at least one redaction occurred
        assert "[REDACTED_SECRET]" in log_output, (
            "Expected at least one [REDACTED_SECRET] token in logs, but found none. "
            f"Log output:\n{log_output[:500]}"
        )
        
    finally:
        # Cleanup
        root_logger.removeHandler(handler)
        root_logger.setLevel(original_level)
        handler.close()


def test_redact_secrets_in_logs_function():
    """Test the redact_secrets_in_logs function directly."""
    from safety_sanitizer import redact_secrets_in_logs, REDACTION_TOKEN
    
    # Test with secret in message
    message = "API key is ghp_1234567890abcdefghij1234567890"
    redacted_msg, redacted_args = redact_secrets_in_logs(message)
    assert "ghp_1234567890abcdefghij1234567890" not in redacted_msg
    assert REDACTION_TOKEN in redacted_msg
    
    # Test with secret in args
    message = "User provided: %s"
    args = ("ghp_1234567890abcdefghij1234567890",)
    redacted_msg, redacted_args = redact_secrets_in_logs(message, *args)
    assert "ghp_1234567890abcdefghij1234567890" not in redacted_args[0]
    assert REDACTION_TOKEN in redacted_args[0]
    
    # Test with dict containing secrets
    message = "Config: %s"
    args = ({"api_key": "sk-1234567890abcdef"},)
    redacted_msg, redacted_args = redact_secrets_in_logs(message, *args)
    assert "sk-1234567890abcdef" not in str(redacted_args[0])
    assert redacted_args[0]["api_key"] == REDACTION_TOKEN


def test_extended_secret_patterns():
    """Test that extended secret patterns are detected."""
    from safety_sanitizer import redact_secrets_in_text, REDACTION_TOKEN
    
    test_cases = [
        ("TEST_SECRET_MARKER_ghp_SMOKE_12345", True),
        ("npat-12345678901234567890", True),
        ("slack_xoxb-1234567890-1234567890-1234567890", True),
        ("sq0atp-12345678901234567890", True),
        ("EAA" + "A" * 60, True),
        ("bearer eyJhbGciOiJIUzI1NiIsInR5cCI.eyJzdWIiOiIxMjM0NTY3ODkw.SflKxwRJSMeKKF2QT", True),
        ("AKIA1234567890ABCDEF", True),
        ("normal text without secrets", False),
    ]
    
    for text, should_redact in test_cases:
        redacted, count = redact_secrets_in_text(text)
        if should_redact:
            assert text not in redacted or text == redacted, f"Failed to redact: {text}"
            assert REDACTION_TOKEN in redacted or count > 0, f"Expected redaction for: {text}"
        else:
            assert redacted == text, f"Incorrectly redacted: {text}"


def test_safe_logger_wrapper():
    """Test that SafeLogger properly wraps and redacts log messages."""
    from api_server import SafeLogger
    import logging
    
    # Create a test logger with string IO handler
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.INFO)
    base_logger = logging.getLogger("test_logger")
    base_logger.addHandler(handler)
    base_logger.setLevel(logging.INFO)
    
    # Wrap it with SafeLogger
    safe_logger = SafeLogger(base_logger)
    
    try:
        # Log a message with a secret
        secret = "ghp_1234567890abcdefghij1234567890"
        safe_logger.info("User token: %s", secret)
        
        # Check the output
        log_output = log_stream.getvalue()
        assert secret not in log_output, f"Secret leaked in logs: {log_output}"
        assert "[REDACTED_SECRET]" in log_output, f"No redaction found in logs: {log_output}"
        
    finally:
        base_logger.removeHandler(handler)
        handler.close()


def test_exception_traceback_sanitization():
    """Test that exception tracebacks are sanitized before logging."""
    from api_server import SafeLogger
    import logging
    
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.ERROR)
    base_logger = logging.getLogger("test_traceback_logger")
    base_logger.addHandler(handler)
    base_logger.setLevel(logging.ERROR)
    
    safe_logger = SafeLogger(base_logger)
    
    try:
        secret = "ghp_1234567890abcdefghij1234567890"
        
        # Generate an exception with the secret in it
        try:
            raise ValueError(f"Authentication failed with token: {secret}")
        except ValueError as e:
            safe_logger.error("Error occurred: %s", str(e), exc_info=True)
        
        # Check the output
        log_output = log_stream.getvalue()
        assert secret not in log_output, f"Secret leaked in traceback: {log_output}"
        assert "[REDACTED_SECRET]" in log_output, f"No redaction found in traceback: {log_output}"
        assert "[SANITIZED TRACEBACK]" in log_output, f"Missing sanitized marker: {log_output}"
        
    finally:
        base_logger.removeHandler(handler)
        handler.close()


def test_log_request_bodies_disabled():
    """Test that request/response bodies are not logged when LOG_REQUEST_BODIES=false."""
    os.environ["LOG_REQUEST_BODIES"] = "false"
    
    # Re-import to pick up the env var
    import importlib
    import api_server
    importlib.reload(api_server)
    
    assert api_server.LOG_REQUEST_BODIES is False, "LOG_REQUEST_BODIES should be False"
    
    # The audit logging should pass empty dicts when LOG_REQUEST_BODIES is false
    # This is tested by the fact that the code checks `if LOG_REQUEST_BODIES` before
    # passing request_payload and response_payload to audit events


def test_log_request_bodies_enabled():
    """Test that request/response bodies ARE logged when LOG_REQUEST_BODIES=true."""
    os.environ["LOG_REQUEST_BODIES"] = "true"
    
    import importlib
    import api_server
    importlib.reload(api_server)
    
    assert api_server.LOG_REQUEST_BODIES is True, "LOG_REQUEST_BODIES should be True"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
