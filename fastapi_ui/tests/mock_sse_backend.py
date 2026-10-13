"""
Tiny fake of the radlab-semantic-search-engine REST API used by the smoke test.

It implements the endpoints from configs/ui-configuration.json with the same
response shapes as the real backend: {"status": True, "body": {...}} and
{"status": False, "errors": [...]}.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

VALID_CREDENTIALS = {"user": "pass"}

SEARCH_RESPONSE = {
    "query_response_id": 42,
    "results": {
        "stats": {
            "doc-a.pdf": {"score_weighted": 0.31, "pages": 12},
            "doc-b.pdf": {"score_weighted": 0.87, "pages": 3},
        },
        "detailed_results": {
            "1": {"score": 0.11, "text": "fragment A", "page": 2},
            "2": {"score": 0.94, "text": "fragment B", "page": 7},
        },
    },
}

CHAT_RESPONSE = {
    "history": [
        {"role": "user", "text": "Cześć", "text_translated": None},
        {
            "role": "assistant",
            "text": "Cześć! W czym pomóc?",
            "text_translated": None,
        },
    ],
    "last_state": [
        {
            "content_supervisor_state": {"status": "ok"},
            "rag_message_state": {
                "extracted_query": "jakieś pytanie",
                "sse_response": {
                    "general_stats_json": json.dumps(
                        {"doc-a.pdf": {"score_weighted": 0.5, "pages": 1}}
                    ),
                    "detailed_results_json": json.dumps(
                        {"1": {"score": 0.5, "text": "fragment", "page": 1}}
                    ),
                },
            },
        }
    ],
    "generation_time": 1.25,
}

REQUEST_LOG = []


def _ok(body):
    return {"status": True, "body": body}


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence the default logging
        pass

    def _send(self, payload, status=200):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("application/x-www-form-urlencoded"):
            return {
                k: v[-1]
                for k, v in parse_qs(
                    raw.decode("utf-8"), keep_blank_values=True
                ).items()
            }
        return {"_raw": raw, "_content_type": content_type}

    def _route(self):
        parsed = urlparse(self.path)
        body = self._read_body()
        REQUEST_LOG.append(
            {
                "method": self.command,
                "path": parsed.path,
                "query": {k: v[-1] for k, v in parse_qs(parsed.query).items()},
                "auth": self.headers.get("Authorization", ""),
                "body": {
                    k: (f"<{len(v)} bytes>" if k == "_raw" else v)
                    for k, v in body.items()
                },
                "raw_text": (
                    body.get("_raw", b"").decode("utf-8", errors="replace")
                    if isinstance(body.get("_raw", b""), bytes)
                    else ""
                ),
            }
        )
        return parsed.path.rstrip("/"), body

    def do_GET(self):  # noqa: N802
        path, _body = self._route()
        ep = path.split("/")[-1]
        if ep == "collections":
            return self._send(
                _ok({"collections": [{"name": "user_col"}, {"name": "user_kol"}]})
            )
        if ep == "generative_models":
            return self._send(
                _ok({"llama-8b": {"ctx": 4096}, "qwen-7b": {"ctx": 8192}})
            )
        if ep == "embedders":
            return self._send(_ok({"models": ["embedder-a", "embedder-b"]}))
        if ep == "rerankers":
            return self._send(_ok({"models": ["reranker-a"]}))
        if ep == "categories":
            return self._send(_ok({"categories": ["b", "a", None, "c"]}))
        if ep == "documents":
            return self._send(
                _ok({"documents": [{"name": "b.pdf"}, {"name": "a.pdf"}]})
            )
        return self._send(_ok({}))

    def do_POST(self):  # noqa: N802
        path, body = self._route()
        ep = path.split("/")[-1]
        if ep == "login":
            if VALID_CREDENTIALS.get(body.get("username")) == body.get("password"):
                return self._send({"token": "test-token-123"})
            return self._send({"detail": "Invalid credentials"}, status=401)
        if ep == "new_collection":
            return self._send(_ok({"collection_id": 7}))
        if ep == "upload_and_index_files":
            return self._send(_ok({"documents": 2, "indexed_chunks": 42}))
        if ep == "search_with_options":
            if body.get("collection_name") == "err_col":
                return self._send(
                    {
                        "status": False,
                        "errors": [
                            {
                                "code": "COLLECTION_NOT_FOUND",
                                "msg": "Collection not found!",
                                "required_params": ["collection_name"],
                            }
                        ],
                    }
                )
            return self._send(_ok(SEARCH_RESPONSE))
        if ep == "generative_answer":
            return self._send(
                _ok(
                    {
                        "response_id": 99,
                        "answer": "To jest odpowiedź.",
                        "generation_time": 2.5,
                    }
                )
            )
        if ep == "rate_generative_answer":
            return self._send(_ok({"rated": True}))
        if ep == "new_chat":
            return self._send(_ok({"chat": {"id": 5}}))
        if ep == "add_user_message":
            return self._send(_ok(CHAT_RESPONSE))
        return self._send(_ok({}))


def start_mock_backend(port: int = 0):
    server = HTTPServer(("127.0.0.1", port), MockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == "__main__":
    started = start_mock_backend(8271)
    print(
        f"Mock SSE backend listening on http://127.0.0.1:{started.server_address[1]}"
    )
    threading.Event().wait()
