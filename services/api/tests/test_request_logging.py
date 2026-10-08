from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient
from health_api.api.middleware import request_logger
from health_api.main import create_app
from sqlalchemy.exc import SQLAlchemyError


def test_request_logs_are_structured_and_exclude_request_data() -> None:
    app = create_app()

    @app.post("/log-probe/{item_id}")
    async def probe(item_id: str) -> None:
        raise SQLAlchemyError("SECRET_SQL SECRET_BODY")

    @app.get("/failure-probe/{item_id}")
    async def failure(item_id: str) -> None:
        raise RuntimeError("SECRET_STACK SECRET_SQL")

    output = StringIO()
    handler = request_logger.handlers[0]
    with patch.object(handler, "stream", output), TestClient(app) as client:
        responses = [
            client.post(
                "/log-probe/SECRET_PATH?cursor=SECRET_QUERY",
                content="SECRET_BODY",
                headers={
                    "Authorization": "Bearer SECRET_TOKEN",
                    "X-Request-ID": "SECRET!HEADER",
                },
            ),
            client.get("/failure-probe/SECRET_PATH"),
            client.get("/SECRET_UNMATCHED?notes=SECRET_QUERY"),
            client.get(
                f"/profile/{UUID(int=1)}?cursor=SECRET_QUERY",
                headers={"Authorization": "Bearer SECRET_TOKEN"},
            ),
            client.post("/log-probe/SECRET_PATH", content="SECRET_BODY" * 10000),
        ]

    assert [response.status_code for response in responses] == [503, 500, 404, 401, 413]
    lines = output.getvalue().splitlines()
    assert len(lines) == len(responses)
    records = [json.loads(line) for line in lines]

    assert records[0] == {
        "duration_ms": records[0]["duration_ms"],
        "event": "http_request_completed",
        "method": "POST",
        "request_id": responses[0].headers["x-request-id"],
        "route": "/log-probe/{item_id}",
        "severity": "ERROR",
        "status_code": 503,
    }
    assert records[2]["route"] == "<unmatched>"
    assert all("SECRET" not in line for line in lines)
    assert all("SECRET" not in response.text for response in responses)
    assert all(isinstance(record["duration_ms"], int) for record in records)
    assert records[4] == {
        "body_limit_bytes": 65_536,
        "duration_ms": records[4]["duration_ms"],
        "event": "http_request_rejected",
        "method": "POST",
        "rejection_reason": "body_limit_exceeded",
        "request_id": responses[4].headers["x-request-id"],
        "route": "<unmatched>",
        "severity": "WARNING",
        "status_code": 413,
    }


def test_safe_request_id_is_echoed_and_logged() -> None:
    app = create_app()
    request_id = "client.req_123-ABC"
    output = StringIO()
    handler = request_logger.handlers[0]
    with patch.object(handler, "stream", output), TestClient(app) as client:
        response = client.get("/healthz", headers={"X-Request-ID": request_id})

    record = json.loads(output.getvalue())
    assert response.status_code == 200
    assert response.headers["x-request-id"] == request_id
    assert record["request_id"] == request_id


def test_invalid_or_oversized_request_id_is_replaced() -> None:
    app = create_app()
    output = StringIO()
    handler = request_logger.handlers[0]
    with patch.object(handler, "stream", output), TestClient(app) as client:
        response = client.get("/healthz", headers={"X-Request-ID": "x" * 65})

    generated_id = response.headers["x-request-id"]
    UUID(generated_id)
    record = json.loads(output.getvalue())
    assert record["request_id"] == generated_id
