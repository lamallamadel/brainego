# Needs: python-package:pytest>=9.0.2

import json
import logging

from structured_logger import StructuredJSONFormatter


def test_structured_formatter_redacts_message_and_extra_fields() -> None:
    formatter = StructuredJSONFormatter(service_name="test-service", include_trace=False)
    base_logger = logging.getLogger("test.structured_logger")
    record = base_logger.makeRecord(
        name="test.structured_logger",
        level=logging.INFO,
        fn=__file__,
        lno=12,
        msg="request payload token=supersecretvalue123",
        args=(),
        exc_info=None,
        extra={
            "extra_fields": {
                "api_key": "plain-secret-key-value",
                "note": "safe note",
            }
        },
    )

    formatted = formatter.format(record)
    payload = json.loads(formatted)

    assert payload["message"] != "request payload token=supersecretvalue123"
    assert payload["message_redactions"] >= 1
    assert payload["api_key"] == "[REDACTED_SECRET]"
    assert payload["note"] == "safe note"
    assert payload["extra_fields_redactions"] >= 1
