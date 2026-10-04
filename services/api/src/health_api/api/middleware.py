"""Request correlation and strict request-body size limits."""

from __future__ import annotations

import json
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBoundaryMiddleware:
    def __init__(self, app: ASGIApp, max_body_bytes: int = 65_536) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid4())
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
            if total > self.max_body_bytes:
                body = json.dumps(
                    {
                        "code": "request_too_large",
                        "message": "Request body exceeds the 65536 byte limit.",
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
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(name.lower() == b"x-request-id" for name, _ in headers):
                    headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, replay_receive, response_send)
