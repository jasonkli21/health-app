"""Numeric-loopback and disposable process helpers shared by the standalone probes."""

import json
import os
import socket
import sys
from hashlib import sha256
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from threading import Thread
from time import sleep

PAS_AUDIENCE = "https://pas-fixture.invalid"
HEALTH_AUDIENCE = "https://health-fixture.invalid"
SERVICE = "pas@health-fixture.invalid"
RESULT = "Synthetic Health dispatch completed."
TENANT = "paired-health-lane"
CONTENT = "Summarize my app records using my saved preference."
FIREBASE_ISSUER = "https://securetoken.google.com/health-fixture"
PREFERENCE = {
    "kind": "preference",
    "category": "preferences",
    "key": "r5_synthetic_presentation_format",
    "label": "Synthetic presentation format",
    "value": {"type": "text", "value": "bullets"},
}


def canonical(data):
    return json.dumps(
        data, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode()


def digest(raw):
    return sha256(raw).hexdigest()


def output(data):
    print(json.dumps(data, default=str), flush=True)


def request(port, method, path, raw=None, headers=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=8)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(8)
    try:
        sock.connect(("127.0.0.1", port))
        conn.auto_open = 0
        conn.sock = sock
        conn.request(method, path, body=raw, headers=headers or {})
        reply = conn.getresponse()
        body = reply.read(65537)
        assert len(body) <= 65536
        return reply.status, body, tuple(reply.getheaders())
    finally:
        conn.close()
        sock.close()


def network_fence(ports, attempts):
    def audit(event, args):
        denied = event in {
            "socket.getaddrinfo",
            "socket.getnameinfo",
            "socket.gethostbyname",
            "socket.gethostbyname_ex",
            "socket.gethostbyaddr",
            "socket.sendto",
            "socket.sendmsg",
        }
        if event == "socket.connect":
            addr = args[1]
            denied = not (
                isinstance(addr, tuple) and addr[0] == "127.0.0.1" and addr[1] in ports
            )
        if event == "socket.bind":
            denied = args[1] != ("127.0.0.1", 0)
        if denied:
            attempts.append(event)
            raise PermissionError("paired fixture numeric loopback only")

    sys.addaudithook(audit)


class QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def read(self):
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 65536:
            raise ValueError("invalid request length")
        return self.rfile.read(size)

    def respond(self, status, raw=b"", **headers):
        self.send_response(status)
        self.send_header("content-length", str(len(raw)))
        for name, value in headers.items():
            self.send_header(name.replace("_", "-"), value)
        self.end_headers()
        if raw:
            try:
                self.wfile.write(raw)
            except BrokenPipeError:
                pass


class NumericServer(ThreadingHTTPServer):
    def server_bind(self):
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address


def listener(handler):
    server = NumericServer(("127.0.0.1", 0), handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server


def receiver():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    config = json.loads(sys.stdin.readline())
    key = Ed25519PrivateKey.generate()
    network_fence(set(), [])

    class Receiver(QuietHandler):
        def do_POST(self):
            raw = self.read()
            data = json.loads(raw)
            contents = [message["content"] for message in data["messages"]]
            observed = {
                "path": self.path,
                "attempt": self.headers["x-pas-attempt"],
                "digest": digest(raw),
                "declared_digest": self.headers["x-pas-payload-sha256"],
                "has_health_preference": any(
                    "bullets" in item and "Synthetic presentation format" in item
                    for item in contents
                ),
                "has_pas_memory": any(
                    "I prefer reminders with one topic at a time." in item
                    for item in contents
                ),
                "model": data["model"],
            }
            with open(config["observed"], "a") as ledger:
                ledger.write(json.dumps(observed) + "\n")
                ledger.flush()
                os.fsync(ledger.fileno())
            outcome = config["outcome"]
            if outcome == "disconnect":
                self.close_connection = True
                return
            if outcome == "timeout":
                sleep(2.4)
            if outcome == "429":
                self.respond(429)
                return
            reply = canonical(
                {
                    "attempt": self.headers["x-pas-attempt"],
                    "payload_sha256": observed["digest"],
                    "result": RESULT,
                    "usage": 0,
                }
            )
            self.respond(200, reply, x_fixture_signature=key.sign(reply).hex())

    with NumericServer(("127.0.0.1", 0), Receiver) as server:
        output(
            {
                "port": server.server_port,
                "key": key.public_key().public_bytes_raw().hex(),
                "pid": os.getpid(),
            }
        )
        server.serve_forever()


if __name__ == "__main__":
    receiver()
