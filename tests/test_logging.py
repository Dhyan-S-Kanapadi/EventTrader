import json
import logging

from eventtrader.logging import JsonFormatter


def test_json_logging_omits_extra_fields_and_exception_details():
    record = logging.LogRecord(
        "eventtrader.test", logging.WARNING, __file__, 1, "database_readiness_failed", (), None
    )
    record.password = "secret-sentinel"
    record.exc_text = "exception with secret-sentinel"
    output = JsonFormatter().format(record)
    parsed = json.loads(output)
    assert parsed["event"] == "database_readiness_failed"
    assert parsed["level"] == "WARNING"
    assert parsed["timestamp"].endswith("+00:00")
    assert "secret-sentinel" not in output
