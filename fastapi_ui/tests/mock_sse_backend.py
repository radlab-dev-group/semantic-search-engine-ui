"""
Tiny fake of the radlab-semantic-search-engine REST API used by the smoke test.

It implements the endpoints from configs/ui-configuration.json with the same
response shapes as the real backend: {"status": True, "body": {...}} and
{"status": False, "errors": [...]}.
"""

import email.policy
import json
import threading
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

VALID_CREDENTIALS = {"user": "pass"}

# Generative models answer with Markdown, so the fake backend does the same.
GENEATIVE_ANSWER = """## Podsumowanie

**To jest odpowiedź.** Wynika ona z dwóch dokumentów:

- `doc-a.pdf` — opis procesu
- `doc-b.pdf` — wyniki pomiarów

| Dokument | Score |
| --- | ---: |
| doc-a.pdf | 0.87 |

Więcej w [dokumentacji](https://example.com/docs).
"""

SEARCH_RESPONSE = {
    "query_response_id": 42,
    "results": {
        "stats": {
            "doc-a.pdf": {"score_weighted": 0.31, "pages": 12},
            "doc-b.pdf": {"score_weighted": 0.87, "pages": 3},
        },
        "detailed_results": {
            "1": {"score": 0.11, "text": "fragment A", "page": 2},
            "2": {
                "score": 0.94,
                "text": "fragment B\n\n## Sekcja\n\n**pogrubiony** <script>x</script>",
                "page": 7,
                "left_context": "kontekst **przed**",
                "right_context": [{"text_number": 9, "text_str": "kontekst po"}],
            },
        },
    },
}

# SearchQueryController.format_search_history_entry (newest first)
SEARCH_HISTORY = [
    {
        "query_id": 12,
        "query_response_id": 42,
        "query": "Jak wygląda proces ofertowy?",
        "query_str": "Jak wygląda proces ofertowy?",
        "collection_id": 1,
        "collection_name": "user_col",
        "query_options": {"max_results": 8},
        "results": {
            "query": "Jak wygląda proces ofertowy?",
            "stats": SEARCH_RESPONSE["results"]["stats"],
            "detailed_results": SEARCH_RESPONSE["results"]["detailed_results"],
            "structured_results": [],
        },
        "stats": SEARCH_RESPONSE["results"]["stats"],
        "detailed_results": SEARCH_RESPONSE["results"]["detailed_results"],
        "structured_results": [],
        "answers": [
            {
                "id": 98,
                "response_id": 98,
                "is_generative": True,
                "answer_options": {},
                "query_instruction_prompt": "odpowiedz krótko",
                "generated_answer": "**Zapisana odpowiedź** z historii.",
                "generated_answer_translated": None,
                "rate_value": 4,
                "rate_value_max": 5,
                "rate_comment": "Dobra odpowiedź",
                "generation_time": 3.25,
            }
        ],
        "generated_answer": "**Zapisana odpowiedź** z historii.",
    },
    {
        "query_id": 11,
        "query_response_id": 41,
        "query": "Wyniki pomiarów <b>2025</b>",
        "collection_id": 1,
        "collection_name": "user_col",
        "query_options": {},
        "results": {
            "stats": {"doc-b.pdf": {"score_weighted": 0.5}},
            "detailed_results": {"1": {"score": 0.5, "text": "pomiar"}},
        },
        "answers": [],
    },
    {
        "query_id": 10,
        "query_response_id": 40,
        "query": "Pytanie z innej kolekcji",
        "collection_id": 2,
        "collection_name": "user_kol",
        "results": {"stats": {}, "detailed_results": {}},
        "answers": [],
    },
]

# CollectionOfDocumentsSerializer: id, name, display_name, description,
# created_on, metadata_json (chunking declared on the collection; null = none)
COLLECTIONS = [
    {
        "id": 1,
        "name": "user_col",
        "display_name": "Moje dokumenty",
        "description": "Kolekcja użytkownika",
        "created_on": "2026-09-30T11:20:33.123456+02:00",
        "metadata_json": {
            "chunking": {"max_tokens_in_chunk": 512, "number_of_overlap_tokens": 32},
            "strict_chunking": False,
        },
    },
    {
        "id": 2,
        "name": "user_kol",
        "display_name": "",
        "description": "",
        "created_on": None,
        "metadata_json": None,
    },
    {
        "id": 3,
        "name": "user_strict",
        "display_name": "Sztywny podział",
        "description": "Kolekcja z wymuszonym podziałem",
        "created_on": "2026-10-01T08:00:00Z",
        "metadata_json": {
            "chunking": {"max_tokens_in_chunk": 256, "number_of_overlap_tokens": 0},
            "strict_chunking": True,
        },
    },
]

