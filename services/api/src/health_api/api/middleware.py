"""Request correlation and strict request-body size limits."""

from __future__ import annotations

import json
import logging
import sys
from time import monotonic
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_logger = logging.getLogger("health_api.requests")
if not request_logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    request_logger.addHandler(handler)
request_logger.setLevel(logging.INFO)
request_logger.propagate = False


class RequestBoundaryMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        max_body_bytes: int = 65_536,
        path_limits: dict[str, int] | None = None,
    ) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes
        self.path_limits = path_limits or {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
        body_limit = self.path_limits.get(scope.get("path", ""), self.max_body_bytes)
        started = monotonic()
        status = 500
        response_started = False

        def log_completion() -> None:
            route = scope.get("route")
            template = getattr(route, "path", "<unmatched>")
            # Route templates are application source, never user-supplied paths.
            request_logger.info(
                "request_id=%s route=%s status=%d duration_ms=%d",
                request_id,
                template,
                status,
                round((monotonic() - started) * 1000),
            )

        scope.setdefault("state", {})["request_id"] = request_id
        chunks: list[bytes] = []
        total = 0
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > body_limit:
                status = 413
                body = json.dumps(
                    {
                        "code": "request_too_large",
                        "message": f"Request body exceeds the {body_limit} byte limit.",
                        "field_errors": None,
                        "request_id": request_id,
                    },
                    separators=(",", ":"),
                ).encode("utf-8")
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode("ascii")),
                            (b"x-request-id", request_id.encode("ascii")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body, "more_body": False})
                log_completion()
                return
            chunks.append(chunk)
            more_body = message.get("more_body", False)

        request_body = b"".join(chunks)
        delivered = False

        async def replay_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": request_body, "more_body": False}
            return await receive()

        async def response_send(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                headers = list(message.get("headers", []))
                if not any(name.lower() == b"x-request-id" for name, _ in headers):
                    headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, replay_receive, response_send)
        except Exception:  # noqa: BLE001 - final privacy boundary for unexpected errors
            # Handle unexpected errors inside the server error boundary: allowing
            # them to escape causes Uvicorn to log raw exception/SQL details.
            status = 500
            if not response_started:
                body = json.dumps(
                    {
                        "code": "internal_error",
                        "message": "The request could not be completed.",
                        "field_errors": None,
                        "request_id": request_id,
                    }
                ).encode("utf-8")
                await response_send(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send({"type": "http.response.body", "body": body})
        finally:
            log_completion()
