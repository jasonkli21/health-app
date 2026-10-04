from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from health_api.api.middleware import request_logger
from health_api.main import create_app
from sqlalchemy.exc import SQLAlchemyError


def test_request_logs_only_generated_id_template_status_duration() -> None:
    app = create_app()

    @app.post("/log-probe/{item_id}")
    async def probe(item_id: str) -> None:
        raise SQLAlchemyError("SECRET_SQL SECRET_BODY")

    @app.get("/failure-probe/{item_id}")
    async def failure(item_id: str) -> None:
        raise RuntimeError("SECRET_STACK SECRET_SQL")

    client = TestClient(app)
    with patch.object(request_logger, "info") as log:
        responses = [
            client.post(
                "/log-probe/SECRET_PATH?cursor=SECRET_QUERY",
                content="SECRET_BODY",
                headers={"Authorization": "Bearer SECRET_TOKEN", "X-Request-ID": "SECRET_HEADER"},
            ),
            client.get("/failure-probe/SECRET_PATH"),
            client.get("/SECRET_UNMATCHED?notes=SECRET_QUERY"),
            client.get(
                f"/profile/{uuid4()}?cursor=SECRET_QUERY",
                headers={"Authorization": "Bearer SECRET_TOKEN"},
            ),
            client.post("/log-probe/SECRET_PATH", content="SECRET_BODY" * 10000),
        ]
    assert [response.status_code for response in responses] == [503, 500, 404, 401, 413]
    rendered = [call.args[0] % call.args[1:] for call in log.call_args_list]
    assert len(rendered) == 5
    assert all("SECRET" not in line for line in rendered)
    assert "route=/log-probe/{item_id}" in rendered[0]
    assert "route=<unmatched>" in rendered[2]
    assert all("request_id=" in line and "duration_ms=" in line for line in rendered)
    assert all("SECRET" not in response.text for response in responses)
