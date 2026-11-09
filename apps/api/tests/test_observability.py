import json
import logging

from conftest import TEST_PASSWORD


def test_http_emits_safe_correlated_json_without_input_or_raw_url(client, caplog):
    with caplog.at_level(logging.INFO, logger="altvia.requests"):
        response = client.post(
            "/api/v1/auth/sessions?secret=never-log-query",
            json={
                "email": "employee@example.test",
                "password": TEST_PASSWORD,
            },
            headers={"X-Correlation-ID": "logging-proof"},
        )
    assert response.status_code == 201
    records = [row for row in caplog.records if row.name == "altvia.requests"]
    assert len(records) == 1
    from altvia.observability import SafeJsonFormatter

    text = SafeJsonFormatter().format(records[0])
    data = json.loads(text)
    assert data["correlation_id"] == "logging-proof" and data["status"] == 201
    assert data["route"] == "/api/v1/auth/sessions"
    assert TEST_PASSWORD not in text and "never-log-query" not in text and "csrf" not in text


def test_foreign_logger_exception_and_format_arguments_cannot_expose_secrets():
    from altvia.observability import SafeJsonFormatter

    record = logging.LogRecord(
        "dramatiq.worker",
        logging.ERROR,
        __file__,
        1,
        "redis://:secret-password@host leaked %s",
        ("private-token",),
        None,
    )
    output = SafeJsonFormatter().format(record)
    assert "secret-password" not in output and "private-token" not in output
    assert json.loads(output)["component"] == "dramatiq.worker"