# GET filter_options: what the engine uses for an undeclared collection
CHUNKING_DEFAULTS = {"max_tokens_in_chunk": 500, "number_of_overlap_tokens": 0}

# GET embedders / rerankers: "models" (names) plus "models_info"
EMBEDDERS_INFO = [
    {"name": "embedder-a", "vector_size": 768, "max_model_length": 512, "device": "cuda"},
    {"name": "embedder-b", "vector_size": 1024, "max_model_length": None, "device": "cpu"},
]
RERANKERS_INFO = [{"name": "reranker-a", "max_model_length": 512, "device": "cuda"}]

# errors[] of the engine (HTTP 200, status False), messages per language
CHUNKING_ERRORS = {
    "CHUNKING_TOO_LONG": {
        "error_code": "000005_DATA",
        "pl": "Chunk jest dłuższy niż maksymalna długość wejścia embedera.",
        "en": "The chunk is longer than the maximum input length of the embedder.",
    },
    "CHUNKING_MISMATCH": {
        "error_code": "000006_DATA",
        "pl": "Parametry fragmentowania są niezgodne z ustawionymi dla kolekcji.",
        "en": "Chunking settings differ from the ones of the collection.",
    },
}


def _chunking_error(name, lang):
    error = CHUNKING_ERRORS[name]
    return {
        "status": False,
        "errors": [
            {
                "error_code": error["error_code"],
                "message": error.get(lang if lang in ("pl", "en") else "pl"),
            }
        ],
    }


def _collection(name):
    return next((c for c in COLLECTIONS if c["name"] == name), None)


def _refused_chunking(collection_name, indexing_options, lang):
    """Chunking checks of upload_and_index_files / add_and_index_texts."""
    options = indexing_options
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except ValueError:
            options = {}
    if not isinstance(options, dict):
        options = {}
    collection = _collection(collection_name) or {}
    metadata = collection.get("metadata_json") or {}
    declared = metadata.get("chunking") or CHUNKING_DEFAULTS
    requested = options.get("max_tokens_in_chunk")
    overlap = options.get("number_of_overlap_tokens")
    if requested is None and overlap is None:
        return None
    if requested is None:
        requested = declared["max_tokens_in_chunk"]
    if overlap is None:
        overlap = declared["number_of_overlap_tokens"]
    if metadata.get("strict_chunking") and (
        requested != declared["max_tokens_in_chunk"]
        or overlap != declared["number_of_overlap_tokens"]
    ):
        return _chunking_error("CHUNKING_MISMATCH", lang)
    if requested > EMBEDDERS_INFO[0]["max_model_length"]:
        return _chunking_error("CHUNKING_TOO_LONG", lang)
    return None


def _multipart_fields(raw: bytes, content_type: str) -> dict:
    """Text fields of a multipart/form-data body (file parts are skipped)."""
    message = BytesParser(policy=email.policy.HTTP).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        + raw
    )
    fields = {}
    for part in message.iter_parts():
        if part.get_filename():
            continue
        name = part.get_param("name", header="content-disposition")
        if name:
            fields[name] = part.get_payload(decode=True).decode("utf-8", "replace")
    return fields


# Documents of the collection with their use_in_search flag; GET documents
# lists only the enabled ones, unless with_disabled=true is asked for
DOCUMENTS_IN_SEARCH = {"b.pdf": True, "a.pdf": True, "old.pdf": False}

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
        if "application/json" in content_type:
            try:
                parsed_json = json.loads(raw.decode("utf-8"))
                if isinstance(parsed_json, dict):
                    return parsed_json
            except Exception:
                pass
        body = {"_raw": raw, "_content_type": content_type}
        if content_type.startswith("multipart/form-data"):
            try:
                body.update(_multipart_fields(raw, content_type))
            except Exception:
                pass
        return body

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
        query = REQUEST_LOG[-1]["query"]
        if ep == "search_history":
            name = query.get("collection_name")
            if name == "err_col":
                return self._send({"status": False, "errors": [{"msg": "boom"}]})
            return self._send(
                _ok(
                    {
                        "history": [
                            entry
                            for entry in SEARCH_HISTORY
                            if not name or entry["collection_name"] == name
                        ]
                    }
                )
            )
        if ep == "get_search_history":
            for entry in SEARCH_HISTORY:
                if str(entry["query_response_id"]) == query.get("query_response_id"):
                    return self._send(_ok(entry))
            return self._send(
                {
                    "status": False,
                    "errors": [
                        {"code": "RESPONSE_ACCESS_DENIED", "msg": "Access denied"}
                    ],
                }
            )
        if ep == "collections":
            return self._send(_ok({"collections": COLLECTIONS}))
        if ep == "generative_models":
            return self._send(
                _ok({"llama-8b": {"ctx": 4096}, "qwen-7b": {"ctx": 8192}})
            )
        if ep == "embedders":
            return self._send(
                _ok(
                    {
                        "models": ["embedder-a", "embedder-b"],
                        "models_info": EMBEDDERS_INFO,
                    }
                )
            )
        if ep == "rerankers":
            return self._send(
                _ok({"models": ["reranker-a"], "models_info": RERANKERS_INFO})
            )
        if ep == "filter_options":
            return self._send(
                _ok(
                    {
                        "templates": {},
                        "urls": [],
                        "categories": ["a", "b"],
                        "chunking_defaults": CHUNKING_DEFAULTS,
                    }
                )
            )
        if ep == "categories":
            return self._send(_ok({"categories": ["b", "a", None, "c"]}))
        if ep == "documents":
            if query.get("with_disabled") == "true":
                return self._send(
                    _ok(
                        {
                            "documents": [
                                {"id": index, "name": name, "use_in_search": used}
                                for index, (name, used) in enumerate(
                                    DOCUMENTS_IN_SEARCH.items(), start=1
                                )
                            ]
                        }
                    )
                )
            return self._send(
                _ok(
                    {
                        "documents": [
                            {"name": name}
                            for name, used in DOCUMENTS_IN_SEARCH.items()
                            if used
                        ]
                    }
                )
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
            # Optional "chunking" (JSON string in the form) and strict_chunking
            chunking = body.get("chunking")
            if isinstance(chunking, str):
                chunking = json.loads(chunking)
            if not isinstance(chunking, dict):
                chunking = dict(CHUNKING_DEFAULTS)
            if chunking["max_tokens_in_chunk"] > EMBEDDERS_INFO[0]["max_model_length"]:
                return self._send(
                    _chunking_error("CHUNKING_TOO_LONG", body.get("lang"))
                )
            strict = str(body.get("strict_chunking", "false")).lower() == "true"
            return self._send(
                _ok(
                    {
                        "collection_id": 7,
                        "chunking": chunking,
                        "strict_chunking": strict,
                    }
                )
            )
        if ep == "upload_and_index_files":
            refused = _refused_chunking(
                body.get("collection_name"),
                body.get("indexing_options"),
                body.get("lang"),
            )
            if refused is not None:
                return self._send(refused)
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
                        "answer": GENEATIVE_ANSWER,
                        "generation_time": 2.5,
                    }
                )
            )
        if ep == "rate_generative_answer":
            return self._send(_ok({"rated": True}))
        if ep == "delete_collection":
            return self._send(
                _ok(
                    {
                        "deleted": {"documents": 2, "pages": 10, "texts": 42},
                        "dropped_collection": True,
                    }
                )
            )
        if ep == "delete_documents":
            return self._send(
                _ok(
                    {
                        "deleted": {"documents": 1, "pages": 5, "texts": 20},
                        "deleted_vectors": 20,
                        "not_found": [],
                    }
                )
            )
        if ep == "delete_texts":
            return self._send(
                _ok(
                    {
                        "deleted": {"texts": 2},
                        "deleted_vectors": 2,
                        "not_found": [],
                    }
                )
            )
        if ep == "set_documents_use_in_search":
            names = body.get("documents[]") or []
            found = [name for name in names if name in DOCUMENTS_IN_SEARCH]
            if not found:
                return self._send(
                    {
                        "status": False,
                        "errors": [
                            {"code": "DOCUMENT_NOT_FOUND", "msg": "Document not found"}
                        ],
                    }
                )
            for name in found:
                DOCUMENTS_IN_SEARCH[name] = bool(body.get("use_in_search"))
            return self._send(
                _ok(
                    {
                        "updated_documents": len(found),
                        "use_in_search": bool(body.get("use_in_search")),
                        "not_found": [n for n in names if n not in found],
                    }
                )
            )
        if ep == "add_and_index_texts":
            refused = _refused_chunking(
                body.get("collection_name"),
                body.get("indexing_options"),
                body.get("lang"),
            )
            if refused is not None:
                return self._send(refused)
            return self._send(_ok({"indexed_documents": 1, "indexed_chunks": 3}))
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
